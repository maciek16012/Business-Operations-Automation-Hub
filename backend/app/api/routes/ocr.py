from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import ConfigDict, Field
from sqlalchemy import select

from app.api.dependencies import Service
from app.models.entities import OCRDocument, ReviewDecision, ValidationIssue
from app.ocr.pipeline import FIELDS, business_checks, normalize_field
from app.schemas.cases import SafeTextModel
from app.services.errors import WorkflowError

router = APIRouter()


class OCRReview(SafeTextModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)
    values: dict[
        Literal[
            "document_number",
            "tax_id",
            "issue_date",
            "net_total",
            "vat_total",
            "gross_total",
            "currency",
        ],
        str,
    ] = Field(min_length=7, max_length=7)


@router.post("/{case_id}/{document_id}/review")
async def review_ocr(case_id: UUID, document_id: UUID, data: OCRReview, service: Service):
    case = await service.get(case_id, lock=True)
    service.check_editable(case)
    doc = await service.db.scalar(
        select(OCRDocument)
        .where(OCRDocument.id == document_id, OCRDocument.case_id == case_id)
        .with_for_update()
    )
    if doc is None:
        raise WorkflowError("NOT_FOUND", "OCR document not found", 404)
    if not data.reason.strip():
        raise WorkflowError("REASON_REQUIRED", "Review requires reason", 422)
    if any(len(v) > 255 or any(ord(c) < 32 for c in v) for v in data.values.values()):
        raise WorkflowError("VALUE_INVALID", "Invalid review value", 422)
    incoming: dict[str, str] = {str(k): v for k, v in data.values.items()}
    values = {f: normalize_field(f, incoming.get(f)) for f in FIELDS}
    checks = business_checks(values)
    if not all(checks.values()):
        raise WorkflowError(
            "OCR_VALIDATION", "Correct NIP, dates, currency and arithmetic before review", 422
        )
    before = doc.reviewed_values
    doc.reviewed_values = values
    doc.review_reason = data.reason
    doc.reviewed = True
    for issue in await service.rows(ValidationIssue, case.id):
        if (
            issue.code == "OCR_REVIEW_REQUIRED"
            and issue.field_name == f"attachment:{doc.attachment_id}"
        ):
            issue.resolved = True
    service.apply(
        case,
        {
            "tax_id": values["tax_id"],
            "estimated_value": values["gross_total"],
            "currency": values["currency"],
        },
    )
    service.audit(
        case,
        "OCR_HUMAN_REVIEW",
        {
            "document_id": str(doc.id),
            "before": before,
            "selected": values,
            "reason": data.reason,
            "business_validation": checks,
        },
        "operator",
    )
    service.db.add(
        ReviewDecision(
            case_id=case.id,
            action="correct",
            comment=data.reason,
            changes={"ocr_document_id": str(doc.id), "selected": values},
            actor="operator",
        )
    )
    await service.revalidate(case)
    await service.db.commit()
    return await service.detail(case)
