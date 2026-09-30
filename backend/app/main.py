import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.company.auth import bootstrap
from app.company.auth import router as auth_router
from app.company.monitoring import dependencies, request_context
from app.company.secrets import validate_startup
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.errors import WorkflowError


@asynccontextmanager
async def lifespan(app):
    validate_startup()
    async with SessionLocal() as db:
        await bootstrap(db)
    yield


logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(title=settings.app_name, version="0.7.0", lifespan=lifespan)
app.include_router(auth_router, prefix=settings.api_v1_prefix + "/auth", tags=["Authentication"])


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": e["loc"], "type": e["type"], "msg": "Invalid value"} for e in exc.errors()
            ]
        },
    )


app.middleware("http")(request_context)


@app.get("/health/live")
async def live():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    async with SessionLocal() as db:
        checks = await dependencies(db)
    critical = (
        ["postgresql"]
        + (["clamav"] if settings.security_preflight_enabled else [])
        + (["tesseract", "paddle"] if settings.ocr_enabled else [])
    )
    ok = all(checks.get(k) == "HEALTHY" for k in critical)
    return JSONResponse(
        status_code=200 if ok else 503, content={"status": "ready" if ok else "unavailable"}
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(WorkflowError)
async def workflow_error(request: Request, exc: WorkflowError):
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
    )
