# Milestone 3 — raport końcowy

Data finalizacji: 2026-09-28. Repozytorium: C:\AI\BusinessOperationsAutomationHub.

## Wynik

Działający lokalny dual OCR jest zintegrowany z uploadem PDF/skanów oraz inbound e-mail/n8n. Obydwa silniki dostają niezależnie oryginalne bajty dokumentu, nie widzą odpowiedzi drugiego silnika ani ground truth. Oba RAW, strony, tekst, confidence, współrzędne i czasy są zachowane. Comparator i deterministyczny resolver działają dopiero po obu inference. Istniejąca ścieżka TXT fixture M1/M2 pozostaje dostępna.

Wykonano jeden finalny HOLDOUT, pełną regresję, E2E PDF i skanu oraz przegląd w UI. Po HOLDOUT nie zmieniano konfiguracji ani kodu benchmarkowanego pipeline. Polityka pozostaje konserwatywna: wszystkie dokumenty tej próbki wymagają potwierdzenia operatora.

## Wersje i architektura

- Tesseract **5.5.3**, zbudowany ze stabilnego tagu; `tessdata_fast/4.1.0`, `pol+eng`, PSM 6.
- PaddleOCR **3.7.0**, PaddlePaddle **3.3.1**, PaddleX **3.7.2**, CPU, 2 wątki, MKLDNN wyłączone; `PP-OCRv5_mobile_det` i `latin_PP-OCRv5_mobile_rec`; maksymalny bok detektora 960 px.
- PDFium **4.30.0**, rasteryzacja PDF 200 DPI; Pillow **11.3.0**. Dwa osobne kontenery Python 3.12 izolują zależności. Pełne zainstalowane wersje: `ocr-services/*/installed-versions.txt`; hashe plików modeli: `configs/ocr-model-hashes.json`.
- Wersje sprawdzono przed implementacją przez oficjalne PyPI JSON i GitHub releases. Źródła: [Tesseract releases](https://github.com/tesseract-ocr/tesseract/releases), [PaddleOCR PyPI](https://pypi.org/project/paddleocr/3.7.0/), [PaddlePaddle PyPI](https://pypi.org/project/paddlepaddle/3.3.1/), [PaddleOCR installation](https://www.paddleocr.ai/v3.3.0/en/version3.x/installation.html). Faktyczną zgodność potwierdziły uruchomione inference, nie samo deklarowane wersjonowanie.

Nie korzystano z płatnych API, LLM ani chmury inference. Modele zostały pobrane z oficjalnych źródeł i pozostają w lokalnym volume. Usługi widzą dokument i stały profil preprocessingu, nie bazę BOAH ani ground truth.

Kontrakt `OCRResult`: provider/version, document_id, raw_text, pages (linie/słowa, coordinates, confidence), provider_confidence, processing_time_ms, error, raw_provider_output. Współrzędne dotyczą obrazu po preprocessingu, nie przeliczonej pozycji w oryginalnym PDF. Jeden błąd/timeout nie ukrywa odpowiedzi drugiego silnika.

## Dataset i metodologia

**16 dokumentów / 16 stron: DEV 8 + HOLDOUT 8**. Dwie strony to cyfrowe PDF, pozostałe obrazy. Każdy split zawiera: digital, scan, poor scan, skew, low contrast, compression, table, orientation. Polskie znaki, daty, NIP, kwoty i siedem pól krytycznych są obecne. Dane powstały deterministycznie w `scripts/generate_ocr_dataset.py`; nie użyto prywatnych dokumentów ani danych klientów. Nazwy/adresy są syntetyczne, NIP-y to stałe testowe do sprawdzania checksum.

Manifest wiąże oryginały z SHA-256. Ground truth jest osobne i zgodne ze schematem datasetu. HOLDOUT wygenerowano przed DEV, lecz jego inference i wyniki nie były używane podczas strojenia. Przy wznowieniu nie było pliku freeze, znacznika wykonania ani katalogu wyników HOLDOUT; były tylko eksperymenty DEV. To mały smoke benchmark jednej rodziny szablonów z różnymi wartościami i degradacjami, **nie reprezentatywny dowód produkcyjny dla dowolnych faktur**.

CER/WER: Levenshtein, micro-average po zwinięciu whitespace, z zachowaniem wielkości liter i polskich znaków. Exact porównuje surowe wyekstrahowane pole; normalized porównuje wartości po normalizacji. Wszystkie 7 pól jest krytycznych, więc normalized i critical accuracy są tu równe. Braki liczą się jako błąd. Latency obejmuje preprocess/raster/inference oraz inicjalizację przy zimnym modelu; p95 to nearest-rank ceil(0.95*n), przy n=8 jest maksimum. To obserwacje lokalnego CPU, nie test obciążeniowy. Failure rate oznacza błąd techniczny lub brak tekstu, nie błędne znaki.

## DEV i wybór preprocessingu

Osiem jawnych profili, bez iloczynu kombinacji brute-force:

| Profil | Tesseract CER / critical | Paddle CER / critical |
|---|---:|---:|
| baseline | 17.2764% / 80.36% | 9.7561% / 100.00% |
| contrast | 17.2764% / 80.36% | 9.7053% / 100.00% |
| denoise | 18.0894% / 80.36% | 9.7561% / 100.00% |
| deskew | 17.2256% / 80.36% | 9.7053% / 100.00% |
| dpi | 17.1748% / 80.36% | 9.8069% / 100.00% |
| grayscale | 17.2764% / 80.36% | 9.7561% / 100.00% |
| orientation | 3.6585% / 92.86% | 0.4573% / 100.00% |
| threshold | 17.2764% / 80.36% | 10.0102% / 100.00% |

Wybrano **orientation dla obu providerów**: grayscale + autocontrast oraz geometryczny obrót strony poziomej o 90°. To ograniczona heurystyka dla tego rodzaju dokumentów; nie jest ogólnym rozpoznawaniem orientacji 0/90/180/270. Profil podniósł Tesseract z 45/56 do 52/56 poprawnych pól; w Paddle poprawił głównie tekst ogólny. Pozostałe pojedyncze zabiegi nie poprawiły trafności pól. Nie dodawano kombinacji po zobaczeniu HOLDOUT.

Pierwsza próba serwerowego detektora Paddle zużyła około 20 GB RAM i została przerwana na DEV; zastąpiono ją mobilnym detektorem. W fazie DEV naprawiono też parser TSV Tesseracta (literalne cudzysłowy nie mogą połykać kolejnych wierszy). Niekompletne/wadliwe robocze próby `dev-baseline`, `dev-mobile-baseline`, `dev-grayscale` nie są wynikami finalnymi ani częścią commita.

## Zamrożenie i jeden HOLDOUT

Freeze: `2026-09-28T04:26:31.968891+00:00`. SHA-256 pliku `configs/ocr-freeze.json`:

`82ed1e7338285c63459fb6f23e39a22342a4d1859efbda3de2740a44e723b7ff`

Manifest zamraża konfigurację, pipeline, serwery, Dockerfile, spis wersji, hashe modeli, Compose OCR, skrypt benchmarku, dataset i truth. `.gitattributes` zachowuje ich dokładne bajty w Git na Windows. `datasets/ocr/holdout-executed.json` powstał atomowo przed inference; tryb `x` blokuje kolejne uruchomienie. HOLDOUT używa tylko zamrożonych profili; nadpisanie CLI jest zabronione. Marker wskazuje ten sam hash freeze. Wszystkie hashe zweryfikowano po benchmarku i przy finalizacji. Nie kasowano markera i nie powtarzano HOLDOUT.

## Pełne wyniki

| Split | Provider | CER | WER | Exact fields | Normalized fields | Critical fields | Failure rate | Mean ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DEV | tesseract | 3.6585% | 5.9028% | 92.8571% | 92.8571% | 92.8571% | 0.00% | 464.45 | 543.23 |
| DEV | paddle | 0.4573% | 3.4722% | 100.0000% | 100.0000% | 100.0000% | 0.00% | 4288.06 | 7286.15 |
| HOLDOUT | tesseract | 3.5425% | 5.2083% | 92.8571% | 92.8571% | 92.8571% | 0.00% | 504.66 | 876.19 |
| HOLDOUT | paddle | 0.5567% | 4.5139% | 100.0000% | 100.0000% | 100.0000% | 0.00% | 4550.93 | 8991.32 |

| Critical field | DEV Tesseract | DEV Paddle | HOLDOUT Tesseract | HOLDOUT Paddle |
|---|---:|---:|---:|---:|
| document_number | 100.0% | 100.0% | 100.0% | 100.0% |
| tax_id | 100.0% | 100.0% | 100.0% | 100.0% |
| issue_date | 100.0% | 100.0% | 100.0% | 100.0% |
| net_total | 87.5% | 100.0% | 87.5% | 100.0% |
| vat_total | 87.5% | 100.0% | 87.5% | 100.0% |
| gross_total | 87.5% | 100.0% | 87.5% | 100.0% |
| currency | 87.5% | 100.0% | 87.5% | 100.0% |

## Consensus i decyzje dokumentowe

W obu splitach po 56 par pól: **52 agreement/both-correct (92.8571%)**, **4 disagreement/one-correct conflict (7.1429%)**, **0 both-wrong agreement**, **0 both-wrong disagreement**. False consensus: 0/56 wszystkich par i 0/52 zgodnych par. Nie oznacza to, że false consensus nie występuje w realnym świecie; przypadek identycznej błędnej odpowiedzi jest osobno testowany i agreement nie jest traktowane jako prawda.

| Split | AUTO_ACCEPT | REVIEW_REQUIRED | BOTH_FAILED | Błędne critical fields auto-accepted |
|---|---:|---:|---:|---:|
| DEV | 0 | 8 | 0 | 0 |
| HOLDOUT | 0 | 8 | 0 | 0 |

AUTO_ACCEPT oznacza brak obowiązku review na poziomie całego dokumentu, a nie samo przepisanie propozycji pola do sprawy. Obecny resolver nie uznaje numeru dokumentu, daty i waluty za potwierdzone wyłącznie dlatego, że OCR się zgadzają. Stąd zerowa automatyzacja dokumentowa jest oczekiwaną własnością tej wersji; **zero błędnych auto-accept przy zero auto-accept nie pozwala oszacować ryzyka automatycznej akceptacji**. Propozycje pól mogą wypełnić formularz, ale approval pozostaje zablokowane.

NIP checksum oraz spójna trójka netto+VAT=brutto (tolerancja 0.01) mogą rozwiązać konflikt, jeśli dokładnie jedna wersja spełnia silną regułę. Porównanie znormalizowanych pól jest dokładne; sama różnica jednego grosza nie jest ignorowana. Obie wersje pozostają w audycie. Waluty: PLN/EUR/USD/GBP/CHF, nieujemne kwoty, poprawna nieprzyszła data, numer obecny oraz reguły M1. Zgodność z regułami nie dowodzi tożsamości z oryginałem.

## Integracja i E2E

Migracja `f3a901c2d700` dodaje `ocr_documents`, zachowując RAW report oraz osobno reviewed_values/reason. Istniejący CaseService obsługuje dokumenty OCR przy `OCR_ENABLED=true`; TXT nadal używa DevelopmentExtractionProvider. MIME/rozszerzenia: PDF, PNG, JPEG, TIFF; 5 MiB na plik, 10 stron i limit 20 mln pikseli strony. Kod serwisów posiada zabezpieczenia liczby stron/pikseli; nie traktujemy tego jako produkcyjnego sandboxa dokumentów.

Pole `ocr_documents` jest widoczne w szczegółach sprawy. Endpoint `POST /api/v1/ocr/{case_id}/{document_id}/review` wymaga siedmiu wartości, uzasadnienia i przejścia reguł; sprawdza własność dokumentu i edytowalność sprawy. Oryginalny report nie jest nadpisywany. `OCR_REVIEW_REQUIRED` nie znika wskutek zwykłego patcha danych biznesowych.

Finalny E2E `3eae7b4f`:
- PDF upload case `d6d46058-a6ef-4e02-83f2-415d85f11114`: realne oba OCR → CONSENSUS_UNVERIFIED → REVIEW_REQUIRED; approval przed review zablokowane. W UI potwierdzono 7 pól z dokumentem i podano reason → **READY**, zapis OCR_HUMAN_REVIEW. UI pokazuje A/B, normalized, comparison, reason, business checks i raw evidence.
- Skan tabeli przez n8n fixture/inbound case `0005e878-f0b0-424a-ad44-407ca991f747`: realne OCR → CONFLICT_REVIEW → korekta/przegląd → READY → APPROVED → EXPORTED (JSON i XLSX). Replay zwrócił duplicate bez drugiego OCR/sprawy.
- Szczegóły i czasy: `docs/milestone-3-e2e.json`. Screenshot `milestone-3-ui.png` w outputs zadania. To rzeczywisty dokument syntetyczny, nie mock odpowiedzi silników. Nie testowano zewnętrznej skrzynki IMAP bez credentials; n8n i backend wykonały realny transfer dokumentu.

## Końcowe testy i infrastruktura

- **166 passed PostgreSQL**, 16.36 s: 135 regresyjnych M1/M2 + 31 nowych OCR.
- **164 passed, 2 skipped SQLite**, 3.64 s (skipy współbieżności PostgreSQL).
- **6/6 testów workflow n8n**.
- Ruff format: 59 plików; Ruff lint: PASS; mypy: 49 source files, PASS.
- Frontend lint/typecheck/build: PASS, Next 16.3.6; kompilacja 236 ms, TypeScript 1327 ms.
- Alembic check: no new upgrade operations. Wcześniej podczas M3 wykonano pełny cykl upgrade/downgrade do M2/base/fresh upgrade na jednorazowej bazie; PASS. Przy finalizacji sprawdzono zgodność żywej bazy bez destrukcyjnego downgrade danych.
- Compose config PASS. Backend, PostgreSQL, n8n, Tesseract, Paddle healthy; frontend Up. Porty OCR wyłącznie localhost 8011/8012. Interfejs http://localhost:3000, API http://localhost:8000/docs.
- Nowe testy: kontrakt, money normalization, obie strony konfliktu NIP, arytmetyka, identyczny błędny wynik, rozbieżne błędy, timeout/malformed response/provider unavailable, jedna i dwie awarie, upload, email, dedupe, blokada review, immutable approved case, metryka odległości.

## Ograniczenia i rekomendacja

1. Mały syntetyczny dataset, jedna rodzina etykiet/szablonów; HOLDOUT jest wariantem wartości i degradacji, nie niezależną kolekcją realnych układów. 100% pól Paddle w 8 dokumentach nie uzasadnia wyboru jednego silnika ani automatycznego approval.
2. Ekstraktor pól jest deterministyczny i oparty o jawne etykiety, nie uniwersalne document intelligence. Tesseract nie odczytał czterech krytycznych pól tabeli; słabość pozostawiono bez dostrajania po HOLDOUT.
3. Polityka celowo wymaga review wszystkich dokumentów z niezweryfikowanym numerem/datą/walutą. Brak zysku w automatycznej akceptacji; zysk to porównanie i wykrywanie niepewności.
4. Confidence providerów nie jest wspólną skalibrowaną miarą. Zgodny błędny NIP/kwoty mogą spełniać reguły; checksum/arytmetyka nie są oracle.
5. Synchroniczne lokalne CPU inference. Timeout HTTP backendu 90 s, benchmarku 180 s; praca silnika może trwać po zerwaniu połączenia. Brak produkcyjnej kolejki/cancel, izolacji dla wrogich dokumentów i testu dużej współbieżności. Nie dodawano tych elementów pozornie dla architektury.
6. RAW w JSON bazy może rosnąć; przyszły etap powinien rozważyć object-storage references, retry/reprocessing z wersjonowaniem i limity retencji. Ten etap zachowuje M1/M2.

Rekomendacja: zachować dwa niezależne silniki i konserwatywny review. Następny etap powinien przygotować nowy zamknięty dataset wielu układów, więcej tabel/wielostronicowych skanów, explicit false-consensus challenge set, pomiar kosztu review i kalibrację bezpiecznego auto-accept. Nowe ulepszenia benchmarkować w nowej wersji z nowym holdout, nie na tym wykorzystanym.

## Odtworzenie

```powershell
Set-Location C:\AI\BusinessOperationsAutomationHub
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.ocr.yml ps
docker compose exec -T backend alembic check
node --test n8n/tests/workflows.test.cjs
Set-Location backend
uv sync --extra dev
uv run ruff format --check app tests alembic
uv run ruff check app tests alembic
uv run mypy app
uv run pytest -q
$env:TEST_DATABASE_URL='postgresql+asyncpg://boah:boah_dev_password@localhost:5432/boah'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
uv run python ../scripts/demo_dual_ocr.py
Set-Location ../frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

n8n fixture musi być opublikowane zgodnie z `n8n/README.md`. Dane DB powyżej to jawne lokalne wartości przykładowe. DEV można powtórzyć pod nową nazwą: `backend/.venv/Scripts/python.exe scripts/benchmark_ocr.py --split dev --name dev-new-run`.

Historyczne polecenia finalnego HOLDOUT (już wykonane, **nie uruchamiaj ponownie i nie usuwaj markera**): `scripts/benchmark_ocr.py --freeze`, następnie `--split holdout --name holdout-final`. Do weryfikacji używaj zapisanych RAW i raportów. Raporty: `datasets/ocr/results/dev-selected/report.{json,csv,md}` i `holdout-final/report.{json,csv,md}`. RAW per dokument/provider znajdują się obok raportów.

## Git

Lokalny commit Milestone 3 obejmuje źródła, testy, dokumentację, freeze oraz wyłącznie syntetyczny dataset i jego wyniki ewaluacyjne. Wykluczono .env, klucze, lokalne modele/volume, cache, runtime storage, eksporty aplikacji i niekompletne eksperymenty. Raport E2E jest oczyszczonym dowodem z syntetycznymi identyfikatorami. Nie wykonano push. Hash commita i końcowy status są podane w odpowiedzi końcowej.

## Kontrola zgodności wdrożonego kodu

Po HOLDOUT porównano także pliki serwerów uruchomionych kontenerów z zamrożonym repozytorium. Różnią się wyłącznie CRLF/LF: obrazy zbudowane przed zamrożeniem zawierają odpowiednio 236 i 237 CRLF; normalizacja zakończeń linii daje dokładnie hashe zamrożonych źródeł. Nie zmieniono instrukcji ani parametrów inference.

- Tesseract deployed SHA-256: d3a45b303a062196c6fc1c3878e07bbbcc872852721260a62c736c4f19d8d0aa; LF-normalized/frozen: b3c56a6a91bf36fc9ab28e3101344a426d5e01cf28d58a009790e2e2036af1bd.
- Paddle deployed SHA-256: a217307f5283578283ee2d0adc34e60df7f52d1cbfb9219b70d4812db81f06ce; LF-normalized/frozen: 3c47cd7b731b4a1fa30230fc7d16c78670f846c7abaf15d6c346534363bc3f2a.

Kontrola indeksu: wszystkie pliki manifestu freeze mają dokładnie zadeklarowane hashe zarówno w katalogu roboczym, jak i w indeksie Git. 268 plików zmiany, około 4.63 MB; brak niedozwolonych ścieżek runtime oraz trafień sprawdzanych wzorców kluczy/tokenów. Syntetyczne wyniki benchmarków są celowymi dowodami ewaluacji, nie danymi aplikacyjnego runtime.
