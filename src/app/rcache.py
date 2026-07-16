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
from collections import OrderedDict
from functools import wraps


def ttl_cache(maxsize: int = 256, ttl: float = 1800.0):
    def decorator(fn):
        store: "OrderedDict" = OrderedDict()   # key -> (value, ts); ordered by recency
        lock = threading.Lock()                # guards store + key_locks
        key_locks: dict = {}                   # per-key compute lock (single-flight)

        def _get_locked(key):
            """Return (hit?, value). Drops the entry if expired. Caller holds `lock`."""
            hit = store.get(key)
            if hit is None:
                return False, None
            value, ts = hit
            if time.time() - ts >= ttl:
                del store[key]                 # evict expired instead of leaking it
                return False, None
            store.move_to_end(key)             # mark most-recently-used
            return True, value

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            with lock:
                ok, value = _get_locked(key)
                if ok:
                    return value
                klock = key_locks.setdefault(key, threading.Lock())

            # Single-flight: only one thread computes a given key; others wait
            # here and then read the freshly-cached value instead of re-scanning.
            with klock:
                try:
                    with lock:
                        ok, value = _get_locked(key)
                        if ok:
                            return value
                    value = fn(*args, **kwargs)   # exceptions propagate, not cached
                    with lock:
                        store[key] = (value, time.time())
                        store.move_to_end(key)
                        while len(store) > maxsize:
                            store.popitem(last=False)   # evict least-recently-used
                    return value
                finally:
                    # Always drop the per-key lock — including when fn() raised —
                    # so a failed computation doesn't leak lock objects.
                    with lock:
                        key_locks.pop(key, None)

        wrapper.cache_clear = lambda: (store.clear(), key_locks.clear())
        return wrapper

    return decorator
