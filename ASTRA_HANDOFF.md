# ASTRA HANDOFF — Milestone 1

## Project

**Business Operations Automation Hub**

This repository is a prepared starter for a portfolio-grade business process automation system.

Do not rebuild the repository from scratch. The basic structure, configuration, models/contracts, frontend skeleton, Docker setup, sample data and documentation scaffolding are already present.

Your task is to complete **Milestone 1** as a working, tested vertical slice.

---

# 1. Business goal

The system automates a typical small/medium-company workflow for incoming business inquiries and documents.

Target flow:

```text
EMAIL / MANUAL UPLOAD
        ↓
INGESTION
        ↓
DEDUPLICATION
        ↓
DOCUMENT EXTRACTION
        ↓
CLASSIFICATION
        ↓
NORMALIZATION
        ↓
VALIDATION
        ↓
HUMAN REVIEW
        ↓
APPROVAL
        ↓
EXPORT: XLSX / JSON / later PDF / webhook
        ↓
AUDIT
```

Later milestones will add real email ingestion, n8n workflows, OCR benchmarking, real document OCR, LLM-assisted extraction, confidence scoring, optional OpenAI-compatible providers and more advanced exports.

Do not implement those future milestones prematurely.

---

# 2. Milestone 1 objective

Deliver a complete working vertical slice:

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

At the end of this milestone it must be possible to:

1. create a case,
2. upload one or more documents,
3. store original files,
4. calculate SHA-256 for attachments,
5. detect duplicate documents,
6. extract basic structured data using the development extraction provider,
7. store raw and normalized values separately,
8. run deterministic validation,
9. assign the case to READY or REVIEW_REQUIRED,
10. inspect the case in the admin UI,
11. inspect validation issues and extracted fields,
12. manually correct case data,
13. record all manual changes in the audit trail,
14. approve or reject a case,
15. prevent approval when blocking validation issues remain,
16. export approved cases to JSON,
17. export approved cases to XLSX,
18. record exports in the database and audit trail,
19. demonstrate the workflow with sample fixtures,
20. run a meaningful automated test suite successfully.

This should be a real working application, not a mock UI.

---

# 3. Existing stack

Keep the existing stack unless a genuine technical problem requires a small correction.

## Backend

- Python
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- PostgreSQL

## Frontend

- Next.js
- TypeScript

## Storage

Milestone 1 uses:

**LocalFilesystemStorage**

The repository intentionally does **not** use MinIO in this milestone.

Files must be stored through the existing storage abstraction, not by calling filesystem operations directly from business logic.

Default container path:

```text
/data/documents
```

Configuration:

```text
STORAGE_BACKEND=filesystem
STORAGE_PATH=/data/documents
```

The path is backed by a persistent Docker volume.

Preserve the `ObjectStorage` abstraction so that a future milestone can add an S3-compatible implementation without changing domain/business logic.

Do not reintroduce MinIO in Milestone 1.

## Export

- JSON
- XLSX using openpyxl

## Infrastructure

- Docker Compose

Expected services:

- backend
- frontend
- postgres

## Tests

- pytest
- integration tests where useful

---

# 4. Repository philosophy

Do not spend time replacing working boilerplate merely because you would structure it differently.

Prefer extending the existing starter.

You may refactor something when:

- it is broken,
- it blocks correct implementation,
- it creates a serious architectural problem,
- a small change materially improves testability or correctness.

Avoid cosmetic rewrites.

Do not add unnecessary enterprise abstractions.

Do not introduce microservices.

Do not add Kubernetes.

Do not add paid infrastructure dependencies.

---

# 5. Domain model

Use and complete the domain model already present in the repository.

The system should contain at least the following entities.

## Case

Representative fields:

- internal ID
- public case identifier
- customer_name
- customer_email
- company_name
- tax_id
- request_title
- request_description
- requested_deadline
- currency
- estimated_value
- status
- created_at
- updated_at

Public case identifiers must be deterministic enough for normal business use and unique.

Example:

```text
CASE-2026-000042
```

Do not use fragile client-side numbering.

## Source

Represents where a case came from.

Milestone 1 needs at least:

- manual_upload
- api

Email will be added later.

## Attachment

Store at least:

- original filename
- MIME type
- size
- SHA-256
- storage key/path
- created timestamp
- relation to case

Duplicate detection must not rely on filenames alone.

## ExtractedField

Store at least:

- field_name
- raw_value
- normalized_value
- confidence if available
- source attachment
- extraction method/provider
- timestamps if appropriate

Raw and normalized values must remain distinguishable.

## ValidationIssue

Store at least:

- code
- severity
- field
- human-readable message
- status/resolved state
- timestamps where useful

Severities:

```text
INFO
WARNING
ERROR
CRITICAL
```

