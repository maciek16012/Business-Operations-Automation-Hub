# Business Operations Automation Hub — engineering case study

## Problem

Operational documents rarely arrive through one channel. Email attachments, upload forms, APIs and shared folders produce a mixture of readable PDFs, scans, tables and ambiguous content. A useful automation system must do more than extract a few fields: it must reject unsafe input, preserve originals, identify the document route, validate business data, surface uncertainty and deliver approved records without losing traceability.

I built BOAH as an independent portfolio project to demonstrate that complete workflow. It uses fictional companies and synthetic documents; no customer deployment or business savings are claimed.

## Solution

BOAH provides one self-hosted pipeline: intake → security → classification → extraction → deterministic validation → human review → approval → routing. Operators work in a dashboard connected to actual persisted cases, scans, document evidence, review tasks and audit events. The demo includes both successful processing and situations where automation must stop.

## Architecture

FastAPI services own workflow decisions and transaction boundaries. PostgreSQL stores cases, extracted values, document tables/cells, reviews, jobs and audit history. Alembic evolves that schema. An ObjectStorage boundary keeps physical filesystem paths out of domain logic. Tesseract and PaddleOCR run as separate CPU services; n8n provides orchestration and notification handoff. Next.js presents the existing operator workflow and company settings.

The [README diagram](../../README.md#architecture) shows the main boundaries. The system remains one application with integration workers; it is not an unnecessarily distributed microservice platform.

## Key engineering challenges

**Safe sequencing.** Parsing/OCR/classification must never precede a conclusive persisted SAFE scan. Security incidents and scanner outages create blocking evidence rather than silently passing into document processing. The real local tests include blocked inputs and approval attempts through the API.

**Extraction is not business truth.** Raw readings, normalized fields, validation results and human corrections have separate representations. Money uses Decimal; checksum, date, currency and arithmetic rules make predictable business decisions. Agreement between two OCR engines is useful evidence, not proof that both are correct.

**Efficient invoice routing.** Trustworthy native PDF text avoids unnecessary OCR. Scans use the primary engine; a second engine is invoked selectively when evidence fails safety checks. The resulting STP decision is distinct from downstream approval and integration delivery.

**Uncertainty without invented values.** Grid geometry and confidence can be incomplete. Missing cells remain visible and count against evaluation accuracy. Unsupported handwriting returns unresolved values instead of promoting ordinary printed OCR to a reliable handwriting claim.

**Failure-aware delivery.** Network calls cannot be made exactly once through a database transaction. Workers persist artifact snapshots and idempotency identities, bound retries and surface dead letters. Webhook payloads remain stable across attempts; receiving systems still need to honor idempotency keys.

## Security model

ClamAV, MIME/magic checks and bounded upload rules form the input boundary. Local identities use Argon2id and opaque HttpOnly sessions; production cookies are Secure/SameSite and browser writes require CSRF validation. ADMIN, OPERATOR, REVIEWER and VIEWER permissions are enforced in the backend. Disabling or changing a user revokes sessions, and last-administrator protection prevents accidental lockout.

Connector credentials are write-only AES-GCM records with per-record associated data. DNS/IP validation constrains outbound networking, redirects are not followed, production IMAP verifies TLS and SFTP requires a pinned host key. Restored IMAP records are checked at connection time too. Trusted named mounts and restricted templates protect filesystem destinations. The master key is an operational dependency kept separately from backups.

The [security review](../milestone7/security-review.md) records tests and remaining boundaries. Host/Docker administrators remain trusted; this project does not claim an independent pentest or security certification.

## Document intelligence and human-in-the-loop

The classifier is a versioned local heuristic based on content/layout signals. Its score is not a calibrated probability. Invoice handling preserves the established routing pipeline. Printed tables, handwritten-like tables, generic documents and UNKNOWN are review oriented. Table corrections preserve raw evidence, require a reason and use revision checks to reject stale changes. Unsafe documents cannot be unlocked by ordinary review.

There is no installed full model for real human handwriting recognition. The evaluation and demo use clearly labeled rasterized italic text as a proxy. A useful product behavior is the conservative response: leave the unsupported value unresolved and let a person confirm it against the original.

## Integrations and reliability

Native IMAP preserves message metadata, uses UID/UIDVALIDITY and reads bodies without marking messages processed prematurely. Message identity and content deduplication are separate. The watched folder waits for file stability before intake. Existing manual upload/API paths stay compatible.

Approved SAFE cases can route to filesystem/NAS mounts, SFTP or HMAC-signed webhooks. JSON/XLSX and originals are traceable artifacts. Failed integrations create review tasks and an existing durable notification outbox. The tested n8n sink acknowledges durable receipt; a final company email/channel must be configured separately.

## Production engineering

The standalone production Compose profile exposes only Caddy 80/443; DB, API, UI runtime, OCR, ClamAV, n8n and workers remain private. Application containers use UID10001, read-only root filesystems and restricted privileges. Upstream OCR/scanner requirements are documented rather than hidden.

Monitoring probes real dependencies and worker heartbeats. Maintenance backups contain database/object storage plus a schema/hash manifest, exclude the master key and require empty targets for restore. Retention uses dry-run confirmation, excludes active work and preserves database audit evidence. These are single-host operational foundations, not HA/PITR or a publicly proven deployment.

## Testing and measured results

The recorded M7 regression passed 281 SQLite tests with two PostgreSQL-only skips and all 283 PostgreSQL tests; nine n8n tests passed. Security tests cover negative paths, and actual local protocols exercise IMAP/SFTP/webhooks. Restore independently checked 140 stored objects and four encrypted records; production images passed HTTPS with an explicitly trusted local CA. M8 release checks are recorded separately in the [report](../milestone8/Milestone-8-raport.md).

On the preserved 20-document synthetic invoice HOLDOUT, STP was 19/20 (95%) with zero observed false accepts. On the 20-document classification/table HOLDOUT, classification was 85%, table structure 75%, cell accuracy 30.56%, numeric-cell accuracy 25%, and review rate 95%. Those numbers expose table limitations instead of presenting a synthetic result as universal accuracy. Historical HOLDOUTs are unchanged and are never seeded into the demo. See [evaluation notes](EVALUATION.md).

## Reproducible presentation

A Windows one-command script creates a dedicated local project, private service network, random ignored credentials and independent synthetic fixtures. A guarded reset checks the project marker, resolved paths and volume ownership before deleting only demo resources. The walkthrough shows a real login, document, review, guarded approval, archive/exports/webhook and audit. The recording script supports a short later OBS demonstration; no film or release publication is required.

## Limitations and future improvements

Single-company local identities, no SSO/MFA or multi-tenant SaaS. Real handwriting and difficult table layouts need separate work and new independent datasets. No manual reconstruction of missing table structure is provided. Backup authenticity/key recovery and external destination/n8n backup remain operational responsibilities. Durable delivery snapshots need a future lifecycle policy. Public DNS/ACME and a customer deployment are not validated by a local smoke test.

Future work could add independently evaluated layout/handwriting providers, unseen-template datasets, confidence calibration, SSO/MFA and stronger operational recovery. It must not retune the existing pipeline against historical HOLDOUTs.
