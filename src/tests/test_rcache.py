"""Unit tests for the TTL + single-flight result cache (no server needed)."""
import threading
import time

from src.app.rcache import ttl_cache


def test_hit_and_miss():
    calls = {"n": 0}

    @ttl_cache(ttl=10)
    def f(x):
        calls["n"] += 1
        return x * 2

    assert f(3) == 6
    assert f(3) == 6
    assert calls["n"] == 1  # second call served from cache


def test_expiry_recomputes():
    calls = {"n": 0}

    @ttl_cache(ttl=0.2)
    def f(x):
        calls["n"] += 1
        return x

    f(1)
    time.sleep(0.25)
    f(1)
    assert calls["n"] == 2


def test_lru_eviction():
    calls = {"n": 0}

    @ttl_cache(maxsize=2, ttl=100)
    def f(x):
        calls["n"] += 1
        return x

    f(1); f(2); f(3)          # inserting 3rd evicts LRU (key 1)
    n = calls["n"]
    f(1)                       # 1 was evicted → recompute
    assert calls["n"] == n + 1
    f(3)                       # 3 still cached
    assert calls["n"] == n + 1


def test_exception_not_cached_and_no_lock_leak():
    calls = {"n": 0}

    @ttl_cache(ttl=100)
    def f(x):
        calls["n"] += 1
        raise ValueError("boom")

    for _ in range(3):
        try:
            f("k")
        except ValueError:
            pass
    assert calls["n"] == 3  # never cached; per-key lock released each time


def test_single_flight_dedupes_concurrent_calls():
    calls = {"n": 0}
    started = threading.Event()

    @ttl_cache(ttl=100)
    def slow(x):
        calls["n"] += 1
        started.set()
        time.sleep(0.2)
        return x

    threads = [threading.Thread(target=slow, args=("same",)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1  # 8 concurrent identical calls computed once
