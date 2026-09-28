"""Independent inference, explicit comparison, conservative deterministic resolver."""

import asyncio
import base64
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.validation.nip import valid_nip

FIELDS = (
    "document_number",
    "tax_id",
    "issue_date",
    "net_total",
    "vat_total",
    "gross_total",
    "currency",
)
MONEY = ("net_total", "vat_total", "gross_total")
Outcome = Literal[
    "CONSENSUS_VALID", "CONSENSUS_UNVERIFIED", "CONFLICT_RESOLVED", "CONFLICT_REVIEW", "BOTH_FAILED"
]


class OCRResult(BaseModel):
    provider: str
    provider_version: str
    document_id: str
    raw_text: str = ""
    pages: list[dict] = Field(default_factory=list)
    provider_confidence: float | None = None
    processing_time_ms: float = Field(ge=0)
    error: str | None = None
    raw_provider_output: dict | list | str | None = None


def normalize_field(field: str, value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    if field in MONEY:
        text = re.sub(r"\s", "", text).replace("PLN", "").replace("zł", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            number = Decimal(text)
            if not number.is_finite():
                return None
            if isinstance(number.as_tuple().exponent, int) and int(number.as_tuple().exponent) < -2:
                return None
            return format(number.quantize(Decimal(".01")), "f")
        except InvalidOperation:
            return None
    if field == "tax_id":
        return re.sub(r"[\s-]", "", text)
    if field == "currency":
        return text.upper()
    if field == "issue_date":
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        return None
    return text.upper().replace(" ", "")


LABELS = {
    "document_number": r"(?:Faktura|Numer dokumentu)",
    "tax_id": r"NIP",
    "issue_date": r"Data wystawienia",
    "net_total": r"(?:Netto|Razem netto)",
    "vat_total": r"(?:VAT|Razem VAT)",
    "gross_total": r"(?:Brutto|Razem brutto)",
    "currency": r"Waluta",
}


def extract_fields(text: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for field, label in LABELS.items():
        # Allow label/value on adjacent OCR lines. Never use a peer result/truth.
        matches = re.findall(r"(?:^|\n)\s*" + label + r"\s*[:：]?\s*([^\n]+)", text, re.I)
        result[field] = matches[0].strip() if len(matches) == 1 else None
    return result


def business_checks(values: dict[str, str | None]) -> dict[str, bool]:
    def amount(f):
        try:
            return Decimal(values.get(f) or "NaN")
        except InvalidOperation:
            return Decimal("NaN")

    amounts = [amount(f) for f in MONEY]
    nonnegative = all(a.is_finite() and a >= 0 for a in amounts)
    arithmetic = nonnegative and abs(amounts[0] + amounts[1] - amounts[2]) <= Decimal(".01")
    try:
        valid_date = date.fromisoformat(values.get("issue_date") or "") <= date.today()
    except ValueError:
        valid_date = False
    return {
        "nip_checksum": valid_nip(values.get("tax_id") or ""),
        "money_nonnegative": nonnegative,
        "net_plus_vat_equals_gross": arithmetic,
        "currency_allowed": values.get("currency") in {"PLN", "EUR", "USD", "GBP", "CHF"},
        "issue_date_valid": valid_date,
        "document_number_present": bool(values.get("document_number")),
    }


def compare(a: OCRResult, b: OCRResult) -> dict:
    raw_a = extract_fields(a.raw_text) if not a.error else dict.fromkeys(FIELDS)
    raw_b = extract_fields(b.raw_text) if not b.error else dict.fromkeys(FIELDS)
    na = {f: normalize_field(f, raw_a[f]) for f in FIELDS}
    nb = {f: normalize_field(f, raw_b[f]) for f in FIELDS}
    checks_a = business_checks(na)
    checks_b = business_checks(nb)
    rows: list[dict] = []
    for f in FIELDS:
        x, y = na[f], nb[f]
        selected = None
        outcome = "CONFLICT_REVIEW"
        reason = "Disagreement or missing value requires human review"
        if a.error and b.error:
            outcome = "BOTH_FAILED"
            reason = "Neither provider produced usable inference"
        elif x is not None and x == y and not a.error and not b.error:
            selected = x
            outcome = "CONSENSUS_UNVERIFIED"
            reason = "Agreement is not ground truth"
            strong = (f == "tax_id" and checks_a["nip_checksum"]) or (
                f in MONEY and checks_a["net_plus_vat_equals_gross"]
            )
            if strong:
                outcome = "CONSENSUS_VALID"
                reason = (
                    "Agreement supported by checksum/arithmetic (not proof of source correctness)"
                )
        elif x is not None and y is not None and not a.error and not b.error:
            if f == "tax_id" and checks_a["nip_checksum"] != checks_b["nip_checksum"]:
                selected = x if checks_a["nip_checksum"] else y
                outcome = "CONFLICT_RESOLVED"
                reason = "Exactly one candidate satisfies NIP checksum"
            elif (
                f in MONEY
                and checks_a["net_plus_vat_equals_gross"] != checks_b["net_plus_vat_equals_gross"]
            ):
                selected = x if checks_a["net_plus_vat_equals_gross"] else y
                outcome = "CONFLICT_RESOLVED"
                reason = "Exactly one complete provider money tuple satisfies arithmetic"
        rows.append(
            dict(
                field=f,
                raw_a=raw_a[f],
                raw_b=raw_b[f],
                normalized_a=x,
                normalized_b=y,
                comparison="equal" if x is not None and x == y else "different",
                outcome=outcome,
                selected=selected,
                reason=reason,
            )
        )
    selected_values = {row["field"]: row["selected"] for row in rows}
    checks = business_checks(selected_values)
    states = {row["outcome"] for row in rows}
    outcome = (
        "BOTH_FAILED"
        if a.error and b.error
        else "CONFLICT_REVIEW"
        if "CONFLICT_REVIEW" in states or not all(checks.values())
        else "CONSENSUS_UNVERIFIED"
        if "CONSENSUS_UNVERIFIED" in states
        else "CONFLICT_RESOLVED"
        if "CONFLICT_RESOLVED" in states
        else "CONSENSUS_VALID"
    )
    return dict(
        providers=[a.model_dump(), b.model_dump()],
        fields=rows,
        business_validation={"a": checks_a, "b": checks_b, "selected": checks},
        selected=selected_values,
        outcome=outcome,
        review_required=outcome not in {"CONSENSUS_VALID", "CONFLICT_RESOLVED"},
    )


async def infer(
    url: str, provider: str, document_id: str, content: bytes, profile="baseline", timeout=90.0
) -> OCRResult:
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json={
                    "document_id": document_id,
                    "content_base64": base64.b64encode(content).decode(),
                    "preprocessing": profile,
                },
            )
            response.raise_for_status()
            result = OCRResult.model_validate(response.json())
            if result.document_id != document_id or result.provider != provider:
                raise ValueError("Provider identity mismatch")
            return result
    except (httpx.HTTPError, ValueError) as exc:
        return OCRResult(
            provider=provider,
            provider_version="unavailable",
            document_id=document_id,
            processing_time_ms=(time.perf_counter() - start) * 1000,
            error="TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "PROVIDER_FAILURE",
        )


async def dual(document_id: str, content: bytes) -> dict:
    from app.core.config import settings

    a, b = await asyncio.gather(
        infer(
            settings.ocr_tesseract_url,
            "tesseract",
            document_id,
            content,
            settings.ocr_tesseract_profile,
        ),
        infer(settings.ocr_paddle_url, "paddle", document_id, content, settings.ocr_paddle_profile),
    )
    return compare(a, b)


def supported(filename: str, mime: str) -> bool:
    from app.core.config import settings

    return (
        settings.ocr_enabled
        and filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"))
        and mime.split(";")[0].lower()
        in {"application/pdf", "image/png", "image/jpeg", "image/tiff", "application/octet-stream"}
    )
