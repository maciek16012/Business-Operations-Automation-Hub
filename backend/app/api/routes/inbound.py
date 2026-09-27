from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import Service
from app.schemas.cases import Decision
from app.schemas.inbound import InboundEmail, InboundResult
from app.services.inbound import EmailIngestionService

router = APIRouter()


@router.post(
    "/email",
    response_model=InboundResult,
    status_code=201,
    responses={200: {"model": InboundResult}},
)
async def ingest_email(payload: InboundEmail, response: Response, service: Service):
    result = await EmailIngestionService(service).ingest(payload)
    await service.db.commit()
    response.status_code = 201 if result["result"] == "created" else 200
    return result


@router.post("/messages/{message_id}/attachments/{attachment_id}/review")
async def review_attachment(
    message_id: UUID, attachment_id: UUID, data: Decision, service: Service
):
    result = await EmailIngestionService(service).review_attachment(
        message_id, attachment_id, data.reason
    )
    await service.db.commit()
    return result
