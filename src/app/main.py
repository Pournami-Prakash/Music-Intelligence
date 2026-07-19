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
import os
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.app.cache import _load_computed
from src.app.routes import stats, artists, tracks, discovery, social, playlists, embeddings, soundtrack

app = FastAPI(title="Music Intelligence Atlas API", version="0.2.0")

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
    response = await call_next(request)
    if _malloc_trim is not None:
        try:
            _malloc_trim(0)
        except Exception:
            pass
    return response


@app.on_event("startup")
def _startup_warmup():
    """Pre-load heavy artifacts in background so first requests are fast."""
    if os.environ.get("SKIP_STARTUP_WARMUP", "").lower() in {"1", "true", "yes"}:
        return

    def _warm():
        # Only the small, still-pandas artifacts are worth pre-loading. The big
        # string-heavy tables (artist_edges, editorial_playlist_tracks,
        # track_stats) are now streamed from local disk via DuckDB on demand, so
        # warming them into pandas would defeat the point.
        threads = [
            threading.Thread(target=lambda: _load_computed("processed/editorial_playlists.parquet"), daemon=True),
            threading.Thread(target=lambda: _load_computed("computed/artist_stats.parquet"), daemon=True),
        ]
        for t in threads:
            t.start()
    threading.Thread(target=_warm, daemon=True).start()


app.include_router(stats.router)
app.include_router(artists.router)
app.include_router(tracks.router)
app.include_router(discovery.router)
app.include_router(social.router)
app.include_router(playlists.router)
app.include_router(embeddings.router)
app.include_router(soundtrack.router)
