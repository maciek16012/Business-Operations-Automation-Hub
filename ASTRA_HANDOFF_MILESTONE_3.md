# ASTRA HANDOFF — Milestone 3
## Dual OCR / Document Intelligence

Przeczytaj najpierw:

- Milestone-2-raport.md
- configs/ocr-benchmark.json
- datasets/ocr/README.md
- datasets/ocr/ground-truth.schema.json
- istniejący backend i architekturę ExtractionProvider

Nie przebudowuj Milestone 1 ani Milestone 2.

## Cel

Zaimplementuj dwutorowy pipeline OCR:

DOCUMENT
→ OCR ENGINE A
→ OCR ENGINE B
→ independent raw results
→ normalization
→ field comparison
→ deterministic business validation
→ consensus/conflict decision
→ existing human-review pipeline

Oba silniki MUSZĄ wykonywać OCR niezależnie.

Wynik jednego providera nigdy nie może wpływać na inference drugiego.

## Obowiązkowe baseline providers

Engine A:
Tesseract 5.x

Engine B:
PaddleOCR 3.x

Przed przypięciem wersji sprawdź aktualne kompatybilne stabilne wydania
i zapisz dokładnie użyte wersje w raporcie.

Preferuj lokalne inference.
Nie używaj płatnego API.

Zależności obu silników powinny być możliwie odizolowane.
Istnieją katalogi:

ocr-services/tesseract
ocr-services/paddle

Możesz użyć osobnych kontenerów/provider services, jeśli jest to
najczystszy sposób uniknięcia konfliktów zależności.

Nie twórz jednak niepotrzebnej architektury microservices.

## Obowiązkowy kontrakt

Każdy provider musi zwracać wspólny model zawierający przynajmniej:

provider
provider_version
document_id
raw_text
pages
words/lines jeśli dostępne
coordinates jeśli dostępne
provider_confidence jeśli dostępne
processing_time_ms
error
raw_provider_output/reference

Raw result każdego providera zachowaj.

## Dataset

Zaprojektuj i przygotuj reprezentatywny SANITIZED/SYNTHETIC dataset.

Minimum:

- czyste dokumenty cyfrowe
- dobre skany
- gorsze skany
- lekko obrócone strony
- niski kontrast
- artefakty kompresji
- tabele
- polskie znaki
- liczby
- NIP
- daty
- wartości pieniężne

Nie używaj prywatnych danych bez anonimizacji.

Podziel dataset na:

dev
holdout

Nie dostrajaj na holdout.

## Preprocessing

Provider A i B mogą mieć własny preprocessing.

Eksperymentuj na DEV z:

- deskew
- orientation
- grayscale
- contrast
- thresholding
- denoise
- DPI normalization

Nie twórz ogromnej przestrzeni brute-force.

W raporcie zapisz, co faktycznie poprawiło wyniki.

## Benchmark

Dla KAŻDEGO dokumentu uruchom niezależnie:

A(document)
B(document)

Policz:

CER
WER
exact field accuracy
normalized field accuracy
critical field accuracy
provider failure rate
latency mean
latency p95

oraz:

pairwise agreement
pairwise disagreement
both-correct agreement
one-correct conflict
both-wrong agreement / false consensus

False consensus jest szczególnie ważną metryką.

## Field extraction

Pola krytyczne:

document_number
tax_id
issue_date
net_total
vat_total
gross_total
currency

Zachowaj oddzielnie:

OCR A value
OCR B value
normalized A
normalized B
ground truth
comparison result

## Comparator

Zaimplementuj jawny comparator per-field.

Comparator sam nie oznacza poprawności.

## Business resolver

Po comparatorze wykorzystaj deterministyczne reguły:

- checksum polskiego NIP
- net + VAT = gross
- poprawna waluta
- poprawne daty
- wartości >= 0
- istniejące reguły walidacyjne BOAH

Jeśli tylko jedna wersja spełnia silną regułę biznesową,
można oznaczyć konflikt jako deterministycznie rozwiązany,
ale zachowaj obie wartości w audycie.

## Wyniki consensus

Zaimplementuj co najmniej:

CONSENSUS_VALID
CONSENSUS_UNVERIFIED
CONFLICT_RESOLVED
CONFLICT_REVIEW
BOTH_FAILED

Nie utożsamiaj zgodności OCR z prawdą.

## Integracja BOAH

Po benchmarku zintegruj dual OCR z istniejącym systemem.

Realny PDF/skan trafiający przez istniejący upload/email pipeline ma:

1. trafić do obu OCR
2. zachować oba raw results
3. zostać porównany
4. przejść walidację
5. wejść w READY lub REVIEW_REQUIRED

Human review musi pokazywać konflikt, jeżeli istnieje.

Nie usuwaj wcześniejszej ścieżki fixture.
Testy regresyjne M1/M2 muszą pozostać stabilne.

## UI

Operator powinien móc zobaczyć:

OCR A
OCR B
comparison
business validation
final selected/normalized value
powód decyzji

Nie przebudowuj całego frontendu.

## Raport benchmarku

Generuj:

JSON
CSV
Markdown

Raport powinien zawierać:

provider
CER
WER
field accuracy
critical field accuracy
failure rate
latency

oraz osobną sekcję consensus.

Pokaż osobno DEV i HOLDOUT.

## Testy

Dodaj testy m.in.:

provider contract
provider failure
timeout
comparison
money normalization
NIP conflict
false consensus
one-engine failure
both-engine failure
business resolver
integration with existing review
regression M1/M2

## Ważne przypadki

A correct / B correct
A correct / B wrong
A wrong / B correct
A wrong / B wrong differently
A wrong / B wrong identically
A unavailable / B available
B unavailable / A available
both unavailable

Każdy przypadek ma mieć jawne oczekiwane zachowanie.

## Nie implementuj

LLM OCR
OpenAI Vision
Gemini Vision
RAG
CRM
ERP
outbound e-mail
public cloud deployment

## Finalna weryfikacja

Uruchom wszystkie istniejące testy M1/M2.

Uruchom nowe testy OCR.

Uruchom benchmark DEV.

Zamroź konfigurację.

Następnie wykonaj JEDEN finalny benchmark HOLDOUT.

Nie dostrajaj po zobaczeniu HOLDOUT.

Zweryfikuj Docker.
Zweryfikuj UI.
Zweryfikuj realny dokument przez:

upload → dual OCR → comparison → validation → review/READY

## Raport końcowy

Utwórz:

Milestone-3-raport.md

Podaj:

- dokładne wersje OCR
- architekturę
- dataset
- liczbę dokumentów/stron
- wyniki DEV
- wyniki HOLDOUT
- false consensus rate
- metryki per critical field
- latency
- failure rate
- test count
- wyniki regresji M1/M2
- wyniki E2E
- znane ograniczenia
- rekomendację dotyczącą dalszej architektury

Nie wybieraj „zwycięzcy” tylko na podstawie jednej metryki.

Priorytetem projektu jest wiarygodne wykrywanie błędów,
a nie maksymalizowanie jednej liczby accuracy.
