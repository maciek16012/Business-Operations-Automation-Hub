"""Authenticated encryption and fail-closed deployment checks."""

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.models.company import Secret
from app.models.operations import now


def master_key() -> bytes:
    value = settings.boah_master_key
    if settings.boah_master_key_file:
        value = Path(settings.boah_master_key_file).read_text().strip()
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError("Invalid BOAH_MASTER_KEY encoding") from exc
    if len(key) != 32:
        raise ValueError("BOAH_MASTER_KEY must encode 32 random bytes")
    return key


def encrypt(record: Secret, value: str) -> None:
    record.nonce = os.urandom(12)
    record.ciphertext = AESGCM(master_key()).encrypt(
        record.nonce, value.encode(), str(record.id).encode()
    )
    record.updated_at = now()


def decrypt(record: Secret) -> str:
    return (
        AESGCM(master_key())
        .decrypt(record.nonce, record.ciphertext, str(record.id).encode())
        .decode()
    )


def validate_startup() -> None:
    if settings.app_env != "production":
        return
    master_key()
    if not settings.auth_enabled or not settings.auth_cookie_secure or settings.debug:
        raise ValueError("Production requires authentication, secure cookies and debug disabled")
    if settings.connector_allow_plaintext_test or not settings.security_preflight_enabled:
        raise ValueError("Production requires secure connectors and M5 security")
    if not settings.public_url.startswith("https://"):
        raise ValueError("Production PUBLIC_URL must use HTTPS")
    if "boah_dev_password" in settings.database_url:
        raise ValueError("Production database credentials must be explicitly configured")
    if settings.boah_initial_admin_password and (
        len(settings.boah_initial_admin_password) < 16
        or len(set(settings.boah_initial_admin_password)) < 8
        or settings.boah_initial_admin_password.lower()
        in {"changemechangemechangeme", "passwordpasswordpassword"}
    ):
        raise ValueError("Production bootstrap password requires at least 16 characters")
    if settings.boah_service_token and len(settings.boah_service_token) < 32:
        raise ValueError("Service token too short")
