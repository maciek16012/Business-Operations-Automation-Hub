# Milestone 8 — raport końcowy

Data weryfikacji: **2026-09-30**. Repozytorium: `C:\AI\BusinessOperationsAutomationHub`. Branch: `milestone-8-portfolio-demo-release`. Baza i niezmieniony HEAD: `a80f9631b7953f56335fd4c75ad0440ff7c80e1d`.

**M8 ukończony jako lokalne przygotowanie portfolio/demo/release. Nie wykonano commita, push, tagu ani publikacji release. Zmiany pozostają w working tree do ręcznego review.**

## Zakres i zachowanie istniejącego produktu

Przed pracą sprawdzono czysty stan repo, strukturę, starter, README, raporty M1–M7, istniejący frontend/screenshoty, compose, produkcję, E2E, backup/restore, security i zapisane benchmarki. Nie zbudowano produktu od nowa i nie dodano nowego modelu, OCR, connectora ani subsystemu.

M5 security gate pozostaje przed klasyfikacją. M4 invoice pipeline i M6 adaptive extraction są zachowane. Historyczne M4/M6 HOLDOUT, dane, konfiguracje, raporty, OCR i pipeline nie zostały zmienione ani uruchomione. Bieżąca regresja testów jednostkowych/integracyjnych nie jest ponownym przebiegiem historycznego HOLDOUT.

Jedyną zmianą istniejącego kodu aplikacji jest kosmetyczne zastąpienie badge `M6` przez `Document types` w dashboardzie. Historyczna migracja M7 pozostaje bez zmian. Nie zmieniono plików M4.

## README i materiały portfolio

- [README](../../README.md): opis produktu i odbiorców, capabilities, cztery aktualne screenshoty, diagram Mermaid, workflow, security/integracje/review/intelligence, deployment, Quick Start, demo, testy, mierzone evaluation, ograniczenia, stack, struktura, dokumentacja, roadmap i status licencji.
- [CASE-STUDY](../portfolio/CASE-STUDY.md): problem biznesowy, architektura i decyzje, bezpieczeństwo, granice automatyzacji, integracje, obsługa błędów, recovery i wyniki.
- [PORTFOLIO-SUMMARY](../portfolio/PORTFOLIO-SUMMARY.md): opis projektu po polsku, **636 słów**, bez przypisywania sobie wdrożenia u klienta.
- [CAPABILITIES](../portfolio/CAPABILITIES.md), [EVALUATION](../portfolio/EVALUATION.md), [RELEASE-CHECKLIST](../portfolio/RELEASE-CHECKLIST.md), [RELEASE-NOTES](../portfolio/RELEASE-NOTES.md): macierz rzeczywistych funkcji, denominatory i granice wyników, wykonane lokalne gates i proponowane `v1.0.0-demo` do ręcznej decyzji.
- [CONFIGURATION](../CONFIGURATION.md) i [TROUBLESHOOTING](../TROUBLESHOOTING.md): profile, wymagane/env/optional wartości, klucze i restore, fail-closed, TLS, montowania, jobs, zimne cache i bezpieczna diagnostyka.
- [DEMO-GUIDE](../demo/DEMO-GUIDE.md): walkthrough 5–10 minut; [VIDEO-SCRIPT](../demo/VIDEO-SCRIPT.md): 3–5 minut do późniejszego nagrania. Nie wykonano publikacji ani nagrania wideo.

README rozróżnia małe syntetyczne benchmarki, lokalną weryfikację protokołów/HTTPS i niepotwierdzone wdrożenie publiczne. Nie dodano fikcyjnego CI badge ani wybranej za użytkownika licencji.

## Niezależne syntetyczne demo

[Demo](../../demo/README.md) zawiera sześć PDF: invoice-ready, invoice-review, printed-table, handwritten-table-like, generic-document, unknown; dodatkowo harmless `blocked-sample.exe.txt` i manifest. Firmy/osoby są fikcyjne, adresy używają `example.com`. NIP jest syntetyczny; w ćwiczeniu poprawny checksum ma `9900000000`, celowo błędny `9900000001`. Przykład handwriting to rasteryzowany druk kursywą, **nie realne rozpoznawanie pisma ręcznego**.

`scripts/demo/build_fixtures.py` korzysta z istniejących ReportLab/PyMuPDF i nie czyta danych benchmarkowych. Wszystkie sześć PDF wyrenderowano i obejrzano: czytelne, bez kolizji/ucięcia; minimalne „Note” jest celowo UNKNOWN. Manifest służy wyłącznie świadomemu review, nie ekstraktorowi i nie strojeniu.

