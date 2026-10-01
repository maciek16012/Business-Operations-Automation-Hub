# Proposed release notes — v1.0.0-demo

**Draft for manual review. No tag, commit, GitHub release or public deployment is created by Milestone 8.**

Business Operations Automation Hub is a self-hosted, single-company document workflow demonstration. This packaging brings the completed M1–M7 foundation into a reproducible synthetic portfolio experience.

## Included capabilities

- Secure upload/API, native IMAP and watched-folder intake with deduplication.
- Fail-closed MIME/content/ClamAV preflight before classification and OCR.
- Invoice native-text / primary / selective dual OCR; conservative typed extraction.
- Original previews, uncertainty, human corrections with reasons, approval guards and audit.
- JSON/XLSX, original archiving, pinned SFTP and signed webhook jobs with retries.
- Local identities/RBAC, company settings, encrypted write-only connector secrets.
- Monitoring, backup/restore procedures and a private-service production HTTPS profile.

## M8 packaging

Product-first README, case study, Polish portfolio summary, capability/evaluation reference, configuration/troubleshooting, demo/video guides, screenshot gallery and release checklist. Separate fixtures and guarded Windows startup/reset scripts use a dedicated Docker project, random ignored credentials and loopback-only exposure. The optional email demonstration uses private GreenMail, not a real mailbox.

## Evidence and limits

Local regression: SQLite 281 passed / 2 PostgreSQL-specific skips; PostgreSQL 283 passed; n8n 9 passed. The M8 demo exercises review → approval → export → archive/signed retry and real local SMTP/IMAP. See [M8 report](../milestone8/Milestone-8-raport.md) for commands, UI and reset evidence.

Historical M4 HOLDOUT: 19/20 synthetic invoices passed STP (95%), zero observed false accepts in that sample. Historical M6: 17/20 correct classes (85%), 6/8 table structures correct (75%), cell accuracy 66/216 (~30.6%), 95% document review rate. These are small synthetic evaluations, not guarantees for customer data. Neither HOLDOUT was rerun or tuned in M8.

There is no production handwriting model; handwritten-like fixtures are conservative review demonstrations. Public-domain ACME deployment, real customer integrations, independent security assessment, scale, HA, off-site recovery and hosted CI remain outside verified claims. No license has yet been selected. Review publication and license decisions manually before distributing a release.
