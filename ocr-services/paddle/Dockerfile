FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir paddlepaddle==3.3.1 paddleocr==3.7.0 paddlex==3.7.2 fastapi==0.141.0 uvicorn==0.35.0 pillow==11.3.0 pypdfium2==4.30.0
WORKDIR /app
COPY server.py /app/server.py
ENV OCR_ENGINE=paddle PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True OMP_NUM_THREADS=2
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
