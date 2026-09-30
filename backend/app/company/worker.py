"""Ordered routing and durable bounded retries; no network delivery in API handlers."""

import asyncio
import json
import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.api.dependencies import get_service
from app.company.context import correlation
from app.company.destinations import credentials, deliver, safe_case, test_destination
from app.company.sources import poll_source, test_source
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.company import (
    CompanySettings,
    DeliveryJob,
    DocumentSource,
    OutputDestination,
    RoutingRule,
    RuleDestination,
    WorkerHeartbeat,
)
from app.models.documents import DocumentAnalysis
from app.models.entities import Case
from app.models.operations import NotificationOutbox, ReviewTask, now


async def enqueue_routes(service):
    rules = list(
        await service.db.scalars(
            select(RoutingRule)
            .where(RoutingRule.enabled.is_(True))
            .order_by(RoutingRule.priority, RoutingRule.id)
        )
    )
    for case in await service.db.scalars(
        select(Case).where(Case.status.in_(["APPROVED", "EXPORTED"]))
    ):
        try:
            await safe_case(service, case)
        except ValueError:
            continue
        documents = await service.rows(DocumentAnalysis, case.id)
        for rule in rules:
            if rule.case_state == "EXPORTED" and case.status != "EXPORTED":
                continue
            matches = [d for d in documents if rule.document_type in {"*", d.document_type}]
            if not matches or (rule.require_reviewed and not all(d.reviewed for d in matches)):
                continue
            destinations = await service.db.scalars(
                select(OutputDestination)
                .join(RuleDestination)
                .where(RuleDestination.rule_id == rule.id, OutputDestination.enabled.is_(True))
            )
            for destination in destinations:
                key = f"delivery:{case.id}:{destination.id}"
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert

                insert = (
                    pg_insert
                    if service.db.get_bind().dialect.name == "postgresql"
                    else sqlite_insert
                )
                job_id = uuid.uuid4()
                created = await service.db.scalar(
                    insert(DeliveryJob)
                    .values(
                        id=job_id,
                        case_id=case.id,
                        destination_id=destination.id,
                        idempotency_key=key,
                        kind="DELIVERY",
                        status="PENDING",
                        attempts=0,
                        next_retry=now(),
                        created_at=now(),
                        artifacts=[],
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                    .returning(DeliveryJob.id)
                )
                if created:
                    service.audit(
                        case,
                        "DELIVERY_ENQUEUED",
                        {
                            "job_id": str(job_id),
                            "rule_id": str(rule.id),
                            "destination_id": str(destination.id),
                        },
                    )
    await service.db.commit()


async def dead_letter(service, job):
    if not job.case_id:
        return
    existing = await service.db.scalar(
        select(ReviewTask).where(ReviewTask.active_key == f"integration:{job.id}")
    )
    if existing:
        return
    case = await service.get(job.case_id)
    task = ReviewTask(
        id=uuid.uuid4(),
        case_id=case.id,
        active_key=f"integration:{job.id}",
        task_type="INTEGRATION_FAILURE",
        reason_code="DELIVERY_DEAD_LETTER",
        priority="HIGH",
        title="Integration delivery failed",
        description="Delivery exhausted its bounded retries. Administrator intervention required.",
        payload={"job_id": str(job.id), "public_case_id": case.public_id, "attachment": None},
    )
    service.db.add(task)
    await service.db.flush()
    company = await service.db.get(CompanySettings, 1)
    event_id = uuid.uuid4()
    service.db.add(
        NotificationOutbox(
            id=event_id,
            task_id=task.id,
            case_id=case.id,
            payload={
                "event_id": str(event_id),
                "task_id": str(task.id),
                "case_id": str(case.id),
                "public_case_id": case.public_id,
                "task_type": "INTEGRATION_FAILURE",
                "priority": "HIGH",
                "reason": "DELIVERY_DEAD_LETTER",
                "link": settings.public_url + f"/?case={case.id}",
                "recipient": company.notifications.get("integration") if company else None,
            },
        )
    )
    service.audit(case, "DELIVERY_DEAD_LETTER", {"job_id": str(job.id)})


async def process_job(service):
    job = await service.db.scalar(
        select(DeliveryJob)
        .where(
            DeliveryJob.status.in_(["PENDING", "RETRY", "RUNNING"]), DeliveryJob.next_retry <= now()
        )
        .order_by(DeliveryJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not job:
        return False
    job_id = job.id
    correlation.set(str(job_id))
    if job.attempts >= settings.delivery_max_attempts:
        job.status = "DEAD_LETTER"
        await dead_letter(service, job)
        await service.db.commit()
        return True
    job.status = "RUNNING"
    job.attempts += 1
    job.next_retry = now() + timedelta(minutes=5)
    await service.db.commit()  # Lease makes retries recoverable after a worker crash.
    connector = None
    try:
        if job.destination_id:
            connector = await service.db.get(OutputDestination, job.destination_id)
            if not connector or (job.kind == "DELIVERY" and not connector.enabled):
                raise ValueError("Destination disabled")
            if job.kind == "TEST":
                await asyncio.to_thread(
                    test_destination, connector, await credentials(service, connector)
                )
            else:
                await deliver(service, job, connector)
        elif job.source_id:
            connector = await service.db.get(DocumentSource, job.source_id)
            if not connector:
                raise ValueError("Source missing")
            await asyncio.to_thread(test_source, connector, await credentials(service, connector))
        else:
            raise ValueError("Job has no connector")
        connector.status = "HEALTHY"
        connector.last_success = now()
        connector.last_error = None
        job.status = "SUCCEEDED"
        job.completed_at = now()
        job.last_error = None
        if job.case_id:
            service.audit(
                await service.get(job.case_id),
                "DELIVERY_SUCCEEDED",
                {"job_id": str(job.id), "attempt": job.attempts},
            )
        await service.db.commit()
    except Exception as exc:
        # Exception text can contain credentials or remote content. Persist only its class.
        error = type(exc).__name__
        await service.db.rollback()
        job = await service.db.get(DeliveryJob, job_id)
        job.last_error = error
        job.status = "DEAD_LETTER" if job.attempts >= settings.delivery_max_attempts else "RETRY"
        job.next_retry = now() + timedelta(
            seconds=settings.delivery_retry_seconds * 2 ** min(job.attempts - 1, 8)
        )
        model = OutputDestination if job.destination_id else DocumentSource
        connector = await service.db.get(model, job.destination_id or job.source_id)
        if connector:
            connector.status = "UNAVAILABLE"
            connector.last_error = error
        if job.status == "DEAD_LETTER":
            await dead_letter(service, job)
        await service.db.commit()
    logging.getLogger("boah.delivery").info(
        json.dumps(
            {
                "event": "delivery_attempt",
                "request_id": str(job_id),
                "case_id": str(job.case_id) if job.case_id else None,
                "status": job.status,
                "attempt": job.attempts,
            }
        )
    )
    return True


async def tick():
    correlation.set(uuid.uuid4().hex)
    async with SessionLocal() as db:
        heartbeat = await db.get(WorkerHeartbeat, "delivery")
        if heartbeat:
            heartbeat.updated_at = now()
        else:
            db.add(WorkerHeartbeat(name="delivery"))
        await db.commit()
        service = get_service(db)
        source = await db.scalar(
            select(DocumentSource)
            .where(
                DocumentSource.enabled.is_(True),
                DocumentSource.kind.in_(["IMAP", "WATCHED_FOLDER"]),
                (DocumentSource.next_poll_at.is_(None)) | (DocumentSource.next_poll_at <= now()),
            )
            .order_by(DocumentSource.next_poll_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if source:
            source_id = source.id
            try:
                await poll_source(service, source)
                source.next_poll_at = now() + timedelta(seconds=source.interval_seconds)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                source = await db.get(DocumentSource, source_id)
                assert source is not None
                source.status = "UNAVAILABLE"
                source.last_error = type(exc).__name__
                source.next_poll_at = now() + timedelta(seconds=source.interval_seconds)
                await db.commit()
        await enqueue_routes(service)
        for _ in range(10):
            if not await process_job(service):
                break


async def main():
    from app.company.secrets import validate_startup

    validate_startup()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    while True:
        try:
            await tick()
        except Exception as exc:
            logging.getLogger("boah").error("worker_tick_failed type=%s", type(exc).__name__)
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