[Compose demo](../../docker-compose.demo.yml) używa osobnego projektu `boah-portfolio-demo`, istniejących produkcyjnych Dockerfile aplikacji, dotychczasowych OCR/ClamAV/n8n oraz prywatnych fixture services GreenMail/webhook. Jedyny opublikowany port to **127.0.0.1:3080**. Pięć własnych wolumenów: DB, storage, n8n, modele Paddle i sygnatury ClamAV.

### Seed / start / reset

- `start_demo.ps1`: sprawdza Docker Linux, tworzy losowe niezależne credentials/key, chroniony ACL runtime i marker; buduje obrazy, uruchamia usługi/migracje, importuje credential/publikuje istniejący workflow n8n, seeduje siedem przypadków zwykłymi authenticated APIs.
- `seed_demo.py`: bez bezpośrednich insertów DB/omijania security; zachowuje raw readings i zapisuje jawne powody review. Wymaga development + marker + właściwej tożsamości i pustej/DEMO-ONLY firmy. Powtórzenie nie duplikuje przypadków/connectorów/użytkowników.
- `-WithEmail`: realny SMTP → prywatny GreenMail → native IMAP → SAFE → INVOICE, bez Gmail ani prywatnej skrzynki.
- `reset_demo.ps1`: wymaga wpisania nazwy projektu lub jawnego `-ConfirmDemoReset`; sprawdza marker/path/reparse points, nazwy/ownership dokładnie pięciu wolumenów i scope kontenerów. Usuwa wyłącznie dedykowany demo/runtime, bez globalnego prune.

**Weryfikacja resetu:** odrzucono seed w production i reset z obcym markerem przed mutacją. Właściwy reset usunął tylko demo. Porównanie pełnego inventory przed/po potwierdziło zachowanie **31 pozostałych kontenerów (ID/nazwa) i 23 pozostałych wolumenów (nazwy)**. Pierwszą próbę pomocniczego porównania inventory poprawiono: filtr negatywny Docker nie zwracał właściwego zbioru; właściwą weryfikację powtórzono na pełnym inventory wyłączając tylko dokładny prefix demo. [Dowód](reset-validation.json).

Po resetach uruchomiono demo od świeżego DB/model/signature cache; cold startup, import n8n, seed i email przeszły. Poprawiono dwa drobne błędy nowych helperów podczas realizacji: przekazywanie `-d` przez PowerShell i podwójne otwieranie już użytego klienta HTTP. Finalne helpery i powtórzony start są działające.

## E2E i końcowy stan

[API E2E](verification.json): login → case/document → blokada wczesnej approval 409 → normalne review → approval → JSON/XLSX → archiwum PDF/JSON/XLSX → signed webhook. Dwa delivery jobs SUCCEEDED; webhook potrzebował **2 prób**, archiwum **1**. Odbiornik potwierdził HMAC, stabilny body/idempotency. Audit zawiera SAFE przed CLASSIFICATION_STARTED, OCR_HUMAN_REVIEW, case_approved i export_generated. Preview, summary, metrics i wszystkie siedem zależności/worker heartbeat probes przeszły.

[Email](email-result.json): rzeczywiste lokalne SMTP/IMAP, SAFE i INVOICE. [Post-UI check](post-ui-check.json): dziewięć unikalnych spraw po repeated seed, brak duplikatów; blocked sample nie ma OCR ani analizy dokumentu i approval daje 409.

**Rzeczywisty UI:** login/dashboard/case/original/typed table/human review/company/sources/destinations/routing/users/System zweryfikowano w przeglądarce. Test connection pokazał queued, następnie uchwycone RUNNING → SUCCEEDED (stan tworzenia zadania to PENDING). W przykładzie invoice-review człowiek poprawił numer na `DEMO/2026/002` i NIP na `9900000000` z uzasadnieniem: REVIEW_REQUIRED → READY → APPROVED → EXPORTED. Z UI wygenerowano JSON/XLSX; delivery jobs i archiwum również potwierdzono po API/filesystem. [UI review](ui-review.txt).

Oba OCR zgodnie odczytały błędny numer jako `VAT/INVOICE`: review zachowało pierwotny wynik i skorygowało go względem oryginału. **Nie poprawiono ekstraktora na podstawie tego demo ani HOLDOUT.** To czytelny przykład granicy samej zgodności silników.

