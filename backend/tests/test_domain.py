from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import CaseStatus
from app.domain.state_machine import ALLOWED_TRANSITIONS, ensure_transition
from app.extraction.development import DevelopmentExtractionProvider
from app.storage.base import LocalFilesystemStorage
from app.validation.engine import ValidationEngine
from app.validation.nip import valid_nip
from app.validation.normalization import normalize, normalize_money


@pytest.mark.parametrize("current", list(CaseStatus))
@pytest.mark.parametrize("target", list(CaseStatus))
def test_transition_matrix(current, target):
    if target in ALLOWED_TRANSITIONS[current]:
        ensure_transition(current, target)
    else:
        with pytest.raises(ValueError):
            ensure_transition(current, target)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5260250274", True),
        ("5260250275", False),
        ("526025027", False),
        ("52602502744", False),
        ("526025027x", False),
        ("0000000000", False),
        ("５２６０２５０２７４", False),
    ],
)
def test_nip(value, expected):
    assert valid_nip(value) is expected


def test_nip_separators():
    value, _ = normalize("tax_id", " 526-025 02-74 ")
    assert valid_nip(value)


@pytest.mark.parametrize(
    "raw,expected,currency",
    [
        ("12 500,00 PLN", "12500.00", "PLN"),
        ("0.10", "0.10", None),
        ("-500 PLN", "-500.00", "PLN"),
        ("1\u00a0250,50 eur", "1250.50", "EUR"),
    ],
)
def test_money(raw, expected, currency):
    assert normalize_money(raw) == (Decimal(expected), currency)


@pytest.mark.parametrize(
    "raw", ["NaN", "Infinity", "1,2,3", "12 50", "1e9", "1.001", "1000000000000"]
)
def test_bad_money(raw):
    with pytest.raises(ValueError):
        normalize_money(raw)


def test_validation_rules():
    invalid = {
        "customer_email": "nope",
        "tax_id": "1234567890",
        "requested_deadline": date(2020, 1, 1),
        "estimated_value": Decimal("-1"),
        "currency": "XYZ",
        "duplicate": True,
    }
    codes = {i.code for i in ValidationEngine().validate(invalid, today=date(2026, 1, 1))}
    assert codes == {
        "CUSTOMER_REQUIRED",
        "TITLE_REQUIRED",
        "EMAIL_INVALID",
        "NIP_INVALID",
        "DEADLINE_INVALID",
        "VALUE_INVALID",
        "CURRENCY_UNSUPPORTED",
        "DUPLICATE_ATTACHMENT",
    }
    assert (
        ValidationEngine().validate(
            {
                "company_name": "Example",
                "request_title": "Quote",
                "estimated_value": Decimal("0.10"),
                "currency": "PLN",
                "tax_id": "5260250274",
            }
        )
        == []
    )
    assert "CURRENCY_REQUIRED" in {
        i.code for i in ValidationEngine().validate({"estimated_value": Decimal("1")})
    }


@pytest.mark.parametrize(
    "key", ["../secret", "/etc/passwd", "C:/secret", "..\\secret", "", "a/../../secret"]
)
def test_storage_paths(tmp_path, key):
    storage = LocalFilesystemStorage(str(tmp_path))
    with pytest.raises(ValueError):
        storage.get(key)


def test_storage_roundtrip_and_collision(tmp_path):
    storage = LocalFilesystemStorage(str(tmp_path / "nested" / "objects"))
    first, second = storage.put(b"original"), storage.put(b"original")
    assert first != second
    assert storage.get(first) == b"original"
    assert storage.get(second) == b"original"


async def test_provider_contract():
    fields = await DevelopmentExtractionProvider().extract(
        b"Customer: Example\nEstimated value: -2 PLN"
    )
    assert [(f.field_name, f.raw_value) for f in fields] == [
        ("customer_name", "Example"),
        ("estimated_value", "-2 PLN"),
    ]
    with pytest.raises(ValueError):
        await DevelopmentExtractionProvider().extract(b"Customer: A\nCustomer: B")
