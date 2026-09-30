"""M7 security contracts against database/session/API boundaries."""

import base64
import os
import socket
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.api.dependencies import get_service
from app.company.auth import COOKIE, bootstrap, digest
from app.company.boundaries import mounted, resolve, webhook
from app.company.destinations import file_deliver, safe_case
from app.company.schemas import ConnectorData
from app.company.secrets import decrypt, encrypt, validate_startup
from app.core.config import settings
from app.main import app
from app.models.company import Secret, Session, SystemAudit
from app.models.operations import now

PASSWORD = "Synthetic-M7-test-password!"


@pytest.fixture
async def admin(client, monkeypatch, tmp_path):
    for key, value in {
        "auth_enabled": True,
        "boah_master_key": base64.b64encode(os.urandom(32)).decode(),
        "boah_initial_admin_email": "admin@example.com",
        "boah_initial_admin_password": PASSWORD,
        "mounted_roots": {"archive": str(tmp_path)},
    }.items():
        monkeypatch.setattr(settings, key, value)
    async for service in app.dependency_overrides[get_service]():
        await bootstrap(service.db)
    result = await client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert result.status_code == 200, result.text
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return client


async def test_session_csrf_logout(admin):
    token = admin.cookies.get(COOKIE)
    me = await admin.get("/api/v1/auth/me")
    assert token not in me.text and PASSWORD not in me.text
    assert me.headers["cache-control"] == "no-store"
    assert (await admin.get("/api/v1/auth/me")).json()["csrf_token"] == me.json()["csrf_token"]
    assert (
        await admin.put("/api/v1/settings/company", json={"company_name": "Synthetic"})
    ).status_code == 200
    assert (
        await admin.put(
            "/api/v1/settings/company",
            headers={"X-CSRF-Token": "bad"},
            json={"company_name": "Synthetic"},
        )
    ).status_code == 403
    assert (
        await admin.post("/api/v1/auth/logout", headers={"Origin": "https://evil.invalid"})
    ).status_code == 403
    async for service in app.dependency_overrides[get_service]():
        session = await service.db.get(Session, digest(token))
        assert session and session.csrf_hash != admin.headers["X-CSRF-Token"]
    assert (await admin.post("/api/v1/auth/logout")).status_code == 200
    admin.cookies.set(COOKIE, token)
    assert (await admin.get("/api/v1/cases")).status_code == 401


async def test_expiry(admin):
    async for service in app.dependency_overrides[get_service]():
        session = await service.db.get(Session, digest(admin.cookies.get(COOKIE)))
        session.expires_at = now() - timedelta(seconds=1)
        await service.db.commit()
    assert (await admin.get("/api/v1/cases")).status_code == 401


@pytest.mark.parametrize("role", ["VIEWER", "REVIEWER", "OPERATOR"])
async def test_backend_role_matrix(admin, role):
    user = await admin.post(
        "/api/v1/settings/users",
        json={"email": f"{role.lower()}@example.com", "password": PASSWORD, "role": role},
    )
    assert user.status_code == 201 and "password" not in user.text
    login = await admin.post(
        "/api/v1/auth/login", json={"email": f"{role.lower()}@example.com", "password": PASSWORD}
    )
    admin.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert (await admin.get("/api/v1/cases")).status_code == 200
    assert (await admin.get("/api/v1/settings/sources")).status_code == 403
    assert (await admin.post("/api/v1/settings/destinations", json={})).status_code == 403
    assert (await admin.get("/api/v1/system/metrics")).status_code == 403
    result = await admin.post("/api/v1/cases", json={})
    assert result.status_code == (201 if role == "OPERATOR" else 403)


async def test_disable_revokes_and_last_admin_protected(admin):
    users = (await admin.get("/api/v1/settings/users")).json()
    path = f"/api/v1/settings/users/{users[0]['id']}"
    assert (await admin.put(path, json={"role": "VIEWER", "enabled": True})).status_code == 409
    assert (
        await admin.post(
            "/api/v1/settings/users",
            json={"email": "another@example.com", "password": PASSWORD, "role": "ADMIN"},
        )
    ).status_code == 201
    assert (await admin.put(path, json={"role": "ADMIN", "enabled": False})).status_code == 200
    assert (await admin.get("/api/v1/cases")).status_code == 401


