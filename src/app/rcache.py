"""
Tiny in-process TTL + LRU result cache for deterministic read endpoints.

Analytical endpoints (six-degrees, mood-contradiction, collision, …) are pure
functions of their query params for the lifetime of the loaded data, and each
call re-scans parquets through DuckDB. Memoising the small JSON result bounds
that repeated scanning — which is what keeps memory flat and latency low under
concurrent/repeated traffic — while a TTL still lets R2 refreshes flow through.
"""
import threading
import time
from functools import wraps


def ttl_cache(maxsize: int = 256, ttl: float = 1800.0):
    def decorator(fn):
        store: dict = {}
        order: list = []
        lock = threading.Lock()          # guards store/order
        key_locks: dict = {}             # per-key compute lock (single-flight)

        def _get(key):
            now = time.time()
            hit = store.get(key)
            if hit is not None:
                value, ts = hit
                if now - ts < ttl:
                    return True, value
                store.pop(key, None)
            return False, None

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            with lock:
                ok, value = _get(key)
                if ok:
                    return value
                klock = key_locks.setdefault(key, threading.Lock())

            # Single-flight: only one thread computes a given key; others wait
            # here and then read the freshly-cached value instead of re-scanning.
            with klock:
                with lock:
                    ok, value = _get(key)
                    if ok:
                        return value
                value = fn(*args, **kwargs)   # exceptions propagate, not cached
                with lock:
                    if key not in store:
                        order.append(key)
                    store[key] = (value, time.time())
                    while len(order) > maxsize:
                        store.pop(order.pop(0), None)
                    key_locks.pop(key, None)
                return value

        wrapper.cache_clear = lambda: (store.clear(), order.clear(), key_locks.clear())
        return wrapper

    return decorator
