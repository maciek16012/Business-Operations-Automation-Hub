from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.api.dependencies import Service
from app.core.config import settings
from app.models.entities import Attachment
from app.services.errors import WorkflowError

router = APIRouter()


@router.post("/{case_id}")
async def upload(case_id: UUID, service: Service, files: Annotated[list[UploadFile], File()]):
    if not 1 <= len(files) <= 10:
        raise WorkflowError("FILE_COUNT", "Upload between 1 and 10 files", 422)
    incoming = []
    for file in files:
        name = (file.filename or "document.txt").replace("\\", "/").split("/")[-1]
        if not name.lower().endswith(".txt") or file.content_type not in {
            "text/plain",
            "application/octet-stream",
        }:
            raise WorkflowError(
                "FILE_TYPE", "Development provider accepts UTF-8 .txt fixtures only", 415
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
    return Response(
        service.storage.get(attachment.storage_key),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(attachment.original_filename)
            )
        },
    )
