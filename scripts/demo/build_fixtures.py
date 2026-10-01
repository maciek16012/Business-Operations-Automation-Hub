"""Independent, synthetic portfolio documents; never reads evaluation datasets."""

import json
from io import BytesIO
from pathlib import Path

import pymupdf
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "demo/fixtures"
ROWS = [
    ["Name", "Score A", "Score B", "Total", "Maximum", "Percent"],
    ["Team A", "3", "4", "7", "10", "70"],
    ["Team B", "4", "5", "9", "10", "90"],
    ["Team C", "2", "3", "5", "10", "50"],
]
INVOICE = {
    "document_number": "DEMO/2026/001",
    "tax_id": "9900000000",
    "issue_date": "2026-09-30",
    "net_total": "1000.00",
    "vat_total": "230.00",
    "gross_total": "1230.00",
    "currency": "PLN",
}


def page(title):
    out = BytesIO()
    c = Canvas(out, pagesize=(600, 800), invariant=1, pageCompression=1)
    c.setTitle(title)
    c.setAuthor("BOAH synthetic demo generator")
    c.setFillColor(colors.HexColor("#12334A"))
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, 755, title)
    c.setFillColor(colors.HexColor("#496679"))
    c.setFont("Helvetica", 9)
    c.drawString(
        40, 730, "SYNTHETIC DEMO | Fictional company and identifiers | No personal documents"
    )
    c.setFillColor(colors.black)
    return out, c


def finish(out, c, name):
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#496679"))
    c.drawString(40, 35, "BOAH portfolio demonstration - not an evaluation or HOLDOUT sample")
    c.save()
    (OUTPUT / name).write_bytes(out.getvalue())


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for review in [False, True]:
        name = "invoice-review.pdf" if review else "invoice-ready.pdf"
        out, c = page("FAKTURA VAT / INVOICE")
        lines = [
            "Sprzedawca: Northstar Demo Workshops (fictional)",
            "Nabywca: Meadow Demo Operations (fictional)",
            "Numer faktury: DEMO/2026/002" if review else "Numer faktury: DEMO/2026/001",
            "NIP: 9900000001" if review else "NIP: 9900000000",
            "Data wystawienia: 2026-09-30",
            "Netto: 1000,00 PLN",
            "VAT: 230,00 PLN",
            "Brutto: 1230,00 PLN",
            "Waluta: PLN",
            "Opis: Equipment inspection and maintenance scheduling.",
            "Synthetic invoice for a controlled local document operations walkthrough.",
        ]
        c.setFont("Helvetica", 13)
        for i, line in enumerate(lines):
            c.drawString(40, 675 - i * 34, line)
        if review:
            c.setFont("Helvetica", 10)
            c.drawString(
                40, 235, "Demo discrepancy: the tax identifier checksum is intentionally invalid."
            )
            c.drawString(
                40, 215, "Verified fictional identifier for the review exercise: 9900000000."
            )
        finish(out, c, name)
        fields = {
            **INVOICE,
            "document_number": "DEMO/2026/002" if review else INVOICE["document_number"],
        }
        entries.append(
            {"file": name, "type": "INVOICE", "review_exercise": review, "review_values": fields}
        )
    for handwriting in [False, True]:
        name = "handwritten-table-like.pdf" if handwriting else "printed-table.pdf"
        out, c = page(
            "Assessment / handwritten entries" if handwriting else "Assessment score sheet"
        )
        if handwriting:
            c.setFont("Helvetica", 10)
            c.drawString(
                40,
                700,
                "Rasterized italic printing is a handwriting-like proxy, "
                "NOT real human handwriting.",
            )
        x0, y0, width, height = 35, 665, 88, 55
        c.setStrokeColor(colors.HexColor("#78919F"))
        for col in range(7):
            c.line(x0 + col * width, y0, x0 + col * width, y0 - len(ROWS) * height)
        for row in range(len(ROWS) + 1):
            c.line(x0, y0 - row * height, x0 + 6 * width, y0 - row * height)
        for r, row in enumerate(ROWS):
            for col, value in enumerate(row):
                x, y = x0 + col * width + 6, y0 - r * height - 32
                if handwriting and r > 0:
                    with pymupdf.open() as doc:
                        p = doc.new_page(width=80, height=40)
                        p.insert_text(
                            (4, 27), value, fontname="heit", fontsize=14, color=(0.1, 0.2, 0.4)
                        )
                        image = ImageReader(
                            BytesIO(p.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png"))
                        )
                        c.drawImage(image, x - 3, y - 11, width=80, height=40)
                else:
                    c.setFont("Helvetica-Bold" if r == 0 else "Helvetica", 10)
                    c.drawString(x, y, value)
        c.setFont("Helvetica", 11)
        c.drawString(
            40,
            360,
            "Verify cells against the original. Uncertain values stay in review until confirmed.",
        )
        finish(out, c, name)
        entries.append(
            {
                "file": name,
                "type": "HANDWRITTEN_TABLE" if handwriting else "PRINTED_TABLE",
                "review_rows": ROWS,
            }
        )
    out, c = page("Operations memo")
    c.setFont("Helvetica", 13)
    for i, line in enumerate(
        [
            "Northstar Demo Workshops: next month's service coordination.",
            "Please schedule the inspection and reserve a maintenance window.",
            "Confirm the equipment list with the fictional operations team.",
            "This memo has no financial totals or personal information.",
        ]
    ):
        c.drawString(40, 665 - i * 35, line)
    finish(out, c, "generic-document.pdf")
    entries.append({"file": "generic-document.pdf", "type": "GENERIC_DOCUMENT"})
    out = BytesIO()
    c = Canvas(out, pagesize=(600, 800), invariant=1)
    c.setFont("Helvetica", 14)
    c.drawString(40, 730, "Note")
    c.save()
    (OUTPUT / "unknown.pdf").write_bytes(out.getvalue())
    entries.append({"file": "unknown.pdf", "type": "UNKNOWN"})
    (OUTPUT / "blocked-sample.exe.txt").write_text(
        "Harmless plain text. The executable-like filename suffix demonstrates the security "
        "filename policy. No executable code, antivirus signature or malware is present.\n",
        encoding="utf-8",
    )
    entries.append(
        {
            "file": "blocked-sample.exe.txt",
            "type": "BLOCKED",
            "reason": "EXECUTABLE_CONTENT",
            "safe_representation": True,
        }
    )
    (OUTPUT / "manifest.json").write_text(
        json.dumps(
            {"synthetic": True, "independent_of_holdout": True, "fixtures": entries}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print("Created six synthetic PDFs and one harmless security-policy representation.")


if __name__ == "__main__":
    build()
