"""Real backup -> empty isolated PostgreSQL/storage -> API and hash verification."""

import hashlib
import importlib.util
import json
import secrets
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime-m7"
spec = importlib.util.spec_from_file_location("backup", ROOT / "scripts/backup/boah_backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)
base = backup.compose(
    None,
    [
        "docker-compose.yml",
        "docker-compose.ocr.yml",
        "docker-compose.security.yml",
        "docker-compose.m7-test.yml",
    ],
)
values = dict(
    line.split("=", 1)
    for line in (RUNTIME / "integration.env").read_text().splitlines()
    if "=" in line
)
state = json.loads((RUNTIME / "e2e-state.json").read_text())
project = "boah-m7-restore-" + secrets.token_hex(3)
archive = RUNTIME / (project + ".tar.gz")
restore_file = RUNTIME / "restore-compose.yml"
pwd = secrets.token_urlsafe(24)
# All target volumes are project-scoped and new. No existing volume is deleted.
restore_file.write_text(
    '''services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: boah
      POSTGRES_USER: boah
      POSTGRES_PASSWORD: "'''
    + pwd
    + """"
    volumes: [restore_db:/var/lib/postgresql/data]
    healthcheck:
      test: [CMD, pg_isready, -U, boah]
      interval: 2s
      retries: 30
  backend:
    image: businessoperationsautomationhub-backend:latest
    env_file: [integration.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://boah:"""
    + pwd
    + """@postgres:5432/boah
      STORAGE_PATH: /data/documents
    volumes: [restore_files:/data/documents]
    ports: ["127.0.0.1:18000:8000"]
    depends_on: {postgres: {condition: service_healthy}}
volumes:
  restore_db:
  restore_files:
"""
)
restore_file.chmod(0o600)
target = backup.compose(project, [str(restore_file)])


def command(base, *args):
    subprocess.run([*base, *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


command(base, "stop", "backend", "review-worker", "delivery-worker", "n8n")
try:
    manifest = backup.backup(base, archive)
    print("Backup created and SHA-256 manifest verified", flush=True)
    backup.verify(archive)
finally:
    command(base, "up", "-d", "backend", "review-worker", "delivery-worker", "n8n")
command(target, "up", "-d", "--wait", "postgres")
backup.restore(target, archive, True)
print("Restore into empty isolated database and storage completed", flush=True)
command(target, "up", "-d", "backend")
with httpx.Client(base_url="http://localhost:18000/api/v1", timeout=30) as client:
    for _ in range(30):
        try:
            response = client.post(
                "/auth/login",
                json={
                    "email": values["BOAH_INITIAL_ADMIN_EMAIL"],
                    "password": values["BOAH_INITIAL_ADMIN_PASSWORD"],
                },
            )
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Restored backend not ready")
    detail = client.get("/cases/" + state["case_id"]).json()
    assert detail["id"] == state["case_id"] and detail["documents"] and detail["attachments"]
    assert client.get("/settings/sources").json()[0]["secret_configured"]
# Read and hash every restored object through the restored container.
script = """import hashlib,json
from pathlib import Path
from app.core.config import settings
root=Path(settings.storage_path)
values={}
for p in root.rglob('*'):
 if p.is_file():
  values['storage/'+p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps(values))
"""
actual = json.loads(backup.run(target, "exec", "-T", "backend", "python", "-c", script))
expected = {k: v for k, v in manifest["files"].items() if k.startswith("storage/")}
assert actual == expected
# Authenticated decryption with the separately supplied key, never print secret contents.
script = """import asyncio
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.company import Secret
from app.company.secrets import decrypt
async def check():
 async with SessionLocal() as db:
  rows=list(await db.scalars(select(Secret)))
  assert rows and all(decrypt(row) for row in rows)
  print(len(rows))
asyncio.run(check())
"""
count = int(backup.run(target, "exec", "-T", "backend", "python", "-c", script))
result = {
    "status": "PASS",
    "project": project,
    "schema_version": manifest["schema_version"],
    "manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "restored_objects_verified": len(actual),
    "encrypted_secrets_decrypted": count,
    "master_key_included": False,
    "case_id": detail["id"],
    "documents": len(detail["documents"]),
    "attachments": len(detail["attachments"]),
    "existing_volumes_deleted": False,
}
(ROOT / "docs/milestone7/backup-restore-e2e.json").write_text(json.dumps(result, indent=2) + "\n")
command(target, "stop")
print(json.dumps(result), flush=True)
