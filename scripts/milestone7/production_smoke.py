"""Isolated production images behind HTTPS. Trust only this test Caddy CA explicitly."""

import json
import secrets
import ssl
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime-m7"
values = dict(
    line.split("=", 1)
    for line in (RUNTIME / "integration.env").read_text().splitlines()
    if "=" in line
)
pwd = secrets.token_urlsafe(32)
(RUNTIME / "master-key.secret").write_text(values["BOAH_MASTER_KEY"])
(RUNTIME / "master-key.secret").chmod(0o600)
config = RUNTIME / "production-smoke.yml"
config.write_text(
    '''services:
  postgres:
    image: postgres:17-alpine
    environment: {POSTGRES_USER: boah, POSTGRES_DB: boah, POSTGRES_PASSWORD: "'''
    + pwd
    + """"}
    volumes: [smoke_db:/var/lib/postgresql/data]
    networks: [smoke]
    healthcheck:
      test: [CMD, pg_isready, -U, boah]
      interval: 2s
      retries: 30
  backend:
    image: boah-m7-backend-production:local
    env_file: [integration.env]
    environment:
      APP_ENV: production
      AUTH_COOKIE_SECURE: "true"
      CONNECTOR_ALLOW_PLAINTEXT_TEST: "false"
      PUBLIC_URL: https://localhost:8443
      BACKEND_CORS_ORIGINS: https://localhost:8443
      DATABASE_URL: postgresql+asyncpg://boah:"""
    + pwd
    + """@postgres:5432/boah
      BOAH_MASTER_KEY_FILE: /run/secrets/master-key
      MOUNTED_ROOTS: '{}'
    user: "10001:10001"
    read_only: true
    tmpfs: ["/tmp:size=256m,mode=1777"]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    volumes: [smoke_storage:/data/documents, "./master-key.secret:/run/secrets/master-key:ro"]
    networks: [smoke, dependencies]
    depends_on: {postgres: {condition: service_healthy}}
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')"]
      interval: 5s
      timeout: 15s
      retries: 20
  frontend:
    image: boah-m7-frontend-production:local
    networks: [smoke]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
  proxy:
    image: caddy:2.11-alpine
    environment: {BOAH_DOMAIN: localhost}
    volumes:
      - ../deploy/milestone7/Caddyfile:/etc/caddy/Caddyfile:ro
      - smoke_tls:/data
      - smoke_config:/config
    ports: ["127.0.0.1:8443:443"]
    networks: [smoke]
    read_only: true
    tmpfs: [/tmp]
    depends_on: {backend: {condition: service_healthy}}
networks:
  smoke:
  dependencies:
    external: true
    name: businessoperationsautomationhub_default
volumes:
  smoke_db:
  smoke_storage:
  smoke_tls:
  smoke_config:
""",
    encoding="utf-8",
)
project = "boah-m7-production-smoke-" + secrets.token_hex(3)
base = ["docker", "compose", "-p", project, "-f", str(config)]
subprocess.run([*base, "up", "-d"], check=True, cwd=ROOT)
ca = RUNTIME / "production-smoke-ca.pem"
for _ in range(30):
    result = subprocess.run(
        [
            *base,
            "exec",
            "-T",
            "proxy",
            "cat",
            "/data/caddy/pki/authorities/local/root.crt",
        ],
        capture_output=True,
    )
    if result.returncode == 0:
        ca.write_bytes(result.stdout)
        break
    time.sleep(1)
else:
    raise RuntimeError("Local CA unavailable")
context = ssl.create_default_context(cafile=str(ca))
with httpx.Client(base_url="https://localhost:8443", verify=context, timeout=30) as client:
    assert client.get("/").status_code == 200
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    result = client.post(
        "/api/v1/auth/login",
        json={
            "email": values["BOAH_INITIAL_ADMIN_EMAIL"],
            "password": values["BOAH_INITIAL_ADMIN_PASSWORD"],
        },
    )
    assert result.status_code == 200, result.status_code
    cookie = result.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    assert client.get("/api/v1/settings/company").json()["configured"] is False
    assert (
        client.put(
            "/api/v1/settings/company",
            json={"company_name": "Synthetic HTTPS deployment"},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/cases").status_code == 401
uid = subprocess.check_output([*base, "exec", "-T", "backend", "id", "-u"]).decode().strip()
assert uid == "10001"
frontend_uid = (
    subprocess.check_output([*base, "exec", "-T", "frontend", "id", "-u"]).decode().strip()
)
assert frontend_uid == "10001"
report = {
    "status": "PASS",
    "https_certificate_verified": True,
    "trust": "explicit local Caddy CA, no system trust changes",
    "secure_httponly_samesite_cookie": True,
    "bootstrap_admin_login_logout": True,
    "fresh_company_wizard_api": True,
    "readiness": True,
    "backend_uid": uid,
    "frontend_uid": frontend_uid,
    "read_only_app_containers": True,
    "host_binding": "127.0.0.1:8443",
    "public_acme_certificate_tested": False,
}
(ROOT / "docs/milestone7/production-smoke.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
subprocess.run([*base, "stop"], check=True, cwd=ROOT)
print(json.dumps(report), flush=True)
