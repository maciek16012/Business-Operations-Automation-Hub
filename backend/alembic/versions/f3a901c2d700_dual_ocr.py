"""Preserve independent OCR evidence and human resolution."""

import sqlalchemy as sa

from alembic import op

revision = "f3a901c2d700"
down_revision = "e5ebcbe7c468"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ocr_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "attachment_id",
            sa.Uuid(),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("reviewed_values", sa.JSON(), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ocr_documents_case_id", "ocr_documents", ["case_id"])


def downgrade():
    op.drop_table("ocr_documents")
