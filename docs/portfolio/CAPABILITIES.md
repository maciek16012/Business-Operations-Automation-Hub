# Capability matrix

| Capability | Current status / boundary |
|---|---|
| Manual upload / API intake | Supported |
| Native IMAP | Supported; verified TLS mandatory in production |
| Watched folder | Supported; stable-file detection and content dedup |
| MIME/magic / virus scanning | Supported; ClamAV fail-closed, block/quarantine before parsing |
| Invoice extraction / STP | Supported within evaluated invoice field/layout scope |
| Printed tables | Extraction plus mandatory human review; incomplete cells remain visible |
| Handwritten tables | Experimental human-review workflow; no full real-human HTR model |
| Generic / UNKNOWN | Conservative text/unresolved review; no automatic UNKNOWN approval |
| Validation / approval / audit | Supported and backend enforced |
| JSON / XLSX / original archive | Supported |
| Filesystem / mounted NAS | Supported; host must provision trusted mounts |
| SFTP | Supported with required pinned host key |
| Signed webhook / API receiver | Supported; at-least-once, receiver idempotency required |
| n8n review notification | Durable handoff supported; final email/channel requires configuration |
| Local auth / RBAC / CSRF | Supported: ADMIN, OPERATOR, REVIEWER, VIEWER |
| Encrypted connector secrets | Supported: write-only AES-GCM; key managed separately |
| Monitoring / metrics | Real probes/heartbeats; admin-only aggregate Prometheus text |
| Backup / restore | Supported: maintenance snapshot, hash/schema validation, empty target |
| Retention | Supported with dry-run/confirmation; delivery snapshot lifecycle pending |
| Production HTTPS profile | Provided and locally validated; no public/customer deployment claimed |
| Public cloud SaaS / multi-tenancy | Not provided |
| SSO / MFA / HA / PITR | Not provided |
| Real handwriting recognition | Not provided |
| Universal document understanding | Not provided |

See [evaluation boundaries](EVALUATION.md), [security review](../milestone7/security-review.md) and [demo](../demo/DEMO-GUIDE.md).
