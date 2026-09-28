"""Transactional tasks and notifications; no manual security release."""

import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from app.core.config import settings
from app.models.entities import Attachment, Case, ValidationIssue
from app.models.operations import AttachmentSecurityScan, NotificationOutbox, ReviewTask
from app.security.preflight import preflight

if TYPE_CHECKING:
    from app.services.cases import CaseService

TASK_TYPES = {
    "OCR_REVIEW_REQUIRED": "OCR_REVIEW",
    "EMAIL_EXTRACTION_FAILED": "EXTRACTION_FAILURE",
    "EMAIL_ATTACHMENT_UNSUPPORTED": "UNSUPPORTED_ATTACHMENT",
    "SECURITY_UNSAFE": "SECURITY_QUARANTINE",
}


async def gate(service: "CaseService", case: Case, attachment: Attachment, data: bytes) -> bool:
    if not settings.security_preflight_enabled:
        service.audit(case, "SECURITY_COMPATIBILITY_MODE", {"attachment_id": str(attachment.id)})
        return True
    scan = AttachmentSecurityScan(
        attachment_id=attachment.id,
        case_id=case.id,
        claimed_mime=attachment.mime_type,
        extension=PurePosixPath(attachment.original_filename).suffix.lower()[:32],
        sha256=attachment.sha256,
        size_bytes=len(data),
    )
    service.db.add(scan)
    await service.db.flush()
    service.audit(case, "ATTACHMENT_SECURITY_SCAN_STARTED", {"scan_id": str(scan.id)})
    result = await preflight(attachment.original_filename, attachment.mime_type or "", data)
    for key in ("verdict", "reason", "detected_mime", "scanner_version", "threat_name", "checks"):
        setattr(scan, key, getattr(result, key))
    scan.completed_at = datetime.now(UTC)
    events = {
        "SAFE": "ATTACHMENT_SECURITY_SAFE",
        "BLOCKED": "ATTACHMENT_BLOCKED",
        "QUARANTINED": "ATTACHMENT_QUARANTINED",
        "SCAN_FAILED": "ATTACHMENT_SECURITY_SCAN_FAILED",
    }
    service.audit(
        case,
        events[scan.verdict],
        {"scan_id": str(scan.id), "attachment_id": str(attachment.id), "reason": scan.reason},
    )
    if scan.verdict != "SAFE":
        service.db.add(
            ValidationIssue(
                case_id=case.id,
                code="SECURITY_UNSAFE",
                severity="CRITICAL",
                field_name=f"attachment:{attachment.id}",
                message=f"{scan.verdict}: {scan.reason}; processing prohibited",
            )
        )
        await service.db.flush()
        await reconcile(service, case)
        return False
    return True


async def close_task(
    service: "CaseService", case: Case, task: ReviewTask, reason: str, status: str = "RESOLVED"
) -> None:
    task.status, task.active_key = status, None
    task.resolved_at = task.updated_at = datetime.now(UTC)
    task.payload = {**task.payload, "resolution": reason}
    service.audit(
        case,
        "REVIEW_TASK_RESOLVED",
        {"task_id": str(task.id), "status": status, "reason": reason},
        "operator",
    )


async def reconcile(service: "CaseService", case: Case) -> None:
    issues = await service.rows(ValidationIssue, case.id)
    tasks = await service.rows(ReviewTask, case.id)
    active_issues = {str(i.id) for i in issues if not i.resolved}
    for task in tasks:
        if task.active_key and task.payload["issue_id"] not in active_issues:
            await close_task(service, case, task, "Resolved through validated document review")
    for issue in issues:
        if issue.resolved or issue.code not in TASK_TYPES:
            continue
        key = f"{case.id}:{issue.field_name}:{issue.code}"
        if any(t.active_key == key for t in tasks):
            continue
        attachment_id = uuid.UUID(issue.field_name.split(":")[1]) if issue.field_name else None
        attachment = await service.db.get(Attachment, attachment_id) if attachment_id else None
        task = ReviewTask(
            case_id=case.id,
            attachment_id=attachment_id,
            active_key=key,
            task_type=TASK_TYPES[issue.code],
            reason_code=issue.code,
            priority="CRITICAL" if issue.code == "SECURITY_UNSAFE" else "HIGH",
            title=TASK_TYPES[issue.code].replace("_", " "),
            description=issue.message,
            payload={
                "issue_id": str(issue.id),
                "public_case_id": case.public_id,
                "attachment": attachment.original_filename if attachment else None,
            },
        )
        service.db.add(task)
        await service.db.flush()
        tasks.append(task)
        service.audit(
            case, "REVIEW_TASK_CREATED", {"task_id": str(task.id), "type": task.task_type}
        )
        if settings.review_notifications_enabled:
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
                        "task_type": task.task_type,
                        "priority": task.priority,
                        "reason": task.reason_code,
                        "link": f"http://localhost:3000/?case={case.id}",
                    },
                )
            )
            service.audit(case, "REVIEW_NOTIFICATION_QUEUED", {"event_id": str(event_id)})
    await service.db.flush()
