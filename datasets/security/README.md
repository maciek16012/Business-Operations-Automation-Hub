# M5 synthetic security fixtures

Fixtures are generated in memory by `scripts/milestone5/e2e.py::fixtures` and
`backend/tests/test_security_operations.py::fixture_bytes`. No confidential
documents or binary malware samples are committed. Inputs are deterministic;
the PDF generator disables random document IDs.

Matrix: valid native PDF, rendered invoice PNG/JPEG, spoofed extension, spoofed
MIME, harmless MZ bytes renamed PDF, standard harmless EICAR test string, unknown
binary format, harmless archive header, active/encrypted PDF name markers, mixed
SAFE/BLOCKED case. The size condition lowers the policy limit to 4/8 bytes in tests;
no large files, archive bombs or executable programs are generated.

EICAR is assembled only in test memory and sent to the local scanner. It is never
executed. Archive limits use rejection and scanner-response tests, not real bombs.

These fixtures are independent from closed M3/M4 DEV/HOLDOUT datasets and are
security acceptance tests, not an OCR accuracy evaluation.