async def test_throttle_audit_and_sanitized_validation(admin, caplog):
    for _ in range(5):
        result = await admin.post(
            "/api/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD}
        )
        assert result.status_code == 401
    assert (
        await admin.post(
            "/api/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD}
        )
    ).status_code == 429
    result = await admin.post(
        "/api/v1/auth/login", json={"email": "invalid", "password": PASSWORD, "extra": PASSWORD}
    )
    assert result.status_code == 422 and PASSWORD not in result.text
    async for service in app.dependency_overrides[get_service]():
        audit = list(
            await service.db.scalars(select(SystemAudit).where(SystemAudit.event == "LOGIN_FAILED"))
        )
        assert len(audit) == 6 and all(a.correlation_id for a in audit)
        assert PASSWORD not in str([a.details for a in audit])
    assert PASSWORD not in caplog.text


async def test_secret_write_only_rotation(admin):
    payload = {
        "name": "Synthetic IMAP",
        "kind": "IMAP",
        "config": {"host": "mail.example.com", "username": "demo"},
        "secret": {"password": PASSWORD},
    }
    created = await admin.post("/api/v1/settings/sources", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["secret_configured"]
    for path in ["sources", "export", "audit"]:
        result = await admin.get("/api/v1/settings/" + path)
        assert PASSWORD not in result.text and "ciphertext" not in result.text
    async for service in app.dependency_overrides[get_service]():
        record = await service.db.scalar(select(Secret))
        assert PASSWORD.encode() not in record.ciphertext and PASSWORD in decrypt(record)
    payload["secret"] = {"password": "Replacement-synthetic-value"}
    assert (
        await admin.put("/api/v1/settings/sources/" + created.json()["id"], json=payload)
    ).status_code == 200


@pytest.mark.parametrize("tamper", ["ciphertext", "nonce", "id", "key"])
def test_aead_tampering(monkeypatch, tamper):
    monkeypatch.setattr(settings, "boah_master_key", base64.b64encode(os.urandom(32)).decode())
    record = Secret(id=uuid.uuid4())
    encrypt(record, PASSWORD)
    assert decrypt(record) == PASSWORD
    if tamper == "id":
        record.id = uuid.uuid4()
    elif tamper == "key":
        monkeypatch.setattr(settings, "boah_master_key", base64.b64encode(os.urandom(32)).decode())
    else:
        value = getattr(record, tamper)
        setattr(record, tamper, bytes([value[0] ^ 1]) + value[1:])
    with pytest.raises(InvalidTag):
        decrypt(record)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fe80::1", "0.0.0.0", "224.0.0.1"],
)
def test_ssrf_private_metadata(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
    monkeypatch.setattr(settings, "connector_network_allowlist", [])
    with pytest.raises(ValueError):
        resolve("external.example", 443)


def test_ssrf_mixed_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", (ip, 443)) for ip in ["8.8.8.8", "10.0.0.5"]],
    )
    monkeypatch.setattr(settings, "connector_network_allowlist", [])
    with pytest.raises(ValueError):
        resolve("example.com", 443)
    monkeypatch.setattr(settings, "connector_network_allowlist", ["10.0.0.0/24"])
    assert resolve("example.com", 443) == "10.0.0.5"


def test_webhook_pins_ip_rejects_redirect(monkeypatch):
    import app.company.boundaries as boundaries

    monkeypatch.setattr(settings, "connector_allow_plaintext_test", True)
    monkeypatch.setattr(boundaries, "resolve", lambda *a: "8.8.8.8")
    sock = Mock()
    connect = Mock(return_value=sock)
    monkeypatch.setattr(socket, "create_connection", connect)
    connection = Mock()
    connection.getresponse.return_value.status = 302
    monkeypatch.setattr(boundaries.http.client, "HTTPConnection", Mock(return_value=connection))
    with pytest.raises(ValueError, match="302"):
        webhook("http://example.com/hook", b"{}", {})
    connect.assert_called_once_with(("8.8.8.8", 80), timeout=15)
    connection.request.assert_called_once()
    sock.close.assert_called()


