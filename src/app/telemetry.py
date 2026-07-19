"""Small, privacy-preserving operational counters for the portfolio deployment.

Only route templates and coarse feature events are retained. User queries,
artist names, track titles, IP addresses, and headers are never stored.
"""
from collections import Counter
from threading import Lock
from time import monotonic

_started = monotonic()
_lock = Lock()
_requests = Counter()
_events = Counter()
_latency_total_ms = Counter()
_latency_max_ms = Counter()


def record_request(route: str, status: int, elapsed_ms: float) -> None:
    key = f"{route}|{status}"
    with _lock:
        _requests[key] += 1
        _latency_total_ms[route] += round(elapsed_ms, 2)
        _latency_max_ms[route] = max(_latency_max_ms[route], round(elapsed_ms, 2))


def record_event(feature: str, outcome: str) -> None:
    with _lock:
        _events[f"{feature}|{outcome}"] += 1


def snapshot() -> dict:
    with _lock:
        route_counts = Counter()
        for key, count in _requests.items():
            route_counts[key.rsplit("|", 1)[0]] += count
        latency = {
            route: {
                "avg_ms": round(_latency_total_ms[route] / count, 1),
                "max_ms": _latency_max_ms[route],
            }
            for route, count in route_counts.items() if count
        }
        return {
            "uptime_seconds": round(monotonic() - _started, 1),
            "requests": dict(_requests),
            "events": dict(_events),
            "latency": latency,
            "privacy": "Aggregated route templates only; query values are not retained.",
        }
