import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.operations import now


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_class_conf"),
        CheckConstraint(
            "document_type IN ('INVOICE','HANDWRITTEN_TABLE',"
            "'PRINTED_TABLE','GENERIC_DOCUMENT','UNKNOWN')",
            name="ck_document_type",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    attachment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("attachments.id"), unique=True)
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float]
    classifier: Mapped[str] = mapped_column(String(64))
    reasons: Mapped[list] = mapped_column(JSON)
    pages: Mapped[list] = mapped_column(JSON)
    raw_text: Mapped[str] = mapped_column(Text)
    artifacts: Mapped[dict] = mapped_column(JSON)
    strategy: Mapped[str] = mapped_column(String(64))
    review_required: Mapped[bool]
    reviewed: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentTable(Base):
    __tablename__ = "document_tables"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_analyses.id"), index=True)
    page: Mapped[int]
    row_count: Mapped[int]
    column_count: Mapped[int]
    bbox: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(64))
    irregular: Mapped[bool]


class DocumentCell(Base):
    __tablename__ = "document_cells"
    __table_args__ = (
        UniqueConstraint("table_id", "row", "column", name="uq_table_cell"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_cell_conf"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_tables.id"), index=True)
    row: Mapped[int]
    column: Mapped[int]
    raw_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float]
    bbox: Mapped[list | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(64))
    uncertain: Mapped[bool]


class DocumentCorrection(Base):
    __tablename__ = "document_corrections"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_analyses.id"), index=True)
    revision: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    changes: Mapped[list] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(64), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
