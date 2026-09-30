# Milestone 7 — raport końcowy

Data weryfikacji: 2026-09-30. Repozytorium: `C:\AI\BusinessOperationsAutomationHub`. Branch: `milestone-7-production-readiness-company-integrations`. Baza/HEAD: `c129e1ecc36f2bb6593579a9e6e59d47dfaec18b`.

M7 został dokończony na istniejącym rozwiązaniu. Nie przebudowano startera, nie cofnięto funkcjonalnych zmian M7, nie osłabiono M5 i nie zmieniono konfiguracji/pipeline M4/M6. **Nie wykonano stagingu, commita ani push.** Produkcyjny wariant został zweryfikowany lokalnie przez rzeczywiste HTTPS; publiczne wdrożenie i certyfikat ACME wymagają właściwej domeny oraz infrastruktury firmy.

## Co dokończono po wznowieniu

- Indywidualne porównanie pięciu plików M4 z c129e1e: każdy identyczny bajtowo i AST; nie wykonywano kolejnego restore. Wcześniej usunięto wyłącznie formatowanie/BOM/puste wiersze. Zapisano SHA-256 każdego pliku w `docs/milestone7/m4-preservation.json`.
- Potwierdzenie i końcowa walidacja poprawionego Caddyfile, standalone production compose i obu obrazów produkcyjnych.
- Runtime zabezpieczenie IMAP po restore: produkcja odrzuca TLS=false niezależnie od wcześniejszego zapisu konfiguracji lub plaintext-test flag. Dodano test regresyjny.
- Utrzymanie stabilnego CSRF między kartami; poprawione raportowanie realnego stanu usług, storage i niedostępnych connectorów; strukturalne logowanie HTTP/workerów.
- Przegląd Settings, konfiguracji write-only secrets, asynchronicznego Test connection oraz sześciu kroków kreatora; poprawiono specyficzność CSS siatki System i dostępność Sign out w wąskim widoku. Viewer nie widzi Settings/System/New case; ograniczenia egzekwuje także API.
- Powtarzalny smoke HTTPS tworzy osobny projekt na każdy przebieg, bez nadpisywania poprzedniej bazy i wolumenów.
- Końcowa pełna regresja SQLite/PostgreSQL, analiza statyczna, lint/TypeScript/build, testy n8n, migracja i kontrole workerów.
- Instrukcja wdrożenia, backup/restore i eksploatacji, przegląd security, aktualizacja README/.env.example oraz niniejszy raport.

## Zakres działającego M7

Company Settings i first-run guide obejmują tożsamość firmy, timezone/locale/currency, role użytkowników, źródła, destynacje, uporządkowane reguły routingu, odbiorców powiadomień, System i Backup/retention. Opcjonalne metadata mają kolumnę w modelu; nie dodano edytora dowolnego JSON w głównym przepływie UI.

Uwierzytelnienie: lokalne konta Argon2id, losowa sesja w HttpOnly cookie, hash tokena w DB, expiry/logout/revoke, throttling i lockout, audyt, CSRF oraz backend RBAC ADMIN/OPERATOR/REVIEWER/VIEWER. Pierwszy admin z chronionego środowiska lub interaktywnego CLI; inicjalizacja wyłącznie pustego identity store. Service token ma ograniczony zakres ingestion/notification.

Sekrety: write-only AES-GCM z per-record nonce/AAD, fail-closed produkcyjny master key, brak wartości w GET/export/error/log. UI pokazuje jedynie stan configured; puste pole zachowuje sekret. Host master key jest Docker secret i nie trafia do backupu.

Źródła: native IMAP z UIDVALIDITY/UID, BODY.PEEK, deduplikacją M2 i zachowaniem metadanych; watched folder ze stabilizacją pliku, limitami rozmiaru i content dedup. Oba używają istniejącego intake, **M5 SAFE przed M6**. Ręczny upload/API pozostają zachowane.

