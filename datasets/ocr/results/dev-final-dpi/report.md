# OCR benchmark: dev

Profiles: {'tesseract': 'dpi', 'paddle': 'dpi'}

| Provider | CER | WER | Exact | Normalized/critical | Failures | Mean ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| tesseract | 0.1717 | 0.5451 | 0.8036 | 0.8036 | 0.0000 | 606.5 | 799.1 |
| paddle | 0.0981 | 0.1458 | 1.0000 | 1.0000 | 0.0000 | 3961.5 | 4369.1 |

## Consensus

```json
{
  "agreement": 45,
  "disagreement": 11,
  "both_correct": 45,
  "one_correct_conflict": 11,
  "both_wrong_agreement": 0,
  "both_wrong_disagreement": 0,
  "field_pairs": 56,
  "pairwise_agreement": 0.8035714285714286,
  "pairwise_disagreement": 0.19642857142857142,
  "false_consensus_rate_all_pairs": 0.0,
  "false_consensus_rate_agreements": 0.0
}
```

## Per critical field

{
  "tesseract": {
    "document_number": 0.875,
    "tax_id": 0.875,
    "issue_date": 0.875,
    "net_total": 0.75,
    "vat_total": 0.75,
    "gross_total": 0.75,
    "currency": 0.75
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
