#!/usr/bin/env python3
"""Per-artifact memory probe for the 512 MB box.

Runs as the container's main process, loads each artifact the API touches — one
at a time, cumulatively (the worst-case sequential-warm scenario) — and prints
the cgroup memory delta after each. Shows exactly what consumes RAM and whether
it's real (anon) or reclaimable page cache (file).

    docker run --rm --memory=512m --memory-swap=512m --env-file .env atlas-api \
      sh -c 'export LD_PRELOAD=$(ls /usr/lib/*/libjemalloc.so.2); python deploy/mem_probe.py'
"""
import gc

M = 1024 * 1024


def _cgroup():
    try:  # cgroup v2
        cur = int(open("/sys/fs/cgroup/memory.current").read().strip())
        stat = {}
        for line in open("/sys/fs/cgroup/memory.stat"):
            parts = line.split()
            if len(parts) >= 2:
                stat[parts[0]] = int(parts[1])
        return cur, stat.get("anon", 0), stat.get("file", 0)
    except Exception:
        try:  # cgroup v1
            cur = int(open("/sys/fs/cgroup/memory/memory.usage_in_bytes").read().strip())
            return cur, 0, 0
        except Exception:
            return 0, 0, 0


def _rss():
    for l in open("/proc/self/status"):
        if l.startswith("VmRSS"):
            return int(l.split()[1]) * 1024
    return 0


_prev = {"cur": 0}


def report(label):
    gc.collect()
    cur, anon, fil = _cgroup()
    print(f"{label:44} cur={cur // M:4d}MiB (Δ{(cur - _prev['cur']) // M:+5d})  "
          f"anon={anon // M:4d} file={fil // M:4d}  rss={_rss() // M:4d}")
    _prev["cur"] = cur


report("baseline (python only)")
from src.app.cache import local_parquet, duck_df, _load_computed   # noqa: E402
from src.storage.duckdb_r2 import R2_PATH                          # noqa: E402
report("after imports")

print("\n-- pandas artifacts (_load_computed → resident DataFrame) --")
for key in [
    "computed/artist_stats.parquet", "enrichment/artist_lastfm.parquet",
    "enrichment/artist_genres.parquet", "enrichment/fma_enrichment.parquet",
    "processed/editorial_playlists.parquet", "computed/artist_images.parquet",
    "computed/artist_habitat.parquet", "computed/playlist_title_terms.parquet",
]:
    try:
        _load_computed(key)
    except Exception as e:
        print(f"  (skip {key}: {e})")
    report(f"pandas  {key.split('/')[-1]}")

print("\n-- local parquets the API still downloads to /tmp --")
for key, where in [
    ("computed/track_stats_top.parquet", "track_name_lc = 'circles'"),
    ("computed/artist_edges.parquet", "artist_a_name = 'Drake'"),
    ("embeddings/track2vec_vocab_lookup.parquet", "track_name_lc = 'circles'"),
]:
    p = local_parquet(key)
    if p:
        try:
            duck_df(f"SELECT * FROM read_parquet('{p.as_posix()}') WHERE {where} LIMIT 5")
        except Exception as e:
            print(f"  (query failed {key}: {e})")
    report(f"local   {key.split('/')[-1]}")

print("\n-- R2 httpfs queries (no local file; memory only during query) --")
for key, where in [
    ("enrichment/listenbrainz_lookup.parquet", "spotify_track_uri = 'x'"),   # song-passport
    ("processed/editorial_tracks_slim.parquet", "track_name = 'x'"),          # forensics
    ("computed/track_stats_lookup.parquet", "track_name_lc = 'circles'"),     # song-passport miss
    ("processed/tracks.parquet", "lower(track_name) LIKE 'circ%'"),           # search top-up
]:
    try:
        duck_df(f"SELECT * FROM read_parquet('{R2_PATH}/{key}') WHERE {where} LIMIT 5")
    except Exception as e:
        print(f"  (r2 {key} failed: {e})")
    report(f"r2sql   {key.split('/')[-1]}")

cur, anon, fil = _cgroup()
print(f"\nPEAK cgroup: {cur // M} MiB / 512  (anon {anon // M} real, file {fil // M} reclaimable cache)")
print("If cur≈512 with large 'file': page cache is the pressure (fix = smaller/remote artifacts).")
print("If 'anon' is large: real memory (DuckDB buffers / pandas) — lower memory_limit or remote more.")
