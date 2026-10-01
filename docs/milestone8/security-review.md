# M8 security and repository review

M8 introduces demo/release packaging, not a security subsystem. Existing M5 preflight and M7 auth/RBAC, encryption, SSRF/path policy and production TLS guards remain intact. See [M7 security review](../milestone7/security-review.md) for implementation boundaries and residual risks.

- Demo has a fixed separate Compose project and five dedicated volumes; only loopback `127.0.0.1:3080` is published. It does not merge with production compose.
- Random runtime credentials/master key are generated once, ignored by Git and protected by a Windows ACL. Logins are stored only in the protected ignored directory. A repeated start does not overwrite them.
- Seed requires the explicit development instance marker, exact runtime identity and a blank/DEMO-ONLY company. The production negative check rejects before API calls.
- Reset checks identity, non-linked paths, exact volume allowlist and project ownership, asks for a typed project confirmation (or explicit automation switch), then deletes only that project/runtime. Actual reset preserved 31 unrelated container IDs/names and 23 volume names.
- The filename-policy fixture is harmless plain text; no executable/EICAR/malware payload is shipped. The seed asserts its BLOCKED verdict, no OCR/document analysis and denied approval.
- Normal SAFE → classification ordering is asserted in the real E2E audit; review/approval/export go through authenticated CSRF-protected APIs, not direct DB inserts.
- Local demo permits private plaintext IMAP and HTTP webhook fixtures only. Production remains TLS/HTTPS, fail-closed and private-service; production config publishes only Caddy 80/443. This demo must not be exposed publicly.
- Temporary n8n credential copies have restricted permissions and are deleted after import. Runtime state/model caches, archives, protocol receipts and env files are not release artifacts.
- Changed/untracked release files are scanned against actual generated secrets without printing values; only synthetic documents/screenshots and sanitized evidence are candidates for review.

No independent penetration test, public-host deployment, dependency supply-chain audit or customer-data evaluation is claimed. Hosted CI is optional and was not fabricated. The master key must be backed up separately for real operations; demo reset intentionally destroys its disposable state.
