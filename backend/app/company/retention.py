"""Retention preserves DB metadata/audit; physical deletion requires an explicit plan hash."""

import hashlib
import json
from datetime import timedelta

from sqlalchemy import select

from app.company.auth import audit, aware
from app.models.company import CompanySettings, DeliveryJob, RetentionDeletion
from app.models.entities import Attachment, Case, Export
from app.models.operations import AttachmentSecurityScan, ReviewTask, now


async def plan(service):
    company = await service.db.get(CompanySettings, 1)
    if not company:
        return {"items": [], "plan_id": hashlib.sha256(b"[]").hexdigest()}
    items = []
    cases = await service.db.scalars(select(Case).where(Case.status.in_(["EXPORTED", "FAILED"])))
    for case in cases:
        active = await service.db.scalar(
            select(ReviewTask.id)
            .where(ReviewTask.case_id == case.id, ReviewTask.status.in_(["OPEN", "ACKNOWLEDGED"]))
            .limit(1)
        )
        pending = await service.db.scalar(
            select(DeliveryJob.id)
            .where(DeliveryJob.case_id == case.id, DeliveryJob.status != "SUCCEEDED")
            .limit(1)
        )
        if active or pending:
            continue
        for attachment in await service.rows(Attachment, case.id):
            scan = await service.db.scalar(
                select(AttachmentSecurityScan)
                .where(AttachmentSecurityScan.attachment_id == attachment.id)
                .order_by(AttachmentSecurityScan.created_at.desc())
                .limit(1)
            )
            if not scan:
                continue
            category = "safe" if scan.verdict == "SAFE" else "quarantine"
            days = company.retention.get(category + "_days")
            if days and aware(case.updated_at) < now() - timedelta(days=days):
                items.append(
                    {
                        "case_id": str(case.id),
                        "storage_key": attachment.storage_key,
                        "kind": category,
                    }
                )
        for export in await service.rows(Export, case.id):
            if export.storage_key and aware(case.updated_at) < now() - timedelta(
                days=company.retention.get("export_days", 365)
            ):
                items.append(
                    {"case_id": str(case.id), "storage_key": export.storage_key, "kind": "export"}
                )
    retained = []
    for item in items:
        deletion = await service.db.get(RetentionDeletion, item["storage_key"])
        if deletion is None or deletion.deleted_at is None:
            retained.append(item)
    retained.sort(key=lambda i: i["storage_key"])
    return {
        "items": retained,
        "plan_id": hashlib.sha256(json.dumps(retained, sort_keys=True).encode()).hexdigest(),
    }


async def execute(service, plan_id, actor):
    from app.services.errors import WorkflowError

    result = await plan(service)
    if result["plan_id"] != plan_id:
        raise WorkflowError("STALE_PLAN", "Retention plan changed; run dry-run again", 409)
    import uuid

    for item in result["items"]:
        case = await service.get(uuid.UUID(item["case_id"]), lock=True)
        # Recheck under case lock; review/state operations use the same lock.
        current = await plan(service)
        if item not in current["items"]:
            continue
        deletion = await service.db.get(RetentionDeletion, item["storage_key"])
        if deletion is None:
            deletion = RetentionDeletion(
                storage_key=item["storage_key"], case_id=case.id, artifact_kind=item["kind"]
            )
            service.db.add(deletion)
        audit(
            service.db,
            "RETENTION_DELETION_AUTHORIZED",
            actor,
            item["storage_key"],
            case_id=str(case.id),
            artifact_kind=item["kind"],
        )
        await (
            service.db.commit()
        )  # Preserve intent even if the process dies during physical removal.
        service.storage.delete(item["storage_key"])
        deletion.deleted_at = now()
        await service.db.commit()
    return {"deleted": len(result["items"]), "audit_preserved": True}
