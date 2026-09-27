# ASTRA HANDOFF — Milestone 2
## Email Ingestion + n8n Orchestration

Project: **Business Operations Automation Hub**

Repository: `C:\AI\BusinessOperationsAutomationHub`

Milestone 1 is complete and verified. Do not rebuild or redesign the existing working core unless a concrete defect blocks this milestone.

The existing system already provides a working vertical slice:

```text
UPLOAD
→ INGEST
→ EXTRACT
→ NORMALIZE
→ VALIDATE
→ REVIEW
→ APPROVE
→ EXPORT
→ AUDIT
```

Milestone 2 adds a real business entry channel:

```text
EMAIL
→ n8n
→ normalized inbound message
→ attachments
→ BOAH API
→ existing processing pipeline
→ READY / REVIEW_REQUIRED
→ audit + operator UI
```

The purpose is to turn the application into a real office/business-process automation system without destabilizing Milestone 1.

---

## 1. Primary goal

Implement reliable inbound email ingestion through n8n and integrate it with the existing Milestone 1 backend.

The final system must be able to receive a business email, preserve important message metadata and body, transfer attachments to the backend, create exactly one business case for one inbound message, run the existing pipeline, and expose the result in the existing operator UI.

The integration must be safe against accidental duplicate processing.

Do not implement OCR/LLM in this milestone.

---

## 2. Existing Milestone 1 must remain stable

Preserve existing behavior, especially:

- controlled state machine,
- LocalFilesystemStorage through ObjectStorage,
- PostgreSQL,
- SHA-256 attachment handling,
- existing within-case duplicate detection,
- deterministic extraction provider,
- normalization,
- validation engine,
- NIP validation,
- human review,
- backend-enforced approval rules,
- JSON/XLSX exports,
- audit trail,
- frontend case list/detail,
- existing tests,
- Docker-based local environment.

Regression is not acceptable. Run the existing test suite before and after implementation.

---

## 3. Scope of Milestone 2

Implement:

1. n8n as part of the local Docker environment,
2. persistent n8n data,
3. generic IMAP-based inbound email workflow,
4. safe transfer of message metadata and attachments to the backend,
5. backend model/API support for inbound email,
6. message-level idempotency,
7. attachment-level reuse of existing SHA-256 logic,
8. audit events for email ingestion,
9. case/source visibility in the UI,
10. useful n8n error handling,
11. importable/exported workflow JSON committed to the repository,
12. deterministic local/integration test path that does not require committing mailbox credentials,
13. documentation for connecting a real mailbox,
14. real end-to-end verification when credentials/environment permit.

Explicitly do NOT add production OCR, LLM extraction, RAG, CRM, ERP, PDF generation, RBAC, cloud deployment or unrelated automation.

---

## 4. Target architecture

```text
IMAP mailbox
    ↓
n8n Email Trigger (IMAP)
    ↓
normalize metadata/body/attachments
    ↓
BOAH inbound-email API
    ↓
message idempotency check
    ├── replay → safe no-op + audit
    └── new → create Case + Source/InboundMessage
                 ↓
            persist attachments
                 ↓
            existing M1 pipeline
                 ↓
        READY / REVIEW_REQUIRED
```

n8n orchestrates. FastAPI/domain remains the source of truth for domain state and business rules.

Do not duplicate NIP validation, monetary validation, approval rules or state-machine logic in n8n.

---

## 5. n8n service

Add n8n to Docker Compose.

Requirements:

- use an official public n8n image,
- pin a version or document a deliberate version policy,
- persistent n8n volume,
- consistent timezone,
- no credentials committed to Git,
- backend reachable using Docker service networking,
- usable local n8n UI,
- startup through normal `docker compose up -d --build` flow.

Do not add MinIO.

Document the local n8n URL and setup behavior.

---

## 6. Workflow files in repository

Create a clear location such as:

```text
n8n/
  workflows/
    inbound-email.json
    inbound-email-error.json
  README.md
```

Workflow JSON must be importable/exportable and must not contain secrets.

If exported JSON contains credential IDs/references, sanitize them appropriately and document how the user binds credentials after import.

---

## 7. Generic IMAP ingestion

Use n8n's IMAP email trigger for the real inbound workflow.

Do not bind architecture to Gmail, Outlook or another single provider.

Capture useful metadata where available:

- RFC Message-ID,
- From,
- To,
- Cc if useful,
- Reply-To if useful,
- Subject,
- received/sent timestamp,
- plain-text body,
- HTML body if retained,
- attachment filenames,
- attachment MIME types.

Do not map arbitrary headers into uncontrolled domain fields.

