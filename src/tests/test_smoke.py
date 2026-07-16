"""
Smoke tests for all main API endpoints.

Runs against a live server (default: http://localhost:8000).
Does NOT require R2 data to be fully loaded — expects graceful degradation
(200 with empty/null fields) when data isn't available.

Usage:
    pytest src/tests/test_smoke.py -v
    BASE_URL=http://localhost:8000 pytest src/tests/test_smoke.py -v
"""

import json as _json
import os
from pathlib import Path

import pytest
import requests

BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

# Snapshot pages are served as static JSON by the frontend; their heavy backend
# routes are gated off by default (ENABLE_LEGACY_HEAVY_ENDPOINTS).
STATIC_DATA_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "data"
_LEGACY_ON = os.environ.get("ENABLE_LEGACY_HEAVY_ENDPOINTS", "").lower() in {"1", "true", "yes"}


def get(path: str, params: dict | None = None, timeout: int = 10) -> requests.Response:
    return requests.get(f"{BASE}{path}", params=params, timeout=timeout)


def post(path: str, json: dict | None = None, timeout: int = 10) -> requests.Response:
    return requests.post(f"{BASE}{path}", json=json or {}, timeout=timeout)


# ── Infrastructure ────────────────────────────────────────────────────────────

def test_health():
    r = get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_stats():
    r = get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["playlists"] > 0
    assert body["tracks"] > 0
    assert body["artists"] > 0
    # has_isrc_pct may be None if manifest not generated yet — that's fine


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_tracks_returns_results():
    r = get("/api/search-tracks", params={"q": "love"})
    assert r.status_code == 200
    body = r.json()
    # Returns {"results": [...]}
    assert isinstance(body, dict)
    assert "results" in body
    assert isinstance(body["results"], list)


def test_search_tracks_short_query_safe():
    # "a" is below _MIN_SUBSTR_LEN — must not crash
    r = get("/api/search-tracks", params={"q": "a"})
    assert r.status_code == 200
    assert "results" in r.json()


def test_search_tracks_no_query():
    r = get("/api/search-tracks")
    assert r.status_code in (200, 422)  # 422 if q is required


# ── Artist endpoints ───────────────────────────────────────────────────────────

def test_artist_ubiquity_known():
    r = get("/api/artist-ubiquity/Drake")
    assert r.status_code == 200
    body = r.json()
    if "playlist_count" in body:
        assert body["playlist_count"] >= 0
        assert "rank" in body
    else:
        assert "error" in body or "detail" in body or "message" in body


def test_artist_ubiquity_unknown():
    r = get("/api/artist-ubiquity/XYZNoSuchArtist12345")
    assert r.status_code in (200, 404)


def test_artist_ubiquity_with_uri():
    r = get("/api/artist-ubiquity/Drake",
            params={"artist_uri": "spotify:artist:3TVXtAsR1Inumwj472S9r4"})
    assert r.status_code == 200


def test_artist_habitat_known():
    r = get("/api/artist-habitat/Taylor Swift")
    assert r.status_code == 200


def test_artist_habitat_unknown():
    r = get("/api/artist-habitat/XYZNoSuchArtist12345")
    assert r.status_code in (200, 404)


def test_artist_image():
    r = get("/api/artist-image/Radiohead")
    assert r.status_code == 200
    body = r.json()
    assert "artist" in body
    # image_url may be None if Spotify isn't configured


def test_artist_images_batch():
    r = post("/api/artist-images/batch", json={"artists": ["Drake", "Adele"]})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, (list, dict))


def test_doppelganger():
    r = get("/api/doppelganger/Radiohead")
    assert r.status_code == 200


def test_compass():
    r = get("/api/compass/Kendrick Lamar", timeout=45)
    assert r.status_code == 200


def test_ancestry():
    r = get("/api/ancestry/The Beatles")
    assert r.status_code == 200


# ── Artist-based query endpoints ──────────────────────────────────────────────

def test_basicness_known_artist():
    # basicness is an artist lookup against artist_stats, not a track lookup
    r = get("/api/basicness/Drake")
    assert r.status_code in (200, 404)


def test_basicness_short_query_safe():
    # "OK" is below _MIN_SUBSTR_LEN=3 — must not crash
    r = get("/api/basicness/OK")
    assert r.status_code in (200, 404)


# ── Track endpoints ───────────────────────────────────────────────────────────

@pytest.mark.slow
def test_song_passport():
    # Scans 806 MB playlist_tracks.parquet over R2 HTTP — takes 15-30s
    r = get("/api/song-passport/Bohemian Rhapsody", timeout=60)
    assert r.status_code == 200


