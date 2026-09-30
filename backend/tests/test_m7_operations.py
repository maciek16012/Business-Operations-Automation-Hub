"""M7 worker recovery, routing, intake and retention contracts."""

import hashlib
import importlib.util
import io
import json
import tarfile
import time
import uuid
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.dependencies import get_service
from app.company.retention import execute, plan
from app.company.sources import payload_from_email, poll_source
from app.company.worker import enqueue_routes, process_job
from app.core.config import settings
from app.main import app
from app.models.company import (
    CompanySettings,
    DeliveryJob,
    DocumentSource,
    OutputDestination,
    RetentionDeletion,
    RoutingRule,
    RuleDestination,
    SourceItem,
)
from app.models.documents import DocumentAnalysis
from app.models.entities import Attachment
from app.models.operations import AttachmentSecurityScan, NotificationOutbox, ReviewTask, now


async def approved(service, verdict="SAFE"):
    case = await service.create({"source": "api"})
    case.status = "APPROVED"
    data = b"Synthetic retained evidence"
    attachment = Attachment(
        id=uuid.uuid4(),
        case_id=case.id,
        original_filename="synthetic.txt",
        mime_type="text/plain",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=service.storage.put(data),
    )
    service.db.add(attachment)
    await service.db.flush()
    service.db.add(
        AttachmentSecurityScan(
            case_id=case.id,
            attachment_id=attachment.id,
            verdict=verdict,
            sha256=attachment.sha256,
            extension="txt",
            size_bytes=len(data),
        )
    )
    service.db.add(
        DocumentAnalysis(
            case_id=case.id,
            attachment_id=attachment.id,
            document_type="INVOICE",
            confidence=1,
            classifier="synthetic-test",
            reasons=[],
            pages=[],
            raw_text="synthetic",
            artifacts={},
            strategy="test",
            review_required=False,
            reviewed=True,
        )
    )
    await service.db.commit()
    return case, attachment


async def test_routing_dedup_security_and_review(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mounted_roots", {"archive": str(tmp_path)})
    async for service in app.dependency_overrides[get_service]():
        good, _ = await approved(service)
        bad, _ = await approved(service, "QUARANTINED")
        destination = OutputDestination(
            id=uuid.uuid4(),
            name="archive",
            kind="FILESYSTEM",
            enabled=True,
            config={
                "root": "archive",
                "path_template": "{case_id}",
                "filename": "{case_id}.{extension}",
                "artifacts": ["json", "xlsx"],
            },
        )
        service.db.add(destination)
        await service.db.flush()
        for priority in [1, 2]:
            rule = RoutingRule(
                id=uuid.uuid4(),
                name="invoice",
                priority=priority,
                document_type="INVOICE",
                require_reviewed=True,
            )
            service.db.add(rule)
            await service.db.flush()
            service.db.add(RuleDestination(rule_id=rule.id, destination_id=destination.id))
        await service.db.commit()
        await enqueue_routes(service)
        await enqueue_routes(service)
        jobs = list(await service.db.scalars(select(DeliveryJob)))
        assert len(jobs) == 1 and jobs[0].case_id == good.id and jobs[0].case_id != bad.id
        assert await process_job(service)
        assert jobs[0].status == "SUCCEEDED"
        assert len(list(tmp_path.rglob("*.json"))) == 1 and len(list(tmp_path.rglob("*.xlsx"))) == 1
        before = [service.storage.get(item["storage_key"]) for item in jobs[0].artifacts]
        jobs[0].status = "RETRY"
        jobs[0].next_retry = now()
        await service.db.commit()
        assert await process_job(service)
        assert jobs[0].status == "SUCCEEDED"
        assert before == [service.storage.get(item["storage_key"]) for item in jobs[0].artifacts]


async def test_bounded_retry_deadletter_outbox_and_no_error_secret(client, monkeypatch):
    import app.company.worker as worker

    monkeypatch.setattr(settings, "delivery_max_attempts", 2)

    async def fail(*args):
        raise ValueError("DO-NOT-LOG-REMOTE-SECRET")

    monkeypatch.setattr(worker, "deliver", fail)
    async for service in app.dependency_overrides[get_service]():
        case, _ = await approved(service)
        destination = OutputDestination(
            id=uuid.uuid4(), name="failing", kind="WEBHOOK", enabled=True, config={}
        )
        service.db.add(destination)
        await service.db.flush()
        job = DeliveryJob(
            case_id=case.id,
            destination_id=destination.id,
            kind="DELIVERY",
            idempotency_key="unit-retry",
        )
        service.db.add(job)
        await service.db.commit()
        identity = job.id
        await process_job(service)
        job = await service.db.get(DeliveryJob, identity)
        assert job.status == "RETRY" and job.last_error == "ValueError"
        job.next_retry = now()
        await service.db.commit()
        await process_job(service)
        job = await service.db.get(DeliveryJob, identity)
        assert job.status == "DEAD_LETTER" and job.attempts == 2
        task = await service.db.scalar(
            select(ReviewTask).where(ReviewTask.task_type == "INTEGRATION_FAILURE")
        )
        assert task and await service.db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.task_id == task.id)
        )
        assert not await process_job(service)