---

## 8. Message identity and idempotency

Message-level idempotency is mandatory.

Existing attachment SHA-256 deduplication is not sufficient because the same email may be replayed/re-fetched.

Create a backend representation such as `InboundMessage` (or an equally clear model) containing at least:

- id,
- source/provider type,
- external_message_id / RFC Message-ID,
- sender,
- recipients where useful,
- subject,
- received timestamp,
- text body,
- HTML body if retained,
- processing status,
- related case_id,
- created_at,
- updated_at.

Use a database uniqueness constraint for stable source identity, preferably conceptually:

```text
(source_type, external_message_id)
```

If Message-ID is missing/untrustworthy, implement and document a stable fallback fingerprint based on message characteristics.

Do not identify messages by subject or attachment filename alone.

Repeated delivery of the same message must not create a second case.

For a replay:

- return a deterministic API response,
- identify the existing case where possible,
- record the idempotency decision/audit event,
- perform no duplicate business processing,
- let n8n treat the result as a successful idempotent no-op rather than an error.

Test this thoroughly, including concurrency where practical.

---

## 9. Inbound email API contract

Create a dedicated backend contract for n8n, conceptually for example:

```text
POST /api/v1/inbound/email
```

The exact route may follow existing conventions.

It must accept:

- normalized email metadata,
- message body,
- zero or more attachments.

`multipart/form-data` is acceptable. A carefully designed two-step protocol is also acceptable if safer/easier to make idempotent. Choose one and document the decision.

The endpoint must:

1. validate the inbound payload,
2. enforce message idempotency in PostgreSQL,
3. create/store the inbound message/source,
4. create exactly one Case for a new message,
5. persist attachments through ObjectStorage,
6. calculate/reuse SHA-256 logic,
7. run the existing processing pipeline,
8. write audit events,
9. return a structured machine-readable result.

Suggested semantics:

```json
{
  "result": "created",
  "case_id": "...",
  "public_case_id": "...",
  "message_id": "...",
  "status": "REVIEW_REQUIRED"
}
```

Replay example:

```json
{
  "result": "duplicate",
  "case_id": "...",
  "public_case_id": "...",
  "message_id": "...",
  "status": "REVIEW_REQUIRED"
}
```

Expected replay is not an HTTP 500 condition.

---

## 10. Source model

Extend existing source concepts rather than replacing them.

Email-created cases must clearly expose:

```text
source = email
```

and be linked to the corresponding inbound message.

Do not stuff full email bodies into an opaque generic metadata blob if a dedicated model is cleaner.

---

## 11. Deterministic mapping into Case

Milestone 2 does not perform intelligent LLM interpretation.

Use deterministic mapping only:

- subject may seed `request_title`,
- sender address may seed `customer_email`,
- sender display name may seed `customer_name` when safe,
- plain-text body is preserved as source material,
- attachments enter the existing attachment/extraction flow.

If required business fields cannot be deterministically derived, `REVIEW_REQUIRED` is the correct result.

Do not fake semantic understanding.

---

## 12. Email body safety

Preserve at least:

- text body,
- original subject,
- sender,
- external Message-ID,
- timestamp.

If HTML is retained:

- do not render untrusted HTML directly,
- sanitize or show escaped/plain content,
- avoid an XSS path.

The operator must be able to inspect source context safely.

---

## 13. Attachments

For every attachment:

- preserve original filename as metadata,
- preserve MIME type,
- calculate SHA-256,
- persist through ObjectStorage,
- associate with the single case created for the message,
- reuse existing within-case duplicate rules,
- audit storage/duplicate decisions.

A replay of the same inbound message must not create duplicate attachment rows or duplicate business processing.

Do not trust filenames as storage paths.

Support 0, 1 and multiple attachments. One email creates one case, not one case per attachment.

---

## 14. Unsupported attachment behavior

Reuse existing upload protections and limits.

For an unsupported attachment:

- do not silently discard it,
- return/store a structured processing result,
- record an audit/validation issue,
- prefer review over crashing the whole workflow when safe.

Do not implement antivirus in this milestone.

---

## 15. n8n responsibilities

The n8n workflow should stay thin. It should:

1. receive email via IMAP,
2. normalize the required metadata,
3. expose attachments as binary data,
4. call the BOAH inbound-email API,
5. inspect the structured response,
6. log useful execution context,
7. handle predictable failures,
8. remain safe to replay.

It must NOT:

- validate NIP,
- decide READY vs REVIEW_REQUIRED,
- validate monetary rules,
- write directly to PostgreSQL,
- write directly to BOAH filesystem storage,
- bypass backend state transitions.

