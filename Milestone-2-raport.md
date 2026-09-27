# Milestone 2 — raport końcowy

Data: 2026-09-27. Repozytorium: `C:\AI\BusinessOperationsAutomationHub`.

## Wynik i zakres

Zaimplementowano i zweryfikowano vertical slice: e-mail → n8n → inbound API → jedna sprawa → zapis załączników → istniejąca ekstrakcja/walidacja → review → approval → JSON/XLSX. Zachowano starter, core i testy Milestone 1; raport M1 jest w `docs/verification.md`.

Nie wykonano rzeczywistego odbioru z zewnętrznej skrzynki IMAP, ponieważ nie udostępniono credentials. Workflow IMAP zaimportowano i pozostawiono nieaktywny, gotowy do powiązania ze skrzynką. Binarne załączniki, mapowanie, HTTP, replay, review, eksporty i obsługę błędów wykonano na działającej instancji n8n przez deterministyczny workflow fixture. Nie jest to przedstawiane jako test zewnętrznego IMAP.

## Decyzje architektoniczne i baza

n8n odpowiada za odbiór, mapowanie, HTTP, ograniczone retry i opis awarii. Reguły biznesowe, statusy, idempotencja, walidacja i audyt pozostają w FastAPI. Workflow nie zapisuje do biznesowej bazy ani storage.

Migracja `e5ebcbe7c468`, po `72087185dc49`, dodaje `inbound_messages` jako ósmą tabelę domenową. Zawiera metadane, treści plain/HTML, metodę i klucz tożsamości, wyniki załączników i relację 1:1 z Case. Unikalność `(source_type, identity_key)` oraz `INSERT ON CONFLICT` zabezpieczają równoległe dostarczenia. Rezerwacja tożsamości i utworzenie sprawy są objęte jedną transakcją.

Poprawny Message-ID jest normalizowany: usunięcie zewnętrznych nawiasów/whitespace, domena małymi literami, zachowana wielkość lokalnej części. Fallback to wersjonowany SHA-256 kanonicznego zestawu: nadawca, To/Cc, temat, sent_at, treści i posortowane hashe załączników. received_at, kolejność i nazwy plików nie zmieniają tożsamości. Identyczne wiadomości bez Message-ID mogą być nierozróżnialne.

CaseService otrzymał opcjonalny tryb email_review. Domyślna ścieżka manual upload zachowuje M1. Nieobsługiwany plik jest zachowywany i wymaga uzasadnionego przeglądu przed approval. Błąd ekstrakcji jednego dokumentu nie ukrywa pozostałych. HTML jest wyświetlany w UI jako escaped text, bez wykonywania znaczników.

## Kontrakt API i audyt

`POST /api/v1/inbound/email`: source_type=imap; opcjonalny external_message_id; sender {address,name}; recipients/cc/reply_to; subject; wymagany received_at ze strefą; opcjonalny sent_at; text_body/html_body; attachments [{filename,mime_type,content_base64}]. Maksymalnie 10 załączników, domyślnie 5 MiB każdy. Walidacja wszystkich danych/base64 poprzedza tworzenie sprawy.

201 oznacza result=created; 200 oznacza result=duplicate. Odpowiedź zawiera case_id, public_case_id, message_id, aktualny status, processing_status, identity_method i attachment_results. Replay nie powtarza przetwarzania biznesowego ani nie dodaje dokumentów; po eksporcie zwraca EXPORTED.

`POST /api/v1/inbound/messages/{message_id}/attachments/{attachment_id}/review` wymaga reason, sprawdza przynależność i edytowalność, rozwiązuje tylko problemy przeglądu dokumentu i uruchamia walidację. Nie obchodzi reguł biznesowych.

Zdarzenia: EMAIL_RECEIVED, EMAIL_CASE_CREATED, EMAIL_DUPLICATE_IGNORED, EMAIL_ATTACHMENT_STORED, EMAIL_INGESTION_FAILED, EMAIL_ATTACHMENT_REVIEWED. Pozostałe kontrakty M1 zachowano, w tym zakaz tworzenia email przez zwykłe POST /cases bez wiadomości źródłowej.

## n8n i obsługa awarii

Oficjalny obraz `docker.n8n.io/n8nio/n8n:2.40.7`; port `127.0.0.1:5678`; Europe/Warsaw; persistent volume `n8n_data`; binaria filesystem. n8n generuje klucz szyfrowania wewnątrz volume. JSON nie zawiera haseł, kluczy ani credential IDs.

- `inbound-email.json`: IMAP Resolved → normalizacja → API → klasyfikacja odpowiedzi.
- `inbound-email-fixture.json`: webhook tworzący rzeczywiste binaria n8n, potem te same węzły normalizacji i HTTP.
- `inbound-email-error.json`: Error Trigger i recovery summary z kategorią, execution ID/URL i krokiem naprawczym.

