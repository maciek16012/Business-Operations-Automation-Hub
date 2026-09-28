import asyncio

import pymupdf

from app.core.config import settings
from app.document_routing.policy.router import Route, decide_route
from app.document_routing.preflight.native_pdf import (
    NativePDFTextResult,
    assess_native_text,
    extract_native_pdf_text,
)
from app.document_routing.processor import process_document
from app.document_routing.reporting import build_native_report
from app.document_routing.scoring.native_fields import evaluate_native_fields

VALID_TEXT = (
    "Faktura: FV/2026/001\n"
    "NIP: 5260250995\n"
    "Data wystawienia: 2026-09-20\n"
    "Netto: 100.00\n"
    "VAT: 23.00\n"
    "Brutto: 123.00\n"
    "Waluta: PLN\n"
    "Sprzedawca: Example Company Sp. z o.o.\n"
    "Nabywca: Example Customer Sp. z o.o.\n"
    "Opis: Milestone 4 straight-through processing test document."
)


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_native_pdf_extracts_embedded_text():
    result = extract_native_pdf_text(make_pdf(VALID_TEXT))

    assert result.extraction_error is None
    assert result.page_count == 1
    assert result.pages_with_text == 1
    assert result.text_page_ratio == 1.0
    assert "FV/2026/001" in result.text
    assert result.char_count > 100


def test_invalid_pdf_fails_closed():
    result = extract_native_pdf_text(b"not-a-pdf")

    assert result.extraction_error is not None
    assert result.text == ""
    assert result.char_count == 0


def test_native_quality_gate_accepts_good_text():
    result = extract_native_pdf_text(make_pdf(VALID_TEXT))

    decision = assess_native_text(
        result,
        min_chars_per_page=100,
        min_alnum_ratio=0.30,
        min_printable_ratio=0.95,
        min_text_page_ratio=0.80,
    )

    assert decision.trusted
    assert decision.score == 1.0


def test_native_quality_gate_rejects_sparse_text():
    result = NativePDFTextResult(
        page_count=1,
        text="ABC",
        char_count=3,
        alnum_count=3,
        printable_ratio=1.0,
        alnum_ratio=1.0,
        chars_per_page=3.0,
        pages_with_text=1,
        text_page_ratio=1.0,
    )

    decision = assess_native_text(
        result,
        min_chars_per_page=100,
        min_alnum_ratio=0.30,
        min_printable_ratio=0.95,
        min_text_page_ratio=0.80,
    )

    assert not decision.trusted
    assert "too little embedded text" in decision.reasons


def test_native_field_evidence_valid_document():
    evidence = evaluate_native_fields(VALID_TEXT)

    assert evidence.all_critical_fields_present
    assert evidence.all_business_checks_passed
    assert evidence.deterministic_stp_candidate
    assert evidence.normalized_fields["gross_total"] == "123.00"
    assert evidence.normalized_fields["tax_id"] == "5260250995"


def test_native_field_evidence_rejects_bad_arithmetic():
    evidence = evaluate_native_fields(VALID_TEXT.replace("Brutto: 123.00", "Brutto: 999.00"))

    assert not evidence.all_business_checks_passed
    assert not evidence.deterministic_stp_candidate
    assert not evidence.business_validation["net_plus_vat_equals_gross"]


def test_router_selects_native_text_for_trusted_pdf():
    native = extract_native_pdf_text(make_pdf(VALID_TEXT))

    decision = decide_route(
        filename="invoice.pdf",
        mime_type="application/pdf",
        native_pdf_result=native,
    )

    assert decision.route == Route.NATIVE_TEXT
    assert decision.native_text is not None
    assert decision.native_text.trusted


def test_router_routes_images_to_primary_ocr():
    decision = decide_route(
        filename="scan.png",
        mime_type="image/png",
    )

    assert decision.route == Route.PRIMARY_OCR


def test_native_report_keeps_m3_compatible_shape():
    evidence = evaluate_native_fields(VALID_TEXT)

    report = build_native_report(
        document_id="doc-1",
        raw_text=VALID_TEXT,
        evidence=evidence,
        processing_time_ms=5.0,
        preflight={"trusted": True},
    )

    assert report["route"] == "NATIVE_TEXT"
    assert report["outcome"] == "NATIVE_STP_CANDIDATE"
    assert report["review_required"] is True
    assert report["stp"]["candidate"] is True
    assert report["stp"]["auto_accepted"] is False
    assert len(report["providers"]) == 1
    assert len(report["fields"]) == 7
    assert set(report["selected"]) == {
        "document_number",
        "tax_id",
        "issue_date",
        "net_total",
        "vat_total",
        "gross_total",
        "currency",
    }


