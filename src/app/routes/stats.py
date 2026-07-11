from fastapi import APIRouter

from src.app.cache import _load_manifest

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


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