## ReviewDecision

Track:

- approve
- reject
- manual correction
- comment/reason
- timestamp
- actor placeholder if the current auth model does not yet exist

## Export

Track:

- export type
- generated artifact reference
- timestamp
- success/failure if useful

## AuditEvent

Every meaningful state-changing operation must be recorded.

At minimum:

- case created,
- attachment uploaded,
- duplicate detected,
- extraction performed,
- validation performed,
- status changed,
- field manually corrected,
- validation issue resolved,
- case approved,
- case rejected,
- export generated,
- processing failure.

---

# 6. State machine

Use a controlled state machine.

Statuses:

```text
RECEIVED
PROCESSING
REVIEW_REQUIRED
READY
APPROVED
EXPORTED
DUPLICATE
FAILED
```

Do not allow arbitrary transitions.

Define valid transitions centrally and test them.

The exact transition implementation may be adjusted if necessary, but behavior must remain deterministic.

Examples of expected behavior:

```text
RECEIVED → PROCESSING
PROCESSING → READY
PROCESSING → REVIEW_REQUIRED
PROCESSING → DUPLICATE
PROCESSING → FAILED

REVIEW_REQUIRED → READY
REVIEW_REQUIRED → FAILED

READY → APPROVED
APPROVED → EXPORTED
```

Reject invalid transitions explicitly.

---

# 7. Ingestion

Provide a working API flow for creating a case and uploading one or more attachments.

Requirements:

- persist the case,
- persist attachments,
- store original files through ObjectStorage,
- calculate SHA-256,
- store file metadata,
- detect duplicates,
- generate audit events,
- return predictable API responses.

Use sensible HTTP status codes.

Do not put business logic directly in FastAPI route handlers.

Routes should orchestrate application services.

---

# 8. Duplicate detection

Duplicate detection is a real business requirement.

At minimum:

- SHA-256 must be used,
- duplicate files must be detectable even if the filename changes,
- behavior must be deterministic,
- tests must cover duplicate upload scenarios.

Choose and document whether a duplicate is defined globally or within a business-relevant scope.

Do not silently process an exact duplicate as a fresh document.

Record the duplicate decision in audit history.

---

# 9. Extraction architecture

Do not implement a full OCR or LLM pipeline yet.

Preserve or complete an `ExtractionProvider` abstraction suitable for future providers such as:

- OCR provider,
- local LLM provider,
- OpenAI-compatible provider,
- structured document provider.

For Milestone 1 implement a deterministic development provider.

It may operate on:

- text fixtures,
- structured sample files,
- predictable test inputs.

Its purpose is to make the entire pipeline work end-to-end and test the architecture.

Do not hardcode extraction logic directly into API endpoints.

The extraction provider must not decide business validity.

---

# 10. Normalization

Raw extraction output must be normalized by a separate layer.

Examples:

```text
"12 500,00 PLN"
```

becomes logically equivalent to:

```text
Decimal("12500.00")
currency = "PLN"
```

Normalize at least the fields required by the provided sample scenarios.

Use decimal-safe money handling.

Do not use binary floating point for monetary business rules.

Keep normalization testable independently from extraction.

---

# 11. Validation engine

Create a deterministic validation layer.

AI/extraction output is not authoritative.

At minimum implement and test rules for:

- customer/company presence,
- valid email syntax when email is provided,
- sensible requested deadline parsing/validation,
- estimated value >= 0 when present,
- supported currency,
- Polish NIP syntax and checksum when tax_id is provided,
- required fields appropriate to the implemented case type,
- duplicate attachment detection,
- malformed or inconsistent normalized values.

Validation produces `ValidationIssue` records.

Blocking rules must prevent approval.

After validation, the application must be able to determine whether a case should enter:

```text
READY
```

or:

```text
REVIEW_REQUIRED
```

Do not let an extraction provider or future AI provider directly mark a case as business-valid.

---

# 12. Polish NIP validation

Implement real checksum validation rather than regex-only validation.

Tests must include:

- valid NIP,
- invalid checksum,
- formatting with separators/spaces if normalization supports it,
- invalid length,
- nonnumeric invalid input.

Keep the algorithm isolated and reusable.

---

# 13. Human review

Build a functional review workflow.

The frontend must make it possible to inspect:

- case metadata,
- status,
- attachments,
- extracted fields,
- normalized values where useful,
- validation issues,
- audit trail.

The operator must be able to:

- correct editable business data,
- save corrections,
- rerun validation,
- approve when valid,
- reject with a reason.

Manual changes must produce audit events.

Do not silently overwrite extracted/raw source data when a human changes the normalized/business value.

Preserve traceability.

---

# 14. Approval rules

Approval is a controlled business action.