@pytest.mark.parametrize(
    "path", ["../escape", "/etc/passwd", "C:/Windows", "a\\..\\b", "foo/../../escape"]
)
def test_traversal(monkeypatch, tmp_path, path):
    monkeypatch.setattr(settings, "mounted_roots", {"archive": str(tmp_path)})
    with pytest.raises(ValueError):
        mounted("archive", path)


@pytest.mark.parametrize(
    "template", ["../{case_id}", "{case_id.__class__}", "{case_id!r}", "{case_id:>5}", "C:/test"]
)
def test_template_no_code(monkeypatch, tmp_path, template):
    monkeypatch.setattr(settings, "mounted_roots", {"archive": str(tmp_path)})
    with pytest.raises(ValueError):
        ConnectorData(
            name="bad", kind="FILESYSTEM", config={"root": "archive", "path_template": template}
        ).checked(False)


def test_file_idempotency_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mounted_roots", {"archive": str(tmp_path)})
    config = ConnectorData(name="good", kind="FILESYSTEM", config={"root": "archive"}).checked(
        False
    )
    case = SimpleNamespace(public_id="CASE-TEST", created_at=now())
    file_deliver(config, case, {"documents": []}, [("CASE-TEST.json", b"{}")])
    file_deliver(config, case, {"documents": []}, [("CASE-TEST.json", b"{}")])
    assert len(list(tmp_path.rglob("*.json"))) == 1
    with pytest.raises(ValueError, match="collision"):
        file_deliver(config, case, {"documents": []}, [("CASE-TEST.json", b"different")])


@pytest.mark.parametrize(
    "field,value",
    [
        ("boah_master_key", ""),
        ("auth_enabled", False),
        ("auth_cookie_secure", False),
        ("debug", True),
        ("connector_allow_plaintext_test", True),
        ("security_preflight_enabled", False),
        ("public_url", "http://boah.example"),
        ("boah_initial_admin_password", "short"),
    ],
)
def test_production_fail_closed(monkeypatch, field, value):
    for key, val in {
        "app_env": "production",
        "boah_master_key": base64.b64encode(os.urandom(32)).decode(),
        "auth_enabled": True,
        "auth_cookie_secure": True,
        "debug": False,
        "connector_allow_plaintext_test": False,
        "security_preflight_enabled": True,
        "public_url": "https://boah.example.com",
        "database_url": "postgresql+asyncpg://configured:unique@db/boah",
    }.items():
        monkeypatch.setattr(settings, key, val)
    monkeypatch.setattr(settings, field, value)
    with pytest.raises(ValueError):
        validate_startup()


async def test_delivery_requires_safe(admin):
    from app.models.entities import Case

    async for service in app.dependency_overrides[get_service]():
        case = Case(id=uuid.uuid4(), public_id="CASE-NO-SAFE", status="APPROVED", source="api")
        service.db.add(case)
        await service.db.commit()
        with pytest.raises(ValueError, match="SAFE"):
            await safe_case(service, case)


async def test_retention_confirmation(admin):
    plan = (await admin.get("/api/v1/settings/retention/dry-run")).json()
    assert plan["items"] == []
    result = await admin.post(
        "/api/v1/settings/retention/execute", json={"plan_id": plan["plan_id"], "confirm": False}
    )
    assert result.status_code == 422


async def test_machine_scope(admin, monkeypatch):
    monkeypatch.setattr(
        settings, "boah_service_token", "synthetic-service-token-minimum32characters"
    )
    admin.cookies.clear()
    admin.headers["Authorization"] = "Bearer " + settings.boah_service_token
    assert (await admin.get("/api/v1/settings/company")).status_code == 403
    assert (await admin.post("/api/v1/inbound/email", json={})).status_code == 422


def test_restored_plain_imap_config_fails_closed_in_production(monkeypatch):
    from app.company.sources import connect_imap

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "connector_allow_plaintext_test", True)
    with pytest.raises(ValueError, match="TLS"):
        connect_imap({"tls": False}, {})
