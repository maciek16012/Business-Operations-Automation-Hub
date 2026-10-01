# Evaluation evidence and claim boundaries

This page reads preserved results. No historical HOLDOUT is rerun by demo/release tooling.

## Invoice routing

The [M4 final report](../../datasets/stp/results/stp-holdout-final/report.md) evaluated 20 synthetic documents: 19/20 straight-through (95%), one requiring manual review, zero measured critical-field false accepts and zero document false accepts. Mean time 5550.8 ms, p95 7730.0 ms, average 0.90 OCR invocations per document. Native/primary/dual route counts were 3/16/1. This is evidence for the tested cases, not a confidence interval or universal accuracy claim for arbitrary invoices.

STP is a machine processing decision, not proof of subsequent human/business approval. The profile was selected on DEV and frozen before the final HOLDOUT. New tests must use new data, never tune this version on its HOLDOUT.

## Classification and tables

[M6 HOLDOUT](../milestone6/holdout-results.md): 20 synthetic documents, four per class, classification 17/20 (85%), UNKNOWN 20%, review 19/20 (95%). Table structure was correct for 6/8 (75%); cell accuracy 66/216 (30.56%), numeric cells 35/140 (25%), unresolved 150/216 (69.44%). Missing structures/cells stay in denominators. Per-class accuracy: invoice/generic/UNKNOWN 100%, handwritten-like 75%, printed table 50%.

The handwriting samples are rasterized italic text, sometimes with explicit hints. They are not real human handwriting. The classifier is deterministic heuristics, not a trained/calibrated classification model. High review rates and low cell completeness mean this is a human-in-the-loop workflow. Zero measured fabricated critical values/security bypasses is scoped to the evaluator's definitions and dataset, not a universal absence-of-error claim. Read [M6 methodology](../milestone6/Milestone-6-raport.md).

## Integration and operations evidence

[M7 E2E](../milestone7/e2e.json) used actual local SMTP/IMAP, SFTP and signed HTTP with synthetic PDFs and credentials. It checked deduplication, safe delivery, retry stability, dead letter, RBAC and blocked malicious test input. [Backup/restore](../milestone7/backup-restore-e2e.json) verified 140 object hashes and four decrypted records with the key supplied separately. [HTTPS smoke](../milestone7/production-smoke.json) used production images and an explicitly trusted local Caddy CA; public DNS/ACME and customer deployment were not tested.

## Demo is not a benchmark

M8 fixtures are independently authored, explicitly synthetic and under `demo/fixtures`, with no dataset imports. The seed's pre-reviewed completed invoice uses known fixture values through the normal review API. Its results demonstrate workflow correctness, not independent extraction accuracy. Existing M6/M7 screenshots are labeled as historical synthetic views when reused.
