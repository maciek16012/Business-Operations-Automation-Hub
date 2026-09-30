# Business Operations Automation Hub

A local business-process automation system, implemented through Milestone 7. Operators can ingest inquiries, inspect sources, correct business data, approve cases and generate traceable JSON/XLSX exports.

```text
EMAIL → n8n → INBOUND API / IDEMPOTENCY ┐
                                    ├→ CASE → STORAGE → EXTRACTION → NORMALIZATION
MANUAL UPLOAD / API ─────────────────┘       → VALIDATION → REVIEW → APPROVAL → EXPORT → AUDIT
```

## Run locally

Requirements: Docker Desktop with Linux containers and Compose v2.24+, available ports 3000, 8000, 5432 and 5678.

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

- Operator UI: http://localhost:3000
- API/OpenAPI: http://localhost:8000/docs and http://localhost:8000/openapi.json
- Backend health: http://localhost:8000/health
- n8n: http://localhost:5678 (loopback-only port)

Backend startup applies `alembic upgrade head`. PostgreSQL/backend healthchecks gate dependent services. Development bind mounts remain: restart backend after Python edits; Next.js runs its development server. Local frontend builds and a running development container share `.next`, so restart frontend after a host build if needed. This is a trusted development environment. M7 enables application authentication by default: initialize the first administrator with `docker compose exec backend python -m app.company.bootstrap_admin`. Public deployment must use the standalone production compose and HTTPS instructions below.

## Stack and architecture

Python 3.12, FastAPI, Pydantic, async SQLAlchemy, Alembic, PostgreSQL 17, Next.js 16, TypeScript, openpyxl and n8n 2.40.7. Business logic stays in FastAPI; n8n handles when/where delivery happens.

```mermaid
flowchart LR
    MAIL[Generic IMAP mailbox] --> N8N[n8n orchestration]
    N8N --> IN[Inbound email API / idempotency]
    IN --> S[Case and export services]
    UI[Next.js review desk] --> API[FastAPI routes]
    API --> S
    S --> DB[(PostgreSQL)]
    S --> OBJ[ObjectStorage]
    OBJ --> FS[(LocalFilesystemStorage / volume)]
    S --> EXT[Development extraction provider]
    EXT --> NORM[Decimal-safe normalization]
    NORM --> VAL[Deterministic validation]
    VAL --> REVIEW[Human review / approval]
    REVIEW --> EXP[JSON / XLSX]
    S --> AUDIT[Audit events]
    AUDIT --> DB
    N8N --> ERR[Error Trigger / recovery summary]
```

Local filesystem object storage is behind `ObjectStorage`. Only LocalFilesystemStorage knows physical paths. `boah_files` persists originals/exports at `/data/documents`; `postgres_data` persists business data; `n8n_data` persists workflow, credential and execution state. Back up these volumes; `docker compose down -v` destroys them. MinIO is not an active dependency.

## Configuration

`.env.example` documents defaults. Compose derives the backend connection from POSTGRES_DB/USER/PASSWORD; a host-run backend uses DATABASE_URL with localhost. Compose sets STORAGE_BACKEND=filesystem and STORAGE_PATH=/data/documents; outside Docker choose a writable storage path. MAX_UPLOAD_BYTES defaults to 5242880. BACKEND_CORS_ORIGINS defaults to http://localhost:3000. NEXT_PUBLIC_API_BASE_URL must be browser-reachable, not an internal Docker hostname. Development database credentials are nonproduction defaults.

n8n uses the official image pinned to `docker.n8n.io/n8nio/n8n:2.40.7`, timezone N8N_TIMEZONE (Europe/Warsaw by default), filesystem binary data and seven-day execution retention. Its credential-encryption key is generated inside the persistent volume. Never commit that key, mailbox credentials or instance-specific credential exports.

## Milestone 1 manual demo

1. Create a case in the UI and upload `sample_data/review_required.txt`.
2. Inspect REVIEW_REQUIRED, NIP/amount errors, source extraction, original attachment and audit. Approval is blocked by the backend, not merely the UI.
3. Correct tax_id to `5260250274` and estimated_value to `12 500,00 PLN`; save corrections and revalidate. READY appears; raw extraction remains unchanged and resolved issues stay in history.
4. Approve, then export JSON and XLSX. EXPORTED cases remain immutable but allow additional export generation/downloads.
5. In another case upload valid_inquiry.txt and duplicate_renamed.txt. The second upload is ignored with a duplicate warning/audit; only one original is stored.
6. Rejection requires a reason, records ReviewDecision/audit and ends in FAILED.

