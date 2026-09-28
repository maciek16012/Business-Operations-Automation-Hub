"""Synthetic invoice dataset. Generate once before DEV; never tune on HOLDOUT."""

import io, json, hashlib, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/ocr"
FONT = Path("C:/Windows/Fonts/arial.ttf")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
pdfmetrics.registerFont(TTFont("Synthetic", str(FONT)))
font = ImageFont.truetype(str(FONT), 30)
styles = [
    "digital",
    "scan",
    "poor",
    "skew",
    "contrast",
    "compression",
    "table",
    "orientation",
]
manifest = []
for split, offset in [("dev", 0), ("holdout", 40)]:
    for i, style in enumerate(styles):
        identifier = f"{split}-{i + 1:02}-{style}"
        folder = OUT / "input" / split
        folder.mkdir(parents=True, exist_ok=True)
        truthdir = OUT / "ground_truth" / split
        truthdir.mkdir(parents=True, exist_ok=True)
        net = 1000 + (i + offset) * 137
        vat = net * 23
        gross = net * 100 + vat
        money = lambda cents: f"{cents // 100} {cents % 100:02}".replace(" ", ",")
        fields = {
            "document_number": f"FV/{100 + i + offset}/2026",
            "tax_id": "5260250274" if i % 2 == 0 else "8567346215",
            "issue_date": f"2026-0{1 + i % 8}-{10 + i:02}",
            "net_total": money(net * 100),
            "vat_total": money(vat),
            "gross_total": money(gross),
            "currency": "PLN",
        }
        lines = [
            "DOKUMENT SYNTETYCZNY - NIE DO OBROTU",
            "Faktura: " + fields["document_number"],
            "NIP: " + fields["tax_id"],
            "Data wystawienia: " + fields["issue_date"],
            "Sprzedawca: Żółć i Źródło - Przykład Sp. z o.o.",
            "Opis: Usługa modernizacji biura, ilość 1",
            "Netto: " + fields["net_total"],
            "VAT: " + fields["vat_total"],
            "Brutto: " + fields["gross_total"],
            "Waluta: PLN",
        ]
        if style == "digital":
            path = folder / (identifier + ".pdf")
            c = canvas.Canvas(str(path), pagesize=(595, 842))
            c.setFont("Synthetic", 13)
            for n, line in enumerate(lines):
                c.drawString(35, 790 - n * 34, line)
            c.save()
        else:
            im = Image.new("RGB", (1400, 1800), "white")
            d = ImageDraw.Draw(im)
            for n, line in enumerate(lines):
                d.text((65, 100 + n * 110), line, font=font, fill="black")
            if style == "table":
                for n in range(6, 11):
                    d.line(
                        (45, 75 + n * 110, 1330, 75 + n * 110),
                        fill=(90, 90, 90),
                        width=2,
                    )
                d.line((45, 735, 45, 1175), fill="gray", width=2)
                d.line((1330, 735, 1330, 1175), fill="gray", width=2)
            if style == "poor":
                im = im.resize((560, 720)).resize((1400, 1800))
                im = im.filter(ImageFilter.GaussianBlur(0.8))
            if style == "skew":
                im = im.rotate(2 if split == "dev" else -2, fillcolor="white")
            if style == "contrast":
                im = ImageEnhance.Contrast(im).enhance(0.18)
            if style == "orientation":
                im = im.rotate(-90, expand=True, fillcolor="white")
            path = folder / (
                identifier + (".jpg" if style == "compression" else ".png")
            )
            im.save(path, **({"quality": 12} if style == "compression" else {}))
        record = {
            "document_id": identifier,
            "source_file": path.relative_to(ROOT).as_posix(),
            "split": split,
            "document_type": "invoice",
            "language": "pl",
            "pages": 1,
            "conditions": [style],
            "full_text": "\n".join(lines),
            "fields": fields,
        }
        (truthdir / (identifier + ".json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest.append(
            {
                "id": identifier,
                "split": split,
                "source_file": record["source_file"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pages": 1,
            }
        )
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Generated 16 synthetic documents / 16 pages: DEV 8, HOLDOUT 8. No OCR run.")
