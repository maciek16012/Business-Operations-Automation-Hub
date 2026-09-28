import httpx
import pytest
from pydantic import ValidationError

from app.ocr.pipeline import OCRResult, business_checks, compare, infer, normalize_field

TEXT = (
    "Faktura: FV/1/2026\nNIP: 5260250274\nData wystawienia: 2026-01-10\n"
    "Netto: 1000,00\nVAT: 230,00\nBrutto: 1230,00\nWaluta: PLN"
)


def result(text=TEXT, error=None, provider="tesseract"):
    return OCRResult(
        provider=provider,
        provider_version="test",
        document_id="doc",
        raw_text=text,
        processing_time_ms=2,
        error=error,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("12 500,00 PLN", "12500.00"),
        ("1.234,56", "1234.56"),
        ("0", "0.00"),
        ("-1", "-1.00"),
        ("NaN", None),
        ("infinity", None),
        ("12.345", None),
        ("abc", None),
    ],
)
def test_money(value, expected):
    assert normalize_field("gross_total", value) == expected


def test_contract_requires_identity_and_latency():
    with pytest.raises(ValidationError):
        OCRResult(provider="a")
    with pytest.raises(ValidationError):
        OCRResult(provider="a", provider_version="1", document_id="d", processing_time_ms=-1)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (TEXT, TEXT, "CONSENSUS_UNVERIFIED"),
        (TEXT, TEXT.replace("FV/1", "FV/9"), "CONFLICT_REVIEW"),
        (TEXT.replace("FV/1", "FV/9"), TEXT, "CONFLICT_REVIEW"),
        (TEXT.replace("FV/1", "FV/8"), TEXT.replace("FV/1", "FV/9"), "CONFLICT_REVIEW"),
        (TEXT.replace("FV/1", "FV/9"), TEXT.replace("FV/1", "FV/9"), "CONSENSUS_UNVERIFIED"),
    ],
)
def test_explicit_correct_wrong_cases(a, b, expected):
    report = compare(result(a), result(b, provider="paddle"))
    assert report["outcome"] == expected
    assert report["review_required"]
    assert len(report["providers"]) == 2


@pytest.mark.parametrize(
    "fail_a,fail_b,expected",
    [
        (True, False, "CONFLICT_REVIEW"),
        (False, True, "CONFLICT_REVIEW"),
        (True, True, "BOTH_FAILED"),
    ],
)
def test_engine_failures(fail_a, fail_b, expected):
    report = compare(
        result(error="TIMEOUT" if fail_a else None),
        result(error="UNAVAILABLE" if fail_b else None, provider="paddle"),
    )
    assert report["outcome"] == expected
    assert report["review_required"]
    assert all(x["selected"] is None for x in report["fields"])


@pytest.mark.parametrize("reverse", [False, True])
def test_nip_resolved_both_directions(reverse):
    a = result()
    b = result(TEXT.replace("5260250274", "5260250275"), provider="paddle")
    report = compare(b, a) if reverse else compare(a, b)
    field = next(f for f in report["fields"] if f["field"] == "tax_id")
    assert field["selected"] == "5260250274"
    assert field["outcome"] == "CONFLICT_RESOLVED"
    assert field["raw_a"] != field["raw_b"]


def test_false_consensus_arithmetic_detected():
    text = TEXT.replace("1230,00", "9230,00")
    report = compare(result(text), result(text, provider="paddle"))
    assert report["outcome"] == "CONFLICT_REVIEW"
    assert not report["business_validation"]["selected"]["net_plus_vat_equals_gross"]


def test_false_consensus_valid_but_wrong_nip_not_truth():
    text = TEXT.replace("5260250274", "8567346215")
    report = compare(result(text), result(text, provider="paddle"))
    assert report["review_required"]
    assert report["outcome"] == "CONSENSUS_UNVERIFIED"


def test_one_arithmetic_tuple_resolves():
    report = compare(result(), result(TEXT.replace("1230,00", "9230,00"), provider="paddle"))
    field = next(f for f in report["fields"] if f["field"] == "gross_total")
    assert field["outcome"] == "CONFLICT_RESOLVED"
    assert field["selected"] == "1230.00"


