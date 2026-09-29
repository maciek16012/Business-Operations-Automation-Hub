"""Bounded native and raster grid detection. Called only after persisted SAFE."""

import asyncio

import pymupdf

from app.adaptive.contracts import Cell, Evidence, Table
from app.core.config import settings
from app.ocr.pipeline import infer


def open_document(content: bytes):
    doc = pymupdf.open(stream=content)
    if not doc.is_pdf:
        converted = doc.convert_to_pdf()
        doc.close()
        doc = pymupdf.open(stream=converted, filetype="pdf")
    if not 1 <= len(doc) <= 10:
        doc.close()
        raise ValueError("Document page limit: 10")
    return doc


def clusters(values: list[int]) -> list[float]:
    groups: list[list[int]] = []
    for value in values:
        if groups and value - groups[-1][-1] <= 3:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(g) / len(g) for g in groups]


class TableDetector:
    def native(self, page, number: int) -> list[Table]:
        result = []
        for table in page.find_tables().tables[:8]:
            if table.row_count * table.col_count > 1000:
                raise ValueError("Table cell limit: 1000")
            values = table.extract()
            cells = []
            irregular = False
            for row, geometry in enumerate(table.rows):
                for col, box in enumerate(geometry.cells):
                    value = values[row][col]
                    irregular |= box is None
                    cells.append(
                        Cell(
                            row,
                            col,
                            value or None,
                            list(box) if box else None,
                            0.99 if value else 0,
                            "native-pdf" if value else "unresolved",
                            not bool(value) or box is None,
                        )
                    )
            result.append(
                Table(
                    number,
                    table.row_count,
                    table.col_count,
                    list(table.bbox),
                    cells,
                    "pymupdf-grid",
                    irregular,
                )
            )
        return result

    def raster(self, page, number: int) -> list[Table]:
        # Coordinates remain PDF points, independent of OCR raster scaling.
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY)
        width, height = pix.width, pix.height
        # DEV raster fixtures show thin antialiased rules above luminance 110.
        mask = pix.samples.translate(bytes(1 if x < 200 else 0 for x in range(256)))
        ys = clusters(
            [y for y in range(height) if sum(mask[y * width : (y + 1) * width]) > width * 0.45]
        )
        xs = clusters([x for x in range(width) if sum(mask[x::width]) > height * 0.18])
        if not 3 <= len(xs) <= 21 or not 3 <= len(ys) <= 101:
            return []
        cells = [
            Cell(r, c, None, [xs[c], ys[r], xs[c + 1], ys[r + 1]])
            for r in range(len(ys) - 1)
            for c in range(len(xs) - 1)
        ]
        return [
            Table(
                number,
                len(ys) - 1,
                len(xs) - 1,
                [xs[0], ys[0], xs[-1], ys[-1]],
                cells,
                "raster-projection-grid",
            )
        ]


class LayoutDetector:
    def native(self, content: bytes, mime: str) -> Evidence:
        if mime == "text/plain":
            return Evidence(text=content.decode("utf-8-sig"), pages=[{"page": 1, "source": "text"}])
        evidence = Evidence()
        with open_document(content) as doc:
            for number, page in enumerate(doc, 1):
                if page.rect.width * page.rect.height > 4_000_000:
                    raise ValueError("Page geometry limit")
                text = page.get_text()
                evidence.text += text + "\n"
                tables = TableDetector().native(page, number)
                if not tables:
                    tables = TableDetector().raster(page, number)
                evidence.tables.extend(tables)
                if sum(len(t.cells) for t in evidence.tables) > 1000:
                    raise ValueError("Document cell limit: 1000")
                evidence.pages.append(
                    {
                        "page": number,
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "native_chars": len(text),
                        "tables": len(tables),
                    }
                )
        return evidence

    async def detect(self, content: bytes, mime: str) -> Evidence:
        try:
            evidence = await asyncio.to_thread(self.native, content, mime)
        except Exception as exc:
            return Evidence(errors=["Layout unavailable: " + type(exc).__name__])
        # Native PDFs retain their native evidence. Raster pages use independent
        # baseline OCR geometry; the frozen M4 orientation configuration is untouched.
        if mime != "text/plain" and any(p.get("native_chars", 0) < 40 for p in evidence.pages):
            result = await infer(
                settings.ocr_tesseract_url,
                "tesseract",
                "m6-layout",
                content,
                "baseline",
                timeout=45,
            )
            evidence.artifacts["layout_ocr"] = result.model_dump()
            if result.error:
                evidence.errors.append("Layout OCR unavailable: " + result.error)
            else:
                evidence.text += "\n" + result.raw_text
                CellExtractor().attach(evidence.tables, result.pages, evidence.pages)
        return evidence


class CellExtractor:
    def attach(self, tables: list[Table], ocr_pages: list[dict], pages: list[dict]) -> None:
        for table in tables:
            if table.source != "raster-projection-grid":
                continue
            ocr = next((p for p in ocr_pages if p["page"] == table.page), None)
            if not ocr:
                continue
            geometry = pages[table.page - 1]
            sx, sy = geometry["width"] / ocr["width"], geometry["height"] / ocr["height"]
            for cell in table.cells:
                if not cell.bbox:
                    continue
                words = []
                for word in ocr.get("lines", []):
                    box = word.get("coordinates")
                    if not box or len(box) != 4:
                        continue
                    x, y, w, h = box
                    cx, cy = (x + w / 2) * sx, (y + h / 2) * sy
                    if cell.bbox[0] < cx < cell.bbox[2] and cell.bbox[1] < cy < cell.bbox[3]:
                        words.append(word)
                if words:
                    cell.value = " ".join(w["text"] for w in words)
                    cell.confidence = min(float(w.get("confidence") or 0) for w in words)
                    cell.source = "tesseract-layout"
                    cell.uncertain = cell.confidence < 0.9
