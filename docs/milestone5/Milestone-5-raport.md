# Milestone 5 — Secure Document Intake & Human Review Operations

Data weryfikacji: 2026-09-28. Branch: `milestone-5-secure-intake-review-ops`.
Baza: `7eec8c8` (zamknięty M4). **M5 zaimplementowano i zweryfikowano end-to-end.**
Nie wykonano push. Zmiany pozostawiono do finalnego review bez commita ze względu
na opisaną poniżej odziedziczoną niespójność freeze M4.

## Cel i granica zakresu

Nowa warstwa chroni wejście do istniejącego M4 i tworzy trwałą pracę operatora.
Nie zmieniono algorytmów OCR, routingu, progów, profili ani wyników M3/M4.
Nie wykonywano żadnego HOLDOUT ani strojenia OCR w M5. Testy M5 korzystają wyłącznie
z nowych, syntetycznych danych; nie są benchmarkiem dokładności OCR.

## Architektura i security verdict flow

`manual/API/email -> CaseService.upload -> immutable raw storage -> Attachment
-> AttachmentSecurityScan -> SAFE -> istniejący M4/OCR/extraction -> validation`.

`QUARANTINED / BLOCKED / SCAN_FAILED -> stop -> CRITICAL SECURITY_UNSAFE
-> REVIEW_REQUIRED -> ReviewTask -> transactional outbox -> n8n -> local sink`.

Gate znajduje się w jednym wspólnym miejscu, po zapisaniu oryginalnych bajtów i
przed importem/wywołaniem orkiestracji dokumentów. Nie wprowadzono CaseStatus
QUARANTINED. Scan należy do załącznika; sprawa mieszana nadal zachowuje blokujący
problem niebezpiecznego pliku. Korekta pól, revalidation, duplikat ani przetworzenie
kolejnego SAFE nie zamykają SECURITY_UNSAFE. Approval respektuje ten problem.

Storage używa istniejącego losowego klucza i trybu `xb`; API nie udostępnia
nadpisywania bajtów. Quarantine oznacza trwały rekord skanu, zachowany oryginał,
blokadę przetwarzania i blokadę pobierania przez zwykły endpoint. To logiczna
izolacja w istniejącym storage, nie osobny system WORM ani ochrona przed administratorem hosta.

## Threat model i polityka v1

Źródła zagrożenia: niezaufana treść maila/uploadu, fałszywa nazwa/MIME, executable
podszywający się pod PDF, wykrywalne sygnatury malware, aktywne/encrypted PDF,
niedostępny lub niejednoznaczny skaner, powtórzenia dostarczenia i przypadkowe
zatwierdzenie sprawy z niebezpiecznym załącznikiem.

| Kontrola | Zachowanie |
|---|---|
| Rozmiar security | Pusty lub ponad SECURITY_MAX_ATTACHMENT_BYTES: QUARANTINED/SIZE_LIMIT |
| Hard transport cap | Istniejący limit uploadu 5 MiB: HTTP 413, bez przyjęcia pliku do storage |
| Magic bytes | PDF, PNG, JPEG, TIFF; tekst musi być UTF-8 bez binarnych znaków sterujących |
| Allowlist | PDF/PNG/JPEG/TIFF/TXT; właściwy parser nadal zależy od OCR_ENABLED |
| Nazwa/MIME/magic | Niezgodność: QUARANTINED; application/octet-stream dopuszczalne wyłącznie przy zgodnej nazwie i wykrytym typie |
| Executable | MZ/ELF/shebang/Mach-O oraz niebezpieczne rozszerzenia, także podwójne: BLOCKED |
| ClamAV | Lokalny INSTREAM, framing, timeout, VERSION i jednoznaczna odpowiedź OK/FOUND |
| Malware/heuristic alert | BLOCKED; nazwa sygnatury zapisana |
| Awaria/timeout/error/niepełna odpowiedź | SCAN_FAILED, nigdy SAFE |
| PDF active content | Konserwatywny filtr nazw JS/JavaScript/Launch/EmbeddedFile/OpenAction/AA/RichMedia/Encrypt, także #xx |
| Archive | Brak aplikacyjnego rozpakowywania; typ nie jest dozwolony |

