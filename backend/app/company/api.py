"""Administrator configuration API. Secrets are write-only; tests enqueue worker jobs."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import delete, select, update

from app.api.dependencies import Service
from app.company.auth import UserCreate, audit, passwords, user_json
from app.company.schemas import CompanyData, ConnectorData, RuleData, Strict
from app.company.secrets import encrypt
from app.core.config import settings
from app.models.company import (
    CompanySettings,
    DeliveryJob,
    DocumentSource,
    OutputDestination,
    RoutingRule,
    RuleDestination,
    Secret,
    Session,
    SystemAudit,
    User,
)
from app.models.operations import ReviewTask, now
from app.services.errors import WorkflowError
from app.services.serialization import row_json

router = APIRouter()


def actor(request):
    user = getattr(request.state, "user", None)
    return str(user.id) if user else "development"


def connector_json(row):
    value = row_json(row)
    value.pop("secret_id", None)
    value.pop("runtime_state", None)
    value["secret_configured"] = row.secret_id is not None
    return value


@router.get("/company")
async def company(service: Service):
    row = await service.db.get(CompanySettings, 1)
    if not row:
        return {"configured": False}
    return {
        "configured": True,
        **{
            column.name: getattr(row, "metadata_" if column.name == "metadata" else column.name)
            for column in CompanySettings.__table__.columns
        },
    }


@router.put("/company")
async def save_company(data: CompanyData, request: Request, service: Service):
    row = await service.db.get(CompanySettings, 1)
    if not row:
        row = CompanySettings(id=1)
        service.db.add(row)
    for key, value in data.model_dump(mode="json").items():
        setattr(row, key, value)
    audit(service.db, "COMPANY_CONFIG_CHANGED", actor(request))
    await service.db.commit()
    return await company(service)


@router.get("/roots")
async def roots():
    # Deployment paths are deliberately not disclosed/configurable through the GUI.
    return [{"name": name} for name in sorted(settings.mounted_roots)]


@router.get("/sources")
async def sources(service: Service):
    return [
        connector_json(row)
        for row in await service.db.scalars(select(DocumentSource).order_by(DocumentSource.name))
    ]


@router.get("/destinations")
async def destinations(service: Service):
    return [
        connector_json(row)
        for row in await service.db.scalars(
            select(OutputDestination).order_by(OutputDestination.name)
        )
    ]


async def save_connector(model, data, identity, request, service):
    try:
        config = data.checked(model is DocumentSource)
    except (ValueError, KeyError) as exc:
        raise WorkflowError("INVALID_CONFIG", "Invalid connector configuration", 422) from exc
    row = await service.db.get(model, identity) if identity else model(id=uuid.uuid4())
    if row is None:
        raise WorkflowError("NOT_FOUND", "Connector not found", 404)
    if identity and row.kind != data.kind:
        raise WorkflowError("INVALID_CONFIG", "Connector type cannot change", 422)
    row.name = data.name
    row.kind = data.kind
    row.enabled = data.enabled
    row.config = config
    row.status = "UNCHECKED"
    if model is DocumentSource:
        row.interval_seconds = data.interval_seconds
        row.next_poll_at = now()
    if data.secret is not None:
        record = (
            await service.db.get(Secret, row.secret_id)
            if row.secret_id
            else Secret(id=uuid.uuid4())
        )
        try:
            encrypt(record, json.dumps(data.secret))
        except ValueError as exc:
            raise WorkflowError(
                "KEY_UNAVAILABLE", "Configure BOAH_MASTER_KEY before storing secrets", 503
            ) from exc
        service.db.add(record)
        await service.db.flush()
        row.secret_id = record.id
        audit(service.db, "SECRET_ROTATED", actor(request), str(row.id))
    service.db.add(row)
    audit(
        service.db,
        "INTEGRATION_CONFIG_CHANGED",
        actor(request),
        str(row.id),
        kind=row.kind,
        enabled=row.enabled,
    )
    await service.db.commit()
    return connector_json(row)


@router.post("/sources", status_code=201)
async def create_source(data: ConnectorData, request: Request, service: Service):
    return await save_connector(DocumentSource, data, None, request, service)


@router.put("/sources/{identity}")
async def edit_source(identity: uuid.UUID, data: ConnectorData, request: Request, service: Service):
    return await save_connector(DocumentSource, data, identity, request, service)


@router.post("/destinations", status_code=201)
async def create_destination(data: ConnectorData, request: Request, service: Service):
    return await save_connector(OutputDestination, data, None, request, service)


@router.put("/destinations/{identity}")
async def edit_destination(
    identity: uuid.UUID, data: ConnectorData, request: Request, service: Service
):
    return await save_connector(OutputDestination, data, identity, request, service)


@router.post("/{collection}/{identity}/test", status_code=202)
async def test_connector(collection: str, identity: uuid.UUID, request: Request, service: Service):
    model = {"sources": DocumentSource, "destinations": OutputDestination}.get(collection)
    if model is None or not await service.db.get(model, identity):
        raise WorkflowError("NOT_FOUND", "Connector not found", 404)
    job = DeliveryJob(id=uuid.uuid4(), kind="TEST", idempotency_key="test:" + uuid.uuid4().hex)
    if model is DocumentSource:
        job.source_id = identity
    else:
        job.destination_id = identity
    service.db.add(job)
    audit(service.db, "CONNECTION_TEST_QUEUED", actor(request), str(identity))
    await service.db.commit()
    return row_json(job)


@router.get("/routing")
async def rules(service: Service):
    output = []
    for row in await service.db.scalars(
        select(RoutingRule).order_by(RoutingRule.priority, RoutingRule.id)
    ):
        ids = await service.db.scalars(
            select(RuleDestination.destination_id).where(RuleDestination.rule_id == row.id)
        )
        output.append({**row_json(row), "destinations": [str(i) for i in ids]})
    return output


async def save_rule(data, identity, request, service):
    try:
        ids = {uuid.UUID(i) for i in data.destinations}
    except ValueError as exc:
        raise WorkflowError("INVALID_DESTINATION", "Invalid destination", 422) from exc
    for i in ids:
        if not await service.db.get(OutputDestination, i):
            raise WorkflowError("INVALID_DESTINATION", "Destination not found", 422)
    row = await service.db.get(RoutingRule, identity) if identity else RoutingRule(id=uuid.uuid4())
    if not row:
        raise WorkflowError("NOT_FOUND", "Rule not found", 404)
    for key, value in data.model_dump(exclude={"destinations"}).items():
        setattr(row, key, value)
    service.db.add(row)
    await service.db.flush()
    await service.db.execute(delete(RuleDestination).where(RuleDestination.rule_id == row.id))
    for i in ids:
        service.db.add(RuleDestination(rule_id=row.id, destination_id=i))
    audit(service.db, "ROUTING_RULE_CHANGED", actor(request), str(row.id))
    await service.db.commit()
    return {"id": str(row.id)}


@router.post("/routing", status_code=201)
async def create_rule(data: RuleData, request: Request, service: Service):
    return await save_rule(data, None, request, service)


@router.put("/routing/{identity}")
async def edit_rule(identity: uuid.UUID, data: RuleData, request: Request, service: Service):
    return await save_rule(data, identity, request, service)


@router.get("/jobs")
async def jobs(service: Service):
    rows = await service.db.scalars(
        select(DeliveryJob).order_by(DeliveryJob.created_at.desc()).limit(200)
    )
    return [{k: v for k, v in row_json(row).items() if k != "artifacts"} for row in rows]


@router.post("/jobs/{identity}/retry")
async def retry(identity: uuid.UUID, request: Request, service: Service):
    row = await service.db.get(DeliveryJob, identity)
    if not row or row.status != "DEAD_LETTER":
        raise WorkflowError("INVALID_STATE", "Only dead-letter jobs can be retried", 409)
    row.status = "PENDING"
    row.attempts = 0
    row.next_retry = now()
    task = await service.db.scalar(
        select(ReviewTask).where(ReviewTask.active_key == f"integration:{row.id}")
    )
    if task:
        task.active_key = None
        task.status = "RESOLVED"
        task.resolved_at = now()
    audit(service.db, "DELIVERY_RETRY_REQUESTED", actor(request), str(row.id))
    await service.db.commit()
    return {"ok": True}


@router.get("/users")
async def users(service: Service):
    return [user_json(u) for u in await service.db.scalars(select(User).order_by(User.email))]


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, request: Request, service: Service):
    if await service.db.scalar(select(User.id).where(User.email == str(data.email).lower())):
        raise WorkflowError("ALREADY_EXISTS", "User already exists", 409)
    user = User(
        id=uuid.uuid4(),
        email=str(data.email).lower(),
        password_hash=await asyncio.to_thread(passwords.hash, data.password),
        role=data.role,
    )
    service.db.add(user)
    audit(service.db, "USER_CREATED", actor(request), str(user.id), role=user.role)
    await service.db.commit()
    return user_json(user)


class UserEdit(Strict):
    role: str = Field(pattern="^(ADMIN|OPERATOR|REVIEWER|VIEWER)$")
    enabled: bool


@router.put("/users/{identity}")
async def edit_user(identity: uuid.UUID, data: UserEdit, request: Request, service: Service):
    # Serialize administrative account changes, preserving a usable administrator.
    admins = list(
        await service.db.scalars(
            select(User).where(User.role == "ADMIN", User.enabled.is_(True)).with_for_update()
        )
    )
    user = await service.db.get(User, identity)
    if not user:
        raise WorkflowError("NOT_FOUND", "User not found", 404)
    if user in admins and len(admins) == 1 and (not data.enabled or data.role != "ADMIN"):
        raise WorkflowError("LAST_ADMIN", "Cannot disable or demote the last administrator", 409)
    event = "USER_DISABLED" if not data.enabled else "ROLE_CHANGED"
    user.role = data.role
    user.enabled = data.enabled
    await service.db.execute(update(Session).where(Session.user_id == user.id).values(revoked=True))
    audit(service.db, event, actor(request), str(user.id), role=user.role)
    await service.db.commit()
    return user_json(user)


@router.get("/audit")
async def system_audit(service: Service):
    return [
        row_json(row)
        for row in await service.db.scalars(
            select(SystemAudit).order_by(SystemAudit.created_at.desc()).limit(200)
        )
    ]


@router.get("/export")
async def export_config(service: Service):
    return {
        "schema_version": 1,
        "company": await company(service),
        "sources": await sources(service),
        "destinations": await destinations(service),
        "routing": await rules(service),
        "storage_roots": await roots(),
    }


@router.get("/retention/dry-run")
async def retention_plan(service: Service):
    from app.company.retention import plan

    return await plan(service)


class RetentionExecute(Strict):
    plan_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: bool


@router.post("/retention/execute")
async def retention_execute(data: RetentionExecute, request: Request, service: Service):
    if not data.confirm:
        raise WorkflowError("CONFIRMATION_REQUIRED", "Explicit confirmation required", 422)
    from app.company.retention import execute

    return await execute(service, data.plan_id, actor(request))


@router.get("/backup")
async def backup_info():
    return {
        "format": "boah-m7-v1",
        "mode": "maintenance-window CLI",
        "command": "python scripts/backup/boah_backup.py backup <archive>",
        "restore_requires_force": True,
        "restore_target_must_be_empty": True,
        "master_key_included": False,
    }
