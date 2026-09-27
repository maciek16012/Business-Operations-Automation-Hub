# Sample scenarios

All inputs are synthetic UTF-8 `Label: value` fixtures for the development extraction provider.

| Fixture | Expected result |
|---|---|
| valid_inquiry.txt | READY; PLN 12500.00, valid NIP, distant ISO deadline |
| duplicate_renamed.txt | Byte-for-byte copy of valid_inquiry.txt; upload to the same case to see duplicate warning/audit and no second attachment |
| missing_required.txt | REVIEW_REQUIRED: no customer/company or title |
| invalid_nip.txt | REVIEW_REQUIRED: invalid checksum |
| negative_value.txt | REVIEW_REQUIRED: negative amount |
| malformed_values.txt | REVIEW_REQUIRED: unparseable amount/deadline |
| review_required.txt | REVIEW_REQUIRED; correct NIP to 5260250274 and value to 12 500,00 PLN, then approve/export |

Accepted labels: Customer, Email, Company, NIP, Title, Description, Requested deadline, Estimated value, Currency. Repeated labels, invalid UTF-8 or no recognized fields cause a persisted processing failure. Conflicting fields across different attachments require manual confirmation. The optional confidence column is null because this deterministic provider does not estimate confidence.

M2: email_specification.txt contains only NIP, amount and deadline. scripts/demo_email_ingestion.py supplies synthetic metadata and 0/1/multiple attachments via n8n or direct API.