Magic/lekki filtr bajtów nie wywołują parsera dokumentu. ClamAV sam analizuje formaty
w izolowanym kontenerze jako element security preflight; żaden parser aplikacji,
OCR ani provider ekstrakcji nie dostaje bajtów przed SAFE. Aplikacja nie wykonuje
JS, makr ani osadzonych programów. Leksykalny filtr PDF nie jest pełnym CDR:
nie gwarantuje wykrycia dowolnej obfuskacji lub aktywnej treści skompresowanej.

ClamAV: oficjalna baza `1.4`, przypięty digest
`57deb108fc4c72778aa83eafbca7bb7153e28c3f57c005afd38d31f16da86f23`.
Rzeczywisty silnik: **ClamAV 1.4.6, baza 28137, 2026-09-28 06:24:12**.
Dockerfile dodaje AlertExceedsMax/AlertEncrypted, MaxScanTime 10 s, MaxRecursion 10,
MaxFiles 100, MaxScanSize 20 MiB, MaxFileSize/StreamMaxLength 5 MiB. Przekroczenia
limitów/niejednoznaczne odpowiedzi nie są uznawane za czysty skan. Baza sygnatur
jest aktualizowana przez FreshClam i przechowywana wyłącznie w wolumenie runtime.
Healthcheck sprawdza daemon, a błędy skanowania są fail-closed niezależnie od healthchecka.

Dokumentacja protokołu: https://docs.clamav.net/manual/Usage/ClamdProtocol.html
oraz kontenera: https://docs.clamav.net/manual/Installing/Docker.html.

## Resolution i kolejka operatora

ReviewTask jest osobnym, trwałym modelem, powiązanym z ValidationIssue i Attachment.
Statusy: OPEN, ACKNOWLEDGED, RESOLVED, DISMISSED. Typy: SECURITY_QUARANTINE,
OCR_REVIEW, EXTRACTION_FAILURE, UNSUPPORTED_ATTACHMENT. Priorytet CRITICAL dla
security, HIGH dla pozostałych. Nullable unique `active_key` zapewnia dedup aktywnego
problemu i zachowanie historii zamkniętych zadań. Case lock serializuje decyzje.

* Acknowledge wymaga reason; opcjonalny assigned_to pozostaje deklaracją operatora.
* OCR rozwiązuje się przez istniejące sprawdzenie wszystkich pól dokumentu; zadanie
  zamyka się automatycznie po rozwiązaniu odpowiadającego issue.
* SAFE, ale nieobsługiwany dokument / extraction failure: jawny resolve/dismiss
  z reason po manualnej weryfikacji. Nadal obowiązują pozostałe reguły biznesowe.
* Security: **brak release/override SAFE**. Operator odrzuca całą sprawę z reason,
  co zamyka zadania, ale nie usuwa oryginału, verdictu ani security issue.
  Poprawiony dokument trafia do nowej sprawy i ponownie przechodzi cały gate.
* W M5 nie ma rescan/release załącznika w tej samej sprawie. Dotyczy to również
  SCAN_FAILED; po naprawie usługi operator tworzy nową sprawę. To celowy koszt
  konserwatywnej polityki, a nie obejście malware przez kliknięcie.

UI: istniejący admin z panelem Review Queue, OPEN count, priorytetem/typem,
public case ID, nazwą pliku, reason, datą i statusem. Filtr statusu, paginacja
50 zadań, odświeżanie co 10 s, detail/historia skanów, acknowledge i dozwolone
decyzje. Kontekst OCR jest w istniejącym panelu sprawy.

## Notification architecture

ReviewTask i NotificationOutbox powstają w tej samej transakcji co issue.
Unique task_id oznacza jeden event na utworzone zadanie. Payload webhooka zawiera
event/task/case ID, public ID, typ, priorytet, krótki reason i link z case ID;
nie zawiera bajtów dokumentu ani danych klienta.