Zaimportowano wszystkie trzy workflow i sprawdzono eksport CLI fixture. Fixture i error workflow opublikowano; w 2.40.7 Error Trigger wymaga publikacji. HTTP: timeout 15 s, do 3 prób, 1 s odstępu. Duplicate jest sukcesem idempotent_noop. Kategorie błędów obejmują INVALID_PAYLOAD, BACKEND_UNAVAILABLE, BACKEND_TIMEOUT, INGESTION_FAILED i nieoczekiwane awarie. Brak nieskończonego retry i wysyłki e-maili. Konfiguracja prawdziwej skrzynki i recovery: `n8n/README.md`.

## Testy i pełna weryfikacja

| Kontrola | Wynik |
|---|---|
| Baseline M1 SQLite przed implementacją | 113 passed, 1 skipped |
| Baseline M1 PostgreSQL | 114 passed |
| Pełny SQLite przed przerwaniem | 133 passed, 2 skipped, 2.99 s |
| Pełny PostgreSQL przed przerwaniem | 135 passed, 13.49 s |
| SQLite powtórzony po wznowieniu | 133 passed, 2 skipped, 2.95 s |
| PostgreSQL powtórzony po wznowieniu | 135 passed, 14.85 s |
| Ruff format / lint po wznowieniu | 51 plików sformatowanych; All checks passed |
| mypy po wznowieniu | 43 source files, brak błędów |
| Testy workflow powtórzone po wznowieniu | 6 passed, 0 failed |
| Frontend lint/typecheck/build | PASS przed przerwaniem i po wznowieniu; build 4.3 s, TypeScript 1341 ms |
| Alembic | fresh upgrade; downgrade M1; upgrade M2; downgrade base; fresh upgrade; PASS |
| Alembic check po wznowieniu w kontenerze | No new upgrade operations detected |
| Compose config/build/up | PASS; config/stan powtórzone po wznowieniu |
| UI | źródło, treści, escaped HTML, załącznik, EXPORTED, eksporty i audyt zweryfikowane |

Dwa skipy SQLite dotyczą mechanizmów współbieżności PostgreSQL; na docelowej bazie wszystkie 135 testów przeszło. Test sześciu równoległych dostarczeń wymaga jednej sprawy. Pozostałe nowe testy obejmują fallback, replay po eksporcie, deduplikację plików, niepoprawne payloady bez skutków ubocznych, unsupported/malformed attachment, storage failure, review i oba eksporty. Pliki testów M1 pozostawiono bez zmian.

Przy wznowieniu lokalny `alembic check` początkowo nie rozwiązał dockerowej nazwy hosta `postgres`. Wykonanie tej samej kontroli przez `docker compose exec -T backend alembic check` przeszło. Nie był to błąd migracji i nie wymagał zmian kodu. Pełny wcześniejszy cykl downgrade/upgrade wykonano na osobnej jednorazowej bazie, usuniętej po weryfikacji; nie powtarzano go na danych aplikacji.

## Dowody deterministycznego demo

Główne demo n8n: run_id `milestone2-acceptance`. **7 dostarczeń → 3 nowe sprawy → 3 unikalne zapisane załączniki → 0 dodatkowych spraw z replay.**

| Wariant | Case ID | Pliki | Status końcowy |
|---|---|---:|---|
| zero | 5ad5bbd6-9568-4b28-ae76-b213e8473512 | 0 | REVIEW_REQUIRED |
| one | 2e66f0b9-8be0-4105-b1b1-740e70922445 | 1 | EXPORTED |
| multiple | 66391da0-e8fe-424f-ab67-205929ad11c8 | 2 | REVIEW_REQUIRED |

Wariant multiple zawierał także kopię dokumentu pod inną nazwą, poprawnie pominiętą. Główna wiadomość: `<boah-demo-milestone2-acceptance-one@example.test>`; InboundMessage `e219257b-9eb4-467b-aa25-c73ed3af1018`. Zachowano polski temat i treść, Jan Kowalski, jan@example.test, office@example.test. Transport akceptuje syntetyczne .test, ale istniejąca walidacja biznesowa M1 kieruje ten adres do review. Korekta do jan@example.com doprowadziła do READY → APPROVED → EXPORTED. NIP 5260250274, wartość 12500.00 PLN, termin 2099-10-20.

Eksport JSON: `7d3b195d-f3e1-4e45-9ef8-d96694116c53`; XLSX: `6d26b1d5-ceb7-416c-9e1c-5072431f0602`. Skrypt zweryfikował dane JSON, cztery arkusze XLSX i wartość liczbową. Audyt miał 22 zdarzenia na końcu demo; dodatkowy replay po odtworzeniu kontenerów dodał tylko wpis duplikatu (23), zachował EXPORTED i liczbę spraw.

Osobne demo przez API, run_id `9802a10582`: również 7 dostarczeń, 3 sprawy, 3 załączniki, brak dodatkowych spraw z replay, poprawne review/approval/JSON/XLSX.

