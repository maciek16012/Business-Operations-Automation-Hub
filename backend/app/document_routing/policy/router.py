"""Routing policy for Milestone 4 straight-through processing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from app.core.config import settings
from app.document_routing.preflight.native_pdf import (
    NativePDFTextResult,
    NativeTextDecision,
    assess_native_text,
)


class Route(StrEnum):
    NATIVE_TEXT = "NATIVE_TEXT"
    PRIMARY_OCR = "PRIMARY_OCR"
    DUAL_OCR = "DUAL_OCR"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class RoutingDecision(BaseModel):
    route: Route
    reason: str
    native_text: NativeTextDecision | None = None


def decide_route(
    *,
    filename: str,
    mime_type: str,
    native_pdf_result: NativePDFTextResult | None = None,
) -> RoutingDecision:
    mime = mime_type.split(";", 1)[0].strip().lower()
    name = filename.lower()

    is_pdf = name.endswith(".pdf") or mime == "application/pdf"
    is_image = (
        name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff"))
        or mime in {"image/png", "image/jpeg", "image/tiff"}
    )

    if is_pdf and native_pdf_result is not None:
        native_decision = assess_native_text(
            native_pdf_result,
            min_chars_per_page=settings.stp_native_min_chars_per_page,
            min_alnum_ratio=settings.stp_native_min_alnum_ratio,
            min_printable_ratio=settings.stp_native_min_printable_ratio,
            min_text_page_ratio=settings.stp_native_min_text_page_ratio,
            max_image_area_ratio=settings.stp_native_max_image_area_ratio,
        )

        if native_decision.trusted:
            return RoutingDecision(
                route=Route.NATIVE_TEXT,
                reason="embedded PDF text passed the configured quality gate",
                native_text=native_decision,
            )

        return RoutingDecision(
            route=Route.PRIMARY_OCR,
            reason="PDF native text is absent or below the configured quality gate",
            native_text=native_decision,
        )

    if is_image:
        return RoutingDecision(
            route=Route.PRIMARY_OCR,
            reason="image document requires OCR; primary OCR runs before selective dual escalation",
        )

    return RoutingDecision(
        route=Route.HUMAN_REVIEW,
        reason="document type is outside the automated STP routing policy",
    )



