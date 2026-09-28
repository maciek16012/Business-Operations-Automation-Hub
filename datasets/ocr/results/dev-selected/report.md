# OCR benchmark: dev

Profiles: {'tesseract': 'orientation', 'paddle': 'orientation'}

| Provider | CER | WER | Exact | Normalized/critical | Failures | Mean ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| tesseract | 0.0366 | 0.0590 | 0.9286 | 0.9286 | 0.0000 | 464.4 | 543.2 |
| paddle | 0.0046 | 0.0347 | 1.0000 | 1.0000 | 0.0000 | 4288.1 | 7286.1 |

## Consensus

```json
{
  "agreement": 52,
  "disagreement": 4,
  "both_correct": 52,
  "one_correct_conflict": 4,
  "both_wrong_agreement": 0,
  "both_wrong_disagreement": 0,
  "field_pairs": 56,
  "pairwise_agreement": 0.9285714285714286,
  "pairwise_disagreement": 0.07142857142857142,
  "false_consensus_rate_all_pairs": 0.0,
  "false_consensus_rate_agreements": 0.0
}
```

## Per critical field

{
  "tesseract": {
    "document_number": 1.0,
    "tax_id": 1.0,
    "issue_date": 1.0,
    "net_total": 0.875,
    "vat_total": 0.875,
    "gross_total": 0.875,
    "currency": 0.875
  },
  "paddle": {
    "document_number": 1.0,
    "tax_id": 1.0,
    "issue_date": 1.0,
    "net_total": 1.0,
    "vat_total": 1.0,
    "gross_total": 1.0,
    "currency": 1.0
  }
}
