"""Only explicit header semantics activate formulas. Never fill missing values."""

import re
from decimal import Decimal, InvalidOperation


def number(value: str | None) -> Decimal | None:
    try:
        result = Decimal((value or "").strip().removesuffix("%").replace(",", "."))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def validate_table(rows: list[list[str | None]]) -> list[dict]:
    issues = []
    if len(rows) < 2:
        return [{"code": "TABLE_EMPTY", "message": "Table needs a header and data row"}]
    headers = [(v or "").strip().casefold() for v in rows[0]]
    components = [
        i for i, h in enumerate(headers) if re.fullmatch(r"(score|points|punkty)\s+\w+", h)
    ]
    total = next((i for i, h in enumerate(headers) if h in {"total", "sum", "suma", "razem"}), None)
    maximum = next((i for i, h in enumerate(headers) if h in {"maximum", "max", "possible"}), None)
    percent = next(
        (i for i, h in enumerate(headers) if h in {"percent", "percentage", "%", "procent"}), None
    )
    numeric = set(components + [i for i in (total, maximum, percent) if i is not None])
    for r, row in enumerate(rows[1:], 1):
        values = {i: number(row[i]) for i in numeric}

        def issue(code, column, message, row_number=r):
            issues.append({"code": code, "row": row_number, "column": column, "message": message})

        for col, value in values.items():
            if value is None:
                issue("NUMERIC_UNRESOLVED", col, "Numeric value is missing or invalid")
            elif value < 0:
                issue("NEGATIVE_SCORE", col, "Score must be nonnegative")
        total_value = values.get(total) if total is not None else None
        max_value = values.get(maximum) if maximum is not None else None
        percent_value = values.get(percent) if percent is not None else None
        component_values = [values[i] for i in components if values[i] is not None]
        if total is not None and len(components) >= 2 and len(component_values) == len(components):
            expected_sum = sum((v for v in component_values if v is not None), Decimal(0))
            if total_value is not None and total_value != expected_sum:
                issue("ROW_TOTAL_CONFLICT", total, "Total differs from explicitly labelled scores")
        if percent is not None and percent_value is not None:
            if not 0 <= percent_value <= 100:
                issue("PERCENT_RANGE", percent, "Percentage must be between 0 and 100")
            if total_value is not None and max_value is not None:
                if max_value <= 0:
                    issue("MAXIMUM_INVALID", maximum, "Maximum must be positive")
                elif abs(percent_value - total_value / max_value * 100) > Decimal("0.51"):
                    issue("PERCENT_CONFLICT", percent, "Percentage contradicts total / maximum")
        if (row[0] or "").strip().casefold() in {"total", "totals", "suma"}:
            for col in numeric:
                previous = [number(previous[col]) for previous in rows[1:r]]
                if previous and all(v is not None for v in previous) and values[col] is not None:
                    if col != percent and values[col] != sum(
                        (v for v in previous if v is not None), Decimal(0)
                    ):
                        issue(
                            "COLUMN_TOTAL_CONFLICT", col, "Column total contradicts preceding rows"
                        )
    return issues
