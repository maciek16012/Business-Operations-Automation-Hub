import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.enums import IssueSeverity
from app.domain.state_machine import ensure_transition
from app.extraction.base import ExtractionProvider
from app.models.entities import (
    Attachment,
    AuditEvent,
    Case,
    Export,
    ExtractedField,
    InboundMessage,
    OCRDocument,
    ReviewDecision,
    ValidationIssue,
)
from app.models.operations import AttachmentSecurityScan, ReviewTask
from app.services.errors import WorkflowError
from app.services.operations import close_task, gate, reconcile
from app.services.serialization import row_json, value_json
from app.storage.base import ObjectStorage
from app.validation.engine import ValidationEngine
from app.validation.normalization import FIELDS, normalize

EDITABLE = {"RECEIVED", "READY", "REVIEW_REQUIRED"}


class CaseService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage, provider: ExtractionProvider):
        self.db, self.storage, self.provider = db, storage, provider

    def audit(
        self, case: Case, event: str, details: dict | None = None, actor: str = "system"
    ) -> None:
        self.db.add(
            AuditEvent(case_id=case.id, event_type=event, details=details, actor_type=actor)
        )
        case.updated_at = datetime.now(UTC)

    def transition(self, case: Case, target: str) -> None:
        if case.status == target:
            return
        try:
            ensure_transition(case.status, target)
        except ValueError as exc:
            raise WorkflowError("INVALID_TRANSITION", str(exc)) from exc
        previous = case.status
        case.status = target
        self.audit(case, "status_changed", {"from": previous, "to": target})

    async def get(self, case_id: uuid.UUID, lock: bool = False) -> Case:
        statement = select(Case).where(Case.id == case_id)
        if lock:
            statement = statement.with_for_update()
        case = await self.db.scalar(statement)
        if case is None:
            raise WorkflowError("NOT_FOUND", "Case not found", 404)
        return case

    def check_editable(self, case: Case) -> None:
        if case.status not in EDITABLE:
            raise WorkflowError("CASE_IMMUTABLE", "This case can no longer be modified")

    async def rows(self, model, case_id):
        return list(
            (
                await self.db.scalars(
                    select(model)
                    .where(model.case_id == case_id)
                    .order_by(model.created_at, model.id)
                )
            ).all()
        )

    async def detail(self, case: Case) -> dict:
        result = row_json(case)
        for name, model in (
            ("attachments", Attachment),
            ("extracted_fields", ExtractedField),
            ("validation_issues", ValidationIssue),
            ("review_decisions", ReviewDecision),
            ("exports", Export),
            ("audit_events", AuditEvent),
            ("ocr_documents", OCRDocument),
            ("security_scans", AttachmentSecurityScan),
            ("review_tasks", ReviewTask),
        ):
            result[name] = [row_json(row) for row in await self.rows(model, case.id)]
        inbound = await self.db.scalar(
            select(InboundMessage).where(InboundMessage.case_id == case.id)
        )
        result["inbound_message"] = row_json(inbound) if inbound else None
        return result

    def apply(self, case: Case, values: dict, *, extracted: bool = False) -> dict:
        normalized = {}
        errors = dict(case.normalization_errors or {})
        implied_currency = None
        for field, raw in values.items():
            if field not in FIELDS:
                continue
            try:
                value, currency = normalize(field, raw)
                normalized[field] = value_json(value)
                if not extracted or getattr(case, field) is None:
                    setattr(case, field, value)
                    errors.pop(field, None)
                elif value != getattr(case, field):
                    errors[field] = (
                        "Conflicting document value; confirm the business value manually"
                    )
                if currency:
                    implied_currency = currency
            except (ValueError, TypeError) as exc:
                errors[field] = str(exc)
                normalized[field] = None
                if not extracted:
                    setattr(case, field, None)
        if implied_currency:
            if case.currency and case.currency != implied_currency:
                errors["currency"] = "Amount currency conflicts with the currency field"
            elif not case.currency:
                case.currency = implied_currency
        case.normalization_errors = errors
        return normalized

    async def create(self, data: dict) -> Case:
        case_id = uuid.uuid4()
        case = Case(
            id=case_id,
            public_id=f"CASE-{datetime.now(UTC).year}-{case_id.hex[:20]}",
            source=data.pop("source", "manual_upload"),
            status="RECEIVED",
            normalization_errors={},
        )
        self.db.add(case)
        self.apply(case, data)
        await self.db.flush()
        self.audit(case, "case_created", {"source": case.source})
        await self.db.flush()
        return case

    async def validate(self, case: Case) -> None:
        old = await self.rows(ValidationIssue, case.id)
        duplicate = any(i.code == "DUPLICATE_ATTACHMENT" for i in old)
        payload = {field: getattr(case, field) for field in FIELDS}
        payload["duplicate"] = duplicate
        rules = ValidationEngine().validate(payload)
        from app.validation.engine import RuleIssue

        rules.extend(
            RuleIssue("NORMALIZATION_INVALID", IssueSeverity.ERROR, message, field)
            for field, message in case.normalization_errors.items()
        )
        rules.extend(
            RuleIssue(i.code, IssueSeverity(i.severity), i.message, i.field_name)
            for i in old
            if not i.resolved
            and i.code
            in {
                "EMAIL_ATTACHMENT_UNSUPPORTED",
                "EMAIL_EXTRACTION_FAILED",
                "OCR_REVIEW_REQUIRED",
                "SECURITY_UNSAFE",
            }
        )
        keys = {(r.code, r.field_name, r.message) for r in rules}
        active = {(i.code, i.field_name, i.message) for i in old if not i.resolved}
        for issue in old:
            if not issue.resolved and (issue.code, issue.field_name, issue.message) not in keys:
                issue.resolved = True
                self.audit(
                    case,
                    "validation_issue_resolved",
                    {"issue_id": str(issue.id), "code": issue.code},
                )
        for rule in rules:
            if (rule.code, rule.field_name, rule.message) not in active:
                self.db.add(
                    ValidationIssue(
                        case_id=case.id,
                        code=rule.code,
                        severity=rule.severity,
                        field_name=rule.field_name,
                        message=rule.message,
                    )
                )
        blocking = any(r.severity in {IssueSeverity.ERROR, IssueSeverity.CRITICAL} for r in rules)
        self.audit(case, "validation_performed", {"issues": len(rules), "blocking": blocking})
        self.transition(case, "REVIEW_REQUIRED" if blocking else "READY")
        await self.db.flush()
        await reconcile(self, case)

    async def revalidate(self, case: Case) -> None:
        self.check_editable(case)
        if case.status == "RECEIVED":
            self.transition(case, "PROCESSING")
        await self.validate(case)

    async def correct(self, case: Case, values: dict) -> None:
        self.check_editable(case)
        before = {field: value_json(getattr(case, field)) for field in FIELDS}
        self.apply(case, values)
        changes = {
            field: {"old": before[field], "new": value_json(getattr(case, field)), "input": raw}
            for field, raw in values.items()
        }
        for field in FIELDS:
            after = value_json(getattr(case, field))
            if field not in changes and before[field] != after:
                changes[field] = {
                    "old": before[field],
                    "new": after,
                    "derived_from": "normalization",
                }
        for field, change in changes.items():
            self.audit(case, "field_manually_corrected", {"field": field, **change}, "operator")
        self.db.add(
            ReviewDecision(case_id=case.id, action="correct", changes=changes, actor="operator")
        )
        await self.revalidate(case)

    async def upload(
        self, case: Case, files: list[tuple[str, str, bytes]], *, email_review: bool = False
    ) -> None:
        self.check_editable(case)
        self.transition(case, "PROCESSING")
        for filename, mime, content in files:
            digest = hashlib.sha256(content).hexdigest()
            existing = await self.db.scalar(
                select(Attachment).where(Attachment.case_id == case.id, Attachment.sha256 == digest)
            )
            if existing:
                self.audit(
                    case,
                    "duplicate_detected",
                    {
                        "filename": filename,
                        "sha256": digest,
                        "original_attachment_id": str(existing.id),
                    },
                )
                self.db.add(
                    ValidationIssue(
                        case_id=case.id,
                        code="DUPLICATE_ATTACHMENT",
                        severity="WARNING",
                        message="Exact duplicate ignored; original attachment retained",
                    )
                )
                await self.db.flush()
                continue
            try:
                key = self.storage.put(content)
                attachment = Attachment(
                    case_id=case.id,
                    original_filename=filename,
                    mime_type=mime,
                    size_bytes=len(content),
                    sha256=digest,
                    storage_key=key,
                )
                self.db.add(attachment)
                await self.db.flush()
                self.audit(
                    case,
                    "attachment_uploaded",
                    {"attachment_id": str(attachment.id), "sha256": digest},
                )
                if not await gate(self, case, attachment, content):
                    continue
                from app.document_routing.processor import process_document
                from app.ocr import pipeline

                if pipeline.supported(filename, mime):
                    report = await process_document(
                        document_id=str(attachment.id),
                        filename=filename,
                        mime_type=mime,
                        content=content,
                    )
                    document = OCRDocument(
                        case_id=case.id, attachment_id=attachment.id, report=report
                    )
                    self.db.add(document)
                    self.audit(
                        case,
                        "OCR_COMPLETED",
                        {
                            "attachment_id": str(attachment.id),
                            "outcome": report["outcome"],
                            "fields": report["fields"],
                            "provider_errors": [p["error"] for p in report["providers"]],
                        },
                    )
                    self.apply(
                        case,
                        {
                            "tax_id": report["selected"].get("tax_id"),
                            "estimated_value": report["selected"].get("gross_total"),
                            "currency": report["selected"].get("currency"),
                        },
                        extracted=True,
                    )
                    if report["review_required"]:
                        self.db.add(
                            ValidationIssue(
                                case_id=case.id,
                                code="OCR_REVIEW_REQUIRED",
                                severity="ERROR",
                                field_name=f"attachment:{attachment.id}",
                                message="Independent OCR needs human verification: "
                                + report["outcome"],
                            )
                        )
                    await self.db.flush()
                    continue
                if (email_review or settings.security_preflight_enabled) and not (
                    filename.lower().endswith(".txt")
                    and mime.lower().split(";", 1)[0].strip()
                    in {"text/plain", "application/octet-stream"}
                ):
                    self.db.add(
                        ValidationIssue(
                            case_id=case.id,
                            code="EMAIL_ATTACHMENT_UNSUPPORTED",
                            severity="ERROR",
                            field_name=f"attachment:{attachment.id}",
                            message="Original stored; unsupported type requires operator review",
                        )
                    )
                    self.audit(
                        case, "EMAIL_ATTACHMENT_UNSUPPORTED", {"attachment_id": str(attachment.id)}
                    )
                    await self.db.flush()
                    continue
                try:
                    fields = await self.provider.extract(self.storage.get(key))
                except ValueError:
                    if not email_review and not settings.security_preflight_enabled:
                        raise
                    self.db.add(
                        ValidationIssue(
                            case_id=case.id,
                            code="EMAIL_EXTRACTION_FAILED",
                            severity="ERROR",
                            field_name=f"attachment:{attachment.id}",
                            message="Original stored; extraction failed; operator review required",
                        )
                    )
                    self.audit(
                        case,
                        "EMAIL_INGESTION_FAILED",
                        {"attachment_id": str(attachment.id), "code": "EXTRACTION_FAILED"},
                    )
                    await self.db.flush()
                    continue
                normalized = self.apply(
                    case, {f.field_name: f.raw_value for f in fields}, extracted=True
                )
                for field in fields:
                    self.db.add(
                        ExtractedField(
                            case_id=case.id,
                            attachment_id=attachment.id,
                            field_name=field.field_name,
                            raw_value=field.raw_value,
                            normalized_value=normalized.get(field.field_name),
                            confidence=field.confidence,
                            extraction_method=self.provider.name,
                        )
                    )
                self.audit(
                    case,
                    "extraction_performed",
                    {
                        "attachment_id": str(attachment.id),
                        "provider": self.provider.name,
                        "fields": len(fields),
                    },
                )
            except (ValueError, OSError) as exc:
                self.audit(case, "processing_failure", {"reason": str(exc), "filename": filename})
                self.transition(case, "FAILED")
                await self.db.flush()
                return
        await self.validate(case)

    async def approve(self, case: Case) -> None:
        self.check_editable(case)
        await self.revalidate(case)
        issues = await self.rows(ValidationIssue, case.id)
        if any(not i.resolved and i.severity in {"ERROR", "CRITICAL"} for i in issues):
            await self.db.commit()
            raise WorkflowError("APPROVAL_BLOCKED", "Unresolved blocking validation issues remain")
        self.transition(case, "APPROVED")
        self.db.add(ReviewDecision(case_id=case.id, action="approve", actor="operator"))
        self.audit(case, "case_approved", actor="operator")

    async def reject(self, case: Case, reason: str) -> None:
        self.check_editable(case)
        if not reason.strip():
            raise WorkflowError("REASON_REQUIRED", "Rejection requires a reason", 422)
        self.transition(case, "FAILED")
        self.db.add(
            ReviewDecision(case_id=case.id, action="reject", comment=reason, actor="operator")
        )
        self.audit(case, "case_rejected", {"reason": reason}, "operator")
        for task in await self.rows(ReviewTask, case.id):
            if task.active_key:
                await close_task(self, case, task, "Case rejected: " + reason)