Demo pozostawiono uruchomione. Końcowo jest dziewięć spraw: **3 EXPORTED / 6 REVIEW_REQUIRED**. UI test dokończył pierwotną „Invoice needs review”; dla świeżej prezentacji reset/start odtwarza siedem początkowych przykładów. Dodatkowe dwa przypadki pochodzą z opcjonalnego email i live-flow E2E.

## Screenshoty

[Galeria](../portfolio/screenshots/README.md): **13 prawdziwych aktualnych JPEG M8**, login, dashboard, case workspace, document intelligence/original, human review, company, sources, connection test, destinations, routing, users, System health, exports/audit. Wszystkie obejrzano; nie ma sekretów, prywatnych dokumentów ani makiet.

Full-page capture zgłosiło błąd, więc użyto działającego dokumentowanego viewport capture i przewinięcia sekcji. Bez zmiany treści strony/udawanych ekranów; brakujące obrazy nie były zastępowane fikcją. Historyczne M6/M7 obrazy zachowano bez zmian.

## Quality gates

[Wyniki JSON](quality-gates.json), [SQLite log](tests-sqlite.txt), [PostgreSQL log](tests-postgresql.txt).

| Gate | Wynik bieżącego M8 |
|---|---|
| SQLite, pełna regresja | **281 passed / 2 skipped**, 14.30 s; skipy wyłącznie PostgreSQL concurrency/locking |
| PostgreSQL, pełna regresja | **283 passed / 0 skipped**, 51.62 s; odrębne schematy testowe |
| Ruff app/tests/alembic + scripts/demo | PASS, standardowy cwd backend |
| mypy app | PASS, **88 plików** |
| Format nowych Python helperów | PASS, **3 pliki** |
| Frontend ESLint / TypeScript | PASS / PASS |
| Frontend build / obrazy produkcyjne backend/frontend | PASS przez istniejące Dockerfile.production; końcowy repeat użył prawidłowego cache |
| n8n tests | **9 passed**, 0 failed |
| Alembic check w rzeczywistym PostgreSQL demo | PASS, „No new upgrade operations detected” |
| Compose dev / OCR+security / demo / production | PASS; [sanitized config evidence](compose-validation.json) |
| Demo cold reset/start, repeated seed, local email, API/UI E2E | PASS |
| Runtime usług | **12 running**, skonfigurowane Docker probes healthy, app probes i workers healthy; [evidence](docker-runtime.json) |
| Production config | Caddy tylko **80/443**, auth+secure cookies+fail-closed, plaintext disabled; placeholder validation, nie nowy publiczny deploy |
| Linki, generated-secret scan, scope preservation, diff whitespace | PASS; [final review](repository-review.json) |

M7 HTTPS/backup/real SFTP evidence jest historyczne i niezmienione. W M8 aktualnie sprawdzono production config i zbudowano używane obrazy; nie podszywano tego pod nowe publiczne DNS/ACME/klienckie wdrożenie. Opcjonalnego hosted CI nie dodano; nie ma deklaracji o niewykonanym runie.

## Dokładne komendy

Z root repo (PowerShell; Docker Desktop Linux):

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
.\scripts\demo\start_demo.ps1 -WithEmail
.\scripts\demo\reset_demo.ps1 -ConfirmDemoReset
.\scripts\demo\start_demo.ps1 -WithEmail

docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml exec -T -e APP_ENV=production backend python /demo-tools/seed_demo.py seed
# Powyższa negative-path komenda MUSI odmówić wykonania.
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml exec -T backend python /demo-tools/seed_demo.py verify
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml exec -T backend python /demo-tools/seed_demo.py seed
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml exec -T backend alembic check
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml build backend frontend
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml ps --format json

Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp=../.runtime-demo/tests-sqlite
$env:TEST_DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=../.runtime-demo/tests-postgresql
Remove-Item Env:TEST_DATABASE_URL
.\.venv\Scripts\ruff.exe check app tests alembic ../scripts/demo
.\.venv\Scripts\ruff.exe format --check ../scripts/demo
.\.venv\Scripts\mypy.exe app
Pop-Location

Push-Location frontend
npm run lint
npm run typecheck
node --test ../n8n/tests/workflows.test.cjs ../n8n/tests/review-notifications.test.cjs
Pop-Location

