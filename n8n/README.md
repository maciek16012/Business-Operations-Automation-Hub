# Email ingestion with n8n — Milestone 2

n8n handles delivery orchestration; FastAPI owns message identity, storage, business validation, states and audit. No workflow reads/writes BOAH PostgreSQL or its document filesystem. No OCR, LLM or automatic replies are included.

## Start and import

From the repository root:

```powershell
docker compose up -d --build
docker compose exec -T n8n n8n import:workflow --separate --input=/workflows
docker compose exec -T n8n n8n publish:workflow --id=boahEmailErrors2
docker compose exec -T n8n n8n publish:workflow --id=boahEmailFixture2
docker compose restart n8n
```

Open http://localhost:5678. On a fresh installation, complete n8n's local owner-account setup yourself. Workflows can be imported with the CLI before that setup. **In n8n 2.40.7, the error workflow must be published as well**; an inactive error workflow is not executed. Importing again deactivates imported workflows, so republish the required workflows and restart after a CLI import. Do not reimport over mailbox bindings or locally edited workflows without exporting/backing them up first.

The Compose image is pinned to official `docker.n8n.io/n8nio/n8n:2.40.7`. Upgrade deliberately and rerun the workflow tests before changing the pin. The UI/webhook port is bound to 127.0.0.1. `n8n_data` persists SQLite configuration, workflow state, execution data, filesystem binary data and the automatically generated credential-encryption key. That key is created by n8n inside the volume, never stored in Git. Do not delete the volume or lose its key after saving mailbox credentials. The internal JS task runner is retained for this local setup; no extra runner/queue service is required. Default timezone is Europe/Warsaw, configurable via N8N_TIMEZONE.

## Workflows

- `workflows/inbound-email.json` — generic IMAP trigger, resolved message normalization, bounded HTTP delivery, response classification. Import is inactive and contains no credential references.
- `workflows/inbound-email-fixture.json` — local webhook that creates the same resolved metadata and n8n binary items, then runs the same normalization/HTTP/classification nodes. This proves the non-credential layers; it is not a replacement for the IMAP workflow.
- `workflows/inbound-email-error.json` — Error Trigger and a recovery summary with category, failing node and execution URL. It does not email anyone or create a retry loop.
- `code/*.js` — readable Code-node sources. `scripts/build_email_workflows.py` regenerates the sanitized importable JSON; `node --test n8n/tests/workflows.test.cjs` verifies code parity, mapping and outcomes.

All JSON is free of passwords, tokens, encryption keys and credential IDs. Stable workflow IDs allow the Error Trigger link to resolve after import. n8n's export command can produce an instance-specific backup; do not commit unsanitized credential references or execution data:

```powershell
docker compose exec -T n8n n8n export:workflow --id=boahEmailImapM2 --output=/tmp/inbound-email-export.json
```

## Connect a real generic IMAP mailbox

1. In the n8n UI, open **BOAH - Inbound email (IMAP)**.
2. Open **IMAP mailbox** and create an **IMAP credential**. Supply your provider's host, port (normally 993), username and password/app password in n8n's credential form. Enable TLS; do not disable certificate verification for a real mailbox. OAuth-only servers require a supported IMAP authentication setup; provider-specific OAuth is outside this milestone.
3. Test the credential. Select the mailbox folder, normally INBOX; a dedicated inbound folder is recommended to avoid unrelated mail.
4. Keep Format **Resolved**, attachment prefix `attachment_`, Action **Nothing**, Custom Email Rules `["UNSEEN"]`, and Fetch Only New Emails **off**. Resolved format supplies parsed address objects and binary attachments, including inline attachments. Unknown MIME types are preserved and require backend review.
5. In workflow settings, confirm Error Workflow is **BOAH - Email delivery errors** (ID `boahEmailErrors2`) and that it is published. The backend HTTP URL remains `http://backend:8000/api/v1/inbound/email` inside Docker.
6. Publish the IMAP workflow. Send a synthetic business email to the connected mailbox yourself, with `sample_data/email_specification.txt` attached. This implementation never sends outbound mail.
7. Inspect the n8n execution, the BOAH case/source panel, and the preserved attachment. Replay the saved execution with the original Message-ID and confirm `idempotent_noop` and the same case ID.
8. Mark/archive the original email manually only after confirming ingestion. Disable the local fixture webhook when you no longer need it: `docker compose exec -T n8n n8n unpublish:workflow --id=boahEmailFixture2`, then restart n8n.

