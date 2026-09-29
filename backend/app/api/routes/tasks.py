from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import func, select

from app.api.dependencies import Service
from app.models.entities import ValidationIssue
from app.models.operations import (
    AttachmentSecurityScan,
    NotificationOutbox,
    NotificationReceipt,
    ReviewTask,
)
from app.schemas.cases import SafeTextModel
from app.services.errors import WorkflowError
from app.services.operations import close_task
from app.services.serialization import row_json

router = APIRouter()


class TaskDecision(SafeTextModel):
    action: Literal["acknowledge", "resolve", "dismiss", "reject_case"]
    reason: str = Field(min_length=1, max_length=2000)
    assigned_to: str | None = Field(default=None, max_length=128)


@router.get("")
async def tasks(
    service: Service,
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"] | None = None,
    task_type: Literal[
        "SECURITY_QUARANTINE",
        "OCR_REVIEW",
        "EXTRACTION_FAILURE",
        "UNSUPPORTED_ATTACHMENT",
        "DOCUMENT_REVIEW",
    ]
    | None = None,
    priority: Literal["CRITICAL", "HIGH", "NORMAL"] | None = None,
    case_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    query = select(ReviewTask)
    query = (
        query.where(ReviewTask.status == status)
        if status
        else query.where(ReviewTask.status.in_(["OPEN", "ACKNOWLEDGED"]))
    )
    for column, value in [
        (ReviewTask.task_type, task_type),
        (ReviewTask.priority, priority),
        (ReviewTask.case_id, case_id),
    ]:
        if value is not None:
            query = query.where(column == value)
    total = await service.db.scalar(select(func.count()).select_from(query.subquery()))
    opened = await service.db.scalar(
        select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "OPEN")
    )
    rows = await service.db.scalars(
        query.order_by(ReviewTask.priority, ReviewTask.created_at, ReviewTask.id)
        .offset(offset)
        .limit(limit)
    )
    return {"items": [row_json(t) for t in rows], "total": total, "open_count": opened}


@router.get("/{task_id}")
async def task_detail(task_id: UUID, service: Service):
    task = await service.db.get(ReviewTask, task_id)
    if task is None:
        raise WorkflowError("NOT_FOUND", "Review task not found", 404)
    scans = await service.db.scalars(
        select(AttachmentSecurityScan)
        .where(AttachmentSecurityScan.attachment_id == task.attachment_id)
        .order_by(AttachmentSecurityScan.created_at)
    )
    return {**row_json(task), "security_scans": [row_json(s) for s in scans]}


@router.post("/{task_id}/decision")
async def decision(task_id: UUID, data: TaskDecision, service: Service):
    task = await service.db.get(ReviewTask, task_id)
    if task is None:
        raise WorkflowError("NOT_FOUND", "Review task not found", 404)
    case = await service.get(task.case_id, lock=True)
    await service.db.refresh(task)
    if not data.reason.strip():
        raise WorkflowError("REASON_REQUIRED", "Explain this decision", 422)
    if task.status not in {"OPEN", "ACKNOWLEDGED"}:
        raise WorkflowError("INVALID_TRANSITION", "Task is already closed")
    if data.action == "acknowledge":
        if task.status != "OPEN":
            raise WorkflowError("INVALID_TRANSITION", "Task is already acknowledged")
        task.status = "ACKNOWLEDGED"
        task.acknowledged_at = task.updated_at = datetime.now(UTC)
        task.assigned_to = data.assigned_to
        service.audit(
            case,
            "REVIEW_TASK_ACKNOWLEDGED",
            {"task_id": str(task.id), "reason": data.reason},
            "operator",
        )
    elif data.action == "reject_case":
        await service.reject(case, data.reason)
        for pending in await service.rows(ReviewTask, case.id):
            if pending.active_key:
                await close_task(service, case, pending, "Case rejected: " + data.reason)
        # Security issues and original verdicts deliberately remain unresolved evidence.
    else:
        if task.task_type in {"SECURITY_QUARANTINE", "OCR_REVIEW", "DOCUMENT_REVIEW"}:
            raise WorkflowError(
                "RESOLUTION_FORBIDDEN",
                "Security requires case rejection; OCR requires field review",
            )
        service.check_editable(case)
        issue = await service.db.get(ValidationIssue, UUID(task.payload["issue_id"]))
        if issue:
            issue.resolved = True
        await close_task(
            service,
            case,
            task,
            data.reason,
            "DISMISSED" if data.action == "dismiss" else "RESOLVED",
        )
        await service.revalidate(case)
    await service.db.commit()
    return await task_detail(task_id, service)


class Receipt(SafeTextModel):
    event_id: UUID
    task_id: UUID


@router.post("/notifications/receipt")
async def receipt(data: Receipt, service: Service):
    # Local sink accepts only existing opaque outbox identities, not arbitrary messages.
    event = await service.db.get(NotificationOutbox, data.event_id)
    if event is None or event.task_id != data.task_id:
        raise WorkflowError("NOT_FOUND", "Notification not found", 404)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if service.db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = (
        insert(NotificationReceipt)
        .values(event_id=event.id, task_id=event.task_id, received_at=datetime.now(UTC))
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    result = await service.db.execute(statement.returning(NotificationReceipt.event_id))
    duplicate = result.scalar_one_or_none() is None
    await service.db.commit()
    return {"event_id": str(event.id), "delivered": True, "duplicate": duplicate}
