from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencies import Service
from app.models.entities import AuditEvent, Case
from app.schemas.cases import CaseCreate
from app.services.serialization import row_json

router = APIRouter()


@router.post("", status_code=201)
async def create_case(data: CaseCreate, service: Service):
    case = await service.create(data.model_dump(exclude_unset=True))
    await service.db.commit()
    return await service.detail(case)


@router.get("")
async def list_cases(
    service: Service, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)
):
    rows = await service.db.scalars(
        select(Case).order_by(Case.created_at.desc(), Case.id).offset(offset).limit(limit)
    )
    return {
        "items": [row_json(row) for row in rows],
        "total": await service.db.scalar(select(func.count()).select_from(Case)),
    }


@router.get("/{case_id}")
async def get_case(case_id: UUID, service: Service):
    return await service.detail(await service.get(case_id))


@router.get("/{case_id}/audit")
async def get_audit(case_id: UUID, service: Service):
    await service.get(case_id)
    return [row_json(row) for row in await service.rows(AuditEvent, case_id)]
