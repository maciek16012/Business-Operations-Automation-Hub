"""Actual dependency probes and aggregate Prometheus metrics without PII labels."""

import asyncio
import json
import logging
import shutil
import time
import uuid
from datetime import timedelta
from typing import cast

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CollectorRegistry, Gauge, Histogram, generate_latest
from sqlalchemy import func, select, text

from app.api.dependencies import Service
from app.company.auth import aware
from app.company.context import actor, correlation
from app.core.config import settings
from app.models.company import (
    DeliveryJob,
    DocumentSource,
    OutputDestination,
    Session,
    WorkerHeartbeat,
)
from app.models.documents import DocumentAnalysis
from app.models.entities import Attachment, Case, OCRDocument
from app.models.operations import AttachmentSecurityScan, ReviewTask, now

router = APIRouter()
request_registry = CollectorRegistry()
processing = Histogram(
    "boah_processing_duration_seconds", "Intake request duration", registry=request_registry
)


async def dependencies(db):
    result = {}
    try:
        await db.execute(text("SELECT 1"))
        result["postgresql"] = "HEALTHY"
    except Exception:
        result["postgresql"] = "UNAVAILABLE"
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.clamav_host, settings.clamav_port), 3
        )
        writer.write(b"zPING\0")
        await writer.drain()
        pong = await asyncio.wait_for(reader.read(32), 3)
        writer.close()
        await writer.wait_closed()
        result["clamav"] = "HEALTHY" if b"PONG" in pong else "UNAVAILABLE"
    except Exception:
        result["clamav"] = "UNAVAILABLE"
    urls = {
        "tesseract": settings.ocr_tesseract_url.rsplit("/", 1)[0] + "/health",
        "paddle": settings.ocr_paddle_url.rsplit("/", 1)[0] + "/health",
        "n8n": settings.review_notification_webhook_url.split("/webhook")[0] + "/healthz",
    }
    async with httpx.AsyncClient(timeout=3, follow_redirects=False) as client:

        async def probe(name, url):
            try:
                response = await client.get(url)
                result[name] = "HEALTHY" if response.status_code == 200 else "UNAVAILABLE"
            except Exception:
                result[name] = "UNAVAILABLE"

        await asyncio.gather(*(probe(k, v) for k, v in urls.items()))
    return result


@router.get("/health")
async def health(service: Service):
    checks = await dependencies(service.db)
    for name in ["review", "delivery"]:
        row = await service.db.get(WorkerHeartbeat, name)
        checks[name + "_worker"] = (
            "HEALTHY"
            if row and aware(row.updated_at) > now() - timedelta(seconds=90)
            else "UNAVAILABLE"
        )
    connectors = {}
    models: list[tuple[type[DocumentSource] | type[OutputDestination], str]] = [
        (DocumentSource, "sources"),
        (OutputDestination, "destinations"),
    ]
    for model, label in models:
        rows = cast(
            list[DocumentSource | OutputDestination], list(await service.db.scalars(select(model)))
        )
        connectors[label] = [
            {
                "id": str(c.id),
                "name": c.name,
                "enabled": c.enabled,
                "status": c.status if c.enabled else "DISABLED",
                "last_success": c.last_success,
                "last_error": c.last_error,
            }
            for c in rows
        ]
    storage = []
    for name, path in {"document_store": settings.storage_path, **settings.mounted_roots}.items():
        try:
            space = shutil.disk_usage(path)
            storage.append(
                {
                    "name": name,
                    "free_bytes": space.free,
                    "total_bytes": space.total,
                    "status": "HEALTHY",
                }
            )
        except OSError:
            storage.append({"name": name, "status": "UNAVAILABLE"})
    return {
        "status": "HEALTHY"
        if (
            all(s == "HEALTHY" for s in checks.values())
            and all(s["status"] == "HEALTHY" for s in storage)
            and all(
                not c["enabled"] or c["status"] != "UNAVAILABLE"
                for rows in connectors.values()
                for c in rows
            )
        )
        else "DEGRADED",
        "checks": checks,
        **connectors,
        "storage": storage,
        "checked_at": now(),
    }


@router.get("/metrics")
async def metrics(service: Service):
    registry = CollectorRegistry()

    async def count(model, *conditions):
        return (
            await service.db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
        )

    measurements = {
        "documents_received": await count(Attachment),
        "documents_processed": await count(DocumentAnalysis),
        "security_blocked": await count(
            AttachmentSecurityScan, AttachmentSecurityScan.verdict != "SAFE"
        ),
        "review_required": await count(ReviewTask, ReviewTask.status.in_(["OPEN", "ACKNOWLEDGED"])),
        "processing_failures": await count(Case, Case.status == "FAILED"),
        "integration_delivery_success": await count(DeliveryJob, DeliveryJob.status == "SUCCEEDED"),
        "integration_delivery_fail": await count(DeliveryJob, DeliveryJob.status == "DEAD_LETTER"),
        "queue_depth": await count(
            DeliveryJob, DeliveryJob.status.in_(["PENDING", "RETRY", "RUNNING"])
        ),
        "active_sessions": await count(
            Session, Session.revoked.is_(False), Session.expires_at > now()
        ),
    }
    for name, value in measurements.items():
        Gauge("boah_" + name, "Persisted aggregate " + name, registry=registry).set(value)
    routes = Gauge("boah_ocr_routes", "Persisted OCR route counts", ["route"], registry=registry)
    counts: dict[str, int] = {}
    for report in await service.db.scalars(select(OCRDocument.report)):
        route = report.get("route", "DUAL_OCR")
        route = (
            route
            if route
            in {"NATIVE_TEXT", "PRIMARY_OCR", "DUAL_OCR", "FALLBACK_OCR", "REVIEW_REQUIRED"}
            else "OTHER"
        )
        counts[route] = counts.get(route, 0) + 1
    for route, value in counts.items():
        routes.labels(route).set(value)
    connector = Gauge(
        "boah_connector_health", "Connector count by state", ["kind", "state"], registry=registry
    )
    connector_models: list[type[DocumentSource] | type[OutputDestination]] = [
        DocumentSource,
        OutputDestination,
    ]
    for model in connector_models:
        for kind, status, total in (
            await service.db.execute(
                select(model.kind, model.status, func.count()).group_by(model.kind, model.status)
            )
        ).all():
            connector.labels(kind, status).set(total)
    return Response(
        generate_latest(registry) + generate_latest(request_registry),
        media_type="text/plain; version=0.0.4",
    )


async def request_context(request: Request, call_next):
    identifier = uuid.uuid4().hex
    token = correlation.set(identifier)
    who = actor.set(None)
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = identifier
        if request.url.path.startswith("/api/v1/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        elapsed = time.monotonic() - start
        if request.url.path.startswith(("/api/v1/uploads", "/api/v1/inbound")):
            processing.observe(elapsed)
        logging.getLogger("boah.requests").info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": identifier,
                    "method": request.method,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 2),
                }
            )
        )
        correlation.reset(token)
        actor.reset(who)
