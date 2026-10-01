# Configuration reference

Configuration is deployment-owned; company/source/destination/routing settings are persisted through the authenticated UI/API. This reference describes existing defaults and shipped profiles, not new production guarantees.

## Profiles and required values

| Profile | Entry point | Required inputs / exposure |
|---|---|---|
| Portfolio demo | `scripts/demo/start_demo.ps1`, `docker-compose.demo.yml` | Generates independent random secrets in ignored `.runtime-demo/demo.env`; loopback HTTP 3080 only. Fixed project `boah-portfolio-demo`. |
| Development | `.env.example`, `docker-compose.yml` plus existing OCR/security overlays | Copy example to ignored `.env`; development credentials are examples, not production secrets. Consult [M1 verification](verification.md). |
| Production | `deploy/milestone7/production.env.example`, `docker-compose.production.yml` | Ignored `.env.production`: domain, strong PostgreSQL password, initial admin/password, scoped service token, master-key host file and named intake/archive paths. Only Caddy publishes 80/443. [Detailed deployment](milestone7/deployment.md). |

Production `BOAH_MASTER_KEY_PATH` is the **host file** mounted as a Docker secret. The application reads `BOAH_MASTER_KEY_FILE=/run/secrets/boah_master_key`. Use a random base64-encoded 32-byte key with protected permissions. Preserve it independently alongside backups; losing/changing it makes saved connector secrets unreadable. Do not use demo keys or publish env files. The initial admin is bootstrapped only when identities do not already exist.

## Application and security

| Variable | Default / profile behavior |
|---|---|
| `APP_ENV`, `PUBLIC_URL`, `BACKEND_CORS_ORIGINS` | Development / local URL by default; production compose sets matching HTTPS domain. |
| `AUTH_ENABLED`, `AUTH_COOKIE_SECURE`, `AUTH_SESSION_HOURS` | Auth true; secure-cookie default false for local HTTP, production true; session 8 hours. |
| `BOAH_INITIAL_ADMIN_EMAIL`, `BOAH_INITIAL_ADMIN_PASSWORD` | Empty by default; supply protected bootstrap values. |
| `BOAH_SERVICE_TOKEN` | Scoped n8n backend credential, generated locally; never store a value in tracked workflow JSON. |
| `DATABASE_URL`, `STORAGE_BACKEND`, `STORAGE_PATH` | Async PostgreSQL, filesystem abstraction, `/data/documents`; compose owns volumes. |
| `SECURITY_PREFLIGHT_ENABLED`, `SECURITY_FAIL_CLOSED` | Both true; fail-open is rejected by configuration validation. |
| `MAX_UPLOAD_BYTES`, `SECURITY_MAX_ATTACHMENT_BYTES` | 5 MiB each. |
| `SECURITY_ALLOWED_MIME_TYPES` | PDF, PNG, JPEG, TIFF, plain text; MIME alone does not establish safety. |
| `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_TIMEOUT_SECONDS` | Application defaults localhost / 3310 / 30 seconds; compose host `clamav`. |
| `ADAPTIVE_EXTRACTION_ENABLED` | True; requires persisted SAFE scan. |

## OCR and invoice routing

| Variable | Behavior |
|---|---|
| `OCR_ENABLED` | Default false; demo/production true. |
| `OCR_TESSERACT_URL`, `OCR_PADDLE_URL` | Separate private OCR endpoints in compose. |
| `OCR_TESSERACT_PROFILE`, `OCR_PADDLE_PROFILE` | Application default baseline; demo/production explicitly use frozen `orientation`. |
| `STP_ENABLED`, `STP_PRIMARY_OCR_PROVIDER` | Default false / paddle; demo/production STP true. |
| `STP_NATIVE_*`, `STP_REQUIRE_ZERO_CRITICAL_FALSE_ACCEPTS` | Existing frozen invoice policy; M8 does not tune thresholds. See [evaluation](portfolio/EVALUATION.md). |

Do not tune the pipeline using historical HOLDOUT or interpret synthetic seed success as a new benchmark. No new OCR/handwriting model is introduced.

## Connectors, notifications and optional settings

`MOUNTED_ROOTS` maps deployment-owned names to mounted directories. Filesystem sources/destinations use those names, not arbitrary host paths. `CONNECTOR_NETWORK_ALLOWLIST` is a JSON list of narrowly justified trusted hosts/CIDRs; outbound resolution still receives SSRF checks. Production `CONNECTOR_ALLOW_PLAINTEXT_TEST=false` is enforced; the demo allows only its private `greenmail` / `webhook` fixtures.

Configure IMAP host/port/user/TLS/folder, folder stability/poll interval, archive templates, pinned SFTP host key, webhook target/HMAC and routing predicates in Settings. Secret inputs are write-only and encrypted at rest. A restore does not exempt production IMAP from TLS validation. Test connection creates a durable job; inspect its final result rather than treating PENDING as success.

`DELIVERY_MAX_ATTEMPTS=5`, `DELIVERY_RETRY_SECONDS=30` normally; demo retry delay is 2 seconds. Review notifications default enabled, with the existing n8n webhook and 15-second timeout. Import the sanitized template and bind its runtime credential; [demo startup](demo/DEMO-GUIDE.md) automates this in the isolated profile. SFTP/public email/real NAS are optional and are not prerequisites for portfolio demo startup.

## Backup and release boundaries

Use existing [backup/restore instructions](milestone7/deployment.md), keeping database, objects, n8n state and the separately secured master key consistent. M7 includes a verified local restore; M8 does not claim off-site recovery or hosted CI. [Release checklist](portfolio/RELEASE-CHECKLIST.md) distinguishes checked local gates from manual publishing decisions.
