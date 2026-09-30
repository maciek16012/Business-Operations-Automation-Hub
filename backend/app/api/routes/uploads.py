from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.api.dependencies import Service
from app.core.config import settings
from app.models.company import RetentionDeletion
from app.models.entities import Attachment
from app.models.operations import AttachmentSecurityScan
from app.ocr.pipeline import supported
from app.services.errors import WorkflowError

router = APIRouter()


@router.post("/{case_id}")
async def upload(case_id: UUID, service: Service, files: Annotated[list[UploadFile], File()]):
    if not 1 <= len(files) <= 10:
        raise WorkflowError("FILE_COUNT", "Upload between 1 and 10 files", 422)
    incoming = []
    for file in files:
        name = (file.filename or "document.txt").replace("\\", "/").split("/")[-1]
        if (
            not settings.security_preflight_enabled
            and not supported(name, file.content_type or "")
            and (
                not name.lower().endswith(".txt")
                or file.content_type
                not in {
                    "text/plain",
                    "application/octet-stream",
                }
            )
        ):
            raise WorkflowError(
                "FILE_TYPE",
                "Accepts UTF-8 .txt; enabled dual OCR also accepts PDF/PNG/JPEG/TIFF",
                415,
            )
        content = await file.read(settings.max_upload_bytes + 1)
        await file.close()
        if not content or len(content) > settings.max_upload_bytes:
            raise WorkflowError("FILE_SIZE", "Files must be nonempty and at most 5 MiB", 413)
        if len(name) > 512 or any(ord(char) < 32 for char in name):
            raise WorkflowError("FILENAME_INVALID", "Invalid filename", 422)
        incoming.append((name, file.content_type or "text/plain", content))
    case = await service.get(case_id, lock=True)
    await service.upload(case, incoming)
    await service.db.commit()
    return await service.detail(case)


@router.get("/{case_id}/{attachment_id}")
async def download(case_id: UUID, attachment_id: UUID, service: Service):
    attachment = await service.db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.case_id == case_id)
    )
    if attachment is None:
        raise WorkflowError("NOT_FOUND", "Attachment not found", 404)
    if settings.security_preflight_enabled:
        scan = await service.db.scalar(
            select(AttachmentSecurityScan)
            .where(AttachmentSecurityScan.attachment_id == attachment.id)
            .order_by(AttachmentSecurityScan.created_at.desc())
            .limit(1)
        )
        if scan is None or scan.verdict != "SAFE":
            raise WorkflowError(
                "ATTACHMENT_QUARANTINED", "Unsafe or unscanned download blocked", 403
            )
    if await service.db.get(RetentionDeletion, attachment.storage_key):
        raise WorkflowError("ARTIFACT_RETAINED", "Stored artifact removed by retention policy", 410)
    return Response(
        service.storage.get(attachment.storage_key),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(attachment.original_filename)
            )
        },
    )
