"""
Music Intelligence Atlas — FastAPI entry point.

All business logic lives in src/app/routes/*.  This file handles:
  - App creation + CORS
  - Startup warmup (pre-load FAISS + adjacency in background)
  - Router registration
"""

import os
import sys
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.app.cache import (
    _load_computed, _load_faiss, _get_artist_adj,
)
from src.app.routes import stats, artists, tracks, discovery, social, playlists, embeddings, soundtrack

app = FastAPI(title="Music Intelligence Atlas API", version="0.2.0")

_DEV_ORIGINS  = ["http://localhost:5173", "http://localhost:3000"]
_PROD_ORIGIN  = os.environ.get("FRONTEND_URL", "").strip()
_ALLOWED_ORIGINS = [_PROD_ORIGIN] + _DEV_ORIGINS if _PROD_ORIGIN else _DEV_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_warmup():
    """Pre-load heavy artifacts in background so first requests are fast."""
    def _warm():
        threads = [
            threading.Thread(target=_load_faiss, daemon=True),
            threading.Thread(target=_get_artist_adj, daemon=True),
            threading.Thread(target=lambda: _load_computed("processed/editorial_playlist_tracks.parquet"), daemon=True),
            threading.Thread(target=lambda: _load_computed("processed/editorial_playlists.parquet"), daemon=True),
            threading.Thread(target=lambda: _load_computed("computed/editorial_removed.parquet"), daemon=True),
            threading.Thread(target=lambda: _load_computed("computed/track_stats.parquet"), daemon=True),
            threading.Thread(target=lambda: _load_computed("computed/era_tracks.parquet"), daemon=True),
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
