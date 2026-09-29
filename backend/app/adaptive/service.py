from dataclasses import asdict
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.adaptive.classifier import LocalClassifier
from app.adaptive.handwriting import HandwrittenTableExtractor
from app.adaptive.layout import LayoutDetector
from app.adaptive.validation import validate_table
from app.models.documents import DocumentAnalysis, DocumentCell, DocumentTable
from app.models.entities import Attachment, Case, ValidationIssue
from app.models.operations import AttachmentSecurityScan
from app.services.errors import WorkflowError
from app.services.serialization import row_json

if TYPE_CHECKING:
    from app.services.cases import CaseService


async def assert_safe(service: "CaseService", attachment_id) -> AttachmentSecurityScan:
    scan = await service.db.scalar(
        select(AttachmentSecurityScan)
        .where(AttachmentSecurityScan.attachment_id == attachment_id)
        .order_by(AttachmentSecurityScan.created_at.desc())
        .limit(1)
    )
    if scan is None or scan.verdict != "SAFE":
        raise WorkflowError(
            "SECURITY_REQUIRED", "Persisted SAFE scan required before document analysis"
        )

    return scan


async def process_safe(
    service: "CaseService", case: Case, attachment: Attachment, content: bytes
) -> bool:
    scan = await assert_safe(service, attachment.id)
    service.audit(case, "DOCUMENT_CLASSIFICATION_STARTED", {"attachment_id": str(attachment.id)})
    evidence = await LayoutDetector().detect(
        content, scan.detected_mime or attachment.mime_type or ""
    )
    classification = LocalClassifier().classify(evidence)
    invoice = classification.document_type == "INVOICE"
    strategy = (
        "existing-m4-invoice"
        if invoice
        else {
            "HANDWRITTEN_TABLE": "handwriting-table-review-v1",
            "PRINTED_TABLE": "layout-table-v1",
            "GENERIC_DOCUMENT": "generic-text-review-v1",
            "UNKNOWN": "unclassified-review-v1",
        }[classification.document_type]
    )
    document = DocumentAnalysis(
        case_id=case.id,
        attachment_id=attachment.id,
        document_type=classification.document_type,
        confidence=classification.confidence,
        classifier=classification.classifier,
        reasons=classification.reasons,
        pages=evidence.pages,
        raw_text=evidence.text,
        artifacts=evidence.artifacts,
        strategy=strategy,
        review_required=classification.review_required or not invoice,
    )
    service.db.add(document)
    await service.db.flush()
    service.audit(
        case, "DOCUMENT_CLASSIFIED", {"document_id": str(document.id), **asdict(classification)}
    )
    if classification.review_required:
        service.audit(case, "DOCUMENT_CLASSIFICATION_UNCERTAIN", {"document_id": str(document.id)})
    service.audit(
        case, "ADAPTIVE_EXTRACTION_STARTED", {"document_id": str(document.id), "strategy": strategy}
    )
    if classification.document_type == "HANDWRITTEN_TABLE":
        evidence = await HandwrittenTableExtractor().extract(evidence, {})
    if not invoice:
        for table in evidence.tables:
            stored = DocumentTable(
                document_id=document.id,
                page=table.page,
                row_count=table.rows,
                column_count=table.columns,
                bbox=table.bbox,
                source=table.source,
                irregular=table.irregular,
            )
            service.db.add(stored)
            await service.db.flush()
            for cell in table.cells:
                service.db.add(
                    DocumentCell(
                        table_id=stored.id,
                        row=cell.row,
                        column=cell.column,
                        raw_value=cell.value,
                        confidence=cell.confidence,
                        bbox=cell.bbox,
                        source=cell.source,
                        uncertain=cell.uncertain,
                    )
                )
    if document.review_required:
        service.db.add(
            ValidationIssue(
                case_id=case.id,
                code="ADAPTIVE_REVIEW_REQUIRED",
                severity="ERROR",
                field_name=f"attachment:{attachment.id}",
                message=f"{classification.document_type}: verify classification and document/cells",
            )
        )
        service.audit(
            case, "ADAPTIVE_EXTRACTION_REVIEW_REQUIRED", {"document_id": str(document.id)}
        )
    if not invoice:
        service.audit(
            case,
            "ADAPTIVE_EXTRACTION_COMPLETED",
            {
                "document_id": str(document.id),
                "table_count": len(evidence.tables),
                "review_required": True,
            },
        )
    await service.db.flush()
    return not invoice


async def document_json(service: "CaseService", document: DocumentAnalysis) -> dict:
    result = row_json(document)
    result["tables"] = []
    for table in await service.db.scalars(
        select(DocumentTable)
        .where(DocumentTable.document_id == document.id)
        .order_by(DocumentTable.page, DocumentTable.id)
    ):
        cells = list(
            await service.db.scalars(
                select(DocumentCell)
                .where(DocumentCell.table_id == table.id)
                .order_by(DocumentCell.row, DocumentCell.column)
            )
        )
        rows: list[list[str | None]] = [
            [None for _ in range(table.column_count)] for _ in range(table.row_count)
        ]
        for cell in cells:
            rows[cell.row][cell.column] = (
                cell.corrected_value if cell.corrected_value is not None else cell.raw_value
            )
        result["tables"].append(
            {
                **row_json(table),
                "cells": [row_json(c) for c in cells],
                "issues": validate_table(rows),
            }
        )
    return result
