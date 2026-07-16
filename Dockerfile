FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    SKIP_STARTUP_WARMUP=1 \
    # Curb glibc heap fragmentation: this backend repeatedly decompresses big
    # parquets via DuckDB, and glibc's default per-CPU arenas hold on to freed
    # memory. Fewer arenas + aggressive trim keep resident memory low on a small
    # (512 MB) box. Pairs with the malloc_trim() call in main.py.
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=65536

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-api.txt

COPY . .

EXPOSE 7860

CMD ["sh", "-c", "uvicorn src.app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
