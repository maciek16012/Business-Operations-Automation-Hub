# M7 — Deployment and operations

M7 extends the existing M1–M6 application. Production uses the standalone `docker-compose.production.yml`; never merge it with the development compose files. Only Caddy publishes TCP 80/443. PostgreSQL, backend, frontend, OCR, ClamAV, n8n and workers remain on the private Docker network.

## First production deployment

1. Provision a host, real DNS name and firewall allowing inbound 80/443. Copy `deploy/milestone7/production.env.example` to ignored `.env.production`. Set the domain, fresh strong PostgreSQL password, bootstrap administrator email/password and a random service token (at least 32 characters). Do not use local fixture credentials.
2. Generate a random 32-byte master key encoded as base64 in a separate protected file. Set `BOAH_MASTER_KEY_PATH` to its host path in the environment example. Compose mounts it as a Docker secret. Protect Linux permissions/Windows ACLs and retain an independently protected recovery copy. Never commit it or put it in the application backup.
3. Create incoming/archive directories, set their host paths in `.env.production`, grant the application UID/GID 10001 the necessary access. Incoming is mounted read-only. Archive is writable; configure only trusted, dedicated roots. Database/storage volumes must be preserved.
4. Run `docker compose --env-file .env.production -f docker-compose.production.yml config --quiet`, then `docker compose --env-file .env.production -f docker-compose.production.yml up -d --build`.
5. Check `ps`, HTTPS `/health/ready`, login, first-run guide and Settings/System. Caddy acquires the public certificate when DNS and external network conditions are correct. A local CA smoke test does not prove public ACME issuance.
6. The environment bootstrap creates only the first administrator. Remove its password from the environment after initialization and recreate application containers. Alternatively provision the first account interactively using `docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -m app.company.bootstrap_admin` before any identity exists. Passwords do not appear in CLI arguments.
7. Import/publish n8n workflows and provision its scoped backend Authorization credential. Workflow JSON must remain credential-free. Map notification recipients to an actual company email/channel workflow; the tested durable receipt sink alone does not send email.

Backend and frontend run as UID 10001 with read-only root filesystems, writable `/tmp`, dropped capabilities and no new privileges. Both workers share these controls. PaddleOCR/ClamAV retain upstream runtime privileges where needed for models/signatures; private networking and persistent cache/signature volumes are intentional. Treat Docker, host administrator and mounted roots as trusted boundaries. Keep image dependencies updated through a separate validated release.

## Local reproducible integration environment

Run once: `backend/.venv/Scripts/python.exe scripts/milestone7/init_local.py`. Generated passwords, keys, PDFs, protocol recordings and backups are under ignored `.runtime-m7/`; the initializer refuses to overwrite existing credentials.

Start with `docker compose -f docker-compose.yml -f docker-compose.ocr.yml -f docker-compose.security.yml -f docker-compose.m7-test.yml up -d --build`. Run `backend/.venv/Scripts/python.exe scripts/milestone7/configure_n8n.py`, then `backend/.venv/Scripts/python.exe scripts/milestone7/e2e.py`. The fixture uses real SMTP/IMAP, SFTP and signed HTTP protocols with synthetic PDFs. Plain IMAP is explicitly allowed only in development; production rejects TLS-off configurations at validation and at connection time, including restored database records.

Production image tests: build `backend/Dockerfile.production` as `boah-m7-backend-production:local`, and `frontend/Dockerfile.production` as `boah-m7-frontend-production:local`; run `backend/.venv/Scripts/python.exe scripts/milestone7/production_smoke.py`. Each run creates a fresh isolated project and connects to the existing local OCR/ClamAV dependency network. It trusts only that run's Caddy CA using an explicit TLS context and binds `127.0.0.1:8443`. It does not change system/browser trust or bypass certificate warnings. Successful runs stop their containers; test volumes are retained, never deleted automatically.

## Configuration and connectors

Use Settings for company defaults, users, named storage mounts, sources, destinations, ordered routing, recipients, service health and retention. Secrets are write-only AES-GCM records. Blank secret inputs preserve the configured secret. A connection test queues a worker job: PENDING → RUNNING → SUCCEEDED, or bounded retry/dead letter. It is not synchronous UI networking.

IMAP requires verified TLS in production. SFTP requires a pinned host key obtained through a trusted channel; a mismatch is rejected. Webhooks require HTTPS and a signing secret, never follow redirects, and use stable body/idempotency keys across retries. Private connector endpoints require an explicit narrowly scoped deployment allowlist; metadata/link-local addresses remain blocked. Webhook receivers must honor idempotency keys because transport semantics are at least once.

The native sources reuse M2 ingestion and always pass M5 before M6. Routing only delivers approved/exported cases with persisted SAFE attachments and no unresolved blocking issues. Failed deliveries create integration review tasks and durable notification outbox records. Admin retry is explicit. Historical review/audit evidence remains.

## Backup and restore

Use a maintenance window: stop **all writers** (backend, review-worker, delivery-worker and n8n) while PostgreSQL remains running. The CLI refuses backups with those services running. For production set the compose interpolation environment first (for example, `$env:COMPOSE_ENV_FILES='.env.production'` in PowerShell), then use `backend/.venv/Scripts/python.exe scripts/backup/boah_backup.py backup <new-archive> -f docker-compose.production.yml`. Never print the resulting environment or credentials.

The archive contains a custom PostgreSQL dump, application object storage and a SHA-256 manifest with schema version. It includes encrypted connector configuration, but excludes the master key, `.env`, n8n credentials/state and external destination archives. Back up those separately according to company policy. Protect and authenticate the backup at rest: the internal manifest detects corruption, not a maliciously rewritten archive from an untrusted source.

`verify <archive>` checks the manifest, hashes, allowed entries and bounded archive sizes. `restore <archive> --force --project <new-clean-project> -f <clean-compose>` requires an empty database and empty object storage, rejects unsafe paths, imports the dump/files and applies migrations. Start only the new PostgreSQL initially; provide the same master key separately. Verify documents and secrets through the restored API before starting sources/workers. No existing volume is overwritten or removed. The tested restore is `docs/milestone7/backup-restore-e2e.json`: 140 storage objects hashed, 4 encrypted records decrypted independently, API case/document verification passed.

Restart original writers after backup and check readiness/worker heartbeats. Backups are maintenance based, bounded to 2 GiB expanded archive/1 GiB member; M7 does not provide PITR or HA.

## Monitoring and retention

`/health/live` checks process liveness; `/health/ready` fails on unavailable critical services. Admin `/api/v1/system/health` actually checks DB, ClamAV, both OCR services, n8n, worker heartbeats and mounted free space. An enabled failed connector makes aggregate state DEGRADED. Connector state describes the last attempt, not continuous remote probing.

Admin `/api/v1/system/metrics` exposes Prometheus text with aggregate counters/histograms and bounded non-PII labels. Automated scraping needs authorized admin authentication/fronting; no dedicated metrics token is added. Structured HTTP/worker events use correlation IDs and avoid bodies, query strings and secrets.

Retention uses a dry-run plan, current plan hash and explicit confirmation. Active cases/reviews/deliveries are excluded. Quarantine evidence remains unless an explicit retention policy allows deletion. Database metadata and audit survive; deleted object requests return 410. Durable delivery snapshots are currently retained separately and require a future lifecycle policy.