Kontrolowane awarie działającej instalacji (run_id ad329c46):
- Invalid payload: backend 422; n8n webhook 500; error execution 12, parent 11, INVALID_PAYLOAD.
- Backend zatrzymany: błąd po 13.77 s, error execution 14, parent 13, BACKEND_UNAVAILABLE. Po przywróceniu created, potem duplicate; case 52da26f9-d2e9-4846-a84b-635830a5d554.
- Backend wstrzymany: timeout po 47.06 s, error execution 18, parent 17, BACKEND_TIMEOUT. Spóźnione żądanie zapisało się po wznowieniu; ponowienie zwróciło duplicate dla e08e2b38-71ed-4117-9204-b9b90033a572.
- Dwie odzyskane tożsamości dały dokładnie dwie sprawy. Backend przywrócono. Wszystkie trzy wykonania Error Trigger zakończyły się sukcesem.

Dowody zachowane w outputs zadania: `milestone-2-email-demo.json`, `milestone-2-delivery-errors.json`, `milestone-2-ui.png`, eksporty `CASE-2026-2e66f0b98be04105b1b1.json/.xlsx` oraz `direct-api/`. Manifest demo jest migawką sprzed dodatkowego testu trwałości. Pliki dowodowe sprawdzono po wznowieniu; nie dodaje się danych runtime do Git.

## Stan Docker, Git i finalizacja

Po wznowieniu: backend, PostgreSQL i n8n healthy; frontend Up. UI: http://localhost:3000; API: http://localhost:8000/docs; n8n: http://localhost:5678. Wcześniejsze odtworzenie kontenerów zachowało workflow, sprawy i eksporty.

Repozytorium początkowo nie miało HEAD i wszystkie źródła były untracked. Pierwszy lokalny commit obejmuje istniejący Milestone 1 i Milestone 2, raport, testy oraz sanitized workflow JSON. Nie wykonuje się push. Kontrola indeksu wyklucza .env, credentials, runtime, lokalne dane n8n/storage, cache, .venv i node_modules; `.env.example` zawiera wyłącznie jawne developerskie wartości przykładowe. `backend/app/storage` to kod abstrakcji storage i musi pozostać w repozytorium. Hash oraz wynik końcowego git status podano w odpowiedzi końcowej, aby nie wprowadzać samoodwołania hasha w commicie.

## Ograniczenia i Milestone 3

Brak testu rzeczywistego IMAP bez credentials. UID cursor węzła nie jest trwałą kolejką potwierdzeń; oryginały pozostają nieprzeczytane, a procedurę retry/reconciliation opisano. Identyczne wiadomości bez Message-ID mogą mieć ten sam fingerprint; ponowny Message-ID zawsze wskazuje pierwotną sprawę także przy zmienionym payloadzie.

Terminalny FAILED po awarii storage pozostaje terminalny zgodnie z M1; replay nie uruchamia ponownie przetwarzania. Filesystem i DB nie stanowią transakcji rozproszonej, więc przerwanie może pozostawić orphan object. Base64 jest przesyłane w limitowanym payloadzie. Instalacja jest lokalna/deweloperska, bez publicznego wdrożenia i RBAC. Retencja wykonań n8n: 168 godzin.

Nie wdrażano OCR/PDF extraction, AI/LLM, outbound replies, CRM/ERP, dodatkowych kolejek ani infrastruktury produkcyjnej. Milestone 3: benchmark OCR, provider, dataset i metryki — pozostaje odłożony.

## Odtworzenie — PowerShell

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub
# Tylko na nowej instalacji, gdy .env jeszcze nie istnieje:
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose config --quiet
docker compose ps
# Import na nowej instancji; przed reimportem zachowaj lokalne zmiany/bindings:
docker compose exec -T n8n n8n import:workflow --separate --input=/workflows
docker compose exec -T n8n n8n publish:workflow --id=boahEmailErrors2
docker compose exec -T n8n n8n publish:workflow --id=boahEmailFixture2
docker compose restart n8n
node --test n8n/tests/workflows.test.cjs
docker compose exec -T backend alembic check
Set-Location backend
uv sync --extra dev
uv run ruff format --check app tests alembic
uv run ruff check app tests alembic
uv run mypy app
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
uv run pytest -q
$env:TEST_DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
uv run python ../scripts/demo_email_ingestion.py --via n8n --output-dir ../storage/demo-m2
uv run python ../scripts/demo_email_ingestion.py --via api --output-dir ../storage/demo-m2-api
# Czasowo zatrzymuje/wstrzymuje lokalny backend:
uv run python ../scripts/verify_email_delivery_errors.py --output ../storage/demo-m2-errors.json
Set-Location ../frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

Dostosuj PostgreSQL URL, jeśli zmieniono domyślne dane developerskie. Demo generuje nowy run-id; ponowne użycie tego samego run-id celowo nie spełni asercji nowego pomiaru. Replay wykonuje sam skrypt. Przy lokalnym Alembic ustaw DATABASE_URL z hostem localhost; wewnątrz Compose poprawną nazwą jest postgres.

Cykl migracji wykonuj wyłącznie na nowej bazie jednorazowej: upgrade head → downgrade 72087185dc49 → upgrade head → downgrade base → upgrade head → check. Nie wykonuj downgrade na bazie z zachowanymi sprawami.
