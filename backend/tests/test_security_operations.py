import asyncio
import base64
import struct
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID

import httpx
import pymupdf
import pytest
from PIL import Image
from sqlalchemy import select

from app.api.dependencies import get_service
from app.core.config import settings
from app.extraction.development import DevelopmentExtractionProvider
from app.main import app
from app.models.entities import AuditEvent
from app.models.operations import NotificationOutbox, NotificationReceipt
from app.security.preflight import ClamAV, preflight
from app.services.notifications import deliver_one


def fixture_bytes(kind):
    if kind == "pdf":
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Synthetic security test document. No private data.")
        data = doc.tobytes(no_new_id=True)
        doc.close()
        return data
    if kind in {"png", "jpeg"}:
        stream = BytesIO()
        Image.new("RGB", (16, 16), "white").save(stream, format=kind.upper())
        return stream.getvalue()
    if kind == "eicar":
        return b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    raise ValueError(kind)


@pytest.fixture
def secure(monkeypatch):
    monkeypatch.setattr(settings, "security_preflight_enabled", True)

    async def clean(self, data):
        return "ClamAV test-double", None

    monkeypatch.setattr(ClamAV, "scan", clean)


@pytest.mark.parametrize(
    "kind,mime", [("pdf", "application/pdf"), ("png", "image/png"), ("jpeg", "image/jpeg")]
)
async def test_valid_magic_clean(secure, kind, mime):
    result = await preflight(f"valid.{kind}", mime, fixture_bytes(kind))
    assert result.verdict == "SAFE"
    assert result.checks["antivirus"] == "clean"


@pytest.mark.parametrize(
    "name,mime,data,reason,verdict",
    [
        ("scan.pdf", "image/png", b"%PDF-1.7", "TYPE_MISMATCH", "QUARANTINED"),
        ("scan.png", "application/pdf", b"%PDF-1.7", "TYPE_MISMATCH", "QUARANTINED"),
        ("scan.exe.pdf", "application/pdf", b"%PDF-1.7", "EXECUTABLE_CONTENT", "BLOCKED"),
        (
            "scan.pdf",
            "application/pdf",
            b"MZ synthetic harmless bytes",
            "EXECUTABLE_CONTENT",
            "BLOCKED",
        ),
        ("scan.bin", "application/octet-stream", b"\0\1\2", "UNSUPPORTED_TYPE", "QUARANTINED"),
        ("scan.zip", "application/zip", b"PK\3\4 safe metadata", "UNSUPPORTED_TYPE", "QUARANTINED"),
        (
            "scan.pdf",
            "application/pdf",
            b"%PDF-1.7 /Java#53cript",
            "ACTIVE_OR_ENCRYPTED_PDF",
            "QUARANTINED",
        ),
        (
            "scan.pdf",
            "application/pdf",
            b"%PDF-1.7 /Encrypt",
            "ACTIVE_OR_ENCRYPTED_PDF",
            "QUARANTINED",
        ),
    ],
)
async def test_policy_matrix(secure, name, mime, data, reason, verdict):
    result = await preflight(name, mime, data)
    assert (result.reason, result.verdict) == (reason, verdict)


async def test_size_limit_without_large_payload(secure, monkeypatch):
    monkeypatch.setattr(settings, "security_max_attachment_bytes", 8)
    assert (await preflight("x.txt", "text/plain", b"123456789")).reason == "SIZE_LIMIT"


@pytest.mark.parametrize(
    "failure", [OSError("offline"), TimeoutError("timeout"), ValueError("inconclusive")]
)
async def test_fail_closed(secure, monkeypatch, failure):
    async def fail(self, data):
        raise failure

    monkeypatch.setattr(ClamAV, "scan", fail)
    assert (
        await preflight("x.pdf", "application/pdf", fixture_bytes("pdf"))
    ).verdict == "SCAN_FAILED"


