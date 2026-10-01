# Independent synthetic demo fixtures

These files are authored exclusively for the portfolio walkthrough. The generator reads no benchmark data and no HOLDOUT is used as seed input.

| File | Scenario |
|---|---|
| `fixtures/invoice-ready.pdf` | Fictional invoice; seed explicitly reviews/approves/exports one completed example |
| `fixtures/invoice-review.pdf` | Invalid fictional tax checksum; review must confirm `9900000000` against the exercise note |
| `fixtures/printed-table.pdf` | Printed score table; human table verification |
| `fixtures/handwritten-table-like.pdf` | Rasterized italic printing, explicitly labeled proxy; unresolved cell review, not real HTR |
| `fixtures/generic-document.pdf` | Fictional operations memo |
| `fixtures/unknown.pdf` | Intentionally minimal content; UNKNOWN, mandatory review |
| `fixtures/blocked-sample.exe.txt` | Harmless plain text; executable-like suffix triggers filename policy. No malware/test-virus signature |

Every company/operator is fictional. Example addresses use `example.com`. The synthetic NIP has a valid checksum for demonstrating rules; it is not attributed to a real business. `manifest.json` contains known values for explicit **demo review**, never machine extraction.

Start: `scripts/demo/start_demo.ps1`. See [the guide](../docs/demo/DEMO-GUIDE.md). The idempotent seed uses normal authenticated APIs, keeps raw readings and records its confirmation reason. It does not bypass security, direct-write cases into the database or claim accuracy from known fixture values.

To regenerate intentionally: from the repository root run `uv run --project backend --extra dev python scripts/demo/build_fixtures.py`. PDF generation uses the existing ReportLab/PyMuPDF development dependencies. Render/inspect all PDFs after edits. No evaluation script needs to run.

Seed is guarded by the local demo marker, `APP_ENV=development` and `BOAH_DEMO_INSTANCE=portfolio-v1`; it refuses a different existing company. Runtime credentials/data stay under ignored `.runtime-demo/`. Never use this profile for real/private documents.
