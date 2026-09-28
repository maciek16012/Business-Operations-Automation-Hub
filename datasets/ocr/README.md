# OCR Evaluation Dataset

Dataset Milestone 3 służy do porównania dwóch niezależnych pipeline OCR.

## Splits

### dev

Dokumenty używane podczas implementacji i strojenia preprocessingów.

Wyniki mogą być analizowane podczas developmentu.

### holdout

Zamknięty zestaw końcowy.

Nie wolno dostrajać algorytmów na podstawie wyników holdout.

Holdout służy wyłącznie do końcowego benchmarku.

## Ground truth

Każdy dokument wejściowy powinien mieć odpowiadający plik JSON.

Przykład:

input/dev/invoice-001.png

ground_truth/dev/invoice-001.json

## Zasada niezależności

Ten sam oryginalny dokument trafia niezależnie do:

Engine A
Engine B

Oba wyniki RAW muszą zostać zachowane.

Wynik jednego providera nie może być wejściem ani podpowiedzią dla drugiego.

Comparator działa dopiero po zakończeniu obu ekstrakcji.

## Ważne

Agreement != correctness.

Przypadek, w którym oba OCR zwracają tę samą błędną wartość,
musi być osobno mierzony jako both_wrong_agreement.


## Delivered evaluation (Milestone 3)

16 synthetic documents / 16 pages, 8 DEV + 8 HOLDOUT. Each split has a digital PDF, clean/poor scans, skew, contrast, JPEG compression, table and rotated page. Inputs and ground truth were generated before DEV by scripts/generate_ocr_dataset.py. No customer/private source documents are included. This is a small one-template-family smoke dataset, not evidence of production generalization.

Final reports and independent RAW: results/dev-selected and results/holdout-final. DEV experiments: results/dev-final-*. Ignore abandoned local dev-baseline/dev-mobile-baseline/dev-grayscale runs; they are excluded from Git. Application E2E exports under results/e2e are runtime and excluded.

configs/ocr-freeze.json locks code, model inventory and dataset bytes. holdout-executed.json proves the final run was started once and blocks reuse. Do not regenerate the frozen inputs, delete the marker or tune on the final results. Future optimization needs a new dataset version and holdout. See Milestone-3-raport.md for denominators, decision counts and limitations.