@pytest.mark.parametrize("kind", ["timeout", "unavailable", "malformed", "identity"])
async def test_provider_transport(monkeypatch, kind):
    async def post(self, *args, **kwargs):
        if kind == "timeout":
            raise httpx.ReadTimeout("timeout")
        if kind == "unavailable":
            raise httpx.ConnectError("down")
        return httpx.Response(
            200,
            json={} if kind == "malformed" else result().model_dump(),
            request=httpx.Request("POST", "http://local"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    out = await infer("http://local", "paddle", "other", b"document")
    assert out.error == ("TIMEOUT" if kind == "timeout" else "PROVIDER_FAILURE")


def test_business_rules():
    checks = business_checks(
        {
            "tax_id": "bad",
            "net_total": "-1",
            "vat_total": "0",
            "gross_total": "-1",
            "currency": "BAD",
            "issue_date": "nonsense",
        }
    )
    assert not any(checks.values())


@pytest.mark.parametrize("both_failed", [False, True])
async def test_upload_review_pipeline(client, monkeypatch, both_failed):
    from app.core.config import settings
    from app.ocr import pipeline

    monkeypatch.setattr(settings, "ocr_enabled", True)
    calls = []

    async def dual(doc, content):
        calls.append((doc, content))
        return compare(
            result(error="UNAVAILABLE" if both_failed else None),
            result(error="TIMEOUT" if both_failed else None, provider="paddle"),
        )

    monkeypatch.setattr(pipeline, "dual", dual)
    created = await client.post(
        "/api/v1/cases",
        json={
            "customer_name": "Synthetic",
            "customer_email": "synthetic@example.com",
            "request_title": "OCR review",
        },
    )
    case = created.json()
    cid = case["id"]
    response = await client.post(
        f"/api/v1/uploads/{cid}",
        files={"files": ("invoice.pdf", b"%PDF-synthetic-test", "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    doc = data["ocr_documents"][0]
    assert data["status"] == "REVIEW_REQUIRED"
    assert len(doc["report"]["providers"]) == 2
    assert len(calls) == 1
    blocked = await client.post(f"/api/v1/review/{cid}/approve")
    assert blocked.status_code == 409
    # A business-field patch cannot silently acknowledge OCR evidence.
    patch = await client.patch(f"/api/v1/review/{cid}", json={"tax_id": "5260250274"})
    assert any(
        i["code"] == "OCR_REVIEW_REQUIRED" and not i["resolved"]
        for i in patch.json()["validation_issues"]
    )
    path = f"/api/v1/ocr/{cid}/{doc['id']}/review"
    values = {
        "document_number": "FV/1/2026",
        "tax_id": "5260250274",
        "issue_date": "2026-01-10",
        "net_total": "1000,00",
        "vat_total": "230,00",
        "gross_total": "1230,00",
        "currency": "PLN",
    }
    assert (
        await client.post(
            path, json={"reason": "Checked original", "values": {**values, "gross_total": "999"}}
        )
    ).status_code == 422
    reviewed = await client.post(
        path, json={"reason": "Checked original document visually", "values": values}
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "READY"
    assert reviewed.json()["ocr_documents"][0]["report"] == doc["report"]
    assert reviewed.json()["ocr_documents"][0]["reviewed_values"]["gross_total"] == "1230.00"
    assert (await client.post(f"/api/v1/review/{cid}/approve")).status_code == 200
    assert (
        await client.post(path, json={"reason": "Late edit", "values": values})
    ).status_code == 409


async def test_email_pdf_uses_same_dual_path(client, monkeypatch):
    import base64

    from app.core.config import settings
    from app.ocr import pipeline

    monkeypatch.setattr(settings, "ocr_enabled", True)
    calls = []

    async def dual(doc, content):
        calls.append(doc)
        return compare(result(), result(provider="paddle"))

    monkeypatch.setattr(pipeline, "dual", dual)
    payload = {
        "sender": {"address": "synthetic@example.com"},
        "received_at": "2026-09-27T10:00:00Z",
        "external_message_id": "<ocr-test@example.com>",
        "attachments": [
            {
                "filename": "document.pdf",
                "mime_type": "application/pdf",
                "content_base64": base64.b64encode(b"%PDF-test").decode(),
            }
        ],
    }
    first = await client.post("/api/v1/inbound/email", json=payload)
    assert first.status_code == 201
    replay = await client.post("/api/v1/inbound/email", json=payload)
    assert replay.json()["result"] == "duplicate"
    assert len(calls) == 1
    detail = (await client.get("/api/v1/cases/" + first.json()["case_id"])).json()
    assert len(detail["ocr_documents"]) == 1
    assert not any(i["code"] == "EMAIL_ATTACHMENT_UNSUPPORTED" for i in detail["validation_issues"])


def test_metric_edit_distance_and_false_consensus():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/benchmark_ocr.py"
    spec = importlib.util.spec_from_file_location("benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.distance("kitten", "sitting") == 3
    assert module.distance("same", "same") == 0
    assert module.distance("", "abc") == 3
