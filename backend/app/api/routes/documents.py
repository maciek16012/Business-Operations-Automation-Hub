from uuid import UUID

import pymupdf
from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select

from app.adaptive.layout import open_document
from app.adaptive.service import assert_safe, document_json
from app.adaptive.validation import validate_table
from app.api.dependencies import Service
from app.models.documents import DocumentAnalysis, DocumentCell, DocumentCorrection, DocumentTable
from app.models.entities import Attachment, Case, ValidationIssue
from app.models.operations import AttachmentSecurityScan, ReviewTask
from app.schemas.cases import SafeTextModel
from app.services.errors import WorkflowError

router = APIRouter()


class CellCorrection(SafeTextModel):
    cell_id: UUID
    value: str = Field(max_length=1000)


class DocumentReview(SafeTextModel):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)
    cells: list[CellCorrection] = Field(default_factory=list, max_length=1000)


@router.get("/summary")
async def summary(service: Service):
    async def counts(model, column):
        return {
            key: value
            for key, value in (
                await service.db.execute(
                    select(column, func.count()).select_from(model).group_by(column)
                )
            ).all()
        }

    return {
        "cases": await counts(Case, Case.status),
        "document_types": await counts(DocumentAnalysis, DocumentAnalysis.document_type),
        "security": await counts(AttachmentSecurityScan, AttachmentSecurityScan.verdict),
        "review_tasks": await counts(ReviewTask, ReviewTask.status),
    }


@router.get("/{document_id}")
async def detail(document_id: UUID, service: Service):
    document = await service.db.get(DocumentAnalysis, document_id)
    if document is None:
        raise WorkflowError("NOT_FOUND", "Document not found", 404)
    return await document_json(service, document)


@router.get("/{document_id}/preview")
async def preview(document_id: UUID, service: Service, page: int = Query(1, ge=1, le=10)):
    document = await service.db.get(DocumentAnalysis, document_id)
    if document is None:
        raise WorkflowError("NOT_FOUND", "Document not found", 404)
    scan = await assert_safe(service, document.attachment_id)
    attachment = await service.db.get(Attachment, document.attachment_id)
    assert attachment is not None
    content = service.storage.get(attachment.storage_key)
    if scan.detected_mime == "text/plain":
        return Response(
            content, media_type="text/plain", headers={"X-Content-Type-Options": "nosniff"}
        )
    try:
        with open_document(content) as doc:
            if page > len(doc):
                raise ValueError("Page outside document")
            image = doc[page - 1]
            if image.rect.width * image.rect.height > 4_000_000:
                raise ValueError("Page geometry limit")
            png = image.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).tobytes("png")
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
    except (ValueError, RuntimeError) as exc:
        raise WorkflowError("PREVIEW_UNAVAILABLE", "Cannot render this page safely", 422) from exc


@router.post("/{document_id}/review")
async def review(document_id: UUID, data: DocumentReview, service: Service):
    document = await service.db.get(DocumentAnalysis, document_id)
    if document is None:
        raise WorkflowError("NOT_FOUND", "Document not found", 404)
    case = await service.get(document.case_id, lock=True)
    service.check_editable(case)
    await service.db.refresh(document)
    await assert_safe(service, document.attachment_id)
    if document.revision != data.revision:
        raise WorkflowError("STALE_REVISION", "Document changed; reload before reviewing")
    if not data.reason.strip():
        raise WorkflowError("REASON_REQUIRED", "Document review requires a reason", 422)
    edits = {edit.cell_id: edit.value for edit in data.cells}
    if len(edits) != len(data.cells):
        raise WorkflowError("DUPLICATE_CELL", "Duplicate cell correction", 422)
    cells = list(
        await service.db.scalars(
            select(DocumentCell).join(DocumentTable).where(DocumentTable.document_id == document.id)
        )
    )
    if not set(edits) <= {c.id for c in cells}:
        raise WorkflowError("INVALID_CELL", "Cell does not belong to this document", 422)
    changes = []
    for cell in cells:
        if cell.id in edits:
            changes.append(
                {
                    "cell_id": str(cell.id),
                    "before": cell.corrected_value,
                    "raw": cell.raw_value,
                    "after": edits[cell.id],
                }
            )
            cell.corrected_value = edits[cell.id]
        if cell.uncertain and cell.corrected_value is None:
            raise WorkflowError(
                "UNRESOLVED_CELL", "Confirm every uncertain cell, including blanks", 422
            )
    for table in await service.db.scalars(
        select(DocumentTable).where(DocumentTable.document_id == document.id)
    ):
        values: list[list[str | None]] = [
            [None for _ in range(table.column_count)] for _ in range(table.row_count)
        ]
        for cell in cells:
            if cell.table_id == table.id:
                values[cell.row][cell.column] = (
                    cell.corrected_value if cell.corrected_value is not None else cell.raw_value
                )
        issues = validate_table(values)
        if issues:
            raise WorkflowError("TABLE_VALIDATION", issues[0]["message"], 422)
    document.reviewed = True
    document.revision += 1
    service.db.add(
        DocumentCorrection(
            document_id=document.id, revision=document.revision, reason=data.reason, changes=changes
        )
    )
    for issue in await service.rows(ValidationIssue, case.id):
        if (
            issue.code == "ADAPTIVE_REVIEW_REQUIRED"
            and issue.field_name == f"attachment:{document.attachment_id}"
        ):
            issue.resolved = True
    service.audit(
        case,
        "DOCUMENT_REVIEW_CORRECTED",
        {
            "document_id": str(document.id),
            "revision": document.revision,
            "reason": data.reason,
            "changes": changes,
        },
        "operator",
    )
    await service.revalidate(case)
    await service.db.commit()
    return await service.detail(case)
