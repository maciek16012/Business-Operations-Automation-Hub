"""Generate the independent Milestone 4 STP DEV/HOLDOUT dataset.

Generation does not execute OCR or evaluate HOLDOUT.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets" / "stp"

FONT_PATH = Path("C:/Windows/Fonts/arial.ttf")
if not FONT_PATH.exists():
    FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

pdfmetrics.registerFont(TTFont("STPSynthetic", str(FONT_PATH)))
IMAGE_FONT = ImageFont.truetype(str(FONT_PATH), 28)

STYLES = [
    "native_clean",
    "native_table",
    "native_multipage",
    "native_sparse",
    "hybrid_correct_native",
    "hybrid_wrong_native",
    "scan_clean",
    "scan_poor",
    "scan_skew",
    "scan_contrast",
    "scan_compression",
    "scan_table",
    "scan_orientation",
    "scan_small_text",
    "scan_noise",
    "scan_partial",
    "multipage_scan",
    "mixed_native_scan",
    "scan_foreign_currency",
    "scan_long_document_number",
]

VALID_NIPS = ("5260250274", "8567346215")


def money(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02}"


def make_fields(index: int, offset: int) -> dict[str, str]:
    net_cents = 100_000 + (index + offset) * 13_700
    vat_cents = net_cents * 23 // 100
    gross_cents = net_cents + vat_cents

    currency = "EUR" if index == 18 else "PLN"
    document_number = (
        f"FV/STP/{2026}/{1000 + index + offset}/LONG-DOCUMENT-NUMBER"
        if index == 19
        else f"FV/STP/{100 + index + offset}/2026"
    )

    return {
        "document_number": document_number,
        "tax_id": VALID_NIPS[index % len(VALID_NIPS)],
        "issue_date": f"2026-{1 + (index % 8):02}-{10 + (index % 15):02}",
        "net_total": money(net_cents),
        "vat_total": money(vat_cents),
        "gross_total": money(gross_cents),
        "currency": currency,
    }


def invoice_lines(fields: dict[str, str], *, extra: bool = True) -> list[str]:
    lines = [
        "DOKUMENT SYNTETYCZNY - NIE DO OBROTU",
        f"Faktura: {fields['document_number']}",
        f"NIP: {fields['tax_id']}",
        f"Data wystawienia: {fields['issue_date']}",
        "Sprzedawca: Żółć i Źródło Przykład Sp. z o.o.",
        "Nabywca: Klient Testowy Sp. z o.o.",
        "Opis: Usługa automatyzacji procesów biznesowych",
        f"Netto: {fields['net_total']}",
        f"VAT: {fields['vat_total']}",
        f"Brutto: {fields['gross_total']}",
        f"Waluta: {fields['currency']}",
    ]
    if extra:
        lines += [
            "Termin płatności: 14 dni",
            "Sposób płatności: przelew",
            "Uwagi: dokument przygotowany wyłącznie do testów Milestone 4 STP.",
        ]
    return lines


def render_invoice_image(
    lines: list[str],
    *,
    table: bool = False,
    small_text: bool = False,
    seed: int = 0,
) -> Image.Image:
    image = Image.new("RGB", (1400, 1800), "white")
    draw = ImageDraw.Draw(image)
    font = (
        ImageFont.truetype(str(FONT_PATH), 20)
        if small_text
        else IMAGE_FONT
    )

    spacing = 95 if small_text else 105
    start_y = 90

    for number, line in enumerate(lines):
        draw.text((65, start_y + number * spacing), line, font=font, fill="black")

    if table:
        top = start_y + 6 * spacing - 25
        bottom = start_y + 11 * spacing + 35
        draw.rectangle((45, top, 1340, bottom), outline=(100, 100, 100), width=2)
        for number in range(7, 11):
            y = start_y + number * spacing - 25
            draw.line((45, y, 1340, y), fill=(100, 100, 100), width=2)

    if seed:
        random.seed(seed)

    return image


def degrade(image: Image.Image, style: str, seed: int) -> Image.Image:
    if style == "scan_poor":
        image = image.resize((600, 770)).resize((1400, 1800))
        image = image.filter(ImageFilter.GaussianBlur(0.9))

    elif style == "scan_skew":
        image = image.rotate(
            2.5 if seed % 2 == 0 else -2.5,
            expand=False,
            fillcolor="white",
        )

    elif style == "scan_contrast":
        image = ImageEnhance.Contrast(image).enhance(0.28)

    elif style == "scan_orientation":
        image = image.rotate(-90, expand=True, fillcolor="white")

    elif style == "scan_noise":
        draw = ImageDraw.Draw(image)
        rng = random.Random(seed)
        for _ in range(7000):
            x = rng.randrange(image.width)
            y = rng.randrange(image.height)
            shade = rng.randrange(120, 230)
            draw.point((x, y), fill=(shade, shade, shade))

    elif style == "scan_partial":
        image = image.crop((0, 0, image.width, 1230))
        background = Image.new("RGB", (1400, 1800), "white")
        background.paste(image, (0, 0))
        image = background

    return image


def save_image(image: Image.Image, path: Path, style: str) -> None:
    if style == "scan_compression":
        path = path.with_suffix(".jpg")
        image.save(path, quality=14, optimize=True)
    else:
        image.save(path)


def draw_native_page(c: canvas.Canvas, lines: list[str], *, sparse: bool = False) -> None:
    c.setFont("STPSynthetic", 13)

    shown = lines[:5] if sparse else lines
    for number, line in enumerate(shown):
        c.drawString(35, 790 - number * 34, line)


def image_reader(image: Image.Image) -> ImageReader:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


def add_invisible_text(c: canvas.Canvas, lines: list[str]) -> None:
    text = c.beginText(35, 790)
    text.setFont("STPSynthetic", 13)
    text.setLeading(34)
    text.setTextRenderMode(3)
    for line in lines:
        text.textLine(line)
    c.drawText(text)


def save_pdf_with_image(
    path: Path,
    image: Image.Image,
    *,
    invisible_lines: list[str] | None = None,
) -> None:
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    c.drawImage(image_reader(image), 0, 0, width=595, height=842)
    if invisible_lines:
        add_invisible_text(c, invisible_lines)
    c.save()


def generate_document(
    *,
    split: str,
    index: int,
    style: str,
    offset: int,
) -> dict:
    identifier = f"{split}-{index + 1:02}-{style}"
    input_dir = OUT / "input" / split
    truth_dir = OUT / "ground_truth" / split
    input_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    fields = make_fields(index, offset)
    lines = invoice_lines(fields)
    seed = 1000 + offset + index

    path: Path
    document_class = "ocr_required"
    challenge_tags: list[str] = []

    if style.startswith("native_"):
        path = input_dir / f"{identifier}.pdf"
        c = canvas.Canvas(str(path), pagesize=(595, 842))

        if style == "native_table":
            draw_native_page(c, lines)
            c.rect(30, 420, 530, 170)
            for y in (455, 490, 525, 560):
                c.line(30, y, 560, y)
            document_class = "native_text"

        elif style == "native_multipage":
            draw_native_page(c, lines)
            c.showPage()
            c.setFont("STPSynthetic", 13)
            c.drawString(35, 790, "Załącznik do dokumentu")
            c.drawString(35, 756, "Dodatkowe informacje biznesowe i warunki płatności.")
            document_class = "native_text"

        elif style == "native_sparse":
            draw_native_page(c, lines, sparse=True)
            document_class = "native_uncertain"
            challenge_tags.append("sparse_embedded_text")

        else:
            draw_native_page(c, lines)
            document_class = "native_text"

        c.save()

    elif style in {"hybrid_correct_native", "hybrid_wrong_native"}:
        path = input_dir / f"{identifier}.pdf"
        image = render_invoice_image(lines, seed=seed)

        if style == "hybrid_correct_native":
            embedded_lines = lines
            challenge_tags.append("hybrid_pdf")
        else:
            wrong_fields = dict(fields)
            wrong_fields["document_number"] = f"FAKE/{9000 + index}/2026"
            wrong_fields["tax_id"] = VALID_NIPS[(index + 1) % len(VALID_NIPS)]

            net_cents = 777_700 + index * 10_000
            vat_cents = net_cents * 23 // 100
            gross_cents = net_cents + vat_cents
            wrong_fields["net_total"] = money(net_cents)
            wrong_fields["vat_total"] = money(vat_cents)
            wrong_fields["gross_total"] = money(gross_cents)

            embedded_lines = invoice_lines(wrong_fields)
            challenge_tags += [
                "hybrid_pdf",
                "misleading_embedded_text",
                "internally_valid_wrong_native_fields",
            ]

        save_pdf_with_image(
            path,
            image,
            invisible_lines=embedded_lines,
        )
        document_class = "hybrid"

    elif style == "multipage_scan":
        path = input_dir / f"{identifier}.pdf"
        image1 = render_invoice_image(lines, seed=seed)
        image2 = render_invoice_image(
            [
                "ZAŁĄCZNIK",
                "Dodatkowe informacje do dokumentu.",
                "Pozycje i opis wykonanej usługi.",
            ],
            seed=seed + 1,
        )
        c = canvas.Canvas(str(path), pagesize=(595, 842))
        c.drawImage(image_reader(image1), 0, 0, width=595, height=842)
        c.showPage()
        c.drawImage(image_reader(image2), 0, 0, width=595, height=842)
        c.save()
        document_class = "ocr_required"
        challenge_tags.append("multipage")

    elif style == "mixed_native_scan":
        path = input_dir / f"{identifier}.pdf"
        c = canvas.Canvas(str(path), pagesize=(595, 842))
        draw_native_page(c, lines)
        c.showPage()
        second = render_invoice_image(
            [
                "ZAŁĄCZNIK SKANOWANY",
                "Druga strona celowo nie posiada embedded text.",
                "Routing powinien rozpoznać dokument mieszany.",
            ],
            seed=seed,
        )
        c.drawImage(image_reader(second), 0, 0, width=595, height=842)
        c.save()
        document_class = "hybrid"
        challenge_tags += ["multipage", "mixed_native_and_scan"]

    else:
        table = style == "scan_table"
        small = style == "scan_small_text"
        image = render_invoice_image(
            lines,
            table=table,
            small_text=small,
            seed=seed,
        )
        image = degrade(image, style, seed)

        suffix = ".jpg" if style == "scan_compression" else ".png"
        path = input_dir / f"{identifier}{suffix}"
        save_image(image, path, style)
        document_class = "ocr_required"

        if style in {
            "scan_poor",
            "scan_skew",
            "scan_contrast",
            "scan_compression",
            "scan_orientation",
            "scan_noise",
            "scan_partial",
        }:
            challenge_tags.append(style)

    record = {
        "document_id": identifier,
        "source_file": path.relative_to(ROOT).as_posix(),
        "split": split,
        "document_type": "invoice",
        "document_class": document_class,
        "language": "pl",
        "conditions": [style],
        "challenge_tags": challenge_tags,
        "fields": fields,
        "full_text": "\n".join(lines),
    }

    (truth_dir / f"{identifier}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "id": identifier,
        "split": split,
        "style": style,
        "document_class": document_class,
        "source_file": record["source_file"],
        "ground_truth_file": (
            truth_dir / f"{identifier}.json"
        ).relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "challenge_tags": challenge_tags,
    }


def main() -> None:
    manifest: list[dict] = []

    for split, offset in (("dev", 0), ("holdout", 100)):
        for index, style in enumerate(STYLES):
            manifest.append(
                generate_document(
                    split=split,
                    index=index,
                    style=style,
                    offset=offset,
                )
            )

    manifest_path = OUT / "manifests" / "dataset.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "Generated 40 independent M4 STP documents: "
        "DEV 20, HOLDOUT 20. No OCR or HOLDOUT evaluation executed."
    )


if __name__ == "__main__":
    main()
