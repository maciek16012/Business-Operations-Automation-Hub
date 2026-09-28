"""Attachment security history and durable operator work/outbox."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now():
    return datetime.now(UTC)


class AttachmentSecurityScan(Base):
    __tablename__ = "attachment_security_scans"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('PENDING','SAFE','QUARANTINED','BLOCKED','SCAN_FAILED')",
            name="ck_security_verdict",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_scan_size"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    scanner: Mapped[str] = mapped_column(String(64), default="ClamAV INSTREAM / BOAH policy v1")
    scanner_version: Mapped[str | None] = mapped_column(String(255))
    detected_mime: Mapped[str | None] = mapped_column(String(255))
    claimed_mime: Mapped[str | None] = mapped_column(String(255))
    extension: Mapped[str] = mapped_column(String(32))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    threat_name: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','RESOLVED','DISMISSED')", name="ck_task_status"
        ),
        CheckConstraint("priority IN ('CRITICAL','HIGH','NORMAL')", name="ck_task_priority"),
        CheckConstraint(
            "task_type IN ('SECURITY_QUARANTINE','OCR_REVIEW',"
            "'EXTRACTION_FAILURE','UNSUPPORTED_ATTACHMENT')",
            name="ck_task_type",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attachments.id"))
    active_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    priority: Mapped[str] = mapped_column(String(16), index=True)
    reason_code: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[str | None] = mapped_column(String(128))


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_tasks.id"), unique=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotificationReceipt(Base):
    __tablename__ = "notification_receipts"
    # No FK lock against the in-flight outbox transaction; API validates the identity.
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    task_id: Mapped[uuid.UUID]
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
