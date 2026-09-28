# Milestone 4 — Straight-Through Processing Dataset

This dataset evaluates safe Straight-Through Processing (STP), not OCR quality alone.

## Objective

The primary goal is to maximize the percentage of documents processed without human intervention while preserving the hard safety constraint:

> zero incorrect critical fields auto-accepted on the final evaluation holdout

Target STP rate: 90%.

This target must never override the safety constraint.

## Splits

### DEV

`datasets/stp/input/dev`
`datasets/stp/ground_truth/dev`

DEV may be used for:

- routing development
- native-text quality gate calibration
- OCR escalation policy development
- deterministic validation development
- confidence and risk threshold calibration
- benchmark iteration
- false-consensus investigation

### HOLDOUT

`datasets/stp/input/holdout`
`datasets/stp/ground_truth/holdout`

The HOLDOUT split must remain closed during development.

Rules:

- do not tune routing or thresholds using HOLDOUT results
- do not reuse the Milestone 3 holdout as Milestone 4 tuning data
- freeze code, configuration and dataset manifest before evaluation
- execute the final HOLDOUT evaluation once
- record hashes of the evaluated code/configuration/dataset
- do not modify the policy after inspecting HOLDOUT outcomes

## Required document diversity

The dataset should contain a realistic mixture of:

- native-text PDFs
- scanned PDFs
- hybrid PDFs containing both embedded text and raster content
- PNG/JPEG/TIFF scans
- clean scans
- degraded or noisy scans
- rotated or skewed scans
- multi-page documents
- tables
- different invoice/document layouts
- different field positions
- Polish diacritics
- different NIP/date/money formats
- PLN and supported foreign currencies
- incomplete documents
- ambiguous documents
- cases designed to expose OCR disagreement
- cases designed to expose false consensus between OCR engines
- documents where native PDF text exists but is incomplete or misleading

## Critical fields

The following fields are safety-critical:

- document_number
- tax_id
- issue_date
- net_total
- vat_total
- gross_total
- currency

Ground truth must contain explicit expected values for all applicable critical fields.

## Routing paths

Milestone 4 may route documents through:

- `NATIVE_TEXT`
- `PRIMARY_OCR`
- `DUAL_OCR`
- `HUMAN_REVIEW`

The routing policy should choose the cheapest safe path.

A document must not be routed to AUTO_ACCEPT merely because two OCR engines agree.

## Business validation

AUTO_ACCEPT requires deterministic validation where applicable, including:

- valid Polish NIP checksum
- net + VAT = gross within configured tolerance
- supported currency
- valid issue date
- non-negative monetary values
- all required critical fields present
- no unresolved field conflicts
- no blocking validation issues

## Evaluation outcomes

Each document must end with one of:

- `AUTO_ACCEPT`
- `REVIEW_REQUIRED`
- `PROCESSING_FAILED`

For evaluation purposes, AUTO_ACCEPT is correct only when every critical field matches ground truth.

## Required metrics

At minimum record:

- STP rate
- manual review rate
- critical-field false accept rate
- document false accept rate
- native-text route rate
- primary-OCR route rate
- dual-OCR route rate
- processing-failure rate
- mean processing time
- p95 processing time
- mean OCR invocations per document

The preferred system is not simply the one with the highest STP rate. It is the system that maximizes safe STP while respecting the hard false-accept constraint.
