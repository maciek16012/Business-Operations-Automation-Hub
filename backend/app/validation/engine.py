from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from email_validator import EmailNotValidError, validate_email

from app.domain.enums import IssueSeverity
from app.validation.nip import valid_nip


@dataclass(slots=True)
class RuleIssue:
    code: str
    severity: IssueSeverity
    message: str
    field_name: str | None = None


class ValidationEngine:
    def validate(self, payload: dict[str, object], today: date | None = None) -> list[RuleIssue]:
        issues: list[RuleIssue] = []

        def error(code: str, field: str, message: str) -> None:
            issues.append(RuleIssue(code, IssueSeverity.ERROR, message, field))

        if not (payload.get("customer_name") or payload.get("company_name")):
            error("CUSTOMER_REQUIRED", "customer_name", "Provide a customer or company")
        if not payload.get("request_title"):
            error("TITLE_REQUIRED", "request_title", "Provide a request title")
        email = payload.get("customer_email")
        if email:
            try:
                validate_email(str(email), check_deliverability=False)
            except EmailNotValidError:
                error("EMAIL_INVALID", "customer_email", "Invalid email syntax")
        nip = payload.get("tax_id")
        if nip and not valid_nip(str(nip)):
            error("NIP_INVALID", "tax_id", "Invalid Polish NIP syntax or checksum")
        deadline = payload.get("requested_deadline")
        if deadline is not None and (
            not isinstance(deadline, date) or deadline < (today or date.today())
        ):
            error(
                "DEADLINE_INVALID",
                "requested_deadline",
                "Deadline must be an ISO date, today or later",
            )
        amount = payload.get("estimated_value")
        if amount is not None:
            if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
                error(
                    "VALUE_INVALID", "estimated_value", "Value must be a finite nonnegative decimal"
                )
            if not payload.get("currency"):
                error("CURRENCY_REQUIRED", "currency", "Currency is required for an amount")
        if payload.get("currency") is not None and payload["currency"] not in {
            "PLN",
            "EUR",
            "USD",
            "GBP",
        }:
            error("CURRENCY_UNSUPPORTED", "currency", "Supported currencies: PLN, EUR, USD, GBP")
        if payload.get("duplicate"):
            issues.append(
                RuleIssue(
                    "DUPLICATE_ATTACHMENT",
                    IssueSeverity.WARNING,
                    "Exact duplicate ignored; original attachment retained",
                )
            )
        return issues