def test_processor_uses_native_path_when_stp_enabled(monkeypatch):
    monkeypatch.setattr(settings, "stp_enabled", True)

    report = asyncio.run(
        process_document(
            document_id="doc-native",
            filename="invoice.pdf",
            mime_type="application/pdf",
            content=make_pdf(VALID_TEXT),
        )
    )

    assert report["route"] == "NATIVE_TEXT"
    assert report["outcome"] == "NATIVE_STP_CANDIDATE"
    assert report["stp"]["candidate"] is True
    assert report["review_required"] is True


def test_processor_preserves_legacy_dual_path_when_stp_disabled(monkeypatch):
    monkeypatch.setattr(settings, "stp_enabled", False)

    expected = {
        "providers": [],
        "fields": [],
        "business_validation": {},
        "selected": {},
        "outcome": "LEGACY_TEST",
        "review_required": True,
    }

    async def fake_dual(document_id, content):
        assert document_id == "legacy"
        assert content == b"document"
        return expected

    monkeypatch.setattr("app.document_routing.processor.pipeline.dual", fake_dual)

    report = asyncio.run(
        process_document(
            document_id="legacy",
            filename="scan.pdf",
            mime_type="application/pdf",
            content=b"document",
        )
    )

    assert report is expected
    assert "route" not in report
    assert "report_version" not in report



def test_primary_ocr_auto_accepts_valid_candidate(monkeypatch):
    from app.ocr.pipeline import OCRResult

    monkeypatch.setattr(settings, "stp_enabled", True)
    monkeypatch.setattr(settings, "stp_primary_ocr_provider", "paddle")

    calls = []

    async def fake_infer(url, provider, document_id, content, profile="baseline", timeout=90.0):
        calls.append(provider)
        return OCRResult(
            provider=provider,
            provider_version="test",
            document_id=document_id,
            raw_text=VALID_TEXT,
            processing_time_ms=5.0,
        )

    monkeypatch.setattr("app.document_routing.processor.pipeline.infer", fake_infer)

    report = asyncio.run(
        process_document(
            document_id="primary-valid",
            filename="scan.png",
            mime_type="image/png",
            content=b"image",
        )
    )

    assert calls == ["paddle"]
    assert report["route"] == "PRIMARY_OCR"
    assert report["outcome"] == "PRIMARY_STP_CANDIDATE"
    assert report["review_required"] is False
    assert report["stp"]["candidate"] is True
    assert report["stp"]["auto_accepted"] is True
    assert report["routing"]["secondary_provider_invoked"] is False


def test_primary_ocr_escalates_to_second_engine_when_incomplete(monkeypatch):
    from app.ocr.pipeline import OCRResult

    monkeypatch.setattr(settings, "stp_enabled", True)
    monkeypatch.setattr(settings, "stp_primary_ocr_provider", "paddle")

    incomplete = (
        "Faktura: FV/2026/001\n"
        "NIP: 5260250995\n"
        "Data wystawienia: 2026-09-20"
    )
    calls = []

    async def fake_infer(url, provider, document_id, content, profile="baseline", timeout=90.0):
        calls.append(provider)
        return OCRResult(
            provider=provider,
            provider_version="test",
            document_id=document_id,
            raw_text=incomplete if provider == "paddle" else VALID_TEXT,
            processing_time_ms=5.0,
        )

    monkeypatch.setattr("app.document_routing.processor.pipeline.infer", fake_infer)

    report = asyncio.run(
        process_document(
            document_id="primary-escalation",
            filename="scan.png",
            mime_type="image/png",
            content=b"image",
        )
    )

    assert calls == ["paddle", "tesseract"]
    assert report["route"] == "DUAL_OCR"
    assert report["review_required"] is True
    assert report["routing"]["secondary_provider_invoked"] is True
    assert report["routing"]["primary_provider"] == "paddle"
    assert report["routing"]["secondary_provider"] == "tesseract"


def test_native_quality_gate_rejects_large_raster_even_with_good_text():
    result = NativePDFTextResult(
        page_count=1,
        text=VALID_TEXT,
        char_count=len(VALID_TEXT),
        alnum_count=sum(ch.isalnum() for ch in VALID_TEXT),
        printable_ratio=1.0,
        alnum_ratio=sum(ch.isalnum() for ch in VALID_TEXT) / len(VALID_TEXT),
        chars_per_page=float(len(VALID_TEXT)),
        pages_with_text=1,
        text_page_ratio=1.0,
        max_image_area_ratio=1.0,
        page_max_image_area_ratios=[1.0],
    )

    decision = assess_native_text(
        result,
        min_chars_per_page=100,
        min_alnum_ratio=0.30,
        min_printable_ratio=0.95,
        min_text_page_ratio=0.80,
        max_image_area_ratio=0.80,
    )

    assert not decision.trusted
    assert "large raster image makes embedded PDF text untrusted" in decision.reasons


