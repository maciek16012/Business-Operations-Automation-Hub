from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.dependencies import Service
from app.models.documents import DocumentAnalysis
from app.models.entities import AuditEvent, Case
from app.models.operations import AttachmentSecurityScan
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
    service: Service,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    q: str = Query("", max_length=200),
    status: str | None = None,
):
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    if q.strip():
        query = query.where(
            or_(
                *(
                    column.icontains(q.strip(), autoescape=True)
                    for column in (
                        Case.public_id,
                        Case.request_title,
                        Case.customer_name,
                        Case.company_name,
                    )
                )
            )
        )
    total = await service.db.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        await service.db.scalars(
            query.order_by(Case.created_at.desc(), Case.id).offset(offset).limit(limit)
        )
    )
    ids = [row.id for row in rows]
    types: dict = {}
    scans: dict = {}
    if ids:
        for case_id, kind in await service.db.execute(
            select(DocumentAnalysis.case_id, DocumentAnalysis.document_type).where(
                DocumentAnalysis.case_id.in_(ids)
            )
        ):
            types.setdefault(case_id, set()).add(kind)
        for case_id, verdict in await service.db.execute(
            select(AttachmentSecurityScan.case_id, AttachmentSecurityScan.verdict).where(
                AttachmentSecurityScan.case_id.in_(ids)
            )
        ):
            scans.setdefault(case_id, set()).add(verdict)
    return {
        "items": [
            {
                **row_json(row),
                "document_types": sorted(types.get(row.id, [])),
                "security_states": sorted(scans.get(row.id, [])),
            }
            for row in rows
        ],
        "total": total,
    }


@router.get("/{case_id}")
async def get_case(case_id: UUID, service: Service):
    return await service.detail(await service.get(case_id))


@router.get("/{case_id}/audit")
async def get_audit(case_id: UUID, service: Service):
    await service.get(case_id)
    return [row_json(row) for row in await service.rows(AuditEvent, case_id)]