---

## 16. Error handling and delivery semantics

Implement useful n8n failure handling, ideally with a dedicated Error Trigger workflow or another idiomatic mechanism.

Distinguish at least:

- backend unavailable,
- backend timeout,
- invalid payload,
- expected duplicate/idempotent response,
- unsupported attachment/business review outcome,
- unexpected workflow error.

Do not create infinite retry loops.

Design practical **at-least-once delivery with idempotent backend processing**, not a fake distributed exactly-once system.

Because the backend is idempotent, bounded replay/retry must not create multiple cases.

Document this decision explicitly.

---

## 17. Audit

Add typed email-ingestion audit events, for example:

```text
EMAIL_RECEIVED
EMAIL_DUPLICATE_IGNORED
EMAIL_CASE_CREATED
EMAIL_ATTACHMENT_STORED
EMAIL_INGESTION_FAILED
```

Use the existing audit architecture.

Do not record secrets in audit payloads.

---

## 18. Frontend

Extend the current UI minimally.

For email-origin cases show, where appropriate:

- source: email,
- sender,
- subject,
- received timestamp,
- external Message-ID,
- safe plain-text body,
- attachments.

Do not redesign the app.

Existing review/correction/approval/export behavior must continue unchanged.

---

## 19. Deterministic local demo/test path

Automated tests must not depend on a real Gmail/Outlook/network connection.

Provide a deterministic local path, preferably a script such as:

```text
scripts/demo_email_ingestion.py
```

or an equivalent fixture workflow.

It should prove:

1. first delivery creates a case,
2. second delivery of the same Message-ID creates no additional case,
3. 0/1/multiple attachment variants work,
4. the created case enters the existing pipeline,
5. the case is visible through API/UI.

If useful, provide a manual n8n fixture workflow in addition to the real IMAP workflow, but do not replace the real IMAP workflow with only a mock.

---

## 20. Real mailbox readiness

Prepare the workflow so that a real IMAP mailbox can be connected using n8n credentials without code changes.

If credentials are available locally during implementation, perform a real E2E:

```text
send email
→ mailbox
→ n8n
→ BOAH API
→ case
→ attachment storage
→ existing pipeline
→ UI
```

If credentials are not available, do not invent/hard-code them. Document exact binding steps and verify all non-credential layers with deterministic fixtures.

---

## 21. Secrets

Never commit:

- mailbox password,
- app password,
- OAuth tokens,
- n8n encryption key,
- SMTP/IMAP credentials.

Use `.env` and n8n credential storage. Add non-secret placeholders to `.env.example` where appropriate.

---

## 22. n8n persistence

Persist n8n configuration/workflow state through a Docker volume.

n8n state is not the canonical business database. BOAH business data remains in PostgreSQL.

---

## 23. Database migration

Create an Alembic migration for new email-ingestion tables/constraints.

Verify a fresh schema can be reproduced and run appropriate:

```text
upgrade → downgrade → upgrade
alembic check
```

where practical, consistent with Milestone 1 quality standards.

---

## 24. Tests

Add real tests, not count-padding tests.

Required coverage includes at least:

### Inbound email
- new email creates one case,
- source=email,
- metadata/body persistence,
- 0 attachments,
- 1 attachment,
- multiple attachments.

### Idempotency
- same Message-ID twice,
- same Message-ID transported/replayed again,
- missing Message-ID fallback fingerprint,
- concurrent/replayed ingestion where practical,
- exactly one case created.

### Attachments
- existing SHA-256 behavior preserved,
- filename change does not defeat content dedupe within the business rules,
- unsafe filenames stay safe,
- upload constraints apply.

### Pipeline
- email-origin case runs extraction/normalization/validation,
- incomplete email becomes REVIEW_REQUIRED,
- deterministic valid fixture can become READY,
- human review and approval still work.

### Audit
- receipt/create events,
- replay event,
- attachment events,
- failure event where appropriate.

### API
- structured created response,
- structured duplicate response,
- invalid payload handling,
- malformed metadata handling,
- backend approval/state rules remain enforced.

All Milestone 1 tests must remain green.

---

## 25. n8n workflow verification

Verify:

- workflow imports successfully,
- no credentials are committed,
- binary attachments transfer correctly,
- metadata mapping is correct,
- backend response is parsed,
- duplicate response is treated as success,
- error path works,
- workflow never writes directly to DB/storage,
- replay is safe.

Commit sanitized workflow JSON.

---

## 26. Docker verification

Final Compose includes at least:

- postgres,
- backend,
- frontend,
- n8n.