`uv run python ../scripts/demo.py` from backend repeats the HTTP scenario. All fixtures are synthetic; the valid deadline is intentionally distant. `sample_data/README.md` covers missing data, bad NIP, malformed/negative money and manual review.

## Milestone 2 email demo and IMAP setup

After Compose starts, import sanitized workflows and publish the error and local fixture workflows:

```powershell
docker compose exec -T n8n n8n import:workflow --separate --input=/workflows
docker compose exec -T n8n n8n publish:workflow --id=boahEmailErrors2
docker compose exec -T n8n n8n publish:workflow --id=boahEmailFixture2
docker compose restart n8n
Set-Location backend
uv sync --python 3.12 --extra dev
uv run python ../scripts/demo_email_ingestion.py
```

This executes real n8n nodes with 0/1/multiple binary attachments, verifies replay creates no additional cases, then corrects/approves a case and verifies JSON/XLSX. `--via api` runs the direct API variant. Use a new/default run ID for a fresh measured run.

The real `inbound-email.json` workflow uses n8n's generic IMAP Email Trigger. Complete the local n8n owner setup, bind your host/port/user/password in an IMAP credential, keep TLS enabled, choose the mailbox and publish the workflow. No mailbox credentials were available during implementation, so external IMAP receipt is not claimed as tested. See [n8n/README.md](n8n/README.md) for exact binding, import/export, recovery steps and verified behavior. Reimporting workflows can overwrite local bindings; back up first.

## Rules, states and traceability

- A customer/company and request title are required. Email, NIP, date and amount are validated when present; an amount requires PLN/EUR/USD/GBP. NIP uses checksum validation. Deadlines must be ISO dates today or later. Money uses Decimal and NUMERIC(14,2).
- Public IDs are server-generated CASE-year-20 UUID hex characters with a unique database constraint.
- Controlled states: RECEIVED → PROCESSING → READY/REVIEW_REQUIRED → APPROVED → EXPORTED. Editable cases can receive more documents and move between READY/REVIEW_REQUIRED. Rejection/provider/storage processing failure is terminal FAILED. DUPLICATE is reserved; a skipped within-case attachment duplicate does not invalidate the original case.
- ERROR/CRITICAL issues block approval, which reruns validation under a row lock. Approved/exported cases are immutable. Unsaved UI corrections block approval until saved.
- Raw ExtractedField records retain source/provider/normalization. Reviewed business values live on Case; corrections and inferred changes are audited.
- Attachment SHA-256 deduplication stays within-case. Message identity is separate: `(source_type, identity_key)` is unique globally for IMAP. A usable Message-ID drives identity; otherwise a stable fingerprint uses sender/recipients/subject/sent time/body/content hashes, excluding receipt time and filenames. Identical ID-less emails may collapse; never reuse a Message-ID for different messages.
- Email metadata/body/HTML live on InboundMessage, linked to source=email. Subject/sender seed fields deterministically. No semantic interpretation is faked. HTML is rendered only as escaped text.
- Unsupported/failed-extraction email attachments are preserved and require explicit operator acknowledgment with a reason. Their issues survive revalidation; acknowledgment cannot waive NIP/money/required-field rules.
- Delivery uses up to three HTTP attempts and replay with the same identity. A duplicate is successful no-op. Error Trigger distinguishes unavailable, timeout, invalid payload and unexpected failures. This is not distributed exactly-once execution; originals remain unread and failed executions need recovery before retention expires.

## API

All paths below have `/api/v1` prefix. M1 money/date input values are strings, allowing invalid business values to enter review. PATCH omission preserves a value; null/empty clears it. Unknown keys are rejected.

