"""Regression tests for the meaning of user-facing metrics.

The smoke suite proves routes return JSON. These assertions protect the claims
the interface makes about that JSON.
"""

import json
import os
import re
from pathlib import Path

import pytest
import requests


BASE = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
STATIC_DATA_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "data"


def get(path: str, params: dict | None = None, timeout: int = 90):
    return requests.get(f"{BASE}{path}", params=params, timeout=timeout)


def post(path: str, body: dict, timeout: int = 90):
    return requests.post(f"{BASE}{path}", json=body, timeout=timeout)


def normalize_title(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.lower()).strip()


def test_habitat_percentages_are_distinct_playlist_shares():
    data = get("/api/artist-habitat/Radiohead").json()
    assert data["method_version"] == "distinct-artist-playlist-v2"
    assert all(0 <= item["pct"] <= 100 for item in data["habitats"].values())
    assert all(item["count"] <= data["playlist_count"] for item in data["habitats"].values())


def test_mood_map_reports_unique_matches_separately_from_assignments():
    data = json.loads((STATIC_DATA_DIR / "mood-map.json").read_text())
    assert data["method_version"] == "bounded-keywords-v2"
    assert 0 <= data["unique_matched_titles"] <= data["total_playlists"]
    assert data["assignment_count"] >= data["unique_matched_titles"]
    assert data["categories_overlap"] is True


@pytest.mark.parametrize("era", ["1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"])
def test_time_capsule_tracks_belong_to_selected_release_decade(era):
    data = json.loads((STATIC_DATA_DIR / f"time-capsule-{era}.json").read_text())
    start = int(era[:4])
    assert data["data_source"] == "release_year"
    assert data["method_version"] == "release-year-v2"
    assert all(start <= track["release_year"] <= start + 9 for track in data["top_tracks"])


def test_collision_is_deterministic_and_ranked_by_bridge_score():
    params = {"a": "Drake", "b": "Radiohead"}
    first = get("/api/collision", params=params).json()
    second = get("/api/collision", params=params).json()
    assert first["bridge_artists"] == second["bridge_artists"]
    scores = [item["bridge_score"] for item in first["bridge_artists"]]
    assert scores == sorted(scores, reverse=True)
    assert all(item["shared_with_a"] > 0 and item["shared_with_b"] > 0 for item in first["bridge_artists"])


def test_name_generator_honors_requested_theme_and_is_reproducible():
    first = get("/api/name-generator", {"theme": "party", "count": 8}).json()
    second = get("/api/name-generator", {"theme": "party", "count": 8}).json()
    assert first["names"] == second["names"]
    assert first["corpus_theme"] == "activity"
    anchors = {anchor.lower() for anchor in first["anchors"]}
    assert all(any(anchor in name.lower() for anchor in anchors) for name in first["names"])


def test_roast_exact_examples_are_exact_normalized_titles():
    data = get("/api/roast", {"title": "vibes"}).json()
    assert data["exact_match_count"] >= len(data["exact_examples"])
    assert all(normalize_title(example) == "vibes" for example in data["exact_examples"])


def test_reach_score_is_the_displayed_percentile():
    data = get("/api/main-character/Radiohead").json()
    assert data["score"] == data["percentile"]
    assert "influence" in data["evidence"]["limitations"][0]


def test_tag_lineage_does_not_claim_influence():
    data = get("/api/ancestry/Radiohead").json()
    assert "higher_reach" in data and "lower_reach" in data
    assert "ancestors" not in data and "descendants" not in data
    assert "does not infer chronology" in data["evidence"]["limitations"][0]


def test_doppelgangers_are_sorted_by_displayed_similarity():
    data = get("/api/doppelganger/Radiohead", timeout=120).json()
    similarities = [item["similarity"] for item in data["doppelgangers"]]
    assert similarities == sorted(similarities, reverse=True)
    assert all("embedding_similarity" in item and "tag_similarity" in item for item in data["doppelgangers"])


def test_soundtrack_roles_have_audio_and_stage_targets():
    response = post("/api/soundtrack-gift", {"prompt": "a rainy late-night drive"}, timeout=120)
    assert response.status_code == 200
    data = response.json()
    assert [track["role"] for track in data["tracks"]] == [
        "opener", "build", "anchor", "peak", "wind_down", "closer"
    ]
    assert all(track["energy"] is not None and track["target_energy"] is not None for track in data["tracks"])
    assert data["meta"]["candidate_count"] >= len(data["tracks"])


@pytest.mark.slow
def test_transition_is_an_ordered_scored_route():
    search_a = get("/api/search-tracks", {"q": "No Surprises", "limit": 1}).json()["results"]
    search_b = get("/api/search-tracks", {"q": "Mr. Brightside", "limit": 1}).json()["results"]
    if not search_a or not search_b:
        pytest.skip("Example tracks are outside the interactive search index")
    response = get("/api/transition-finder", {
        "from_uri": search_a[0]["uri"],
        "to_uri": search_b[0]["uri"],
        "limit": 3,
    }, timeout=120)
    if response.status_code in (404, 503):
        pytest.skip(response.json().get("detail", "vector index unavailable"))
    data = response.json()
    assert [bridge["stage"] for bridge in data["bridges"]] == [1, 2, 3]
    assert all("transition_similarity" in bridge for bridge in data["bridges"])
    assert 0 <= data["route_score"] <= 1
