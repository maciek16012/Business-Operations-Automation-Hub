"""Deterministic synthetic M6-only documents. No M3/M4 input is read."""

import argparse
import json
import random
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

TYPES = ["INVOICE", "HANDWRITTEN_TABLE", "PRINTED_TABLE", "GENERIC_DOCUMENT", "UNKNOWN"]
HEADERS = ["Name", "Score A", "Score B", "Total", "Maximum", "Percent"]


def fixture(kind: str, variant: int = 0, seed: int = 61) -> tuple[bytes, dict]:
    rng = random.Random(seed + variant)
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    truth: dict = {"type": kind, "tables": []}
    if kind == "INVOICE":
        text = (
            f"Faktura: M6/{seed}/{variant}\nNIP: 5260250274\nData wystawienia: 2026-01-10\n"
            "Netto: 1000,00\nVAT: 230,00\nBrutto: 1230,00\nWaluta: PLN\n"
            "Synthetic invoice for independent M6 classification evaluation."
        )
        page.insert_text((45, 55), text, fontsize=14)
    elif kind in {"PRINTED_TABLE", "HANDWRITTEN_TABLE"}:
        handwritten = kind == "HANDWRITTEN_TABLE"
        page.insert_text(
            (35, 45),
            "Assessment / handwritten entries" if handwritten else "Assessment score sheet",
            fontsize=16,
        )
        rows = [HEADERS]
        for index in range(3 + variant % 2):
            a, b = rng.randint(1, 5), rng.randint(1, 5)
            rows.append(
                [
                    f"Person {chr(65 + index)}",
                    str(a),
                    str(b),
                    str(a + b),
                    "10",
                    str((a + b) * 10),
                ]
            )
        width, height, x0, y0 = 88, 48, 35, 100
        for col in range(7):
            page.draw_line(
                (x0 + col * width, y0),
                (x0 + col * width, y0 + len(rows) * height),
                width=1,
            )
        for row in range(len(rows) + 1):
            page.draw_line((x0, y0 + row * height), (x0 + 6 * width, y0 + row * height), width=1)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                point = (x0 + c * width + 6, y0 + r * height + 29)
                if handwritten and r > 0:
                    # Rasterized slanted handwriting-like marks, not actual human handwriting.
                    # No searchable text is hidden behind the raster cell image.
                    mini = pymupdf.open()
                    cell = mini.new_page(width=82, height=40)
                    cell.insert_text(
                        (4, 26),
                        value,
                        fontname="heit",
                        fontsize=15,
                        color=(0.1, 0.2, 0.4),
                    )
                    pix = cell.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                    page.insert_image(
                        pymupdf.Rect(point[0] - 3, point[1] - 27, point[0] + 79, point[1] + 13),
                        stream=pix.tobytes("png"),
                    )
                    mini.close()
                else:
                    page.insert_text(point, value, fontsize=10)
        truth["tables"] = [{"rows": rows, "row_count": len(rows), "column_count": 6}]
    elif kind == "GENERIC_DOCUMENT":
        page.insert_text(
            (45, 65),
            "Operations memo\nPlease schedule the equipment inspection next month.\n"
            "This synthetic document describes maintenance arrangements.\n"
            "No financial data or personal information is present.",
            fontsize=13,
        )
    else:
        page.insert_text(
            (45, 65),
            "Note" if variant % 2 == 0 else "Invoice NIP VAT gross total\nAssessment score sheet",
            fontsize=14,
        )
    page.insert_text((45, 760), f"M6 reference {seed}/{variant}", fontsize=8)
    # DEV scan variants intentionally stress raster layout; HOLDOUT uses another seed.
    if variant == 2:
        png = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes("png")
        raster = pymupdf.open()
        target = raster.new_page(width=600, height=800)
        target.insert_image(target.rect, stream=png)
        doc.close()
        doc = raster
    elif variant == 3:
        # Deterministic sparse scan speckles, safe bounded challenge.
        for _ in range(120):
            x, y = rng.uniform(10, 590), rng.uniform(10, 790)
            page.draw_circle((x, y), 0.25, fill=(0.7, 0.7, 0.7))
    if variant == 3:
        image = Image.open(BytesIO(page.get_pixmap().tobytes("png"))).convert("RGB")
        image = image.rotate(1.2, resample=Image.Resampling.BICUBIC, fillcolor="white")
        output = BytesIO()
        image.save(output, format="PNG")
        raster = pymupdf.open()
        target = raster.new_page(width=600, height=800)
        target.insert_image(target.rect, stream=output.getvalue())
        doc.close()
        doc = raster
    for page in doc:
        page.clean_contents()
    data = doc.tobytes(no_new_id=True, deflate=True, garbage=4)
    doc.close()
    return data, truth


def generate(root: Path, split: str):
    seed = 61 if split == "dev" else 7061
    manifest = []
    for kind in TYPES:
        for variant in range(4):
            data, truth = fixture(kind, variant, seed)
            relative = Path(split) / kind.lower() / f"sample-{variant + 1:02}.pdf"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            truth_path = path.with_suffix(".json")
            truth_path.write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
            manifest.append(
                {
                    "document": relative.as_posix(),
                    "truth": truth_path.relative_to(root).as_posix(),
                }
            )
    (root / f"{split}-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "holdout"], required=True)
    parser.add_argument("--root", type=Path, default=Path("datasets/milestone6"))
    args = parser.parse_args()
    generate(args.root, args.split)