| Method | Path | Purpose |
|---|---|---|
| POST | /cases | Create manual_upload/api case, 201 |
| GET | /cases?offset=0&limit=25 | Paginated list, maximum 200 |
| GET | /cases/{id} | Business record, related history, optional inbound_message |
| POST | /uploads/{id} | Multipart files, 1–10 UTF-8 TXT fixtures |
| GET | /uploads/{case_id}/{attachment_id} | Original download |
| PATCH | /review/{id} | Save corrections and revalidate |
| POST | /review/{id}/validate, /approve, /reject | Guarded actions; reject accepts reason |
| POST | /exports/{id}/json or /xlsx | Generate artifact; 201, Location, X-Export-ID |
| GET | /exports/{export_id} | Download stored export |
| GET | /cases/{id}/audit | Chronological audit |
| POST | /inbound/email | Atomic JSON metadata/body/base64 attachments; 201 created / 200 duplicate |
| POST | /inbound/messages/{message_id}/attachments/{attachment_id}/review | Acknowledge attachment review with reason |

The full email JSON contract, limits and replay semantics are in n8n/README.md and OpenAPI. `/cases` intentionally still rejects source=email without an inbound source record. Workflow errors use error.code/message; malformed requests use FastAPI's 422 detail. JSON exports use explicit schema_version/case_id/status/data with decimal strings. XLSX has Summary, Attachments, Validation and Audit with dates, numeric values and formula-injection protection.

## Repository and checks

- backend/app/api, schemas: HTTP contracts and dependency wiring.
- backend/app/services, domain, models: transactional workflow, guards and persistence.
- backend/app/extraction, validation, storage, exports: separate provider/rules/storage/rendering boundaries.
- backend/alembic/versions and backend/tests: migrations and regression/integration suites.
- frontend/app and frontend/lib: existing review desk and typed client.
- n8n/workflows, code, tests: sanitized real IMAP/fixture/error workflows and verification.
- sample_data, scripts, docs: demos, architecture and measured reports.

```powershell
Set-Location backend
uv sync --python 3.12 --extra dev
uv run pytest -q
uv run ruff format --check app tests alembic
uv run ruff check app tests alembic
uv run mypy app
$env:TEST_DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
$env:DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
uv run alembic upgrade head
uv run alembic check
Set-Location ../frontend
npm ci
npm run lint
npm run typecheck
npm run build
Set-Location ..
node --test n8n/tests/workflows.test.cjs
docker compose config --quiet
```

SQLite tests enable foreign keys. PostgreSQL tests create/drop isolated test_<uuid> schemas and exercise concurrent identity/row-lock behavior. Migration upgrade/downgrade verification uses a disposable database, never the populated application DB. `scripts/verify_email_delivery_errors.py` briefly stops/pauses backend and resumes it in finally to verify n8n recovery.

## Limits and next stage

The provider handles UTF-8 fixture text, not OCR/PDF extraction. Processing is synchronous; actors are placeholders, there is no auth/RBAC or automatic reopening of FAILED cases. A storage-processing failure is preserved on a terminal case and flagged by n8n; replay does not create another case. The DB/filesystem cannot share a transaction, so interrupted commits may leave orphaned objects. Back up DB and files together. n8n UID/retention/replay operational limits are documented explicitly in n8n/README.md.

Milestone 3 will address real PDF/scanned documents, OCR benchmarks/provider selection, structured extraction and an evaluation dataset with accuracy metrics. LLM/OpenAI, RAG, outbound replies, CRM/ERP, PDF offers, RBAC and cloud deployment remain out of scope.


## Milestone 3: local dual OCR

Run `docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build` to enable PDF/PNG/JPEG/TIFF ingestion through two independent CPU OCR services. TXT fixtures remain supported. The UI shows both readings, normalization, business checks and a reasoned human-review form. Agreement is not proof of correctness; current policy conservatively requires document review.

See [Milestone 3 report](Milestone-3-raport.md), [OCR services](ocr-services/README.md), and `datasets/ocr/results/holdout-final/report.md`. HOLDOUT has been evaluated once after freezing configuration; do not rerun it or tune on its results.

## Milestone 7 — Company integrations and production readiness

See [deployment and operations](docs/milestone7/deployment.md), [security review](docs/milestone7/security-review.md) and [Milestone-7-raport.md](Milestone-7-raport.md). M7 adds company setup, authenticated roles, encrypted connector secrets, native IMAP/watched-folder intake, safe routing and filesystem/SFTP/signed-webhook delivery. Existing M5 security and M6 review gates remain mandatory. Production uses docker-compose.production.yml alone; only the reverse proxy publishes ports 80/443. Local protocol fixtures use generated synthetic credentials under ignored .runtime-m7/.
