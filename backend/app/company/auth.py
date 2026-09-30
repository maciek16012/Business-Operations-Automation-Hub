"""Local sessions: opaque hashed tokens, Argon2id, CSRF and server-side RBAC."""

import asyncio
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, timedelta
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.api.dependencies import Service
from app.core.config import settings
from app.models.company import LoginThrottle, Session, SystemAudit, User
from app.models.operations import now
from app.services.errors import WorkflowError

router = APIRouter()
passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
COOKIE = "boah_session"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def audit(db, event, actor="system", target=None, **details):
    from app.company.context import correlation

    db.add(
        SystemAudit(
            event=event,
            actor=actor,
            target=target,
            details=details,
            correlation_id=correlation.get(),
        )
    )


def user_json(user):
    return {"id": str(user.id), "email": user.email, "role": user.role, "enabled": user.enabled}


async def current_user(request: Request, service: Service):
    if not settings.auth_enabled:
        if settings.app_env == "production":
            raise WorkflowError("AUTH_REQUIRED", "Authentication required", 401)
        return None
    token = request.cookies.get(COOKIE, "")
    session = await service.db.get(Session, digest(token)) if token else None
    if not session or session.revoked or aware(session.expires_at) <= now():
        raise WorkflowError("AUTH_REQUIRED", "Authentication required", 401)
    user = await service.db.get(User, session.user_id)
    if not user or not user.enabled:
        raise WorkflowError("AUTH_REQUIRED", "Authentication required", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise WorkflowError("CSRF", "Request verification failed", 403)
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            raise WorkflowError("CSRF", "Origin not allowed", 403)
    from app.company.context import actor

    actor.set(str(user.id))
    request.state.user = user
    return user


async def authorize(request: Request, service: Service):
    path = request.url.path.removeprefix(settings.api_v1_prefix)
    bearer = request.headers.get("authorization", "")
    # Dedicated machine credential is narrowly scoped to the preserved n8n intake/sink.
    if settings.boah_service_token and hmac.compare_digest(
        bearer, "Bearer " + settings.boah_service_token
    ):
        if path.startswith("/inbound/") or path.startswith("/review-tasks/notifications/"):
            return
        raise WorkflowError("FORBIDDEN", "Machine credential not allowed here", 403)
    user = await current_user(request, service)
    if user is None:
        return
    if path.startswith("/settings") or path.startswith("/system"):
        allowed = {"ADMIN"}
    elif request.method in {"GET", "HEAD", "OPTIONS"}:
        allowed = {"ADMIN", "OPERATOR", "REVIEWER", "VIEWER"}
    elif path.startswith(("/review/", "/review-tasks/", "/ocr/")) or (
        path.startswith("/documents/") and path.endswith("/review")
    ):
        allowed = {"ADMIN", "REVIEWER"}
    elif path.startswith(("/uploads/", "/cases", "/inbound/", "/exports/")):
        allowed = {"ADMIN", "OPERATOR"}
    else:
        allowed = {"ADMIN"}
    if user.role not in allowed:
        raise WorkflowError("FORBIDDEN", "Insufficient permission", 403)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256, repr=False)


class UserCreate(Login):
    password: str = Field(min_length=16, max_length=256, repr=False)
    role: Literal["ADMIN", "OPERATOR", "REVIEWER", "VIEWER"]


