# Milestone 1 — raport weryfikacji

Repozytorium: C:\AI\BusinessOperationsAutomationHub
Data zakończenia: 2026-09-27
Wynik: zaimplementowany i zweryfikowany pełny vertical slice Milestone 1.

## Zakres

Zachowano starter FastAPI / async SQLAlchemy / Alembic / PostgreSQL oraz Next.js / TypeScript. Działa proces: tworzenie sprawy, upload wielu dokumentów, zapis oryginałów, SHA-256, deduplikacja, ekstrakcja fixture'ów, niezależna normalizacja, walidacja, korekta operatora, zatwierdzenie/odrzucenie, eksport JSON/XLSX i historia audytu. Panel pokazuje załączniki, surowe i znormalizowane pola, problemy walidacyjne i zapisane eksporty. Błędy blokujące uniemożliwiają zatwierdzenie również przez bezpośrednie API. Niezapisane korekty blokują zatwierdzanie w UI.

## Decyzje architektoniczne

- ObjectStorage z LocalFilesystemStorage i trwałym wolumenem /data/documents; bez MinIO.
- ExtractionProvider przyjmuje bytes, bez zależności od fizycznej ścieżki; provider nie rozstrzyga poprawności biznesowej.
- Decimal/NUMERIC(14,2), checksum NIP i deterministyczne reguły walidacyjne.
- Deduplikacja SHA-256 w obrębie sprawy, unikalność (case_id, sha256), pomijanie kopii i zapis decyzji w audycie. Ten sam dokument w innej sprawie jest dozwolony.
- Kontrolowana maszyna stanów i blokady wierszy PostgreSQL chronią operacje współbieżne.
- Korekty zachowują pierwotne ExtractedField; audyt obejmuje także pochodne zmiany, np. walutę wywnioskowaną z ręcznie wprowadzonej kwoty.
- Odrzucenie to terminalny FAILED z ReviewDecision reject i powodem. DUPLICATE pozostaje zarezerwowany w modelu; pominięta kopia nie unieważnia poprawnej sprawy.
- Serwerowe publiczne ID: CASE-rok-20 znaków UUID, unikalne w DB. Brak numerowania w przeglądarce.
- Zatwierdzone/wyeksportowane sprawy są nieedytowalne; ponowne generowanie i pobieranie eksportów jest dozwolone.

## Główne moduły dodane lub zmienione

- backend/app/services/cases.py, exports.py, errors.py, serialization.py — workflow, audyt, przegląd i eksporty.
- backend/app/api/dependencies.py oraz api/routes/{cases,uploads,review,exports}.py — rzeczywiste endpointy.
- backend/app/storage/{base,__init__}.py — interfejs i bezpieczny magazyn plików.
- backend/app/extraction/{base,development}.py — kontrakt i deterministyczny provider.
- backend/app/validation/{engine,normalization,nip}.py — walidacja i normalizacja.
- backend/app/exports/render.py — JSON i XLSX (Summary, Attachments, Validation, Audit).
- backend/app/models/entities.py, schemas/cases.py, domain/state_machine.py, core/config.py — model, kontrakty i konfiguracja.
- backend/alembic/versions/72087185dc49_milestone_1_schema.py — odtwarzalna migracja.
- backend/tests/{conftest,test_domain,test_workflow,test_health}.py — testy jednostkowe/API, PostgreSQL i scenariusze awarii.
- frontend/app/page.tsx, globals.css, frontend/lib/api.ts — działający panel operatora.
- Dockerfile obu usług, docker-compose.yml, .dockerignore, .env.example, lockfile'y, .gitignore.
- README.md, docs/architecture.md, docs/domain-model.md, sample_data i scripts/demo.py.

Zastany .gitignore ignorował każdy katalog storage, w tym kod źródłowy backend/app/storage. Zawężono tę regułę do katalogów danych. Na początku całe repozytorium było nieśledzone w Git; nie wykonywano commitów ani zmian historii. Końcowy przegląd obejmował źródła, konfigurację, status Git i kontrolę pozostałości startera.

## Dokładne wyniki kontroli

