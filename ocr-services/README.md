# Local dual OCR

Run `docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build` from the repo root. The optional overlay enables OCR in BOAH and sets both selected profiles to orientation. Without the overlay M1/M2 TXT behavior remains unchanged.

Tesseract 5.5.3 and PaddleOCR 3.7.0 / PaddlePaddle 3.3.1 execute separately on CPU. See their Dockerfiles and installed-versions.txt. No paid APIs. Paddle downloads official detection/Latin recognition models on first inference into paddle_models; first call can take longer. Do not mount BOAH storage or ground truth into either worker.

Local endpoints: localhost:8011/health and :8012/health; POST /ocr receives document_id, content_base64, preprocessing and returns independent OCRResult. BOAH uses Docker service names. Limits: 5 MiB payload, 10 pages, 20 million rendered pixels per page. PDF 200 DPI; TIFF frames preserved. Output coordinates are in the processed image frame. HTTP timeout does not cancel ongoing CPU inference.

Exact benchmark configuration and byte hashes are in configs/ocr-freeze.json. HOLDOUT is already consumed; do not change frozen files or delete its execution marker. Changes belong to a new evaluation version and a new holdout. Milestone-3-raport.md contains results, limitations, recovery and reproduction.
