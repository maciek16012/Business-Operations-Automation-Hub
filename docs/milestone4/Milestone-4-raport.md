# Milestone 4 — Intelligent Document Routing & Straight-Through Processing

## Status

Milestone 4 completed.

The objective was to maximize safe Straight-Through Processing (STP) while preserving the hard safety constraint:

> zero incorrect critical fields auto-accepted on the final evaluation HOLDOUT

Target STP rate: at least 90%.

Final HOLDOUT result: **95% STP with zero false accepts**.

## Architecture

Milestone 4 replaced unconditional dual OCR with selective document routing:

DOCUMENT
→ PDF/native-text preflight
→ native text when safe
→ primary OCR when native text is unavailable or untrusted
→ selective second OCR only when primary evidence fails deterministic safety checks
→ AUTO_ACCEPT or REVIEW_REQUIRED

Final routing policy:

1. `NATIVE_TEXT`
   - used for PDFs with trustworthy embedded text
   - embedded text must pass structural quality checks
   - large raster layers prevent blind trust in embedded text
   - all critical fields must be present
   - deterministic business validation must pass

2. `PRIMARY_OCR`
   - PaddleOCR is the primary OCR provider
   - only one OCR invocation is used when all critical fields are present and validation succeeds

3. `DUAL_OCR`
   - invoked only when primary OCR is incomplete, invalid, or fails
   - Tesseract is added as the secondary provider
   - existing Milestone 3 comparison/resolution logic remains intact

4. `HUMAN_REVIEW`
   - unresolved or incomplete documents remain review-required
   - no unsafe auto-accept fallback is allowed

## Native PDF safety

Native PDF extraction uses PyMuPDF.

Preflight records:

- page count
- embedded-text character count
- alphanumeric density
- printable-character ratio
- characters per page
- pages containing text
- text-page ratio
- largest raster-image area ratio per page

A large raster image prevents embedded text from being trusted as the sole source.

This rule was added after the DEV challenge case `hybrid_wrong_native` demonstrated that internally valid but incorrect hidden PDF text could otherwise pass deterministic business validation.

After the safety gate was added, the challenge case correctly escalated to OCR.

## Deterministic field validation

Critical fields:

- document_number
- tax_id
- issue_date
- net_total
- vat_total
- gross_total
- currency

Validation includes:

- Polish NIP checksum
- non-negative monetary values
- net + VAT = gross within tolerance
- supported currency
- valid non-future issue date
- document number present
- all critical fields present
- no unresolved conflicts

OCR agreement alone is not treated as ground truth.

## Dataset

A new Milestone 4 dataset was created independently from the Milestone 3 HOLDOUT.

Total:

- DEV: 20 documents
- HOLDOUT: 20 documents

Each split contains:

- native-text PDFs
- native-table PDFs
- multi-page native PDFs
- sparse native PDFs
- correct hybrid PDFs
- deliberately misleading hybrid PDFs
- clean scans
- poor scans
- skewed scans
- low-contrast scans
- compressed scans
- table scans
- rotated scans
- small-text scans
- noisy scans
- partial scans
- multi-page scans
- mixed native/scan PDFs
- foreign-currency documents
- long document numbers

The Milestone 3 HOLDOUT was not reused for Milestone 4 tuning.

## DEV evolution

Initial conservative routing:

- native text when trusted
- otherwise dual OCR

Initial result exposed a false-accept risk in `hybrid_wrong_native`.

After adding the raster-image safety gate:

- false accepts: 0
- STP: 15%

Analysis of the already-produced DEV OCR evidence showed:

- Tesseract deterministic candidates: 14/14 correct
- Paddle deterministic candidates: 16/16 correct

This led to the final architecture:

> native → Paddle primary → selective Tesseract verification only when needed

Final DEV result:

- documents: 20
- auto-accepted: 19
- review-required: 1
- STP rate: 95%
- false-accepted critical fields: 0
- false-accepted documents: 0
- processing failures: 0
- native-text route: 15%
- primary-OCR route: 80%
- dual-OCR route: 5%
- mean OCR invocations/document: 0.9

The only review-required DEV document was the intentionally sparse case with missing monetary fields and currency.

## Freeze

Before HOLDOUT execution, code, configuration, benchmark scripts, OCR routing logic, dependencies and dataset files were frozen with SHA-256.

Freeze created:

`2026-09-28T08:41:24.887015+00:00`

Freeze SHA-256:

`efabd09d4ff94f899323f85f187e5b4bf2d67d228f0b2d7fb1d687fed898ae3b`

The HOLDOUT policy allowed one final run only.

## Final HOLDOUT

HOLDOUT execution:

- started: `2026-09-28T08:45:44.956912+00:00`
- completed: `2026-09-28T08:47:36.019464+00:00`

Results:

| Metric | Result |
|---|---:|
| Documents | 20 |
| AUTO_ACCEPT | 19 |
| REVIEW_REQUIRED | 1 |
| Processing failures | 0 |
| STP rate | **95%** |
| Manual review rate | 5% |
| Critical-field false accepts | **0** |
| Critical-field false-accept rate | **0%** |
| Document false accepts | **0** |
| Document false-accept rate | **0%** |
| Native-text route | 15% |
| Primary-OCR route | 80% |
| Dual-OCR route | 5% |
| Mean OCR invocations/document | **0.9** |
| Mean processing time | 5550.85 ms |
| p95 processing time | 7730.05 ms |
| Safety constraint passed | **Yes** |
| 90% STP target reached | **Yes** |

Route counts:

- `NATIVE_TEXT`: 3
- `PRIMARY_OCR`: 16
- `DUAL_OCR`: 1
- `HUMAN_REVIEW`: 0

The only HOLDOUT document requiring review was the intentionally sparse native document. It lacked enough monetary/currency evidence for safe automation and therefore failed closed into review.

## Regression and quality checks

Before HOLDOUT:

- full backend test suite: **178 passed, 2 skipped**
- Milestone 4 routing tests: **14 passed**
- Ruff: **all checks passed**
- mypy on `app/document_routing`: **no issues found**

Existing Milestone 1–3 behavior remains preserved when STP is disabled.

## Result

Milestone 4 achieved the intended architecture:

- safe native-text bypass
- primary OCR instead of unconditional dual OCR
- selective second-engine verification
- deterministic business validation
- explicit escalation to human review
- backward-compatible OCR report structure
- frozen final evaluation
- 95% STP on DEV
- 95% STP on closed HOLDOUT
- zero incorrect critical fields auto-accepted on both final DEV and HOLDOUT evaluation

No post-HOLDOUT tuning was performed.

## Deferred to Milestone 5

The following are intentionally outside Milestone 4:

- quarantine/security preflight for untrusted inbound attachments
- active operator notifications for `REVIEW_REQUIRED`
- dedicated review queue and escalation workflow