No real mailbox credentials were present during implementation. Real external IMAP receipt is therefore not claimed as verified. The real IMAP workflow imports, uses the installed official node's schema, and is ready for credential binding; binary mapping, HTTP, replay, review, exports and error paths were exercised on a live n8n instance via the fixture workflow.

The [official IMAP node documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.emailimap/) explains resolved format, attachment handling, read/unread actions and credential binding. Node parameters were additionally checked against the installed 2.40.7 source, including typeVersion 2.2.

## Delivery and failure semantics

This is **at-least-once delivery attempts with an idempotent backend**, not distributed exactly-once execution. Each HTTP node has at most three attempts, a 15-second timeout per attempt and one second between attempts. HTTP errors, including invalid payloads, may receive these same bounded retries; there is no infinite retry loop. A timeout can happen after the backend commits. Retrying the unchanged message then returns the existing case without reprocessing attachments.

| Outcome | n8n behavior / recovery |
|---|---|
| New READY case | success / accepted |
| Existing message | success / idempotent_noop |
| REVIEW_REQUIRED, including unsupported attachment | success / operator_review; inspect in BOAH |
| Invalid payload / 4xx | failed execution / INVALID_PAYLOAD; correct the input and replay |
| Backend unavailable / 5xx | failed execution / BACKEND_UNAVAILABLE; restore service then retry saved execution |
| Backend timeout | failed execution / BACKEND_TIMEOUT; retry unchanged identity; a prior request may already have committed |
| Backend preserved FAILED case | failed execution / INGESTION_FAILED; inspect that case, do not invent a new Message-ID |
| Other error | failed execution / UNEXPECTED_WORKFLOW_ERROR |

Error Trigger writes a useful recovery summary in its own execution; no secrets or email bodies are copied into that summary. n8n execution data itself necessarily contains source messages/binaries. It is local and pruned after 168 hours; retry or export evidence before retention expires. Application audit does not include mailbox credentials.

The IMAP node maintains a UID cursor while active. It is not a durable acknowledged-message queue. Leaving originals unread avoids acknowledging delivery in the trigger before BOAH accepts it. Use the failed-execution Retry operation for ordinary recovery; if a trigger failure prevented an execution from being saved, unpublish/republish the IMAP workflow with Fetch Only New Emails off to reread retained unread messages. Replays of already ingested messages are safe. Provider disconnection, mailbox retention, UID changes and trigger-level failures still require operator reconciliation; the implementation does not claim automatic unlimited redelivery.

A committed storage-processing FAILED case is terminal under M1 rules. Its replay is a no-op and n8n flags it for investigation. Automatic reopening or reprocessing of terminal cases is not added in M2. Database rollback before an ingestion commits releases the unique identity claim, permitting a later delivery to create the case. Filesystem writes and DB commits remain separate: an interrupted transaction can leave orphaned objects as documented in M1.

## Inbound API contract

`POST /api/v1/inbound/email`, content type `application/json`. A single request contains metadata and zero to ten base64 attachments. This atomic protocol avoids half-created cases across a multi-step upload protocol and handles dynamic attachment counts in n8n. Base64 has approximately 33% transport overhead; this is acceptable for the bounded local milestone. The backend is authoritative for limits: decoded attachments must be nonempty and at most MAX_UPLOAD_BYTES (5 MiB by default); schema encoded-string cap is 6,990,508 characters. Filename/MIME/body/address lengths are bounded. Body/HTML limits are 200,000 characters each. Invalid metadata, base64 or limits reject the entire request before creating a case. The local fixture webhook also has n8n's HTTP payload limit; use modest test fixtures.

