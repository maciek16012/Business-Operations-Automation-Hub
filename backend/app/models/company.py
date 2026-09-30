"""Single-company administration, authentication and integration records."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.operations import now


class CompanySettings(Base):
    __tablename__ = "company_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(255))
    identifier: Mapped[str | None] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Warsaw")
    locale: Mapped[str] = mapped_column(String(20), default="pl-PL")
    currency: Mapped[str] = mapped_column(String(3), default="PLN")
    notification_email: Mapped[str | None] = mapped_column(String(320))
    notifications: Mapped[dict] = mapped_column(JSON, default=dict)
    retention: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"safe_days": 365, "export_days": 365, "quarantine_days": None}
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    enabled: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(default=0)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Secret(Base):
    __tablename__ = "secrets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SystemAudit(Base):
    __tablename__ = "system_audit"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    target: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentSource(Base):
    __tablename__ = "document_sources"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("secrets.id"))
    runtime_state: Mapped[dict] = mapped_column(JSON, default=dict)
    interval_seconds: Mapped[int] = mapped_column(default=60)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    last_message: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="UNCHECKED")


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("source_id", "identity", name="uq_source_item"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_sources.id"))
    identity: Mapped[str] = mapped_column(String(128))
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutputDestination(Base):
    __tablename__ = "output_destinations"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("secrets.id"))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="UNCHECKED")


class RoutingRule(Base):
    __tablename__ = "routing_rules"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    document_type: Mapped[str] = mapped_column(String(32), default="*")
    case_state: Mapped[str] = mapped_column(String(20), default="APPROVED")
    require_reviewed: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=100)


class RuleDestination(Base):
    __tablename__ = "rule_destinations"
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routing_rules.id", ondelete="CASCADE"), primary_key=True
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("output_destinations.id"), primary_key=True
    )


class DeliveryJob(Base):
    __tablename__ = "delivery_jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)
    destination_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("output_destinations.id"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_sources.id"))
    kind: Mapped[str] = mapped_column(String(20), default="DELIVERY")
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    artifacts: Mapped[list] = mapped_column(JSON, default=list)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(200))
    next_retry: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RetentionDeletion(Base):
    __tablename__ = "retention_deletions"
    storage_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"))
    artifact_kind: Mapped[str] = mapped_column(String(30))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
