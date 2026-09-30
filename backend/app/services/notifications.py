"""Durable at-least-once delivery with idempotent local sink and bounded backoff."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import AuditEvent
from app.models.operations import NotificationOutbox


async def deliver_one(db: AsyncSession, client: httpx.AsyncClient) -> bool:
    event = await db.scalar(
        select(NotificationOutbox)
        .where(
            NotificationOutbox.sent_at.is_(None),
            NotificationOutbox.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(NotificationOutbox.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return False
    event.attempts += 1
    try:
        response = await client.post(
            settings.review_notification_webhook_url,
            json=event.payload,
            headers={"Idempotency-Key": str(event.id)},
            timeout=settings.review_notification_timeout_seconds,
        )
        response.raise_for_status()
        receipt = response.json()
        if receipt.get("event_id") != str(event.id) or receipt.get("delivered") is not True:
            raise ValueError("Missing matching sink receipt")
        event.sent_at = datetime.now(UTC)
        event.last_error = None
        event_type = "REVIEW_NOTIFICATION_SENT"
    except (httpx.HTTPError, ValueError, AttributeError):
        # Do not persist URLs or response bodies, which might contain credentials.
        event.last_error = "Delivery failed or missing sink acknowledgement"
        event.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=min(3600, 2 ** min(event.attempts, 11))
        )
        event_type = "REVIEW_NOTIFICATION_FAILED"
    db.add(
        AuditEvent(
            case_id=event.case_id,
            event_type=event_type,
            details={"event_id": str(event.id), "attempt": event.attempts},
        )
    )
    await db.commit()
    return True


async def run():
    from app.db.session import SessionLocal

    async with httpx.AsyncClient(follow_redirects=False) as client:
        while True:
            try:
                if settings.review_notifications_enabled:
                    async with SessionLocal() as db:
                        from app.models.company import WorkerHeartbeat

                        heartbeat = await db.get(WorkerHeartbeat, "review")
                        if heartbeat:
                            heartbeat.updated_at = datetime.now(UTC)
                        else:
                            db.add(WorkerHeartbeat(name="review"))
                        await db.commit()
                        if await deliver_one(db, client):
                            continue
            except Exception as exc:
                logging.error("Notification worker failed: %s", type(exc).__name__)
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run())
