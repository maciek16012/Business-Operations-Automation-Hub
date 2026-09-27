from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import Service
from app.schemas.cases import Decision, ReviewData

router = APIRouter()


@router.patch("/{case_id}")
async def correct(case_id: UUID, data: ReviewData, service: Service):
    case = await service.get(case_id, lock=True)
    await service.correct(case, data.model_dump(exclude_unset=True))
    await service.db.commit()
    return await service.detail(case)


@router.post("/{case_id}/validate")
async def validate(case_id: UUID, service: Service):
    case = await service.get(case_id, lock=True)
    await service.revalidate(case)
    await service.db.commit()
    return await service.detail(case)


@router.post("/{case_id}/approve")
async def approve(case_id: UUID, service: Service):
    case = await service.get(case_id, lock=True)
    await service.approve(case)
    await service.db.commit()
    return await service.detail(case)


@router.post("/{case_id}/reject")
async def reject(case_id: UUID, data: Decision, service: Service):
    case = await service.get(case_id, lock=True)
    await service.reject(case, data.reason)
    await service.db.commit()
    return await service.detail(case)
