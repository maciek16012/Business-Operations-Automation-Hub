"""Independent CPU OCR worker. No access to BOAH DB, truth, or peer output."""

import base64, csv, io, os, subprocess, tempfile, time, threading
from importlib.metadata import version
from pathlib import Path
from typing import Literal
import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pypdfium2 as pdfium
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()
ENGINE = os.environ["OCR_ENGINE"]
LOCK = threading.Lock()
MODEL = None


class Input(BaseModel):
    document_id: str = Field(max_length=128)
    content_base64: str = Field(max_length=6990508)
    preprocessing: Literal[
        "baseline",
        "grayscale",
        "contrast",
        "threshold",
        "denoise",
        "deskew",
        "dpi",
        "orientation",
    ] = "baseline"


def images(content):
    if content.startswith(b"%PDF"):
        doc = pdfium.PdfDocument(content)
        if not 1 <= len(doc) <= 10:
            raise ValueError("PDF page limit: 10")
        try:
            pages = []
            for i in range(len(doc)):
                page = doc[i]
                width, height = page.get_size()
                if width * height * (200 / 72) ** 2 > 20_000_000:
                    raise ValueError("PDF pixel limit")
                pages.append(page.render(scale=200 / 72).to_pil().convert("RGB"))
            return pages
        finally:
            doc.close()
    image = Image.open(io.BytesIO(content))
    if image.width * image.height > 20_000_000:
        raise ValueError("Image pixel limit")
    pages = []
    if getattr(image, "n_frames", 1) > 10:
        raise ValueError("Image page limit: 10")
    for i in range(getattr(image, "n_frames", 1)):
        image.seek(i)
        if image.width * image.height > 20_000_000:
            raise ValueError("Image pixel limit")
        pages.append(ImageOps.exif_transpose(image).convert("RGB").copy())
    return pages


def preprocess(im, profile):
    if profile == "baseline":
        return im
    im = ImageOps.grayscale(im)
    if profile in ("contrast", "deskew", "threshold", "denoise", "dpi", "orientation"):
        im = ImageOps.autocontrast(im)
    if profile == "denoise":
        im = im.filter(ImageFilter.MedianFilter(3))
    if profile == "threshold":
        import cv2

        im = Image.fromarray(
            cv2.threshold(np.array(im), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        )
    if profile == "deskew":
        # Small-angle projection search: preprocessing only, no OCR/ground truth.
        angles = [-3, -2, -1, 0, 1, 2, 3]

        def score(a):
            x = np.array(im.rotate(a, fillcolor=255)) < 160
            return float(np.var(x.sum(axis=1)))

        im = im.rotate(max(angles, key=score), fillcolor=255)
    if profile == "dpi" and im.width < 1600:
        im = im.resize(
            (1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS
        )
    if profile == "orientation":
        # Landscape business pages: documented limited geometric baseline.
        if im.width > im.height:
            im = im.rotate(90, expand=True, fillcolor=255)
    return im.convert("RGB")


@app.get("/health")
def health():
    return {"status": "ok", "engine": ENGINE}


@app.post("/ocr")
def ocr(data: Input):
    global MODEL
    start = time.perf_counter()
    pages = []
    raw = []
    ver = (
        subprocess.check_output(["tesseract", "--version"], text=True).splitlines()[0]
        if ENGINE == "tesseract"
        else version("paddleocr")
    )
    result = dict(
        provider=ENGINE,
        provider_version=ver,
        document_id=data.document_id,
        raw_text="",
        pages=[],
        provider_confidence=None,
        processing_time_ms=0,
        error=None,
        raw_provider_output=None,
    )
    try:
        content = base64.b64decode(data.content_base64, validate=True)
        with LOCK:
            ims = images(content)
            if ENGINE == "paddle" and MODEL is None:
                from paddleocr import PaddleOCR

                MODEL = PaddleOCR(
                    lang="pl",
                    ocr_version="PP-OCRv5",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    device="cpu",
                    cpu_threads=2,
                    enable_mkldnn=False,
                )
            for number, im in enumerate(ims, 1):
                im = preprocess(im, data.preprocessing)
                lines = []
                if ENGINE == "tesseract":
                    with tempfile.TemporaryDirectory() as td:
                        path = Path(td) / "page.png"
                        im.save(path)
                        tsv = subprocess.check_output(
                            [
                                "tesseract",
                                str(path),
                                "stdout",
                                "-l",
                                "pol+eng",
                                "--psm",
                                "6",
                                "tsv",
                            ],
                            text=True,
                            timeout=60,
                            stderr=subprocess.DEVNULL,
                        )
                    raw.append(tsv)
                    words = []
                    for row in csv.DictReader(
                        io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE
                    ):
                        if row.get("text", "").strip():
                            words.append(
                                dict(
                                    text=row["text"],
                                    confidence=float(row["conf"]) / 100,
                                    coordinates=[
                                        int(row[k])
                                        for k in ("left", "top", "width", "height")
                                    ],
                                    line=[
                                        row["block_num"],
                                        row["par_num"],
                                        row["line_num"],
                                    ],
                                )
                            )
                    grouped = {}
                    for w in words:
                        grouped.setdefault(tuple(w["line"]), []).append(w["text"])
                    text = "\n".join(" ".join(v) for v in grouped.values())
                    lines = words
                else:
                    outputs = list(MODEL.predict(np.array(im)))
                    obj = outputs[0].json
                    if isinstance(obj, str):
                        import json

                        obj = json.loads(obj)
                    raw.append(obj)
                    rec = obj.get("res", obj)
                    texts = rec.get("rec_texts", [])
                    scores = rec.get("rec_scores", [])
                    polys = rec.get("rec_polys", [])
                    lines = [
                        dict(
                            text=t,
                            confidence=float(scores[i]) if i < len(scores) else None,
                            coordinates=polys[i] if i < len(polys) else None,
                        )
                        for i, t in enumerate(texts)
                    ]
                    text = "\n".join(texts)
                pages.append(
                    dict(
                        page=number,
                        width=im.width,
                        height=im.height,
                        text=text,
                        lines=lines,
                    )
                )
        result["pages"] = pages
        result["raw_text"] = "\n".join(p["text"] for p in pages)
        scores = [
            l["confidence"]
            for p in pages
            for l in p["lines"]
            if l.get("confidence") is not None
        ]
        result["provider_confidence"] = sum(scores) / len(scores) if scores else None
        result["raw_provider_output"] = raw
        if not result["raw_text"].strip():
            result["error"] = "NO_TEXT"
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)[:300]
        result["raw_provider_output"] = raw
    result["processing_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
    return result
