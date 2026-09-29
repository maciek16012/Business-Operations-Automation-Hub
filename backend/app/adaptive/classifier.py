import re

from app.adaptive.contracts import Classification, Evidence


class LocalClassifier:
    """Conservative content heuristics, not calibrated ML probabilities."""

    def classify(self, evidence: Evidence) -> Classification:
        text = evidence.text.casefold()
        invoice = sum(
            bool(re.search(pattern, text))
            for pattern in (
                r"\b(invoice|faktura)\b",
                r"\b(nip|tax id|vat id)\b",
                r"\b(netto|net total|brutto|gross total)\b",
                r"\b(vat|tax)\b",
            )
        )
        assessment = bool(re.search(r"\b(assessment|score sheet|oceny|punktacja)\b", text))
        if evidence.errors:
            return Classification("UNKNOWN", 0.0, evidence.errors, True)
        if invoice >= 3 and assessment:
            return Classification(
                "UNKNOWN", 0.3, ["Conflicting invoice and assessment signals"], True
            )
        if invoice >= 3:
            return Classification(
                "INVOICE", 0.96, [f"{invoice} independent invoice content signals"], False
            )
        if evidence.tables:
            cells = [c for t in evidence.tables for c in t.cells if c.row > 0]
            missing = sum(c.value is None or c.uncertain for c in cells) / max(1, len(cells))
            handwriting = bool(re.search(r"handwritten|recznie|ręcznie|manual entries", text))
            if handwriting or missing > 0.35:
                return Classification(
                    "HANDWRITTEN_TABLE",
                    0.78,
                    [
                        "Grid detected",
                        "Handwriting hint or unresolved grid entries",
                        "Handwriting likelihood is heuristic; operator must verify",
                    ],
                    True,
                )
            return Classification(
                "PRINTED_TABLE", 0.92, ["Grid detected with readable printed cell evidence"], False
            )
        if invoice:
            return Classification("UNKNOWN", 0.4, ["Incomplete invoice evidence"], True)
        if len(text.strip()) >= 60:
            return Classification(
                "GENERIC_DOCUMENT",
                0.8,
                ["Readable prose without reliable invoice/table signals"],
                False,
            )
        return Classification("UNKNOWN", 0.2, ["Insufficient content or unsupported layout"], True)
