"""Milestone 4 document processing orchestration."""

from __future__ import annotations

import time

from app.core.config import settings
from app.document_routing.policy.router import Route, decide_route
from app.document_routing.preflight.native_pdf import extract_native_pdf_text
from app.document_routing.reporting import (
    build_native_report,
    build_primary_ocr_report,
)
from app.document_routing.scoring.native_fields import evaluate_native_fields
from app.ocr import pipeline


def _provider_settings(provider: str) -> tuple[str, str]:
    if provider == "tesseract":
        return settings.ocr_tesseract_url, settings.ocr_tesseract_profile
    if provider == "paddle":
        return settings.ocr_paddle_url, settings.ocr_paddle_profile
    raise ValueError(f"Unsupported OCR provider: {provider}")


async def _primary_then_selective_dual(
    *,
    document_id: str,
    content: bytes,
    initial_route: str,
    reason: str,
    native_processing_time_ms: float = 0.0,
) -> dict:
    primary_name = settings.stp_primary_ocr_provider
    secondary_name = "tesseract" if primary_name == "paddle" else "paddle"

    primary_url, primary_profile = _provider_settings(primary_name)

    primary = await pipeline.infer(
        primary_url,
        primary_name,
        document_id,
        content,
        primary_profile,
    )

    evidence = evaluate_native_fields(
        primary.raw_text if not primary.error else ""
    )

    if not primary.error and evidence.deterministic_stp_candidate:
        report = build_primary_ocr_report(
            result=primary,
            evidence=evidence,
        )
        report["routing"] = {
            "initial_route": initial_route,
            "final_route": "PRIMARY_OCR",
            "reason": reason,
            "primary_provider": primary_name,
            "secondary_provider_invoked": False,
            "native_processing_time_ms": native_processing_time_ms,
        }
        return report

    secondary_url, secondary_profile = _provider_settings(secondary_name)

    secondary = await pipeline.infer(
        secondary_url,
        secondary_name,
        document_id,
        content,
        secondary_profile,
    )

    # Keep the established M3 comparison ordering:
    # A = Tesseract, B = Paddle.
    if primary_name == "tesseract":
        tesseract_result = primary
        paddle_result = secondary
    else:
        tesseract_result = secondary
        paddle_result = primary

    report = pipeline.compare(tesseract_result, paddle_result)
    report["route"] = "DUAL_OCR"
    report["report_version"] = "m4-stp-v1"
    report["routing"] = {
        "initial_route": initial_route,
        "final_route": "DUAL_OCR",
        "reason": reason,
        "escalation_reason": (
            "primary OCR failed deterministic STP checks"
            if not primary.error
            else f"primary OCR provider error: {primary.error}"
        ),
        "primary_provider": primary_name,
        "secondary_provider": secondary_name,
        "secondary_provider_invoked": True,
        "primary_missing_critical_fields": evidence.missing_critical_fields,
        "primary_business_validation": evidence.business_validation,
        "native_processing_time_ms": native_processing_time_ms,
    }
    return report


async def process_document(
    *,
    document_id: str,
    filename: str,
    mime_type: str,
    content: bytes,
) -> dict:
    """
    Process one OCR-capable document while preserving Milestone 3 behavior
    when STP routing is disabled.

    Milestone 4 routing:
    - STP disabled -> exact legacy dual OCR
    - trusted native PDF + deterministic validation -> native candidate
    - otherwise -> primary OCR
    - failed primary safety checks -> selective second OCR + comparison
    """

    if not settings.stp_enabled:
        return await pipeline.dual(document_id, content)

    mime = mime_type.split(";", 1)[0].strip().lower()
    is_pdf = filename.lower().endswith(".pdf") or mime == "application/pdf"

    native_result = None
    native_elapsed_ms = 0.0

    if is_pdf:
        started = time.perf_counter()
        native_result = extract_native_pdf_text(content)
        native_elapsed_ms = (time.perf_counter() - started) * 1000

    decision = decide_route(
        filename=filename,
        mime_type=mime_type,
        native_pdf_result=native_result,
    )

    if decision.route == Route.NATIVE_TEXT and native_result is not None:
        evidence = evaluate_native_fields(native_result.text)

        if evidence.deterministic_stp_candidate:
            return build_native_report(
                document_id=document_id,
                raw_text=native_result.text,
                evidence=evidence,
                processing_time_ms=native_elapsed_ms,
                preflight={
                    "page_count": native_result.page_count,
                    "char_count": native_result.char_count,
                    "alnum_count": native_result.alnum_count,
                    "printable_ratio": native_result.printable_ratio,
                    "alnum_ratio": native_result.alnum_ratio,
                    "chars_per_page": native_result.chars_per_page,
                    "pages_with_text": native_result.pages_with_text,
                    "text_page_ratio": native_result.text_page_ratio,
                    "max_image_area_ratio": native_result.max_image_area_ratio,
                    "page_max_image_area_ratios": (
                        native_result.page_max_image_area_ratios
                    ),
                    "quality_score": (
                        decision.native_text.score
                        if decision.native_text
                        else None
                    ),
                    "quality_reasons": (
                        decision.native_text.reasons
                        if decision.native_text
                        else []
                    ),
                },
            )

        return await _primary_then_selective_dual(
            document_id=document_id,
            content=content,
            initial_route="NATIVE_TEXT",
            reason=(
                "native text passed structural quality gate but failed "
                "deterministic field validation"
            ),
            native_processing_time_ms=native_elapsed_ms,
        )

    if decision.route == Route.PRIMARY_OCR:
        return await _primary_then_selective_dual(
            document_id=document_id,
            content=content,
            initial_route="PRIMARY_OCR",
            reason=decision.reason,
            native_processing_time_ms=native_elapsed_ms,
        )

    if decision.route == Route.DUAL_OCR:
        report = await pipeline.dual(document_id, content)
        report["route"] = "DUAL_OCR"
        report["report_version"] = "m4-stp-v1"
        report["routing"] = {
            "initial_route": "DUAL_OCR",
            "final_route": "DUAL_OCR",
            "reason": decision.reason,
            "native_processing_time_ms": native_elapsed_ms,
        }
        return report

    # Unsupported automated types fail closed into human review semantics.
    report = await pipeline.dual(document_id, content)
    report["route"] = "DUAL_OCR"
    report["report_version"] = "m4-stp-v1"
    report["routing"] = {
        "initial_route": decision.route.value,
        "final_route": "DUAL_OCR",
        "reason": "unsupported automated route fell back to conservative dual OCR",
    }
    return report