Osobny worker wybiera event przez PostgreSQL FOR UPDATE SKIP LOCKED, próbuje
wysyłki, zapisuje attempts/last_error/next_attempt_at/sent_at i audyt. Backoff
2^attempt sekund, maks. 1 h, bez porzucania zdarzenia po stałej liczbie prób.
HTTP redirecty wyłączone; brak matching sink receipt nie oznacza sukcesu.

n8n workflow `boahReviewM5`, webhook `boah-review-m5`, waliduje identyfikatory i
wysyła je do stałego lokalnego sinka. Retry HTTP w n8n: 3. Local sink wykonuje
atomowe INSERT ON CONFLICT DO NOTHING z unikalnym event_id; replay nie tworzy
drugiego powiadomienia. Osobna tabela receipt unika blokowania callbacka przez
transakcję workera. Dopiero potwierdzenie sinka powoduje SENT.

Gwarancja to at-least-once HTTP + idempotentny efekt w lokalnym sinku, nie ogólne
exactly-once SMTP. Trwałe receipts oraz aktywna kolejka są lokalnym kanałem demo.
Nie skonfigurowano prawdziwej skrzynki ani nie wysyłano wiadomości do osób.
Przyszłe SMTP: dodać credentials w UI n8n i docelowy kanał za deduplikującym
consumerem; zwykły SMTP nie zapewnia exactly-once przy utracie potwierdzenia.
Nie wolno wstawiać node SMTP przed deduplikację i twierdzić, że replay nie spamuje.

## DB, API, audit

Alembic `59bc8877f30b` po `f3a901c2d700` dodaje:
`attachment_security_scans`, `review_tasks`, `notification_outbox`,
`notification_receipts`; indeksy case/attachment/verdict/status/type/priority/
next_attempt/sent_at, unique active_key/task_id/event_id, constraints verdict,
status, priority, task_type, nieujemny rozmiar. Upgrade istniejącego PostgreSQL
przeszedł, `alembic check`: brak nowych operacji. Istniejące tabele nie są przebudowane.
Stare załączniki nie otrzymują fałszywego SAFE; zwykły download niezeskanowanego
oryginału jest blokowany. Nie wykonano masowego rescan ani backfill zadań historycznych.

API:

* GET `/api/v1/review-tasks`: domyślnie active; status/task_type/priority/case_id,
  offset/limit, total/open_count.
* GET `/api/v1/review-tasks/{id}`: task + historia skanów.
* POST `/api/v1/review-tasks/{id}/decision`: action acknowledge/resolve/dismiss/
  reject_case, wymagany reason, opcjonalny assigned_to; niedozwolone decyzje 409.
* POST `/api/v1/review-tasks/notifications/receipt`: local sink, tylko istniejące
  event_id i zgodny task_id, replay idempotentny; brak dowolnego payloadu wiadomości.
* Case detail rozszerzono o security_scans i review_tasks. Istniejące endpointy
  review/OCR/email zachowują kontrakty, a nowe uploady w secure mode mogą przyjąć
  podejrzany typ do trwałej kwarantanny zamiast dawnego 415 przed storage.

Audyt: wszystkie wymagane ATTACHMENT_SECURITY_SCAN_STARTED/SAFE,
ATTACHMENT_QUARANTINED/BLOCKED/SECURITY_SCAN_FAILED,
REVIEW_TASK_CREATED/ACKNOWLEDGED/RESOLVED,
REVIEW_NOTIFICATION_QUEUED/SENT/FAILED. W reason/notification błędach nie zapisuje
się odpowiedzi HTTP ani URL potencjalnie zawierających credentials.

## Test matrix i rzeczywiste wyniki