A case must not be approved when unresolved blocking validation issues exist.

The backend must enforce this rule.

Do not rely only on disabled frontend buttons.

Test attempts to bypass approval through the API.

---

# 15. JSON export

For APPROVED cases implement a useful JSON export.

It should contain a stable structured representation of the approved business data.

Do not merely serialize arbitrary ORM internals.

Record the export.

Add an audit event.

Return/download it through a sensible API route.

Test it.

---

# 16. XLSX export

For APPROVED cases implement an XLSX export using openpyxl.

The workbook must be useful to a business user, not a raw database dump.

Minimum sheets:

## Summary

Include:

- Case ID
- customer
- company
- NIP
- title
- description
- deadline
- currency
- estimated value
- status

## Attachments

Include relevant attachment metadata.

## Validation

Include validation history/issues relevant to the case.

## Audit

Include readable audit entries in chronological order.

Formatting expectations:

- readable headers,
- sensible column widths,
- dates formatted properly,
- currency/value cells formatted properly,
- freeze panes where useful,
- basic table-like readability,
- no unnecessary visual decoration.

Record the export and audit event.

Test workbook creation and key cell values.

---

# 17. Local filesystem storage

Implement or complete `LocalFilesystemStorage`.

Requirements:

- base directory comes from configuration,
- directory creation is safe,
- generated storage keys avoid filename collisions,
- path traversal must not be possible,
- callers use the ObjectStorage abstraction,
- original filename remains metadata rather than being trusted as a filesystem path,
- retrieval works for export/download scenarios if required,
- deletion can be included if useful but is not a Milestone 1 priority.

Do not couple domain code to `/data/documents`.

Only the filesystem storage implementation should know the physical storage path.

Add tests for storage-key/path safety where practical.

---

# 18. REST API

The REST API must be practical for later n8n integration.

Provide predictable endpoint behavior.

At minimum support flows equivalent to:

- create case,
- upload attachment(s),
- list cases,
- get case details,
- update reviewable data,
- rerun validation,
- approve case,
- reject case,
- generate/fetch JSON export,
- generate/fetch XLSX export,
- view audit events.

Exact URL design may follow the repository's existing conventions.

FastAPI OpenAPI documentation must remain usable.

Use structured errors.

---

# 19. Frontend

The frontend is an admin/workflow UI, not a marketing site.

Keep visual design clean and professional, but prioritize working workflow.

Required views:

## Cases list

Display at least:

- case identifier,
- customer/company,
- title,
- status,
- created/updated time where useful.

## Case detail

Display:

- business fields,
- attachments,
- extracted fields,
- validation issues,
- audit history.

Provide actions:

- edit/correct data,
- rerun validation,
- approve,
- reject,
- export JSON,
- export XLSX when allowed.

Provide clear feedback for API errors and invalid actions.

Do not spend the majority of the milestone polishing CSS.

---

# 20. Docker Compose

The repository's current Milestone 1 Compose setup should use:

- postgres
- backend
- frontend

MinIO is intentionally absent.

The backend stores documents in a persistent Docker volume mounted at:

```text
/data/documents
```

Expected workflow should be as close as practical to:

```powershell
docker compose up -d --build
```

Services should become usable without undocumented manual container surgery.

Use healthchecks where already provided or useful.

Do not add MinIO.

Do not require Docker registry authentication beyond normal public base images.

---

# 21. Database migrations

Use Alembic properly.

Create/update migrations required for the implemented schema.

A fresh environment must be able to create the database schema reproducibly.

Do not rely on manually created tables.

Document the migration/startup behavior.

---

# 22. Sample data

Use and expand `sample_data/` where helpful.

Provide deterministic examples covering at least:

1. valid case,
2. missing required data,
3. invalid Polish NIP,
4. duplicate document,
5. invalid/negative monetary value,
6. case requiring human review.

Fixtures should support both tests and a manual demo.

Do not use real personal data.

---

# 23. Tests

Build meaningful tests.

Do not add symbolic tests merely to increase test count.

Required coverage areas:

- state machine,
- valid/invalid status transitions,
- NIP validation,
- monetary normalization,
- validation engine,
- duplicate detection,
- local filesystem storage behavior,
- upload flow,
- case creation,
- extraction provider contract/flow,
- review corrections,
- audit events,
- approval blocking rules,
- successful approval,
- JSON export,
- XLSX export,
- key REST API flows.

Use integration tests where database/API interaction is the thing being tested.

Keep tests deterministic.

A fresh test run must pass.

---

# 24. Quality checks

Use the repository's configured tooling.

Run appropriate:

- formatter,
- linter,
- type checking if configured,
- pytest,
- frontend lint/type checks/build where applicable.

Fix failures introduced or exposed by your work when they are within scope.

Do not finish with known red tests.

