import re
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = (
    "customer_name",
    "customer_email",
    "company_name",
    "tax_id",
    "request_title",
    "request_description",
    "requested_deadline",
    "currency",
    "estimated_value",
)


def normalize_money(raw: str) -> tuple[Decimal, str | None]:
    text = raw.strip().replace("\u00a0", " ")
    match = re.search(r"\s*([A-Za-z]{3})$", text)
    currency = match.group(1).upper() if match else None
    number = text[: match.start()] if match else text
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?: \d{3})+)(?:[.,]\d{1,2})?", number.strip()):
        raise ValueError("Expected a decimal amount with at most two fractional digits")
    try:
        amount = Decimal(number.replace(" ", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount") from exc
    if not amount.is_finite() or abs(amount) >= Decimal("1000000000000"):
        raise ValueError("Amount outside supported range")
    return amount.quantize(Decimal("0.01")), currency


def normalize(field: str, raw: str | None) -> tuple[object, str | None]:
    if raw is None or not raw.strip():
        return None, None
    value = raw.strip()
    if field == "estimated_value":
        return normalize_money(value)
    if field == "requested_deadline":
        return date.fromisoformat(value), None
    if field == "tax_id":
        value = re.sub(r"[\s-]", "", value)
    if field == "currency":
        value = value.upper()
    limits = {
        "customer_name": 255,
        "customer_email": 320,
        "company_name": 255,
        "tax_id": 32,
        "request_title": 255,
        "currency": 3,
        "request_description": 20000,
    }
    if len(value) > limits.get(field, 20000):
        raise ValueError("Value exceeds field length")
    return value, None
