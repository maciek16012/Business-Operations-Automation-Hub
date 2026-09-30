from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.dependencies import Service
from app.core.config import settings
from app.models.company import RetentionDeletion
from app.models.entities import Export
from app.services.errors import WorkflowError
from app.services.exports import MIME, ExportService

router = APIRouter()


@router.post("/{case_id}/{kind}", status_code=201)
async def generate(case_id: UUID, kind: str, service: Service):
    case = await service.get(case_id, lock=True)
    artifact, content = await ExportService(service).generate(case, kind)
    await service.db.commit()
    return Response(
        content,
        status_code=201,
        media_type=MIME[kind],
        headers={
            "Content-Disposition": f'attachment; filename="{case.public_id}.{kind}"',
            "Location": f"{settings.api_v1_prefix}/exports/{artifact.id}",
            "X-Export-ID": str(artifact.id),
        },
    )


@router.get("/{export_id}")
async def fetch(export_id: UUID, service: Service):
    artifact = await service.db.get(Export, export_id)
    if artifact is None or not artifact.storage_key:
        raise WorkflowError("NOT_FOUND", "Export not found", 404)
    if await service.db.get(RetentionDeletion, artifact.storage_key):
        raise WorkflowError("ARTIFACT_RETAINED", "Stored artifact removed by retention policy", 410)
    return Response(
        service.storage.get(artifact.storage_key),
        media_type=MIME[artifact.export_type],
        headers={
            "Content-Disposition": (
                f'attachment; filename="export-{artifact.id}.{artifact.export_type}"'
            )
        },
    )
