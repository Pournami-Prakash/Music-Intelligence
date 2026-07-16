"""
Shared state and data-loading for the Music Intelligence Atlas API.

All R2 downloads go through _load_computed(), which caches in memory with a
TTL and also checks a local disk copy before hitting the network. This makes
cold starts after a server restart fast (disk hit), while eventual R2 refreshes
keep data current.

Exported for use by route modules:
  r2, sp, con            — singleton clients
  _load_computed         — main parquet loader
  _load_manifest         — data_manifest.json loader
  _load_faiss            — FAISS HNSW index + vocab loader
  _get_artist_adj        — artist co-occurrence adjacency dict
  _chart_for_track       — chart_history lookup by URI
  _chart_for_name        — chart_history lookup by name
  _artist_name_map       — lower-name → canonical-name from edges
"""

import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.r2 import R2Client
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.spotify import SpotifyClient

r2  = R2Client()
sp  = SpotifyClient()
con = get_con()


# DuckDB's memory_limit is a single budget for the whole instance, shared by
# every cursor. Under FastAPI's threadpool, many concurrent heavy scans contend
# for it and throw OutOfMemoryException instead of queueing. This semaphore caps
# how many DuckDB queries run at once so total memory stays bounded on a small
# box; excess requests wait their turn. Tune via DUCKDB_MAX_CONCURRENCY.
_DUCK_SEM = threading.BoundedSemaphore(int(os.getenv("DUCKDB_MAX_CONCURRENCY", "2")))


@contextmanager
def duck_slot():
    """Acquire a concurrency slot and yield a fresh, cursor-isolated DuckDB
    handle. Use for register-blocks; hold the slot until results are
    materialised. Do NOT nest (each graph/query helper takes its own slot)."""
    _DUCK_SEM.acquire()
    try:
        yield con.cursor()
    finally:
        _DUCK_SEM.release()


def duck_df(sql: str, params=None):
    """Run a query under a concurrency slot, return a DataFrame."""
    with duck_slot() as cur:
        return (cur.execute(sql, params) if params is not None else cur.execute(sql)).df()


def duck_one(sql: str, params=None):
    """Run a query under a concurrency slot, return one row (or None)."""
    with duck_slot() as cur:
        return (cur.execute(sql, params) if params is not None else cur.execute(sql)).fetchone()


def duck_all(sql: str, params=None):
    """Run a query under a concurrency slot, return all rows."""
    with duck_slot() as cur:
        return (cur.execute(sql, params) if params is not None else cur.execute(sql)).fetchall()

# ── In-memory cache ────────────────────────────────────────────────────────────
_cache:          dict[str, pd.DataFrame] = {}
_cache_ts:       dict[str, float]        = {}
_image_cache:    dict[str, Optional[str]] = {}
_chart_index:    Optional[dict]          = None
_faiss_index                             = None
_faiss_vocab:    Optional[pd.DataFrame]  = None
_artist_adj:     Optional[dict]          = None
_artist_name_map: dict[str, str]         = {}
_manifest:       Optional[dict]          = None
_manifest_ts:    float                   = 0.0

# Parquets that almost never change get 24 h TTL; everything else 1 h.
_STABLE_KEYS = {
    "processed/playlist_tracks.parquet",
    "processed/tracks.parquet",
    "processed/playlists.parquet",
    "processed/editorial_playlist_tracks.parquet",
    "processed/editorial_tracks_slim.parquet",
    "processed/editorial_playlists.parquet",
    "processed/canonical_tracks.parquet",
    "embeddings/genre_umap.parquet",
    "embeddings/genre_umap_clusters.parquet",
    "computed/editorial_removed.parquet",
    "computed/track_stats.parquet",
    "computed/track_stats_lookup.parquet",
    "embeddings/track2vec_vocab_lookup.parquet",
    "enrichment/listenbrainz_lookup.parquet",
    "computed/era_tracks.parquet",
}
_TTL_STABLE  = 86_400  # 24 h
_TTL_DEFAULT = 3_600   # 1 h