@router.post("/login")
async def login(data: Login, request: Request, response: Response, service: Service):
    email = str(data.email).lower()
    # DB-backed counter by direct peer + account; no untrusted forwarded-IP header.
    key = digest((request.client.host if request.client else "local") + "|" + email)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if service.db.get_bind().dialect.name == "postgresql" else sqlite_insert
    await service.db.execute(
        insert(LoginThrottle)
        .values(id=key, failures=0, window_started=now())
        .on_conflict_do_nothing(index_elements=["id"])
    )
    throttle = await service.db.scalar(
        select(LoginThrottle).where(LoginThrottle.id == key).with_for_update()
    )
    assert throttle
    if throttle.blocked_until and aware(throttle.blocked_until) > now():
        audit(service.db, "LOGIN_FAILED", details_code="THROTTLED")
        await service.db.commit()
        raise WorkflowError(
            "INVALID_CREDENTIALS", "Invalid credentials or temporarily unavailable", 429
        )
    user = await service.db.scalar(select(User).where(User.email == email).with_for_update())
    valid = False
    try:
        valid = await asyncio.to_thread(
            passwords.verify, user.password_hash if user else DUMMY_HASH, data.password
        )
    except VerificationError:
        pass
    if (
        not valid
        or not user
        or not user.enabled
        or (user.locked_until and aware(user.locked_until) > now())
    ):
        throttle.failures += 1
        if throttle.failures >= 5:
            throttle.blocked_until = now() + timedelta(
                seconds=min(900, 30 * 2 ** min(throttle.failures - 5, 5))
            )
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 10:
                user.locked_until = now() + timedelta(minutes=15)
        audit(service.db, "LOGIN_FAILED", target=str(user.id) if user else None)
        await service.db.commit()
        raise WorkflowError(
            "INVALID_CREDENTIALS", "Invalid credentials or temporarily unavailable", 401
        )
    throttle.failures = 0
    throttle.blocked_until = None
    user.failed_logins = 0
    user.locked_until = None
    token = secrets.token_urlsafe(48)
    csrf = digest("csrf:" + token)
    service.db.add(
        Session(
            id=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            expires_at=now() + timedelta(hours=settings.auth_session_hours),
        )
    )
    audit(service.db, "LOGIN_SUCCESS", actor=str(user.id))
    await service.db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        max_age=settings.auth_session_hours * 3600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": user_json(user), "csrf_token": csrf}


@router.get("/me")
async def me(request: Request, service: Service):
    user = await current_user(request, service)
    if user is None:
        return {
            "user": {"role": "ADMIN", "email": "Development compatibility"},
            "auth_enabled": False,
        }
    # Stable across tabs; derived from an HttpOnly session token, returned only same-origin.
    csrf = digest("csrf:" + request.cookies[COOKIE])
    return {"user": user_json(user), "csrf_token": csrf, "auth_enabled": True}


@router.post("/logout")
async def logout(request: Request, response: Response, service: Service):
    user = await current_user(request, service)
    session = await service.db.get(Session, digest(request.cookies.get(COOKIE, "")))
    if session:
        session.revoked = True
    audit(service.db, "LOGOUT", actor=str(user.id) if user else "compatibility")
    await service.db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/sessions")
async def sessions(request: Request, service: Service):
    user = await current_user(request, service)
    if not user:
        return []
    rows = await service.db.scalars(select(Session).where(Session.user_id == user.id))
    return [{"id": s.id, "expires_at": s.expires_at, "revoked": s.revoked} for s in rows]


@router.post("/sessions/{session_id}/revoke")
async def revoke(session_id: str, request: Request, service: Service):
    user = await current_user(request, service)
    session = await service.db.get(Session, session_id)
    if not user or not session or session.user_id != user.id:
        raise WorkflowError("NOT_FOUND", "Session not found", 404)
    session.revoked = True
    await service.db.commit()
    return {"ok": True}


async def bootstrap(db):
    if not settings.boah_initial_admin_email or not settings.boah_initial_admin_password:
        return
    if await db.scalar(select(User.id).limit(1)):
        return
    data = UserCreate(
        email=settings.boah_initial_admin_email,
        password=settings.boah_initial_admin_password,
        role="ADMIN",
    )
    user = User(
        id=uuid.uuid4(),
        email=str(data.email).lower(),
        password_hash=await asyncio.to_thread(passwords.hash, data.password),
        role="ADMIN",
    )
    db.add(user)
    audit(db, "USER_CREATED", target=str(user.id), bootstrap=True)
    await db.commit()
