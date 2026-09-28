FROM python:3.12-slim-bookworm
ARG TESSERACT_VERSION=5.5.3
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl g++ make autoconf automake libtool pkg-config libleptonica-dev libarchive-dev libcurl4-openssl-dev && curl -fsSL https://github.com/tesseract-ocr/tesseract/archive/refs/tags/${TESSERACT_VERSION}.tar.gz | tar xz -C /tmp && cd /tmp/tesseract-${TESSERACT_VERSION} && ./autogen.sh && ./configure --disable-openmp && make -j4 && make install && ldconfig
RUN mkdir -p /usr/local/share/tessdata && curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata -o /usr/local/share/tessdata/eng.traineddata && curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/pol.traineddata -o /usr/local/share/tessdata/pol.traineddata
RUN pip install --no-cache-dir fastapi==0.141.0 uvicorn==0.35.0 pillow==11.3.0 pypdfium2==4.30.0 opencv-python-headless==4.11.0.86 numpy==2.2.6
WORKDIR /app
COPY server.py /app/server.py
ENV OCR_ENGINE=tesseract OMP_THREAD_LIMIT=2
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