# Expected minimum columns per artifact — logged (not raised) on mismatch.
_SCHEMA_CONTRACTS: dict[str, set[str]] = {
    "processed/canonical_tracks.parquet":         {"spotify_track_uri", "track_name", "artist_name"},
    "computed/artist_stats.parquet":              {"artist_name", "playlist_count", "rank"},
    "enrichment/artist_genres.parquet":           {"artist_name"},
    "enrichment/artist_lastfm.parquet":           {"artist_name"},
    "computed/artist_edges.parquet":              {"artist_a_name", "artist_b_name", "shared_playlists"},
    "processed/editorial_playlist_tracks.parquet": {"track_uri", "track_name", "artist_name"},
    "embeddings/track2vec_vocab.parquet":         {"track_uri", "artist_name", "track_name"},
}


def _load_computed(key: str) -> Optional[pd.DataFrame]:
    """Download a parquet from R2 and cache in memory; refresh after TTL.

    Falls back to a stale local disk copy if R2 is unreachable on cold start.
    Uses a staging (.new) path to avoid corrupting the cached file on failure.
    """
    now = time.monotonic()
    ttl = _TTL_STABLE if key in _STABLE_KEYS else _TTL_DEFAULT
    if key in _cache and (now - _cache_ts.get(key, 0)) < ttl:
        return _cache[key]

    tmp     = Path(tempfile.gettempdir()) / key.replace("/", "_")
    tmp_new = tmp.with_name(tmp.name + ".new")

    # Disk hit: use local copy if it's still within TTL
    if tmp.exists() and (time.time() - tmp.stat().st_mtime) < ttl:
        try:
            df = pd.read_parquet(tmp)
            _cache[key] = df
            _cache_ts[key] = now
            return df
        except Exception:
            pass  # corrupt local file — fall through to R2 download

    try:
        tmp_new.unlink(missing_ok=True)
        r2.download(key, tmp_new)
        df = pd.read_parquet(tmp_new)

        required = _SCHEMA_CONTRACTS.get(key)
        if required:
            missing = required - set(df.columns)
            if missing:
                print(f"  [schema] {key}: missing expected columns {missing}", flush=True)

        if key == "processed/editorial_playlist_tracks.parquet":
            # Strip placeholder rows with no track or artist metadata
            bad_name  = df["artist_name"].fillna("").str.strip()
            bad_title = df["track_name"].fillna("").str.strip()
            mask = ((bad_name == "") | (bad_name.str.lower() == "artist")) & (bad_title == "")
            df = df[~mask]

        tmp_new.replace(tmp)
        _cache[key] = df
        _cache_ts[key] = now

        if key == "computed/artist_edges.parquet":
            # Bust the adjacency dict so _get_artist_adj() rebuilds on next call
            global _artist_adj, _artist_name_map
            _artist_adj = None
            _artist_name_map.clear()

        return df

    except Exception as e:
        tmp_new.unlink(missing_ok=True)
        print(f"  [_load_computed] {key} failed: {e}", flush=True)
        if tmp.exists() and key not in _cache:
            try:
                _cache[key] = pd.read_parquet(tmp)
            except Exception:
                pass
        return _cache.get(key)


def local_parquet(key: str) -> Optional[Path]:
    """Ensure an R2 parquet is on local disk (download once, honour TTL) and
    return its path — WITHOUT loading it into pandas.

    This is the low-memory counterpart to _load_computed(): big string-heavy
    tables (artist_edges, editorial_playlist_tracks, track_stats) balloon to
    multiple GB in a resident DataFrame, so instead callers point DuckDB at the
    returned path (read_parquet) and let it stream + filter on disk. Only the
    small filtered result is ever materialised.
    """
    ttl = _TTL_STABLE if key in _STABLE_KEYS else _TTL_DEFAULT
    tmp = Path(tempfile.gettempdir()) / key.replace("/", "_")
    if tmp.exists() and (time.time() - tmp.stat().st_mtime) < ttl:
        return tmp

    tmp_new = tmp.with_name(tmp.name + ".new")
    try:
        tmp_new.unlink(missing_ok=True)
        r2.download(key, tmp_new)
        tmp_new.replace(tmp)
        return tmp
    except Exception as e:
        print(f"  [local_parquet] {key} failed: {e}", flush=True)
        return tmp if tmp.exists() else None  # stale copy beats nothing


