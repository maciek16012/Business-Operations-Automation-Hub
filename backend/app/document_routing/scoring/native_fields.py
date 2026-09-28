"""Field-level evidence derived from trusted native PDF text."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.ocr.pipeline import FIELDS, business_checks, extract_fields, normalize_field


class NativeFieldEvidence(BaseModel):
    raw_fields: dict[str, str | None]
    normalized_fields: dict[str, str | None]
    business_validation: dict[str, bool]
    missing_critical_fields: list[str] = Field(default_factory=list)
    all_critical_fields_present: bool
    all_business_checks_passed: bool
    deterministic_stp_candidate: bool


def evaluate_native_fields(text: str) -> NativeFieldEvidence:
    """
    Parse embedded PDF text using the same deterministic field extraction,
    normalization and business validation rules used by the M3 OCR pipeline.

    This function deliberately produces an STP *candidate*, not a final
    AUTO_ACCEPT decision. Final acceptance belongs to the routing/policy layer
    and must be calibrated on the Milestone 4 DEV dataset.
    """
    raw_fields = extract_fields(text)

    normalized_fields = {
        field: normalize_field(field, raw_fields.get(field))
        for field in FIELDS
    }

    validation = business_checks(normalized_fields)

    missing = [
        field
        for field in FIELDS
        if normalized_fields.get(field) is None
    ]

    all_present = not missing
    all_checks = bool(validation) and all(validation.values())

    return NativeFieldEvidence(
        raw_fields=raw_fields,
        normalized_fields=normalized_fields,
        business_validation=validation,
        missing_critical_fields=missing,
        all_critical_fields_present=all_present,
        all_business_checks_passed=all_checks,
        deterministic_stp_candidate=all_present and all_checks,
    )
