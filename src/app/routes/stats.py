import os
from threading import Lock
from fastapi import APIRouter

from src.app.cache import _load_manifest
from src.app.telemetry import snapshot
from src.app.upstash import upstash_ready

router = APIRouter()
_warm_state = "starting"
_warm_lock = Lock()


def set_warm_state(value: str) -> None:
    global _warm_state
    with _warm_lock:
        _warm_state = value


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@router.get("/ready")
def ready():
    with _warm_lock:
        state = _warm_state
    return {"status": state, "ready": state in {"ready", "deferred"}}


@router.get("/api/capabilities")
def capabilities():
    return {
        "legacy_heavy_endpoints": os.getenv(
            "ENABLE_LEGACY_HEAVY_ENDPOINTS", ""
        ).lower() in {"1", "true", "yes"},
        "track_search": {"fast_path": 599_341, "full_index": 2_262_292},
        "artist_ubiquity": {"rank_coverage": 295_860, "rich_details": 10_000},
        "vectors": {
            "query_coverage": 599_341,
            "candidate_index": "popular_10k",
            "available": upstash_ready(),
        },
        "artist_images": {"cached": 10_000, "live_optional": True},
    }


@router.get("/api/ops")
def ops():
    """Anonymous process-local counters; reset whenever the free host restarts."""
    return snapshot()


@router.get("/api/stats")
def stats():
    m = _load_manifest()
    if m:
        ct_m  = m.get("canonical_tracks", {})
        ast_m = m.get("artist_stats", {})
        ed_m  = m.get("editorial", {})
        mpd_m = m.get("mpd", {})
        return {
            "playlists":              mpd_m.get("playlists", 1_000_000),
            "tracks":                 ct_m.get("rows", 3_620_989),
            "playlist_track_rows":    mpd_m.get("playlist_track_rows", 66_346_428),
            "artists":                ast_m.get("rows", 287_742),
            "editorial_playlists":    ed_m.get("playlists", 9_053),
            "has_isrc":               ct_m.get("has_isrc"),
            "has_isrc_pct":           ct_m.get("has_isrc_pct"),
            "has_mbid":               ct_m.get("has_mbid"),
            "has_mbid_pct":           ct_m.get("has_mbid_pct"),
            "metadata_complete":      ct_m.get("metadata_complete"),
            "metadata_complete_pct":  ct_m.get("metadata_complete_pct"),
            "manifest_generated_at":  m.get("generated_at"),
        }

    return {
        "playlists":            1_000_000,
        "tracks":               3_620_989,
        "playlist_track_rows":  66_346_428,
        "artists":              10_000,
        "editorial_playlists":  9_053,
        "manifest_generated_at": None,
    }