Keep required volumes explicit.

Verify:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Expected final state: PostgreSQL and backend healthy, frontend available, n8n available.

---

## 27. Quality gates

Run the full existing and new quality suite.

Backend:

- pytest default variant,
- PostgreSQL test variant,
- Ruff format check,
- Ruff lint,
- mypy,
- Alembic checks.

Frontend:

- lint,
- typecheck,
- production build.

Infrastructure:

- Compose validation,
- container startup.

n8n:

- workflow import/configuration verification,
- deterministic fixture execution where practical.

Do not finish with known red tests.

---

## 28. Documentation

Update README and architecture docs.

Document:

- why n8n is used,
- why business logic stays in FastAPI,
- email architecture,
- generic IMAP setup,
- inbound-email API contract,
- idempotency model,
- attachment flow,
- retry/replay semantics,
- workflow import and credential binding,
- deterministic demo path,
- known limitations.

Update the Mermaid architecture diagram.

Add a focused `n8n/README.md`.

---

## 29. Portfolio evidence to collect

In the final report record real measured evidence:

- total automated tests,
- PostgreSQL test result,
- replay/idempotency result,
- number of cases created from repeated identical deliveries,
- number of attachments processed,
- n8n workflow result,
- Docker service status,
- demonstration case ID,
- audit event count for the demo,
- resulting case status,
- tested backend-unavailable/replay behavior.

Do not fabricate metrics.

---

## 30. Acceptance scenario

Use a repeatable scenario equivalent to:

```text
Message-ID: <boah-demo-001@example.test>
From: Jan Kowalski <jan@example.test>
Subject: Zapytanie ofertowe — modernizacja biura

Dzień dobry,
proszę o przygotowanie wyceny zgodnie z załączoną specyfikacją.
```

with at least one deterministic test attachment.

First delivery must result in:

```text
n8n receives message
→ backend accepts new message
→ one Case created
→ attachment stored
→ existing pipeline runs
→ READY or REVIEW_REQUIRED according to real validation
→ email audit events present
```

Replay the same Message-ID. Expected:

```text
backend identifies replay
→ zero additional Cases
→ no duplicate attachment/business processing
→ structured idempotent response
→ n8n execution succeeds as a no-op
```

If the case is REVIEW_REQUIRED, verify:

```text
operator inspects email context
→ corrects data
→ validation reruns
→ READY
→ APPROVED
→ existing JSON/XLSX exports still work
```

---

## 31. Explicitly out of scope

Do NOT implement now:

- OCR,
- PDF text extraction,
- LLM/OpenAI/local LLM,
- RAG,
- automatic outbound customer replies,
- CRM,
- ERP,
- Power Query integration,
- PDF offers,
- broad webhook ecosystem,
- RBAC,
- public production deployment,
- multi-tenancy,
- Kubernetes,
- extra queue infrastructure merely for appearance.

---

## 32. Important design rule

Keep this separation:

```text
n8n:
WHEN and WHERE the process moves

FastAPI/domain:
WHAT the business operation means
and WHETHER it is allowed
```

Critical business rules must not exist only inside workflow nodes.

---

## 33. Final verification

Before completion:

1. inspect Git diff/status,
2. verify Milestone 1 regression suite,
3. run complete backend tests,
4. run PostgreSQL tests,
5. run Ruff/mypy,
6. run frontend lint/typecheck/build,
7. verify Alembic,
8. verify Compose,
9. verify n8n startup,
10. import/verify workflow,
11. execute deterministic email demo,
12. replay the same message,
13. prove exactly one case exists,
14. inspect case/audit through API,
15. inspect case through UI,
16. verify review/approval flow,
17. verify JSON/XLSX still work,
18. update documentation to match reality.

Fix discovered issues before declaring completion.

---

## 34. Final report

Create:

```text
Milestone-2-raport.md
```

Include:

- implemented scope,
- architectural decisions,
- database changes,
- inbound email API contract,
- n8n workflows,
- exact test/quality results,
- deterministic demo evidence,
- real IMAP E2E result if credentials were available,
- replay/idempotency evidence,
- Docker status,
- known limitations,
- intentionally deferred Milestone 3 scope,
- exact reproduction commands.

Do not merely say the milestone is complete. Provide evidence.

---

## 35. Planned Milestone 3 — context only

Do not implement it now.

Milestone 3 will focus on:

```text
real PDF/scanned documents
→ OCR provider benchmark
→ selected OCR implementation
→ structured extraction
→ evaluation dataset
→ extraction accuracy metrics
```

Milestone 2 email ingestion must remain independent of any specific OCR or AI provider.
