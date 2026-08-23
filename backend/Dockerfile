FROM python:3.14-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.14-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY --from=base /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=base /usr/local/bin /usr/local/bin
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY data ./data
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
