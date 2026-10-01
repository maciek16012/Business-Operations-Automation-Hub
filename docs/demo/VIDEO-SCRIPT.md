# Video script — 3–5 minutes

Record the local synthetic demo from the [guide](DEMO-GUIDE.md). Hide `.runtime-demo/login.txt`, `.env` contents and developer terminals with credentials. Use a fresh seeded environment. Labels may contain Polish operator controls alongside English settings.

| Time | Screen/action | Suggested narration |
|---|---|---|
| 0:00–0:25 | Login, then dashboard | “BOAH is my self-hosted document operations project. It joins secure intake, extraction, human decisions and delivery in one auditable workflow.” |
| 0:25–1:15 | Completed invoice: preview, SAFE scan, fields, audit | “Documents pass MIME and antivirus checks before analysis. Invoices use native text and selective OCR. This synthetic case was explicitly confirmed by a reviewer; the demo does not measure OCR accuracy.” |
| 1:15–2:10 | Invoice needs review: invalid NIP, reasoned correction, approval | “Uncertain or invalid fields block approval. A reviewer compares the original, records corrected values and explains the change. The server enforces the same guards as the UI.” |
| 2:10–2:50 | Printed table and handwritten-like review | “Typed extraction preserves rows and cells, including uncertainty. This example uses rasterized italic text; there is no production handwriting recognizer. Unknown readings remain unresolved.” |
| 2:50–3:30 | Sources Test connection, jobs, routing/destinations | “Native IMAP and watched folders feed cases. Approved records reach a mounted archive or signed webhook through durable jobs. Failed delivery retries with a stable idempotency key.” |
| 3:30–4:05 | Archive, exports, audit, System health | “The workflow retains originals, structured exports and an audit trail. Operators can inspect dependencies and recover failures.” |
| 4:05–4:30 | README evaluation and limitations | “The reported 95% invoice STP is from 20 synthetic M4 documents, with zero observed false accepts there. M6 classified 17 of 20 documents correctly but cell accuracy was about 31%; review is essential. Local production checks are not evidence of a public customer deployment.” |

If a live transition takes longer, cut waiting time and label the cut. Do not animate fabricated outcomes or describe locally tested controls as independently certified. End on the repository overview; proposed `v1.0.0-demo` is not an already published release.