# ── Graph / network ───────────────────────────────────────────────────────────

def test_six_degrees():
    # params are from_artist / to_artist, not a / b
    r = get("/api/six-degrees",
            params={"from_artist": "Drake", "to_artist": "Kendrick Lamar"},
            timeout=45)
    assert r.status_code == 200


def test_six_degrees_same_artist():
    r = get("/api/six-degrees",
            params={"from_artist": "Drake", "to_artist": "Drake"},
            timeout=45)
    assert r.status_code == 200


# ── Discovery ─────────────────────────────────────────────────────────────────

def test_trend_explorer():
    r = get("/api/trend-explorer/hip-hop")
    assert r.status_code == 200


def test_editorial_graveyard():
    # Served as a static snapshot; heavy backend route gated off (410) by default.
    r = get("/api/editorial-graveyard", timeout=30)
    assert r.status_code == (200 if _LEGACY_ON else 410)
    data = _json.loads((STATIC_DATA_DIR / "editorial-graveyard.json").read_text())
    assert data.get("tracks")


def test_forgotten_hits():
    r = get("/api/forgotten-hits", timeout=30)
    assert r.status_code == (200 if _LEGACY_ON else 410)
    data = _json.loads((STATIC_DATA_DIR / "forgotten-hits.json").read_text())
    assert data.get("tracks")


def test_main_character():
    r = get("/api/main-character/Lana Del Rey")
    assert r.status_code == 200


def test_collision():
    r = get("/api/collision", timeout=45)
    assert r.status_code == 200


def test_roast():
    r = get("/api/roast")
    assert r.status_code == 200


def test_name_generator():
    r = get("/api/name-generator")
    assert r.status_code == 200


def test_time_capsule():
    # Served as per-era static snapshots; heavy backend route gated off by default.
    r = get("/api/time-capsule", timeout=45)
    assert r.status_code == (200 if _LEGACY_ON else 410)
    data = _json.loads((STATIC_DATA_DIR / "time-capsule-2010s.json").read_text())
    assert data.get("top_tracks")


def test_mood_contradiction():
    # Served as a static snapshot (keyed by mood); heavy backend route gated off.
    r = get("/api/mood-contradiction", timeout=45)
    assert r.status_code == (200 if _LEGACY_ON else 410)
    data = _json.loads((STATIC_DATA_DIR / "mood-contradiction.json").read_text())
    assert data.get("sad", {}).get("tracks")


def test_transition_finder_missing_required_param():
    # from_uri is required; no params should return 422
    r = get("/api/transition-finder")
    assert r.status_code == 422


@pytest.mark.slow
def test_transition_finder_with_params():
    # Loads FAISS index on first call — slow on cold server
    r = get("/api/transition-finder",
            params={"from_uri": "spotify:track:7KXjTSCq5nL1LoYtL7XAwS",
                    "to_artist": "Radiohead"})
    assert r.status_code in (200, 404, 503)  # 503 if embeddings not loaded


def test_overlap_arena():
    # Takes optional query params a / b with artist name defaults
    r = get("/api/overlap-arena", params={"a": "Drake", "b": "Taylor Swift"})
    assert r.status_code == 200


# ── Geo / mood ────────────────────────────────────────────────────────────────

def test_playlist_language():
    r = get("/api/playlist-language")
    assert r.status_code == 200


def test_mood_map_clusters():
    r = get("/api/mood-map/clusters")
    assert r.status_code == 200


def test_genre_weather_regions():
    r = get("/api/genre-weather/regions")
    assert r.status_code == 200


def test_genre_weather_clusters():
    r = get("/api/genre-weather/clusters")
    assert r.status_code == 200


# ── Batch / social ────────────────────────────────────────────────────────────

def test_group_blend():
    # body key is "artists", not "playlists"
    r = post("/api/group-blend",
             json={"artists": ["Drake", "Taylor Swift", "Radiohead"]},
             timeout=45)
    assert r.status_code == 200


def test_soundtrack_gift():
    # body key is "prompt"; Ollama (llama3) takes up to 25s on first warm request
    r = post("/api/soundtrack-gift",
             json={"prompt": "something for a late night drive"},
             timeout=35)
    assert r.status_code == 200


def test_forensics():
    # body key is "playlist_url", not "playlist_uri"
    r = post("/api/forensics",
             json={"playlist_url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"})
    assert r.status_code == 200