Wyjścia: filesystem, rzeczywisty SFTP z pinned host key i podpisany webhook. Reguły są uporządkowane, dopasowują dokument/status/review i deduplikują destynacje. Wszystkie załączniki muszą być SAFE, sprawa zatwierdzona/wyeksportowana, bez otwartych blocking issues. Worker zapisuje trwały snapshot artefaktów przed dostawą; retry ma stabilny body/idempotency key, limit i backoff. Dead letter tworzy integration review + istniejący notification outbox; admin może jawnie ponowić.

Monitoring: rzeczywiste DB SELECT, ClamAV ping, oba OCR health, n8n, heartbeats workerów, wolne miejsce mountów i ostatnie wyniki connectorów. Prometheus aggregate bez PII, structured correlation logs. Niedostępny aktywny connector daje DEGRADED, nie fałszywe HEALTHY.

Backup: maintenance, PostgreSQL dump + application storage + schema/SHA-256 manifest. Restore wymaga jawnego --force i pustych docelowych DB/storage; waliduje wpisy/rozmiary/ścieżki, nie nadpisuje istniejącego środowiska. Master key dostarczany osobno. Retention: dry-run/hash/confirmation, wyłączenie aktywnej pracy i konserwatywne zachowanie quarantine, trwały audyt i 410 po usunięciu artefaktu.

Migracja `2836cf000b0e_company_setup_identities_connectors_` dodaje 14 tabel M7 i INTEGRATION_FAILURE do review tasks; istniejące dane i modele M1–M6 zachowane. Alembic upgrade wykonany na rzeczywistym PostgreSQL; check nie wykrywa nowych operacji.

## Końcowe quality gates

| Gate | Wynik |
|---|---|
| Pełna regresja M1–M7, SQLite | **281 passed, 2 skipped**, ostatni przebieg 14.35 s |
| Pełna regresja M1–M7, PostgreSQL | **283 passed**, 60.41 s; izolowane schematy |
| Testy M7 | **55**: 44 security + 11 operations; zawarte w obu pełnych regresjach |
| SQLite skipy | Wyłącznie PostgreSQL concurrency unique-key arbitration i row locking; oba przechodzą na PG |
| Ruff app/tests oraz nowe helpery | PASS |
| mypy app | PASS, **88 plików** |
| Ruff format — zakres zmienionych/nowych Python | PASS, **39 plików**; bez formatowania M4 |
| Frontend ESLint | PASS |
| TypeScript tsc --noEmit | PASS |
| Next production build | PASS |
| Production backend image | PASS |
| Production frontend image po ostatniej poprawce | PASS |
| n8n testy istniejących workflows/review notifications | **9 passed** |
| Alembic check | PASS: No new upgrade operations detected |
| Delivery/review heartbeat CLI | PASS |
| Caddy validate / standalone production compose | PASS; tylko proxy 80/443 |
| HTTPS na finalnych obrazach | PASS; jawnie zaufana lokalna CA, bez verify=False |
| M4 i wszystkie datasets vs c129e1e | Bez zmian; HOLDOUT nie rerunowany |
| git diff --check / sekret/runtime scan | PASS; szczegóły `repository-review.json` |

Pierwszy powtórzony SQLite miał wyłącznie ostrzeżenie sprzątania starego pytest-current (Windows ACL) po wyniku PASS. Powtórka z dedykowanym ignorowanym basetemp zakończyła się bez ostrzeżenia. Cache write sandbox uniemożliwił jeden format-check; powtórzony --no-cache i scoped formatting nowych helperów przeszły. Nie są to nierozwiązane błędy produktu.

## E2E na rzeczywistych usługach

Dowód: `docs/milestone7/e2e.json`, run `f6ea6f24cd`. Użyto wyłącznie syntetycznych danych M7, bez datasetów HOLDOUT.

