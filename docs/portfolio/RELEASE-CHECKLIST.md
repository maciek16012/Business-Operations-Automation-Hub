# Release checklist — proposed v1.0.0-demo

Local verification is complete; publishing is a separate manual decision. Details and evidence: [M8 report](../milestone8/Milestone-8-raport.md).

## Local gates

- [x] Existing M1–M7 implementation and historical evidence inspected.
- [x] M4/M6 HOLDOUT, datasets and pipeline preserved; no benchmark rerun/tuning.
- [x] Independent synthetic fixtures only; no active malware or customer documents.
- [x] One-command Windows demo startup, random credentials, auth and isolated volumes.
- [x] Cold-cache reset/start, production seed rejection, unowned reset rejection and scoped deletion tested.
- [x] Repeated seed is idempotent; final populated demo remains available.
- [x] Case/document/review/approval/export/archive/webhook/audit E2E checked.
- [x] Real local SMTP → IMAP synthetic intake checked.
- [x] Login/dashboard/case/intelligence/review/settings/System UI reviewed; current screenshots captured.
- [x] SQLite and PostgreSQL full regression; Ruff, mypy, frontend lint/types/build, n8n.
- [x] Alembic schema check and development/OCR/security/demo/production compose validation.
- [x] Production publishes only reverse proxy 80/443; demo only loopback 3080.
- [x] README, case study, portfolio summary, demo/video/configuration/troubleshooting complete.
- [x] New/modified Markdown local links/images verified; unchanged historical documents are outside this link gate.
- [x] Changed/untracked files checked against generated secrets; runtime/env/cache excluded.
- [x] Diff whitespace checked; exact pending Git status recorded for manual review.

## Publication decisions — intentionally pending

- [ ] Review all pending M8 changes and create a commit manually.
- [ ] Choose and add a license before distribution; no implicit open-source license claim.
- [ ] Decide whether to create `v1.0.0-demo`, push or publish release notes.
- [ ] Configure hosted CI if desired; no CI badge or claimed hosted run is added.
- [ ] Validate target host, DNS/ACME, external integrations, backup retention and operational monitoring before public deployment.
- [ ] Obtain broader independently collected real-document evaluation before expanding accuracy claims.

The working tree is intentionally **not clean at completion**: the user's requested no-commit/no-push boundary leaves M8 changes for review. This does not mean runtime or credentials belong in Git.