async def test_clamd_wire_protocol_and_eicar(monkeypatch):
    """Real TCP protocol including framed bytes, not an antivirus efficacy claim."""
    calls = []

    async def server(reader, writer):
        command = await reader.readuntil(b"\0")
        if command == b"zVERSION\0":
            writer.write(b"ClamAV protocol-test/1\0")
        else:
            assert command == b"zINSTREAM\0"
            data = b""
            while size := struct.unpack("!I", await reader.readexactly(4))[0]:
                data += await reader.readexactly(size)
            calls.append(data)
            writer.write(
                b"stream: Eicar-Test-Signature FOUND\0"
                if data == fixture_bytes("eicar")
                else b"stream: OK\0"
            )
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(server, "127.0.0.1", 0)
    monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(settings, "clamav_port", listener.sockets[0].getsockname()[1])
    try:
        assert (await ClamAV().scan(b"clean"))[1] is None
        result = await preflight("eicar.txt", "text/plain", fixture_bytes("eicar"))
        assert result.verdict == "BLOCKED" and result.threat_name == "Eicar-Test-Signature"
        assert calls == [b"clean", fixture_bytes("eicar")]
    finally:
        listener.close()
        await listener.wait_closed()


async def create(client):
    response = await client.post(
        "/api/v1/cases",
        json={
            "customer_name": "Synthetic",
            "customer_email": "synthetic@example.com",
            "request_title": "M5 test",
            "tax_id": "5260250274",
            "estimated_value": "1230",
            "currency": "PLN",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def upload(client, cid, files):
    response = await client.post(f"/api/v1/uploads/{cid}", files=[("files", f) for f in files])
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("payload", [b"MZ harmless", b"%PDF-1.7 /JavaScript", b"\x00bad"])
async def test_non_safe_never_calls_parsers(client, secure, monkeypatch, payload):
    async def forbidden(*args, **kwargs):
        pytest.fail("Untrusted bytes reached a parser")

    monkeypatch.setattr("app.document_routing.processor.process_document", forbidden)
    monkeypatch.setattr(DevelopmentExtractionProvider, "extract", forbidden)
    monkeypatch.setattr(settings, "ocr_enabled", True)
    cid = await create(client)
    case = await upload(client, cid, [("untrusted.pdf", payload, "application/pdf")])
    assert case["status"] == "REVIEW_REQUIRED" and not case["ocr_documents"]
    assert case["security_scans"][0]["verdict"] != "SAFE"
    task = case["review_tasks"][0]
    assert task["task_type"] == "SECURITY_QUARANTINE"
    assert (await client.post(f"/api/v1/review/{cid}/approve")).status_code == 409
    assert (
        await client.patch(f"/api/v1/review/{cid}", json={"tax_id": "5260250274"})
    ).status_code == 200
    again = await upload(client, cid, [("renamed.pdf", payload, "application/pdf")])
    assert len(again["security_scans"]) == len(again["review_tasks"]) == 1
    path = f"/api/v1/review-tasks/{task['id']}/decision"
    for action in ["resolve", "dismiss"]:
        assert (
            await client.post(path, json={"action": action, "reason": "cannot bypass"})
        ).status_code == 409
    assert (
        await client.post(path, json={"action": "acknowledge", "reason": "Investigating"})
    ).status_code == 200
    assert (
        await client.post(path, json={"action": "acknowledge", "reason": "Again"})
    ).status_code == 409
    queue = (
        await client.get(
            "/api/v1/review-tasks?status=ACKNOWLEDGED&priority=CRITICAL"
            f"&task_type=SECURITY_QUARANTINE&case_id={cid}"
        )
    ).json()
    assert queue["total"] == 1
    assert (
        await client.post(
            path, json={"action": "reject_case", "reason": "Ask sender for clean replacement"}
        )
    ).status_code == 200
    assert (await client.post(f"/api/v1/review/{cid}/approve")).status_code == 409
    assert (
        await client.post(path, json={"action": "resolve", "reason": "Again"})
    ).status_code == 409
    final = (await client.get(f"/api/v1/cases/{cid}")).json()
    assert final["status"] == "FAILED"
    assert any(
        i["code"] == "SECURITY_UNSAFE" and not i["resolved"] for i in final["validation_issues"]
    )


async def test_mixed_case_keeps_security_blocker(client, secure):
    cid = await create(client)
    case = await upload(
        client,
        cid,
        [
            ("one.txt", b"Request title: Synthetic", "text/plain"),
            ("evil.pdf", b"MZ harmless", "application/pdf"),
            ("two.txt", b"Currency: PLN", "text/plain"),
        ],
    )
    assert [s["verdict"] for s in case["security_scans"]] == ["SAFE", "BLOCKED", "SAFE"]
    assert case["extracted_fields"] and case["status"] == "REVIEW_REQUIRED"
    assert (await client.post(f"/api/v1/review/{cid}/approve")).status_code == 409


@pytest.mark.parametrize("kind", ["unsupported", "failure"])
async def test_manual_review_resolution(client, secure, monkeypatch, kind):
    cid = await create(client)
    monkeypatch.setattr(settings, "ocr_enabled", False)
    if kind == "failure":

        async def failed(*args):
            raise ValueError("synthetic extraction error")

        monkeypatch.setattr(DevelopmentExtractionProvider, "extract", failed)
        files = [("x.txt", b"Synthetic text", "text/plain")]
    else:
        files = [("x.pdf", fixture_bytes("pdf"), "application/pdf")]
    case = await upload(client, cid, files)
    task = case["review_tasks"][0]
    assert task["task_type"] == (
        "EXTRACTION_FAILURE" if kind == "failure" else "UNSUPPORTED_ATTACHMENT"
    )
    response = await client.post(
        f"/api/v1/review-tasks/{task['id']}/decision",
        json={"action": "resolve", "reason": "Read original; verified case fields"},
    )
    assert response.status_code == 200, response.text
    assert (await client.post(f"/api/v1/review/{cid}/approve")).status_code == 200


async def test_outbox_retry_receipt_replay(client, secure):
    cid = await create(client)
    await upload(client, cid, [("bad.exe", b"MZ harmless", "application/octet-stream")])
    async for service in app.dependency_overrides[get_service]():
        db = service.db
        event = (await db.scalars(select(NotificationOutbox))).one()
        assert event.task_id and event.payload["public_case_id"]
        eid, tid = str(event.id), str(event.task_id)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        ) as transport:
            assert await deliver_one(db, transport)
        await db.refresh(event)
        assert event.attempts == 1 and event.last_error and event.sent_at is None
        assert not await deliver_one(db, client)  # backoff prevents immediate replay
        event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

        async def sink(request, eid=eid, tid=tid):
            response = await client.post(
                "/api/v1/review-tasks/notifications/receipt", json={"event_id": eid, "task_id": tid}
            )
            return httpx.Response(response.status_code, json=response.json())

        async with httpx.AsyncClient(transport=httpx.MockTransport(sink)) as transport:
            assert await deliver_one(db, transport)
            assert not await deliver_one(db, transport)
        await db.refresh(event)
        assert event.attempts == 2 and event.sent_at and event.last_error is None
        replay = await client.post(
            "/api/v1/review-tasks/notifications/receipt", json={"event_id": eid, "task_id": tid}
        )
        assert replay.json()["duplicate"] is True
        assert len((await db.scalars(select(NotificationReceipt))).all()) == 1
        audits = (await db.scalars(select(AuditEvent).where(AuditEvent.case_id == UUID(cid)))).all()
        assert {
            "REVIEW_NOTIFICATION_QUEUED",
            "REVIEW_NOTIFICATION_FAILED",
            "REVIEW_NOTIFICATION_SENT",
        } <= {a.event_type for a in audits}


async def test_email_same_gate(client, secure):
    response = await client.post(
        "/api/v1/inbound/email",
        json={
            "sender": {"address": "synthetic@example.com"},
            "received_at": "2026-09-28T10:00:00Z",
            "external_message_id": "<m5-security@example.com>",
            "attachments": [
                {
                    "filename": "bad.pdf",
                    "mime_type": "application/pdf",
                    "content_base64": base64.b64encode(b"MZ harmless").decode(),
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    case = (await client.get(f"/api/v1/cases/{response.json()['case_id']}")).json()
    assert case["security_scans"][0]["verdict"] == "BLOCKED"
    assert case["review_tasks"][0]["task_type"] == "SECURITY_QUARANTINE"


@pytest.mark.parametrize("stp", [False, True])
async def test_safe_keeps_m4_and_m3_then_closes_ocr_task(client, secure, monkeypatch, stp):
    from app.ocr import pipeline
    from tests.test_ocr import TEXT, result

    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "stp_enabled", stp)
    calls = []

    async def infer(url, provider, document_id, content, profile):
        calls.append(provider)
        return result(text=TEXT, provider=provider)

    monkeypatch.setattr(pipeline, "infer", infer)
    cid = await create(client)
    case = await upload(client, cid, [("scan.png", fixture_bytes("png"), "image/png")])
    assert case["security_scans"][0]["verdict"] == "SAFE"
    if stp:
        assert calls == ["paddle"]
        assert case["ocr_documents"][0]["report"]["route"] == "PRIMARY_OCR"
    else:
        assert set(calls) == {"paddle", "tesseract"}
        task = case["review_tasks"][0]
        assert task["task_type"] == "OCR_REVIEW"
        doc = case["ocr_documents"][0]
        reviewed = await client.post(
            f"/api/v1/ocr/{cid}/{doc['id']}/review",
            json={
                "reason": "Read synthetic original",
                "values": {
                    "document_number": "FV/1/2026",
                    "tax_id": "5260250274",
                    "issue_date": "2026-01-10",
                    "net_total": "1000",
                    "vat_total": "230",
                    "gross_total": "1230",
                    "currency": "PLN",
                },
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review_tasks"][0]["status"] == "RESOLVED"


async def test_scanner_failure_persists_without_parsing(client, secure, monkeypatch):
    async def failed(*args):
        raise TimeoutError()

    monkeypatch.setattr(ClamAV, "scan", failed)
    cid = await create(client)
    case = await upload(client, cid, [("scan.png", fixture_bytes("png"), "image/png")])
    assert case["security_scans"][0]["verdict"] == "SCAN_FAILED"
    assert not case["ocr_documents"] and not case["extracted_fields"]
    aid = case["attachments"][0]["id"]
    assert (await client.get(f"/api/v1/uploads/{cid}/{aid}")).status_code == 403


async def test_security_limits_are_persisted(client, secure, monkeypatch):
    monkeypatch.setattr(settings, "security_max_attachment_bytes", 4)
    cid = await create(client)
    case = await upload(client, cid, [("x.txt", b"12345", "text/plain")])
    assert case["security_scans"][0]["reason"] == "SIZE_LIMIT"
    assert case["review_tasks"][0]["task_type"] == "SECURITY_QUARANTINE"


def test_fail_closed_env_accepts_true_and_rejects_false(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("SECURITY_FAIL_CLOSED", "true")
    assert Settings(_env_file=None).security_fail_closed is True
    monkeypatch.setenv("SECURITY_FAIL_CLOSED", "false")
    with pytest.raises(ValidationError, match="does not support fail-open"):
        Settings(_env_file=None)


async def test_inconclusive_clamd_is_never_clean(monkeypatch):
    responses = iter(["ClamAV test", "INSTREAM size limit exceeded. ERROR"])

    async def command(*args):
        return next(responses)

    monkeypatch.setattr(ClamAV, "command", command)
    result = await preflight("x.txt", "text/plain", b"Synthetic limit test")
    assert result.verdict == "SCAN_FAILED"
