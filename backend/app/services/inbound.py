import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.domain.enums import EmailAuditEvent
from app.models.entities import Attachment, InboundMessage, ValidationIssue
from app.schemas.inbound import InboundEmail
from app.services.cases import CaseService
from app.services.errors import WorkflowError


def message_identity(payload: InboundEmail, contents: list[bytes]) -> tuple[str, str]:
    raw = (payload.external_message_id or "").strip()
    match = re.fullmatch(r"<?([^<>\s@]+)@([^<>\s@]+)>?", raw, re.ASCII)
    if match and raw.count("<") == raw.count(">"):
        stable = f"{match[1]}@{match[2].lower()}"
        return hashlib.sha256(("rfc:" + stable).encode()).hexdigest(), "rfc_message_id"
    fingerprint = {
        "version": 1,
        "sender": payload.sender.address.lower(),
        "recipients": sorted(a.address.lower() for a in payload.recipients),
        "cc": sorted(a.address.lower() for a in payload.cc),
        "subject": payload.subject.strip(),
        "sent_at": payload.sent_at.isoformat() if payload.sent_at else None,
        "text": payload.text_body.replace("\r\n", "\n"),
        "html": (payload.html_body or "").replace("\r\n", "\n"),
        "attachments": sorted(hashlib.sha256(content).hexdigest() for content in contents),
    }
    encoded = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest(), "fingerprint_v1"