| Weryfikacja | Wynik |
|---|---|
| Bazowa regresja przed M5 | 178 passed, 2 skipped (SQLite) |
| Nowe testy M5 | 30 passed, w pełnym suite |
| Finalny pełny backend SQLite | **208 passed, 2 skipped**; skipped to istniejące testy PostgreSQL |
| Finalny pełny backend PostgreSQL | **210 passed**, w tym testy współbieżności M1/M2 |
| Ruff app/tests/alembic + skrypt M5 | **PASS** |
| mypy app | **PASS, 64 pliki** |
| Frontend lint / typecheck / production build | **PASS / PASS / PASS** |
| n8n node:test | **9 passed**, 6 istniejących + 3 M5 |
| Alembic upgrade head / check | **PASS / brak rozbieżności schematu** |
| Live E2E | **10 scenariuszy PASS**, rzeczywisty ClamAV, BOAH, PostgreSQL i n8n |
| Live notification delivery/replay | **10/10 eventów SENT i 10 receipts**; dwa replay przez n8n, nadal 10 receipts |
| Realny scanner outage | **SCAN_FAILED**, brak OCR/extraction, approval 409; ClamAV przywrócony |
| UI | **PASS**: queue, context, acknowledge, reject_case, RESOLVED + FAILED, disabled approve |
| Services | backend/PostgreSQL/n8n/ClamAV/Tesseract/Paddle healthy, worker running, UI HTTP 200 |

Testy security: poprawne PDF/PNG/JPEG, extension/MIME mismatch, double extension,
executables, archive/unsupported, active/encrypted PDF, size bez dużego payloadu,
EICAR framing i rzeczywisty ClamAV, niedostępność/timeout/inconclusive scanner,
sentinel dowodzący braku wywołania parserów/providerów, SAFE -> niezmienione
M4 primary i M3 dual, mixed case, shared email gate, blocked download/approval.
Queue: creation/dedup/filtering/ack/invalid transitions, wszystkie cztery typy,
resolve, automatic OCR resolution i reject_case. Notification: durable outbox,
failure/retry/backoff/success, matching receipt, replay bez drugiego sink record.
Konfiguracja env: `true` poprawnie parsowane; fail-open `false` jest odrzucane.

Live E2E nie mierzy CER/WER i nie zmienia reguł M4. Syntetyczny native PDF przeszedł
NATIVE_TEXT, ale zachował wymaganie review wynikające z istniejącego raportu M4;
PNG/JPEG przeszły PRIMARY_OCR. Nie korygowano tego zachowania w M5.

Dowody: `e2e-results.json`, `scanner-outage.json`, `notification-results.json`, `health-results.json`,
`frozen-artifacts-check.json`, `review-ui.png`. Generator fixtures i odtwarzalny
E2E: `scripts/milestone5/e2e.py`; katalog datasetu zawiera wyłącznie opis generatorów.

## Odziedziczona niespójność freeze M4 — ważne ograniczenie

Na początku repo było czyste. M5 nie zmienia chronionych katalogów M3/M4 względem
`7eec8c8`. Odczytowa kontrola 113 hashy M4 wykazała jednak:

* 61 zgodnych bajtowo;
* 44 różnice wyłącznie LF/CRLF checkoutu Windows;
* 8 innych różnic już obecnych w bazowym commicie: pięć plików implementacji
  document_routing, `configs/stp/policy.json`, `scripts/benchmark_stp.py`,
  `scripts/generate_stp_dataset.py`.

Pełne ścieżki i SHA-256 blobów bazowego commita są w JSON dowodowym. Aktualne
wersje tych ośmiu plików odpowiadają bazowemu commitowi po normalizacji EOL.
Nie ustalono w M5 przyczyny historycznych różnic ani równoważności tych wersji
z rzeczywistą wersją benchmarkowaną. Nie zmieniono plików/freeze i nie powtórzono
HOLDOUT. **Nie należy przedstawiać M5 jako ponownej walidacji historycznych wyników M4.**
Ta niespójność wymaga osobnego review pochodzenia artefaktów M4, nie strojenia na HOLDOUT.

## Acceptance i ograniczenia

