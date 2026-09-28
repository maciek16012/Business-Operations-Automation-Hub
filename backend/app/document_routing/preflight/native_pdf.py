"""Native PDF text extraction and quality evidence for Milestone 4 routing."""

from __future__ import annotations

import math
import re

import pymupdf
from pydantic import BaseModel, Field


class NativePDFTextResult(BaseModel):
    page_count: int = Field(ge=0)
    text: str
    char_count: int = Field(ge=0)
    alnum_count: int = Field(ge=0)
    printable_ratio: float = Field(ge=0.0, le=1.0)
    alnum_ratio: float = Field(ge=0.0, le=1.0)
    chars_per_page: float = Field(ge=0.0)
    pages_with_text: int = Field(ge=0)
    text_page_ratio: float = Field(ge=0.0, le=1.0)
    max_image_area_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    page_max_image_area_ratios: list[float] = Field(default_factory=list)
    extraction_error: str | None = None


class NativeTextDecision(BaseModel):
    trusted: bool
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str]


def _clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _page_max_image_area_ratio(page: pymupdf.Page) -> float:
    page_area = page.rect.width * page.rect.height
    if page_area <= 0:
        return 0.0

    ratios: list[float] = []

    for image in page.get_images(full=True):
        xref = image[0]
        for rect in page.get_image_rects(xref):
            ratio = (rect.width * rect.height) / page_area
            ratios.append(min(max(ratio, 0.0), 1.0))

    return max(ratios, default=0.0)


def extract_native_pdf_text(content: bytes) -> NativePDFTextResult:
    """Extract embedded text and structural evidence from a PDF without OCR."""
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        return NativePDFTextResult(
            page_count=0,
            text="",
            char_count=0,
            alnum_count=0,
            printable_ratio=0.0,
            alnum_ratio=0.0,
            chars_per_page=0.0,
            pages_with_text=0,
            text_page_ratio=0.0,
            max_image_area_ratio=0.0,
            page_max_image_area_ratios=[],
            extraction_error=type(exc).__name__,
        )

    try:
        page_texts: list[str] = []
        page_image_ratios: list[float] = []
        pages_with_text = 0

        for page_index in range(len(document)):
            page = document.load_page(page_index)
            page_text = _clean_text(page.get_text("text") or "")
            page_texts.append(page_text)
            page_image_ratios.append(_page_max_image_area_ratio(page))

            if any(ch.isalnum() for ch in page_text):
                pages_with_text += 1

        text = "\n\n".join(part for part in page_texts if part)
        char_count = len(text)
        alnum_count = sum(ch.isalnum() for ch in text)
        printable_count = sum(
            ch.isprintable() or ch in "\n\r\t"
            for ch in text
        )
        page_count = len(document)

        return NativePDFTextResult(
            page_count=page_count,
            text=text,
            char_count=char_count,
            alnum_count=alnum_count,
            printable_ratio=(printable_count / char_count) if char_count else 0.0,
            alnum_ratio=(alnum_count / char_count) if char_count else 0.0,
            chars_per_page=(char_count / page_count) if page_count else 0.0,
            pages_with_text=pages_with_text,
            text_page_ratio=(pages_with_text / page_count) if page_count else 0.0,
            max_image_area_ratio=max(page_image_ratios, default=0.0),
            page_max_image_area_ratios=page_image_ratios,
        )
    finally:
        document.close()


def assess_native_text(
    result: NativePDFTextResult,
    *,
    min_chars_per_page: float,
    min_alnum_ratio: float,
    min_printable_ratio: float,
    min_text_page_ratio: float,
    max_image_area_ratio: float = 1.0,
) -> NativeTextDecision:
    """
    Evaluate native text using externally supplied thresholds.

    Thresholds are intentionally not fixed here so Milestone 4 can calibrate
    them on DEV without modifying the extraction implementation.
    """
    reasons: list[str] = []

    if result.extraction_error:
        return NativeTextDecision(
            trusted=False,
            score=0.0,
            reasons=[f"native extraction failed: {result.extraction_error}"],
        )

    checks = {
        "chars_per_page": result.chars_per_page >= min_chars_per_page,
        "alnum_ratio": result.alnum_ratio >= min_alnum_ratio,
        "printable_ratio": result.printable_ratio >= min_printable_ratio,
        "text_page_ratio": result.text_page_ratio >= min_text_page_ratio,
        "image_area_ratio": result.max_image_area_ratio <= max_image_area_ratio,
    }

    if not checks["chars_per_page"]:
        reasons.append("too little embedded text")
    if not checks["alnum_ratio"]:
        reasons.append("embedded text has low alphanumeric density")
    if not checks["printable_ratio"]:
        reasons.append("embedded text contains too many non-printable characters")
    if not checks["text_page_ratio"]:
        reasons.append("too few pages contain usable embedded text")
    if not checks["image_area_ratio"]:
        reasons.append("large raster image makes embedded PDF text untrusted")

    score = sum(1.0 for passed in checks.values() if passed) / len(checks)

    if not math.isfinite(score):
        score = 0.0

    return NativeTextDecision(
        trusted=all(checks.values()),
        score=score,
        reasons=reasons or ["native text quality gate passed"],
    )



