from app.extraction.base import ExtractedValue, ExtractionProvider

LABELS = {
    "customer": "customer_name",
    "email": "customer_email",
    "company": "company_name",
    "nip": "tax_id",
    "title": "request_title",
    "description": "request_description",
    "requested deadline": "requested_deadline",
    "estimated value": "estimated_value",
    "currency": "currency",
}


class DevelopmentExtractionProvider(ExtractionProvider):
    """UTF-8 key: value fixtures only; no business validity decisions."""

    name = "development-fixture"

    async def extract(self, content: bytes) -> list[ExtractedValue]:
        values = []
        seen = set()
        text = content.decode("utf-8-sig")
        if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
            raise ValueError("Document contains unsupported control characters")
        for line in text.splitlines():
            label, separator, raw = line.partition(":")
            field = LABELS.get(label.strip().lower())
            if separator and field:
                if field in seen:
                    raise ValueError(f"Repeated field: {field}")
                seen.add(field)
                values.append(ExtractedValue(field, raw.strip()))
        if not values:
            raise ValueError("No recognized key: value fields in document")
        return values