def _load_manifest() -> Optional[dict]:
    """Load computed/data_manifest.json from R2, cached for 1 h."""
    global _manifest, _manifest_ts
    now = time.monotonic()
    if _manifest is not None and (now - _manifest_ts) < 3_600:
        return _manifest

    tmp     = Path(tempfile.gettempdir()) / "data_manifest.json"
    tmp_new = tmp.with_name("data_manifest.json.new")
    try:
        tmp_new.unlink(missing_ok=True)
        r2.download("computed/data_manifest.json", tmp_new)
        data = json.loads(tmp_new.read_text())
        tmp_new.replace(tmp)
        _manifest    = data
        _manifest_ts = now
        return _manifest
    except Exception as e:
        tmp_new.unlink(missing_ok=True)
        print(f"  [_load_manifest] failed: {e}", flush=True)
        if tmp.exists() and _manifest is None:
            try:
                _manifest = json.loads(tmp.read_text())
            except Exception:
                pass
        return _manifest


def _load_faiss():
    """Lazy-load the FAISS HNSW index and vocab from R2 (downloads once, caches on disk)."""
    global _faiss_index, _faiss_vocab
    if _faiss_index is not None:
        return _faiss_index, _faiss_vocab
    try:
        import faiss
        tmp = Path(tempfile.gettempdir()) / "track2vec_cache"
        tmp.mkdir(exist_ok=True)

        idx_path   = tmp / "embeddings_track2vec_hnsw.faiss"
        vocab_path = tmp / "embeddings_track2vec_vocab.parquet"

        if not idx_path.exists():
            r2.download("embeddings/track2vec_hnsw.faiss", idx_path)
        if not vocab_path.exists():
            r2.download("embeddings/track2vec_vocab.parquet", vocab_path)

        _faiss_index = faiss.read_index(str(idx_path))
        _faiss_index.hnsw.efSearch = 64
        _faiss_vocab = pd.read_parquet(vocab_path)
        return _faiss_index, _faiss_vocab
    except Exception:
        return None, None


def _get_artist_adj() -> dict[str, dict[str, int]]:
    """Build and cache the artist co-occurrence adjacency dict from artist_edges."""
    global _artist_adj, _artist_name_map
    if _artist_adj is not None:
        return _artist_adj
    df = _load_computed("computed/artist_edges.parquet")
    if df is None:
        return {}
    adj: dict[str, dict[str, int]] = {}
    name_map: dict[str, str] = {}
    for a, b, w in zip(df["artist_a_name"], df["artist_b_name"], df["shared_playlists"]):
        adj.setdefault(a, {})[b] = int(w)
        adj.setdefault(b, {})[a] = int(w)
        name_map[a.lower()] = a
        name_map[b.lower()] = b
    _artist_adj = adj
    _artist_name_map.update(name_map)
    return adj


def _chart_for_track(track_uri: str) -> Optional[dict]:
    """Return chart_history row for a Spotify track URI, or None."""
    global _chart_index
    if _chart_index is None:
        ch = _load_computed("enrichment/chart_history.parquet")
        _chart_index = ch.set_index("uri").to_dict("index") if ch is not None else {}
    return _chart_index.get(track_uri)


def _chart_for_name(track_name: str, artist_name: str) -> Optional[dict]:
    """Fuzzy chart lookup by track name + artist name when URI isn't available."""
    global _chart_index
    if _chart_index is None:
        _chart_for_track("")  # trigger load
    if not _chart_index:
        return None
    tk = track_name.lower().strip()
    ak = artist_name.lower().strip()
    for row in _chart_index.values():
        if row.get("track_name", "").lower() == tk and row.get("artist_name", "").lower() == ak:
            return row
    return None
