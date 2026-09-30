# M7 — Security review

Review date: 2026-09-30. Scope: application code, production configuration, local integration services and actual negative-path tests. This is a development security review, not an independent penetration test or deployment certification.

| Boundary | Control and verification |
|---|---|
| Local identities | Argon2id passwords, opaque random session cookies stored as hashes, expiry/revocation, disabled-user rejection, account/peer throttling, generic failures, last-admin protection. Tested session expiry/logout/access changes and failed login auditing. |
| Browser writes | HttpOnly/SameSite=Strict/Secure production cookies; stable server-checked CSRF token and Origin policy. Authenticated role checks on backend, not just hidden UI controls. ADMIN/OPERATOR/REVIEWER/VIEWER negative tests pass. |
| Machine ingestion | Separate service bearer is restricted to ingestion/notification endpoints. It cannot administer settings or access unrestricted API/metrics. Sanitized workflow templates contain no credentials. |
| Secret storage | AES-GCM, per-record nonce and associated ID, write-only APIs, production key validation. Tampering and wrong keys fail. No secrets in config export, API errors or SQL parameter logs. Master key is separate from backup. |
| Untrusted attachment | Existing fail-closed M5 scan remains before M6 classification/extraction. Real EICAR email blocked; no OCR/classification and approval 409. M4/M6 HOLDOUTs are untouched. |
| Connector network | DNS validates every resolved address, connection pins validated IP; HTTPS/TLS hostname verification, no redirects, explicit private allowlist. Metadata/link-local endpoints blocked. Real SFTP wrong-key connection raises BadHostKeyException. |
| IMAP after restore | Runtime rejects TLS disabled in production even when the persisted record bypasses creation validation or the plaintext-test flag is true. New regression test passes on SQLite/PostgreSQL. |
| Storage paths | Logical deployed roots, relative path/template whitelist, no traversal/absolute paths/symlinks; immutable hash-checked publication. Deployment mounts/host administration remain trusted. |
| Delivery | Approved/exported SAFE cases only; stable durable artifact snapshots, signed webhook, bounded retries, dead letter + review/outbox, explicit admin retry. Receiver idempotency required for at-least-once transport. |
| Backup/retention | Hash/schema/archive validation, explicit empty restore target, master key exclusion; retention dry-run hash confirmation, active work exclusion, audit-first deletion evidence and 410 tombstones. Actual restore independently verified. |
| Deployment | Standalone production compose exposes only proxy80/443. Actual HTTPS TLS verification, secure cookies and UID10001/read-only backend/frontend passed. Production defaults fail closed for insecure auth/debug/security/TLS/key configuration. |
| Observability | Sanitized 422 errors, hidden SQL parameters, bounded labels and structured correlation logs. Runtime scan found none of generated secret values or synthetic document body in backend/worker logs. |

Evidence: `security-runtime-check.json`, `production-smoke.json`, `deployment-check.json`, `e2e.json`, `backup-restore-e2e.json`; M7 has 44 security and 11 operations tests, included in full regression.

Residual limitations: single-company/local identities; no MFA/SSO; host/Docker administrators can access application data; key recovery/rotation requires an operational procedure; public DNS/ACME and real company credentials were not provisioned; upstream Paddle/ClamAV privilege exceptions remain; no independent vulnerability scan/pentest or HA/PITR claim. Invalid IMAP messages can block a source batch until administrator intervention. Externally delivered files and n8n state require separate backups. Retention does not yet expire durable delivery snapshot objects. Backup hash manifests need a trusted archive source or independent signature. Notification receipt means durable handoff, not proven final email delivery.

Repository review: runtime credentials/datasets/keys/archives remain ignored; no commit/staging/push performed. Five M4 files were individually compared to c129e1e, have identical bytes/AST and require no functional rollback.