async def test_watched_stability_temporary_and_content_dedup(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mounted_roots", {"incoming": str(tmp_path)})
    (tmp_path / "pending.part").write_bytes(b"not ready")
    (tmp_path / "first.txt").write_bytes(b"Customer: Synthetic")
    async for service in app.dependency_overrides[get_service]():
        source = DocumentSource(
            id=uuid.uuid4(),
            name="watch",
            kind="WATCHED_FOLDER",
            enabled=True,
            config={"root": "incoming", "path": "", "stable_seconds": 2},
        )
        service.db.add(source)
        await service.db.commit()
        await poll_source(service, source)
        await service.db.commit()
        assert not list(await service.db.scalars(select(SourceItem)))
        source.runtime_state = {
            k: {**v, "since": time.time() - 5} for k, v in source.runtime_state.items()
        }
        await poll_source(service, source)
        await service.db.commit()
        assert len(list(await service.db.scalars(select(SourceItem)))) == 1
        (tmp_path / "second.txt").write_bytes((tmp_path / "first.txt").read_bytes())
        await poll_source(service, source)
        await service.db.commit()
        source.runtime_state = {
            k: {**v, "since": time.time() - 5} for k, v in source.runtime_state.items()
        }
        await poll_source(service, source)
        await service.db.commit()
        assert len(list(await service.db.scalars(select(SourceItem)))) == 1


def test_imap_message_metadata_attachment():
    msg = EmailMessage()
    msg["From"] = "Synthetic <sender@example.com>"
    msg["To"] = "inbox@example.com"
    msg["Message-ID"] = "<synthetic-m7@example.com>"
    msg["Subject"] = "Synthetic invoice"
    msg.set_content("Request body")
    msg.add_attachment(b"file bytes", maintype="application", subtype="pdf", filename="invoice.pdf")
    payload = payload_from_email(msg.as_bytes())
    assert (
        payload.external_message_id == "<synthetic-m7@example.com>"
        and payload.sender.address == "sender@example.com"
    )
    assert payload.attachments[0].decode() == b"file bytes"


async def test_retention_excludes_active_and_quarantine_preserves_audit(client):
    async for service in app.dependency_overrides[get_service]():
        company = CompanySettings(
            id=1,
            company_name="Synthetic",
            retention={"safe_days": 1, "export_days": 1, "quarantine_days": None},
        )
        service.db.add(company)
        safe, a = await approved(service)
        blocked, _ = await approved(service, "QUARANTINED")
        safe.status = blocked.status = "EXPORTED"
        safe.updated_at = blocked.updated_at = now() - timedelta(days=5)
        await service.db.commit()
        result = await plan(service)
        assert [i["storage_key"] for i in result["items"]] == [a.storage_key]
        await execute(service, result["plan_id"], "unit-admin")
        assert await service.db.get(RetentionDeletion, a.storage_key)
        with pytest.raises(FileNotFoundError):
            service.storage.get(a.storage_key)
        assert (await plan(service))["items"] == []


spec = importlib.util.spec_from_file_location(
    "backup", Path(__file__).resolve().parents[2] / "scripts/backup/boah_backup.py"
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_backup_manifest_hash_and_no_key(tmp_path):
    path = tmp_path / "backup.tar.gz"
    backup.pack(
        {"database.dump": b"synthetic-db", "storage/doc": b"synthetic"}, path, "2836cf000b0e"
    )
    manifest, entries = backup.verify(path)
    assert manifest["master_key_included"] is False and entries["storage/doc"] == b"synthetic"
    assert (
        settings.boah_master_key not in json.dumps(manifest) if settings.boah_master_key else True
    )


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "storage/../../escape", "storage\\escape"]
)
def test_backup_rejects_traversal(tmp_path, name):
    path = tmp_path / "evil.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo(name)
        item.size = 1
        archive.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        backup.verify(path)


def test_restore_requires_explicit_confirmation(tmp_path):
    with pytest.raises(ValueError, match="explicit"):
        backup.restore([], tmp_path / "absent", False)
