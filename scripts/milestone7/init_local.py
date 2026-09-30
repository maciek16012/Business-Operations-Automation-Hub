"""Generate local synthetic M7 fixture credentials once, never overwrite existing values."""

import base64
import json
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2] / ".runtime-m7"
for name in ["incoming", "archive", "test-services"]:
    (root / name).mkdir(parents=True, exist_ok=True)
path = root / "integration.env"
if path.exists():
    raise SystemExit("Local fixture environment already exists; retained unchanged.")
values = {
    "BOAH_MASTER_KEY": base64.b64encode(os.urandom(32)).decode(),
    "BOAH_INITIAL_ADMIN_EMAIL": "admin@example.com",
    "BOAH_INITIAL_ADMIN_PASSWORD": secrets.token_urlsafe(32),
    "BOAH_SERVICE_TOKEN": secrets.token_urlsafe(48),
    "M7_MAIL_PASSWORD": secrets.token_urlsafe(32),
    "M7_SFTP_PASSWORD": secrets.token_urlsafe(32),
    "M7_WEBHOOK_HMAC": secrets.token_urlsafe(32),
    "AUTH_ENABLED": "true",
    "MOUNTED_ROOTS": json.dumps({"incoming": "/mnt/incoming", "archive": "/mnt/archive"}),
    "CONNECTOR_NETWORK_ALLOWLIST": json.dumps(["greenmail", "m7-webhook", "m7-sftp"]),
    "CONNECTOR_ALLOW_PLAINTEXT_TEST": "true",
    "OCR_ENABLED": "true",
    "OCR_TESSERACT_URL": "http://tesseract:8080/ocr",
    "OCR_PADDLE_URL": "http://paddle:8080/ocr",
    "OCR_TESSERACT_PROFILE": "orientation",
    "OCR_PADDLE_PROFILE": "orientation",
    "CLAMAV_HOST": "clamav",
    "STP_ENABLED": "true",
    "DELIVERY_RETRY_SECONDS": "2",
    "DELIVERY_MAX_ATTEMPTS": "3",
}
with path.open("x", encoding="utf-8") as stream:
    stream.write("\n".join(k + "=" + v for k, v in values.items()) + "\n")
path.chmod(0o600)
print("Generated .runtime-m7/integration.env. Protect its filesystem ACL; never commit it.")
