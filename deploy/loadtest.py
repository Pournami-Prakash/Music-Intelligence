#!/usr/bin/env python3
"""
Mixed-endpoint load test for the Atlas API.

Fires a varied stream of requests at a fixed concurrency and reports latency
percentiles, throughput, status breakdown, and the slowest request (a proxy for
queue-wait when DUCKDB_MAX_CONCURRENCY throttles). Pair with `docker stats` for
RSS while this runs — see deploy/LINUX_LOADTEST.md.

By default requests are UNCACHED: params are drawn from a large pool so most
miss the result cache (worst case for memory + latency). Use --cached to hammer
one hot key instead (measures the cached fast-path).

Examples:
    python deploy/loadtest.py --base http://localhost:7860 --concurrency 5 --count 300
    python deploy/loadtest.py --base http://localhost:7860 --concurrency 10 --duration 120   # soak
"""
import argparse
import concurrent.futures as cf
import random
import statistics
import time
import urllib.parse
import urllib.request
import urllib.error

# Real values so requests resolve to actual work (not just 404s).
ARTISTS = [
    "Drake", "Kendrick Lamar", "Taylor Swift", "Kanye West", "Rihanna", "Future",
    "J. Cole", "Post Malone", "The Weeknd", "Ariana Grande", "Bad Bunny", "Eminem",
    "Beyonce", "Lana Del Rey", "Radiohead", "Metallica", "Coldplay", "Adele",
    "Travis Scott", "SZA", "Frank Ocean", "Tyler, The Creator", "Lady Gaga",
    "Bruno Mars", "Ed Sheeran", "Billie Eilish", "Nicki Minaj", "Lil Wayne",
    "Childish Gambino", "Justin Bieber", "Doja Cat", "Migos", "21 Savage", "DaBaby",
]
MOODS = ["sad", "happy", "gym", "party", "study", "sleep", "chill"]
TRACKS = [
    "One Dance", "Circles", "HUMBLE.", "Closer", "Congratulations", "As It Was",
    "Blinding Lights", "God's Plan", "Sunflower", "Believer", "Stay", "Levitating",
    "Bad Guy", "Shape of You", "Uptown Funk", "Pepas", "September", "Hello",
]


def uncached_path():
    a, b = random.sample(ARTISTS, 2)
    return random.choice([
        f"/api/six-degrees?from_artist={a}&to_artist={b}",
        f"/api/overlap-arena?a={a}&b={b}",
        f"/api/collision?a={a}&b={b}",
        f"/api/compass/{a}",
        f"/api/doppelganger/{a}",
        f"/api/mood-contradiction?mood={random.choice(MOODS)}&limit=20",
        f"/api/song-passport/{random.choice(TRACKS)}",
        f"/api/search-tracks?q={random.choice(TRACKS)[:5]}&limit=8",
    ])


def cached_path():
    return "/api/mood-contradiction?mood=sad&limit=20"


def fetch(base, path, timeout):
    url = base.rstrip("/") + urllib.parse.quote(path, safe="/?=&")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = -1  # connection error / timeout / reset (e.g. OOM restart)
    return code, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:7860")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--count", type=int, default=0, help="total requests (0 = use --duration)")
    ap.add_argument("--duration", type=int, default=0, help="run for N seconds instead of a fixed count")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--cached", action="store_true", help="hammer one hot key (cached fast-path)")
    args = ap.parse_args()

    pick = cached_path if args.cached else uncached_path
    results = []
    stop_at = time.time() + args.duration if args.duration else None
    total = args.count if args.count else (10**9 if args.duration else 200)

    print(f"load test → {args.base}  concurrency={args.concurrency}  "
          f"{'duration=%ds' % args.duration if args.duration else 'count=%d' % total}  "
          f"mode={'cached' if args.cached else 'uncached'}")

    t_start = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        inflight = set()
        submitted = 0
        while True:
            if stop_at and time.time() >= stop_at:
                break
            if not stop_at and submitted >= total:
                break
            while len(inflight) < args.concurrency and (stop_at or submitted < total):
                inflight.add(ex.submit(fetch, args.base, pick(), args.timeout))
                submitted += 1
            done, inflight = cf.wait(inflight, return_when=cf.FIRST_COMPLETED)
            for d in done:
                results.append(d.result())
        for d in cf.as_completed(inflight):
            results.append(d.result())
    wall = time.perf_counter() - t_start

    lat = sorted(l for _, l in results)
    codes = {}
    for c, _ in results:
        codes[c] = codes.get(c, 0) + 1
    n = len(results)
    ok = codes.get(200, 0)

    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0.0

    print(f"\n  requests      : {n}  in {wall:.1f}s  ({n / wall:.1f} req/s)")
    print(f"  status        : " + "  ".join(f"{k}:{v}" for k, v in sorted(codes.items())))
    print(f"  success rate  : {ok}/{n} ({100 * ok / n:.1f}%)")
    print(f"  latency  p50  : {pct(0.50) * 1000:6.0f} ms")
    print(f"           p95  : {pct(0.95) * 1000:6.0f} ms")
    print(f"           p99  : {pct(0.99) * 1000:6.0f} ms")
    print(f"           max  : {(lat[-1] if lat else 0) * 1000:6.0f} ms   (slowest = queue-wait proxy)")
    errors = n - ok
    if errors:
        print(f"  ⚠️  {errors} non-200 (code -1 = connection reset, e.g. OOM restart)")


if __name__ == "__main__":
    main()
