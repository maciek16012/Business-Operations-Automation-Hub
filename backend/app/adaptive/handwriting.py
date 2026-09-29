"""Optional provider seam. Default never fabricates handwriting transcriptions."""

from app.adaptive.contracts import Evidence, HandwritingProvider


class UnavailableHandwritingProvider:
    async def recognize(self, image: bytes) -> tuple[str | None, float, str]:
        return None, 0.0, "handwriting-provider-unavailable"


class HandwrittenTableExtractor:
    def __init__(self, provider: HandwritingProvider | None = None):
        self.provider = provider or UnavailableHandwritingProvider()

    async def extract(
        self, evidence: Evidence, crops: dict[tuple[int, int, int], bytes]
    ) -> Evidence:
        for table in evidence.tables:
            for cell in table.cells:
                # Preserve trustworthy native printed headers, but printed OCR guesses
                # are never promoted to handwriting recognition.
                if cell.row == 0 or cell.source == "native-pdf":
                    continue
                image = crops.get((table.page, cell.row, cell.column), b"")
                value, confidence, source = await self.provider.recognize(image)
                cell.value, cell.confidence, cell.source = value, confidence, source
                cell.uncertain = True  # Every handwriting result needs operator confirmation in v1.
        return evidence