| Kontrola | Wynik |
|---|---|
| uv run pytest -q — SQLite z włączonymi FK | 113 passed, 1 skipped, 1.76 s |
| uv run pytest -q — TEST_DATABASE_URL PostgreSQL | 114 passed, 7.02 s |
| uv run ruff format --check app tests alembic | 46 files already formatted |
| uv run ruff check app tests alembic | All checks passed |
| uv run mypy app | Success: no issues found in 40 source files |
| npm run lint | PASS |
| npm run typecheck | PASS |
| npm run build | PASS, zoptymalizowany build Next.js |
| docker compose config --quiet | PASS |
| docker compose up -d --build | PASS |
| Alembic upgrade → downgrade → upgrade | PASS, osobna jednorazowa baza PostgreSQL |
| alembic check na bazie testowej i działającej usłudze | No new upgrade operations detected |
| scripts/demo.py na działającym HTTP API | PASS |
| Oryginał i eksporty po restarcie i odtworzeniu kontenera | PASS, identyczne SHA-256 |

Jedyny skip w SQLite dotyczy testu współbieżnych uploadów i zatwierdzeń wymagającego blokad PostgreSQL. Ten test przechodzi w wariancie PostgreSQL. Nie pozostawiono czerwonych testów ani znanych błędów lint/typecheck.

Testy obejmują pełną macierz przejść stanów, poprawne/błędne NIP, kwoty i daty, traversal, rozmiar/typ plików, niepoprawny UTF-8, znaki kontrolne, konflikty dokumentów/walut, duplikaty pod inną nazwą, korekty i zachowanie ekstrakcji, blokowanie zatwierdzeń/eksportów, odrzucanie, formuły XLSX jako tekst, zapis/odczyt eksportów, audyt i awarie magazynu.

## E2E i dowody

Przeglądarka: utworzono CASE-2026-6f18257ff9ed4dcab4d4, wgrano review_required.txt, potwierdzono REVIEW_REQUIRED i nieaktywne zatwierdzanie, poprawiono NIP oraz kwotę, zapisano READY, zatwierdzono i wygenerowano oba eksporty. UI pokazał EXPORTED, rozwiązane problemy, zachowane pierwotne wartości i linki do JSON/XLSX.

Powtarzalny demonstrator HTTP: CASE-2026-48939f9b90d94894b6c3, wynik EXPORTED, 23 zdarzenia audytu, jedna kopia oryginału, dwa eksporty. Sprawdzono odpowiedzi 409 dla próby zatwierdzenia błędnych danych, eksportu przed zatwierdzeniem i korekty po zatwierdzeniu. JSON zawiera 12500.00 PLN, XLSX ma cztery wymagane arkusze i poprawne komórki. Manifest z identyfikatorami i sumami SHA-256: demo-result.json w katalogu wyników.

Stan końcowy kontenerów: postgres healthy, backend healthy, frontend Up. Aplikacja dostępna na http://localhost:3000; dokumentacja API na http://localhost:8000/docs. Usługi pozostawiono uruchomione. Trwałość danych potwierdzono również po odtworzeniu kontenerów, nie tylko restarcie procesu.

## Uruchamianie

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

Powtórzenie scenariusza API:

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub\backend
uv sync --python 3.12 --extra dev
uv run python ../scripts/demo.py
```

Pełne komendy jakościowe i opis konfiguracji znajdują się w README repozytorium.

## Ograniczenia i odroczony zakres

Provider obsługuje UTF-8 .txt z rozpoznawanymi etykietami, nie OCR/PDF. Przetwarzanie jest synchroniczne; brak autoryzacji i rzeczywistej tożsamości operatora, a odrzucenie jest terminalne. To lokalna aplikacja demonstracyjna, nie publiczne wdrożenie produkcyjne. Baza i filesystem nie tworzą jednej transakcji: awaria DB po zapisie pliku może zostawić niepowiązany obiekt; automatyczne sprzątanie/outbox są odroczone. Dane należy zabezpieczać razem z wolumenem plików.

Zgodnie z handoffem nie dodano integracji email, n8n, produkcyjnego OCR, LLM/OpenAI, PDF, webhooków, RBAC ani infrastruktury chmurowej. Milestone 2 ma objąć email i n8n, a dalsze etapy OCR/LLM i rozszerzone eksporty.