| Scenariusz | Wynik |
|---|---|
| A: login admin + company settings | PASS |
| B: SMTP → rzeczywisty IMAP → PDF → M5/M6 | SAFE, INVOICE; case 24062caf-0845-4d42-a60c-099d83e29588 |
| C: ponowiony Message-ID | Jedna sprawa; dedup PASS |
| D: watched folder → intake | PASS; case 0f96040d-c17d-4a35-9e9c-a0dd94666f40 |
| E: zatwierdzenie/review → filesystem | Oryginał PDF + JSON + XLSX, PASS |
| F: podpisany webhook z 503 na pierwszej próbie | SUCCEEDED po 2 próbach; podpis poprawny, body identyczny |
| G: SFTP pinned host key | SUCCEEDED po 1 próbie; osobny realny mismatch odrzucony |
| H: stale niedostępny webhook | DEAD_LETTER po 3 próbach + review task/outbox |
| I/J: Viewer/Reviewer | API403 dla ustawień, read API działa |
| K: secrets | Brak wartości w GET/export/audit |
| L: złośliwy email/EICAR | BLOCKED przed OCR/M6, approval409; case 9da6027a-6f8a-4e70-b669-1b9e1501a28c |
| M: backup/restore | PASS w oddzielnym czystym projekcie, 140 obiektów SHA, 4 odszyfrowane sekrety, API case/document |

`backup-restore-e2e.json` zawiera SHA archiwum/manifestu i schema version. Oryginalne środowisko wznowiono. Kontenery restore/smoke zatrzymano po weryfikacji; wolumeny pozostawiono. Powiadomienie przeszło do durable outbox/sink; nie twierdzimy, że wysłano rzeczywisty firmowy email.

## Production validation

`docs/milestone7/production-smoke.json`: rzeczywisty HTTPS localhost:8443, weryfikacja certyfikatu wyłącznie jawnie wskazaną Caddy CA, homepage/readiness200, bez sesji401, login i zapis company/CSRF działają, logout unieważnia sesję. Cookie Secure/HttpOnly/SameSite=Strict. Backend/frontend rzeczywiście UID10001, read-only root; fresh company API działa. Wykonano także powtórkę po finalnym buildzie UI.

`deployment-check.json`: production compose jest samodzielny i publikuje **wyłącznie reverse proxy 80/443**; nie publikuje DB/backend/frontend/OCR/ClamAV/n8n. Dev compose celowo pozostaje lokalnym starterem i ma inne mapowanie portów. Caddyfile poprawiony do prawidłowych bloków i zaakceptowany przez caddy validate. Nie skonfigurowano publicznej domeny ani prawdziwych firmowych connector credentials; publiczny ACME nie jest zweryfikowany.

## Security review

Szczegóły: `docs/milestone7/security-review.md`. Zweryfikowano RBAC/CSRF/expiry/revoke/throttling, write-only AES-GCM/wrong-key/tamper, SSRF DNS/IP pinning/no redirects, metadata/link-local rejection, SFTP wrong-host-key, path/template traversal, SAFE/approval delivery gates, retention/backup boundaries oraz produkcyjny fail-closed configuration. Test restored plaintext IMAP przechodzi niezależnie od flagi plaintext-test.

`security-runtime-check.json`: realny SFTP key mismatch odrzucony; żadna z wygenerowanych wartości sekretów ani treść syntetycznego dokumentu nie występuje w przejrzanych logach backend/delivery/review; structured HTTP JSON obecny. Nie jest to formalny pentest ani certyfikacja.

## UI review i screenshots

Zachowane sześć rzeczywistych screenshotów w `docs/milestone7/screenshots/`: `login.png`, `company.png`, `sources.png`, `destinations.png`, `routing.png`, `users.png`. Wszystkie przedstawiają syntetyczne lokalne dane, bez wartości sekretów.

