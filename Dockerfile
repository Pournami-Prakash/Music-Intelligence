FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    SKIP_STARTUP_WARMUP=1 \
    # Tuned for a 512 MB box: serialize DuckDB (one heavy query at a time — the
    # 503 cap sheds the overflow) and cap its buffer so a single big R2 scan
    # (e.g. the search top-up over tracks.parquet) can't spike past the limit.
    # Raise both on a roomier host for more throughput.
    DUCKDB_MAX_CONCURRENCY=1 \
    DUCKDB_MEMORY_LIMIT=64MB \
    # This backend repeatedly decompresses big parquets via DuckDB across the
    # threadpool. glibc's allocator holds freed memory in per-thread arenas that
    # malloc_trim() can't reclaim, so RSS climbs under varied load until OOM on a
    # 512 MB box. jemalloc returns freed memory to the OS aggressively (decay
    # settings below) and fragments far less. LD_PRELOAD is set in CMD so it
    # resolves the arch-specific path (amd64 vs arm64).
    MALLOC_CONF=background_thread:true,dirty_decay_ms:0,muzzy_decay_ms:0,narenas:2

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-api.txt

COPY . .

EXPOSE 7860

# Preload jemalloc (path differs by arch) then start uvicorn. exec so signals reach it.
CMD ["sh", "-c", "export LD_PRELOAD=$(ls /usr/lib/*/libjemalloc.so.2 2>/dev/null | head -1); echo \"LD_PRELOAD=$LD_PRELOAD\"; exec uvicorn src.app.main:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