# npm run build jest wykonywane w frontend/Dockerfile.production podczas build/start.
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.ocr.yml -f docker-compose.security.yml config --quiet
docker compose --project-name boah-portfolio-demo --env-file .runtime-demo/demo.env -f docker-compose.demo.yml config --quiet
$env:POSTGRES_PASSWORD='validation-only-not-a-credential'
$env:BOAH_DOMAIN='boah.example.com'
docker compose --env-file deploy/milestone7/production.env.example -f docker-compose.production.yml config --no-env-resolution --format json
Remove-Item Env:POSTGRES_PASSWORD, Env:BOAH_DOMAIN
# Konfigurację parsowano bez publikowania wartości; zapisano tylko sanitized assertions.
.\backend\.venv\Scripts\python.exe scripts/demo/check_release.py --base a80f963 --output docs/milestone8/repository-review.json
git diff --check
git status --short
```

Zapisane końcowe logi regresji pochodzą z tych samych suite'ów; SQLite końcowo używał usuniętego po teście `.runtime-quality-sqlite`, PostgreSQL `backend/tests` z root i `.runtime-demo/tests-postgresql`. Nie zmienia to zakresu testów; reprodukcja powyżej używa wyłącznie ignored runtime.

Render wszystkich PDF wykonano PyMuPDF; gallery pochodzi wyłącznie z Computer Use browser screenshot API. Pomocnicze runtime-only assert scripts parsowały compose config/ps oraz sprawdzały UI case/archiwum; ich sanitized wyniki są dołączone, bez runtime credentials.

## Końcowy security/repository review

[Security review](security-review.md). Release checker kontroluje zmienione/nowe pliki, lokalne Markdown links, dziewięć rzeczywiście wygenerowanych sekretów i nagłówki private key, wyklucza runtime/env/storage/cache/DB/backups oraz porównuje frozen scopes z `a80f963`. Brak trafień sekretów i private/runtime kandydatów. Jest to jawnie ograniczony scan, nie niezależny DLP/pentest. `.runtime-demo` jest ignored; env, credentials, n8n state, model/signature caches, testowe DB/objects/archives/receipts nie wchodzą do zbioru zmian release.

Dodatkowo przeskanowano bajty wszystkich **754 tracked files** pod kątem dziewięciu generated secrets i nagłówków private key; brak trafień. Inventory Git nie zawiera tracked env/key/runtime DB/backup material. [Pełny tracked-material scan](tracked-material-scan.json).

Nie usunięto historycznych raportów ani datasetów reprodukcji. Nie osłabiono M5/M7. Finalny HEAD/branch zachowano, staging jest pusty. Exact status znajduje się poniżej i w [git-status.txt](git-status.txt).

## Znane ograniczenia

- M4 95% STP to **19/20 syntetycznych dokumentów**, zero zaobserwowanych false accepts w tej próbie, bez gwarancji generalizacji.
- M6 **17/20 klas (85%)**, **6/8 struktur (75%)**, **66/216 komórek (30.56%)**, **35/140 numeric (25%)**, review **95%**; handwriting jest proxy, bez realnego HTR.
- Seed celowo potwierdza dane znane z fixture; nie dowodzi niezależnej poprawności OCR/klasyfikatora ani automatic acceptance.
- Single-company/local identities; brak SSO/MFA, multi-tenancy, HA/PITR i realnego wdrożenia u klienta.
- Nie ma ręcznej rekonstrukcji brakującej struktury tabeli; niepewne odczyty wymagają człowieka.
- Demo używa lokalnego HTTP/plaintext fixture IMAP i wymaga Internetu dla cold cache. Nie wolno traktować go jako profilu publicznego production.
- Backup klucza, n8n i zewnętrznych destynacji, retention delivery snapshots oraz obsługa dead-letter są obowiązkami/w przyszłym zakresie operacyjnym.
- Nie dodano hosted CI ani licencji; release/tag/push pozostają decyzją użytkownika po review.
- Screenshots obejmują viewport/sekcje; pełna strona nie była przechwytywana.

## Exact git status --short

```text
 M .gitignore
 M README.md
 M frontend/app/admin-dashboard.tsx
?? demo/
?? deploy/demo/
?? docker-compose.demo.yml
?? docs/CONFIGURATION.md
?? docs/TROUBLESHOOTING.md
?? docs/demo/
?? docs/milestone8/
?? docs/portfolio/
?? scripts/demo/
```
