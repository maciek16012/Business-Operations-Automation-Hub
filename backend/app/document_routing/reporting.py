"""Backward-compatible report builders for Milestone 4 document routing."""

from __future__ import annotations

from app.document_routing.scoring.native_fields import NativeFieldEvidence
from app.ocr.pipeline import FIELDS


def build_native_report(
    *,
    document_id: str,
    raw_text: str,
    evidence: NativeFieldEvidence,
    processing_time_ms: float,
    preflight: dict,
) -> dict:
    """
    Represent native PDF extraction using the existing OCRDocument.report
    contract so Milestone 3 API/UI/review flows remain backward compatible.

    Native text is only marked as an STP candidate here. Final AUTO_ACCEPT
    policy is intentionally deferred until Milestone 4 DEV calibration.
    """
    rows: list[dict] = []

    for field in FIELDS:
        raw = evidence.raw_fields.get(field)
        normalized = evidence.normalized_fields.get(field)

        rows.append(
            {
                "field": field,
                "raw_a": raw,
                "raw_b": None,
                "normalized_a": normalized,
                "normalized_b": None,
                "comparison": "native_single_source",
                "outcome": (
                    "NATIVE_VALIDATED"
                    if normalized is not None
                    else "NATIVE_MISSING"
                ),
                "selected": normalized,
                "reason": (
                    "Value extracted from embedded PDF text and normalized "
                    "with the deterministic document pipeline"
                    if normalized is not None
                    else "Critical field was not extracted from embedded PDF text"
                ),
            }
        )

    return {
        "report_version": "m4-stp-v1",
        "route": "NATIVE_TEXT",
        "providers": [
            {
                "provider": "native_pdf",
                "provider_version": "pymupdf",
                "document_id": document_id,
                "raw_text": raw_text,
                "pages": [],
                "provider_confidence": None,
                "processing_time_ms": processing_time_ms,
                "error": None,
                "raw_provider_output": {
                    "preflight": preflight,
                },
            }
        ],
        "fields": rows,
        "business_validation": {
            "native": evidence.business_validation,
            "selected": evidence.business_validation,
        },
        "selected": evidence.normalized_fields,
        "outcome": (
            "NATIVE_STP_CANDIDATE"
            if evidence.deterministic_stp_candidate
            else "NATIVE_REVIEW_REQUIRED"
        ),
        "review_required": True,
        "stp": {
            "candidate": evidence.deterministic_stp_candidate,
            "auto_accepted": False,
            "policy_status": "awaiting_dev_calibration",
            "missing_critical_fields": evidence.missing_critical_fields,
        },
    }

def build_primary_ocr_report(
    *,
    result,
    evidence: NativeFieldEvidence,
) -> dict:
    """
    Build an M3-compatible report for a single OCR provider.

    A deterministic candidate may be auto-accepted by the M4 policy.
    Missing or invalid critical evidence must be escalated.
    """
    rows: list[dict] = []

    for field in FIELDS:
        raw = evidence.raw_fields.get(field)
        normalized = evidence.normalized_fields.get(field)

        rows.append(
            {
                "field": field,
                "raw_a": raw,
                "raw_b": None,
                "normalized_a": normalized,
                "normalized_b": None,
                "comparison": "primary_single_source",
                "outcome": (
                    "PRIMARY_VALIDATED"
                    if normalized is not None
                    else "PRIMARY_MISSING"
                ),
                "selected": normalized,
                "reason": (
                    "Value extracted by primary OCR and passed deterministic normalization"
                    if normalized is not None
                    else "Critical field was not extracted by primary OCR"
                ),
            }
        )

    candidate = evidence.deterministic_stp_candidate

    return {
        "report_version": "m4-stp-v1",
        "route": "PRIMARY_OCR",
        "providers": [result.model_dump()],
        "fields": rows,
        "business_validation": {
            "primary": evidence.business_validation,
            "selected": evidence.business_validation,
        },
        "selected": evidence.normalized_fields,
        "outcome": (
            "PRIMARY_STP_CANDIDATE"
            if candidate
            else "PRIMARY_REVIEW_REQUIRED"
        ),
        "review_required": not candidate,
        "stp": {
            "candidate": candidate,
            "auto_accepted": candidate,
            "policy_status": (
                "dev_calibrated_primary_candidate"
                if candidate
                else "escalation_required"
            ),
            "missing_critical_fields": evidence.missing_critical_fields,
        },
    }
