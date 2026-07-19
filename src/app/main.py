"""
Music Intelligence Atlas — FastAPI entry point.

All business logic lives in src/app/routes/*.  This file handles:
  - App creation + CORS
  - Startup warmup (pre-load a couple of small artifacts in background)
  - Post-request heap trim (return DuckDB decompression memory to the OS)
  - Router registration
"""

import ctypes
import ctypes.util
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.app.cache import _load_computed, local_parquet
from src.app.telemetry import record_request
from src.app.routes import stats, artists, tracks, discovery, social, playlists, embeddings, soundtrack

app = FastAPI(title="Music Intelligence Atlas API", version="0.2.0")
_REQUEST_SEM = asyncio.Semaphore(int(os.getenv("MAX_INFLIGHT_REQUESTS", "4")))
_REQUEST_WAIT_SECONDS = float(os.getenv("REQUEST_ACQUIRE_TIMEOUT", "2"))

# This is a public, read-only, cookie-less API, so allow any origin by default —
# that avoids CORS breakage when the frontend URL changes (Vercel previews, custom
# domains). Lock it down by setting CORS_ALLOW_ORIGINS to a comma-separated list.
_ORIGINS_ENV = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_ALLOWED_ORIGINS = [o.strip() for o in _ORIGINS_ENV.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,   # required alongside "*"; API uses no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Heap trim ───────────────────────────────────────────────────────────────
# Streaming big parquets through DuckDB churns the heap; glibc frees that memory
# but doesn't always hand it back to the OS, so RSS creeps up under repeated
# scans. After each request we ask glibc to trim, keeping the process small on a
# 512 MB box. No-op on platforms without malloc_trim (e.g. macOS/musl).
try:
    _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    _malloc_trim = _libc.malloc_trim
except (OSError, AttributeError):
    _malloc_trim = None


@app.middleware("http")
async def _trim_heap(request: Request, call_next):
    started = time.perf_counter()
    acquired = False
    response = None
    try:
        if request.url.path in {"/health", "/ready"}:
            response = await call_next(request)
            return response
        try:
            await asyncio.wait_for(_REQUEST_SEM.acquire(), timeout=_REQUEST_WAIT_SECONDS)
            acquired = True
        except TimeoutError:
            response = JSONResponse(
                status_code=503,
                content={"detail": "server_busy", "retry_after_seconds": 5},
                headers={"Retry-After": "5"},
            )
            return response
        response = await call_next(request)
        return response
    finally:
        if acquired:
            _REQUEST_SEM.release()
        route = request.scope.get("route")
        template = getattr(route, "path", request.url.path)
        status = response.status_code if response is not None else 500
        record_request(template, status, (time.perf_counter() - started) * 1000)
        if _malloc_trim is not None:
            try:
                _malloc_trim(0)
            except Exception:
                pass


@app.on_event("startup")
def _startup_warmup():
    """Pre-load heavy artifacts in background so first requests are fast."""
    if os.environ.get("SKIP_STARTUP_WARMUP", "").lower() in {"1", "true", "yes"}:
        stats.set_warm_state("deferred")
        return

    def _warm():
        stats.set_warm_state("warming")
        try:
            # Sequential downloads avoid a cold-start memory/network burst.
            _load_computed("computed/artist_stats.parquet")
            local_parquet("computed/artist_ubiquity_lookup.parquet")
            local_parquet("embeddings/track2vec_vocab_lookup.parquet")
            stats.set_warm_state("ready")
        except Exception as exc:
            print(f"  [warmup] failed: {exc}", flush=True)
            stats.set_warm_state("degraded")
    threading.Thread(target=_warm, daemon=True).start()


app.include_router(stats.router)
app.include_router(artists.router)
app.include_router(tracks.router)
app.include_router(discovery.router)
app.include_router(social.router)
app.include_router(playlists.router)
app.include_router(embeddings.router)
app.include_router(soundtrack.router)
