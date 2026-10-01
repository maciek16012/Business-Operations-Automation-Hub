# Demo guide (5–10 minutes)

This is a disposable, synthetic, single-company environment. It is independent of M4/M6 evaluation datasets. Human confirmations made by the seed are demo actions, not extraction accuracy measurements.

## Start on Windows

From the repository root, with Docker Desktop running **Linux containers**:

```powershell
.\scripts\demo\start_demo.ps1
```

Open <http://localhost:3080>. Read `.runtime-demo/login.txt` locally for the generated admin, operator, reviewer and viewer logins. Do not share this file. Passwords, master key, database credentials and runtime outputs are ignored by Git and protected with a Windows ACL. Only the reverse proxy is published, on loopback port 3080. No Gmail account is needed.

Allow several minutes for a first run: image dependencies, Paddle models and ClamAV signatures require Internet access. Later runs reuse dedicated caches. The script imports/publishes the existing n8n review workflow with a generated scoped credential. Re-running it preserves logins/cases/connectors, but reapplies the demo n8n workflow template.

Optional real **local** email demonstration:

```powershell
.\scripts\demo\start_demo.ps1 -WithEmail
```

This sends a synthetic PDF to the private GreenMail SMTP service and ingests it through native IMAP. Plaintext IMAP is permitted only in this development demo network; production rejects non-TLS IMAP, including restored configurations.

## Suggested walkthrough

| Time | View / action | What to explain |
|---|---|---|
| 0–1 min | Sign in as admin; inspect dashboard and document types | Intake, status, review queue and uncertainty in one workspace. |
| 1–3 min | Open `[DEMO] Completed invoice` | Original preview, SAFE scan, invoice extraction, explicit human confirmation, approval, exports and audit. This seeded result is not proof of automatic extraction accuracy. |
| 3–5 min | Open `[DEMO] Invoice needs review`; inspect invalid NIP | The synthetic identifier `9900000001` fails checksum. In the OCR review form confirm all seven fields against the fixture, change NIP to `9900000000` and give a correction reason. Save the business review, resolve remaining document review if shown, then approve. Blocking issues must disappear first. |
| 5–6 min | Open `[DEMO] Printed score table`, then the handwritten-like case | Inspect rows/cells, evidence, confidence and unresolved values. The handwriting example is rasterized italic text, not a real handwriting recognizer. Keep unconfirmed values unresolved; do not invent readings. |
| 6–7 min | Open generic, unknown and blocked cases | Unknown stays review-required. The harmless `.exe.txt` sample is blocked by filename policy before OCR/classification. There is no executable or malware payload. |
| 7–9 min | Settings: Company, Sources, Destinations, Routing, Users, System | Run Test connection; observe PENDING → SUCCEEDED in durable jobs. Show write-only secrets, role boundaries, health and approved-invoice routing. |
| 9–10 min | Return to completed case; inspect delivery/audit and local archive | Original PDF, JSON and XLSX under `.runtime-demo/archive`; signed webhook job retries with the same identity/body. |

The fixture [manifest](../../demo/fixtures/manifest.json) contains known synthetic values for deliberate human review. The invoice totals are net 1000, VAT 230, gross 1230 PLN, issue date 2026-09-30; document numbers are `DEMO/2026/001` / `002`. Do not describe seed confirmations as autonomous approval or feed these values into the classifier.

## Automated end-to-end smoke

```powershell
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml exec -T backend python /demo-tools/seed_demo.py verify
```

It creates/reuses a separate live-flow case, verifies blocked early approval, real human-review API calls, approval, JSON/XLSX, filesystem archive, signed webhook retry, audit, document preview and service health. Sanitized evidence is written to `.runtime-demo/verification.json`. `-WithEmail` writes `.runtime-demo/email-result.json`. Seed summaries are in `.runtime-demo/seed-state.json`.

## Stop and reset

Stop while preserving synthetic data:

```powershell
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml stop
```

For a clean demonstration:

```powershell
.\scripts\demo\reset_demo.ps1
```

Type `boah-portfolio-demo` when prompted. This permanently deletes only the marked demo's containers, five named volumes and `.runtime-demo`. It checks identity, path/reparse points, volume names and ownership first. It excludes development/M7/production resources. `-ConfirmDemoReset` provides explicit non-interactive confirmation for disposable demo automation. Restart generates fresh credentials and downloads erased model/signature caches again.

Do not use global Docker prune, remove unrelated volumes, merge the demo compose into production or expose port 3080 publicly. For operational deployment use [configuration](../CONFIGURATION.md) and the [production guide](../milestone7/deployment.md). See [troubleshooting](../TROUBLESHOOTING.md).