Przegląd potwierdził login/settings, write-only password fields, Test connection **PENDING → SUCCEEDED**, statuses/jobs/retry, routing, role controls, notification disclaimer i System health. Po wznowieniu przetestowano wszystkie sześć kroków kreatora, zakończenie bez utraty konfiguracji, Viewer z ukrytym Settings/System/New case oraz Sign out w szerokości 656 px. Wylogowanie działa i końcowa sesja browser została zamknięta.

`docs/milestone7/ui-review.txt` zawiera aktualny przegląd DOM. Grid System ma computed display=grid. Siedem usług HEALTHY; aggregate DEGRADED jest oczekiwanym wynikiem aktywnego celowo zepsutego webhooka. Narzędzie browser odmawia obecnie capture nowych screenshotów (Unable to capture screenshot); dlatego nie dodano sfabrykowanego ujęcia finalnego System/wizard. Istniejące sześć ujęć zachowano i zweryfikowano.

## Pięć plików M4

Każdy porównano osobno z `c129e1e`. Dla każdego usunięto wcześniej wyłącznie nie-funkcjonalne formatowanie; aktualny plik jest identyczny bajtowo z bazą, AST także identyczne. Przy tej finalizacji nie wykonano restore ani zmian funkcjonalnych:

1. `backend/app/document_routing/policy/router.py`
2. `backend/app/document_routing/preflight/native_pdf.py`
3. `backend/app/document_routing/processor.py`
4. `backend/app/document_routing/reporting.py`
5. `backend/app/document_routing/scoring/native_fields.py`

Dowód z SHA-256: `docs/milestone7/m4-preservation.json`. Cały document_routing i datasets pozostają bez diff do bazy. M4/M6 HOLDOUT nie uruchamiano ani nie strojono ponownie.

## Znane ograniczenia i operacyjne wymagania

- Single-company/local identities; bez SSO/MFA, HA i PITR. Host/Docker administrators i deployment mounts są zaufani.
- Publiczny DNS/ACME i rzeczywiste firmowe usługi wymagają wdrożenia/provisioningu. Lokalny test HTTPS nie zastępuje publicznej walidacji.
- n8n receipt nie jest dowodem wysłania emaila; końcowy kanał trzeba skonfigurować. n8n state/credentials i zewnętrzne archiwa wymagają osobnego backupu.
- Dostawa ma semantykę at-least-once; webhook odbiorca musi respektować idempotency key. Reguła dostarcza całą zatwierdzoną sprawę, także w sprawie z różnymi typami dokumentów.
- Przy niedającym się przetworzyć mailu źródło może wymagać interwencji administratora; brak fałszywego potwierdzenia przetworzenia. Idle destination status jest ostatnią obserwacją.
- Retention nie wygasza jeszcze trwałych delivery snapshots. Quarantine pozostaje konserwatywnie zachowane. Backup jest maintenance/bounded, a master key wymaga osobnego zabezpieczenia i odzyskania.
- Handwriting pozostaje konserwatywny jak w M6: niepewna wartość pozostaje nierozpoznana/review; M7 nie zmienia OCR ani metryk poprzednich HOLDOUTów.
- Paddle/ClamAV zachowują wymagane upstream privileges/cache volumes; nie deklarujemy pełnego non-root dla wszystkich upstream services.
- Brak aktualnych screenshotów finalnego System/wizard z powodu błędu capture; sześć wcześniejszych screenshotów oraz aktualny DOM są dostępne.

## Stan repozytorium

`docs/milestone7/git-status.txt` zawiera dokładny końcowy `git status --short`; `repository-review.json` potwierdza pusty staging, niezmieniony HEAD, zero runtime credentials w kandydatach zmian i ignorowanie runtime/secrets/backupów. `.env.example` zawiera jedynie dokumentacyjne puste pola i istniejące dev defaults. Żadne `.env`, klucze, prywatne dane, cache, storage ani lokalne n8n dane nie zostały dodane.

**Brak commita i push zgodnie z poleceniem.**