Do not suppress legitimate type/lint problems just to obtain a green command unless there is a documented technical reason.

---

# 25. README

Update the README to reflect the actually implemented system.

Include:

- business problem,
- architecture,
- stack,
- startup instructions,
- environment configuration,
- workflow,
- statuses,
- repository structure,
- API/OpenAPI access,
- sample/demo flow,
- tests,
- current Milestone 1 limitations,
- planned next milestones.

Clearly state that Milestone 1 uses local filesystem object storage behind an abstraction.

Do not advertise MinIO as an active dependency.

Add/update a Mermaid architecture diagram.

Avoid inflated marketing language.

---

# 26. Architecture documentation

Update existing documentation rather than creating excessive duplicate docs.

Document important architectural decisions, especially:

- separation of extraction and validation,
- raw vs normalized values,
- storage abstraction,
- deterministic validation,
- human review,
- controlled state transitions,
- auditability,
- why local filesystem storage is used in Milestone 1,
- how an S3-compatible backend can be added later.

---

# 27. Security/basic robustness

Milestone 1 does not require a full authentication system.

Still implement basic robustness:

- safe uploaded filename handling,
- storage path traversal protection,
- upload size/type handling where practical,
- structured validation errors,
- safe decimal handling,
- no committed secrets,
- `.env.example`,
- database constraints where useful,
- backend enforcement of workflow rules.

Do not build a large auth/RBAC system in this milestone.

---

# 28. Explicitly out of scope

Do **not** implement these now unless a tiny piece is essential for architecture compatibility:

- real email inbox integration,
- n8n workflows,
- production OCR,
- OCR benchmarking,
- real LLM extraction,
- OpenAI calls,
- RAG,
- CRM integrations,
- ERP integrations,
- PDF offer generation,
- webhook automation,
- sophisticated RBAC,
- multi-tenancy,
- Kubernetes,
- microservices,
- production cloud deployment,
- elaborate analytics dashboard.

Do not burn time on future scope.

---

# 29. Acceptance criteria

Milestone 1 is complete only when all of the following are true:

### Infrastructure

- `docker compose up -d --build` works or any unavoidable limitation is precisely documented.
- PostgreSQL starts and is reachable.
- Backend starts.
- Frontend starts.
- Document storage persists through the Docker volume.

### Workflow

A user can demonstrably execute:

```text
create/upload
→ processing
→ extraction
→ normalization
→ validation
→ review if required
→ correction
→ revalidation
→ approval
→ JSON/XLSX export
→ audit inspection
```

### Safety/business rules

- duplicate documents are detected,
- invalid status transitions are blocked,
- blocking validation issues prevent approval,
- API cannot bypass approval rules,
- manual corrections are audited,
- raw/extracted information remains traceable.

### Tests

- meaningful backend test suite passes,
- frontend checks pass where configured,
- exports are tested,
- duplicate and validation edge cases are tested.

### Documentation

- README matches reality,
- architecture docs match reality,
- no active documentation claims MinIO is required in Milestone 1.

---

# 30. Work style

Work autonomously.

Do not stop for minor implementation decisions that can be resolved using normal engineering judgment.

Inspect the existing repository before modifying it.

Prefer completing the full vertical slice over polishing one component excessively.

When you encounter an existing starter defect, fix it and continue.

Do not recreate boilerplate that already exists.

Do not change technologies simply because another stack is personally preferable.

Keep implementation practical and portfolio-grade.

---

# 31. Final verification

Before finishing:

1. inspect repository changes,
2. run backend tests,
3. run frontend checks,
4. run formatter/linter/type checks as configured,
5. validate migrations,
6. validate Docker Compose configuration,
7. exercise the main API/business flow,
8. verify JSON export,
9. verify XLSX export,
10. verify duplicate detection,
11. verify approval blocking,
12. verify audit trail,
13. update README/docs to match implementation.

Fix issues found during verification.

---

# 32. Final report

At completion provide a concise report containing:

- what was implemented,
- important architectural decisions,
- files/modules added or materially changed,
- exact test/check results,
- Docker/service status if available,
- manual E2E flow verified,
- known limitations,
- anything intentionally deferred to Milestone 2,
- exact commands needed to run the project.

Do not merely state that the milestone is complete. Provide evidence.

---

# Planned next milestone — context only

Do not implement this now.

Milestone 2 is expected to introduce:

```text
real email ingestion
→ n8n orchestration
→ attachments
→ Business Operations Automation Hub API
→ processing/review workflow
```

Later:

- OCR benchmark and real OCR,
- LLM extraction,
- confidence thresholds,
- richer document types,
- measurable evaluation dataset.

Milestone 1 must therefore leave clean extension points for these capabilities without implementing them prematurely.