```json
{
  "source_type": "imap",
  "external_message_id": "<boah-demo-001@example.test>",
  "sender": {"address": "jan@example.test", "name": "Jan Kowalski"},
  "recipients": [{"address": "office@example.test"}],
  "cc": [],
  "reply_to": [],
  "subject": "Zapytanie ofertowe — modernizacja biura",
  "received_at": "2026-09-27T12:00:00+02:00",
  "sent_at": "2026-09-27T09:59:00Z",
  "text_body": "Proszę o przygotowanie wyceny.",
  "html_body": null,
  "attachments": [{"filename": "spec.txt", "mime_type": "text/plain", "content_base64": "TklQOiA1MjYwMjUwMjc0"}]
}
```

`received_at` and optional `sent_at` require timezone offsets. Real IMAP resolved output exposes the sender Date as sent_at; received_at is the n8n ingestion receipt time when no original received timestamp is supplied. Only an explicit allowlist of metadata is forwarded, not arbitrary headers.

New delivery: HTTP 201. Replay: HTTP 200. Both return `result` (created/duplicate), `case_id`, `public_case_id`, `message_id` (internal UUID), current case `status`, ingestion `processing_status`, `identity_method` and `attachment_results`. Each attachment result preserves the incoming filename/MIME, SHA-256, stored attachment ID, and result (stored/duplicate/review_required/not_stored). The detail endpoint adds `inbound_message`; old list/review/export APIs remain compatible. `/cases` still only accepts manual_upload/api, preventing an email source with no linked inbound record.

Idempotency is global within `source_type=imap`, including deliveries to multiple mailboxes: `(source_type, identity_key)` is unique. For a usable RFC-style Message-ID, trim whitespace/brackets and lowercase the domain while preserving the local part, then hash. A malformed/missing Message-ID uses versioned SHA-256 over sender, sorted To/Cc addresses, subject, stable sent time, plain/HTML bodies with normalized CRLF and sorted attachment content hashes. Receipt time, attachment order and filenames are deliberately excluded. Identical ID-less messages with identical stable characteristics collapse into one case; this unavoidable ambiguity is documented. A reused valid Message-ID is treated as replay even if the new body differs; do not reuse IDs for distinct messages.

A unique insert arbitrates simultaneous requests before creating a case, all in one transaction. The contender waits for the original transaction and then returns its case. Replays append EMAIL_DUPLICATE_IGNORED but do not create attachments, rerun extraction or modify reviewed fields.

## Review and safe source display

Subject seeds a bounded title; sender address/name seed the corresponding business fields. Full originals stay on InboundMessage. Bodies are not semantically interpreted. Existing extraction can expose conflicts with those seeds, which require manual confirmation. Existing M1 email validation treats reserved `.test` addresses as invalid business email; the demo intentionally reviews/corrects that field to `.com` instead of weakening M1 rules.

HTML is stored for traceability and rendered only as escaped text in a collapsed source section. No dangerouslySetInnerHTML or remote image loading is used. Unsupported MIME types and failed fixture extraction are stored, audited and represented by persistent blocking issues. They are not auto-resolved by revalidation. An operator can inspect the downloaded original, correct business fields and acknowledge the attachment with a reason through the UI or:

`POST /api/v1/inbound/messages/{message_id}/attachments/{attachment_id}/review` with `{"reason":"Inspected and reconciled the source"}`.

The backend validates ownership/state, records the acknowledgment and resolution audit events, then runs the same validation engine. Existing business validation cannot be bypassed by acknowledging an attachment.

## Reproduce checks

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub
node --test n8n/tests/workflows.test.cjs
Set-Location backend
uv run pytest -q
$env:TEST_DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
uv run pytest -q
uv run python ../scripts/demo_email_ingestion.py
# API-only path, without an n8n execution:
uv run python ../scripts/demo_email_ingestion.py --via api
# Briefly stops and pauses the local backend; always resumes in finally:
uv run python ../scripts/verify_email_delivery_errors.py
```

The demo uses a new run ID by default, tests 0/1/multiple attachments, replay, review, approval and JSON/XLSX. Pass `--output-dir <directory>` to retain artifact copies and its measured manifest. The fault-injection script verifies unavailable/timeout/invalid-payload Error Trigger categories and safe recovery. `n8n/execution-evidence.cjs` is a read-only diagnostic helper for the pinned n8n SQLite schema, never part of the orchestration workflow.