Wszystkie funkcjonalne kryteria M5 w opisanym lokalnym środowisku przeszły.
Ochrona nowego intake jest domyślnie włączona i fail-closed. Legacy regression
mode jest jawny w fixture testów (fałszywe PDF z M1–M4); nowe testy M5 włączają
security i mockują wyłącznie granicę AV, a live E2E używa prawdziwego skanera.

Celowo odłożone: uwierzytelnianie/RBAC i wiarygodna tożsamość assigned_to,
produkcyjny kanał SMTP, sandbox per dokument/CDR, HA/outbox monitoring, retencja
i purge, WORM storage, ponowne skanowanie/release w tej samej sprawie, backfill
historycznych tasks/scans, analiza archiwów i dokumentów Office. Obecny admin/API
jest lokalnym demo bez auth; nie należy wystawiać go publicznie. AV i magic bytes
nie dowodzą absolutnego bezpieczeństwa ani poprawności strukturalnej dokumentu.
Stare wyniki M4 pozostają zamknięte z opisaną niespójnością provenance.

## Uruchomienie i odtworzenie

```powershell
docker compose -f docker-compose.yml -f docker-compose.ocr.yml -f docker-compose.security.yml up -d --build
docker compose exec -T n8n n8n import:workflow --input=/workflows/review-notifications.json
docker compose exec -T n8n n8n publish:workflow --id=boahReviewM5
docker compose restart n8n
# Poczekaj na healthy ClamAV; pierwszy start pobiera/aktualizuje sygnatury.
backend/.venv/Scripts/python.exe scripts/milestone5/e2e.py --output docs/milestone5/e2e-results.json
```

Importować tylko nowy workflow, nie cały katalog, aby nie dezaktywować istniejących
email workflows. Backend sam wykonuje `alembic upgrade head` przed startem.
UI: http://localhost:3000, API docs: http://localhost:8000/docs, n8n: http://localhost:5678.
ClamAV port 3310 jest związany z loopback hosta. Wolumenów runtime nie dodawać do Git.

Settings i `.env.example`: SECURITY_PREFLIGHT_ENABLED=true, SECURITY_FAIL_CLOSED=true
(false odrzucane), SECURITY_MAX_ATTACHMENT_BYTES, SECURITY_ALLOWED_MIME_TYPES,
CLAMAV_HOST/PORT/TIMEOUT_SECONDS, REVIEW_NOTIFICATIONS_ENABLED,
REVIEW_NOTIFICATION_WEBHOOK_URL/TIMEOUT_SECONDS. Compose security dodatkowo włącza
istniejący STP; ustawienia i progi zamrożonych algorytmów pozostają niezmienione.

Testy lokalne: `uv sync --extra dev`, `uv run pytest`, `uv run ruff check app tests alembic`,
`uv run mypy app` w backend. PostgreSQL: TEST_DATABASE_URL wskazuje lokalną bazę;
fixture zakłada i usuwa izolowany schemat dla testu. Frontend: `npm run lint`,
`npm run typecheck`, `npm run build`; n8n: `node --test n8n/tests/*.test.cjs`.

## Kluczowe pliki i stan przekazania

`backend/app/security/preflight.py`, `backend/app/models/operations.py`,
`backend/app/services/operations.py`, `backend/app/services/notifications.py`,
`backend/app/api/routes/tasks.py`, wspólny `services/cases.py`, migracja
`59bc8877f30b`, `frontend/app/review-queue.tsx`,
`n8n/workflows/review-notifications.json`, `docker-compose.security.yml`,
`security/clamav/Dockerfile`, `backend/tests/test_security_operations.py`.

Repo gotowe do finalnego review M5. Lokalnego commita nie utworzono; zgodnie z
poleceniem przy wątpliwości pozostawiono zmiany niezatwierdzone. Nie wykonano push.
Kontrola statusu obejmuje wyłącznie kod/config/example env, testy, syntetyczne
generatory i raporty; brak `.env`, credentials, DB, storage, cache i danych n8n.
