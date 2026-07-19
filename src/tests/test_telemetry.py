from src.app.telemetry import record_event, record_request, snapshot


def test_telemetry_aggregates_without_query_values():
    record_request("/api/search-tracks", 200, 12.5)
    record_event("track_search", "full_index")

    data = snapshot()
    assert data["requests"]["/api/search-tracks|200"] >= 1
    assert data["events"]["track_search|full_index"] >= 1
    assert data["latency"]["/api/search-tracks"]["avg_ms"] > 0
    assert "query" not in data
    assert "not retained" in data["privacy"]