class EmailIngestionService:
    def __init__(self, cases: CaseService):
        self.cases = cases
        self.db = cases.db

    async def ingest(self, payload: InboundEmail) -> dict:
        try:
            contents = [attachment.decode() for attachment in payload.attachments]
        except ValueError as exc:
            raise WorkflowError("EMAIL_ATTACHMENT_INVALID", str(exc), 422) from exc
        identity_key, method = message_identity(payload, contents)
        message_id = uuid.uuid4()
        insert = pg_insert if self.db.get_bind().dialect.name == "postgresql" else sqlite_insert
        # Unique insert is the concurrency boundary. A competing delivery waits for commit/rollback.
        statement = (
            insert(InboundMessage)
            .values(
                id=message_id,
                source_type=payload.source_type,
                identity_key=identity_key,
                identity_method=method,
                external_message_id=payload.external_message_id,
                sender_address=payload.sender.address,
                sender_name=payload.sender.name,
                recipients=[a.model_dump() for a in payload.recipients],
                cc=[a.model_dump() for a in payload.cc],
                reply_to=[a.model_dump() for a in payload.reply_to],
                subject=payload.subject,
                received_at=payload.received_at,
                sent_at=payload.sent_at,
                text_body=payload.text_body,
                html_body=payload.html_body,
                processing_status="processing",
                attachment_results=[],
            )
            .on_conflict_do_nothing(index_elements=["source_type", "identity_key"])
            .returning(InboundMessage.id)
        )
        claimed = await self.db.scalar(statement)
        if claimed is None:
            message = await self.db.scalar(
                select(InboundMessage).where(
                    InboundMessage.source_type == payload.source_type,
                    InboundMessage.identity_key == identity_key,
                )
            )
            assert message is not None and message.case_id is not None
            case = await self.cases.get(message.case_id, lock=True)
            self.cases.audit(
                case,
                EmailAuditEvent.DUPLICATE_IGNORED,
                {"message_id": str(message.id), "identity_method": message.identity_method},
            )
            await self.db.flush()
            return self.result(message, case, "duplicate")
        message = await self.db.get(InboundMessage, message_id)
        assert message is not None
        case = await self.cases.create(
            {
                "source": "email",
                "customer_email": payload.sender.address,
                "customer_name": payload.sender.name,
                # Preserve the full subject on InboundMessage; bound only the business title.
                "request_title": payload.subject.strip()[:255] or None,
            }
        )
        message.case_id = case.id
        self.cases.audit(
            case,
            EmailAuditEvent.RECEIVED,
            {"message_id": str(message.id), "identity_method": method},
        )
        self.cases.audit(case, EmailAuditEvent.CASE_CREATED, {"message_id": str(message.id)})
        files = [
            (a.filename.replace("\\", "/").split("/")[-1] or "attachment", a.mime_type, content)
            for a, content in zip(payload.attachments, contents, strict=True)
        ]
        if files:
            await self.cases.upload(case, files, email_review=True)
        else:
            await self.cases.revalidate(case)
        stored = {a.sha256: a for a in await self.cases.rows(Attachment, case.id)}
        issues = await self.cases.rows(ValidationIssue, case.id)
        seen: set[str] = set()
        results = []
        for attachment, content in zip(payload.attachments, contents, strict=True):
            digest = hashlib.sha256(content).hexdigest()
            row = stored.get(digest)
            outcome = "not_stored"
            if row:
                outcome = "duplicate" if digest in seen else "stored"
                if digest not in seen:
                    self.cases.audit(
                        case,
                        EmailAuditEvent.ATTACHMENT_STORED,
                        {
                            "message_id": str(message.id),
                            "attachment_id": str(row.id),
                            "sha256": digest,
                        },
                    )
                    if any(
                        i.field_name == f"attachment:{row.id}" and not i.resolved for i in issues
                    ):
                        outcome = "review_required"
            seen.add(digest)
            results.append(
                {
                    "original_filename": attachment.filename,
                    "mime_type": attachment.mime_type,
                    "sha256": digest,
                    "attachment_id": str(row.id) if row else None,
                    "result": outcome,
                }
            )
        message.attachment_results = results
        message.processing_status = "failed" if case.status == "FAILED" else "processed"
        message.updated_at = datetime.now(UTC)
        if case.status == "FAILED":
            self.cases.audit(
                case,
                EmailAuditEvent.INGESTION_FAILED,
                {"message_id": str(message.id), "code": "PROCESSING_FAILED"},
            )
        await self.db.flush()
        return self.result(message, case, "created")

    @staticmethod
    def result(message, case, result: str) -> dict:
        return {
            "result": result,
            "case_id": case.id,
            "public_case_id": case.public_id,
            "message_id": message.id,
            "status": case.status,
            "processing_status": message.processing_status,
            "identity_method": message.identity_method,
            "attachment_results": message.attachment_results,
        }

    async def review_attachment(self, message_id: uuid.UUID, attachment_id: uuid.UUID, reason: str):
        if not reason.strip():
            raise WorkflowError("REASON_REQUIRED", "Explain how the attachment was reviewed", 422)
        message = await self.db.get(InboundMessage, message_id)
        if message is None or message.case_id is None:
            raise WorkflowError("NOT_FOUND", "Inbound message not found", 404)
        case = await self.cases.get(message.case_id, lock=True)
        self.cases.check_editable(case)
        attachment = await self.db.get(Attachment, attachment_id)
        if attachment is None or attachment.case_id != case.id:
            raise WorkflowError("NOT_FOUND", "Attachment not found in this message", 404)
        issues = await self.cases.rows(ValidationIssue, case.id)
        reviewed = [
            i
            for i in issues
            if i.field_name == f"attachment:{attachment_id}"
            and not i.resolved
            and i.code in {"EMAIL_ATTACHMENT_UNSUPPORTED", "EMAIL_EXTRACTION_FAILED"}
        ]
        if not reviewed:
            raise WorkflowError("NO_ATTACHMENT_REVIEW", "No pending attachment review")
        for issue in reviewed:
            issue.resolved = True
            self.cases.audit(
                case,
                "validation_issue_resolved",
                {"issue_id": str(issue.id), "code": issue.code},
                "operator",
            )
        self.cases.audit(
            case,
            EmailAuditEvent.ATTACHMENT_REVIEWED,
            {"attachment_id": str(attachment_id), "reason": reason},
            "operator",
        )
        await self.cases.revalidate(case)
        return await self.cases.detail(case)
