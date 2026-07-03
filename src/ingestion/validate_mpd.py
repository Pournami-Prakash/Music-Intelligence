"""
Validate processed MPD Parquet files on R2 using DuckDB — no pandas, no full download.

DuckDB reads Parquet metadata and runs aggregations directly over R2 via httpfs.
Only summary stats are pulled into memory.

Usage:
    python src/ingestion/validate_mpd.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH

PL  = f"{R2_PATH}/processed/playlists.parquet"
TR  = f"{R2_PATH}/processed/tracks.parquet"
PT  = f"{R2_PATH}/processed/playlist_tracks.parquet"


def validate():
    con = get_con()
    passed, failed = [], []

    def check(name: str, condition: bool, detail: str = ""):
        if condition:
            passed.append(f"  ✓ {name}")
        else:
            failed.append(f"  ✗ {name}" + (f" — {detail}" if detail else ""))

    print("Validating MPD Parquet files via DuckDB → R2...\n")

    # ── playlists ─────────────────────────────────────────────────────────────
    pl_stats = con.execute(f"""
        SELECT
            COUNT(*)                        AS total,
            COUNT(DISTINCT pid)             AS unique_pids,
            COUNT(*) FILTER (pid IS NULL)   AS null_pids,
            AVG(num_tracks)                 AS avg_tracks,
            SUM(collaborative::INT)         AS collab_count,
            MIN(pid)                        AS min_pid,
            MAX(pid)                        AS max_pid
        FROM read_parquet('{PL}')
    """).fetchone()

    total_pl, unique_pids, null_pids, avg_tracks, collab, min_pid, max_pid = pl_stats

    check("playlists row count = 1,000,000",    total_pl == 1_000_000,       f"got {total_pl:,}")
    check("playlists no duplicate pids",         unique_pids == total_pl,     f"{total_pl - unique_pids:,} dupes")
    check("playlists no null pids",              null_pids == 0,              f"{null_pids:,} nulls")

    print(f"playlists.parquet: {total_pl:,} rows")
    print(f"  pid range       : {min_pid} → {max_pid}")
    print(f"  avg tracks      : {avg_tracks:.1f}")
    print(f"  collaborative   : {collab:,} ({collab/total_pl*100:.1f}%)\n")

    # ── tracks ────────────────────────────────────────────────────────────────
    tr_stats = con.execute(f"""
        SELECT
            COUNT(*)                                    AS total,
            COUNT(DISTINCT track_uri)                   AS unique_uris,
            COUNT(*) FILTER (track_uri IS NULL)         AS null_uris,
            COUNT(*) FILTER (artist_name IS NULL)       AS null_artists,
            COUNT(*) FILTER (duration_ms <= 0)          AS bad_duration,
            COUNT(DISTINCT artist_name)                 AS unique_artists
        FROM read_parquet('{TR}')
    """).fetchone()

    total_tr, unique_uris, null_uris, null_artists, bad_dur, unique_artists = tr_stats

    check("tracks no null URIs",           null_uris == 0,      f"{null_uris:,} nulls")
    check("tracks no duplicate URIs",      unique_uris == total_tr, f"{total_tr - unique_uris:,} dupes")
    check("tracks artist coverage > 95%",  null_artists / total_tr < 0.05,
                                           f"{null_artists:,} null artists")
    check("tracks duration mostly valid",  bad_dur / total_tr < 0.05,
                                           f"{bad_dur:,} with duration ≤ 0")

    print(f"tracks.parquet: {total_tr:,} unique tracks")
    print(f"  unique artists  : {unique_artists:,}")
    print(f"  null artists    : {null_artists:,}\n")

    # ── playlist_tracks ───────────────────────────────────────────────────────
    pt_stats = con.execute(f"""
        SELECT
            COUNT(*)                                AS total,
            COUNT(DISTINCT pid)                     AS unique_pids,
            COUNT(DISTINCT track_uri)               AS unique_uris,
            COUNT(*) FILTER (track_uri IS NULL)     AS null_uris,
            COUNT(*) FILTER (pid IS NULL)           AS null_pids,
            COUNT(*) FILTER (pos < 0)               AS neg_pos,
            MIN(pos)                                AS min_pos,
            MAX(pos)                                AS max_pos
        FROM read_parquet('{PT}')
    """).fetchone()

    total_pt, pt_unique_pids, pt_unique_uris, pt_null_uris, pt_null_pids, neg_pos, min_pos, max_pos = pt_stats

    check("playlist_tracks > 60M rows",    total_pt > 60_000_000,   f"got {total_pt:,}")
    check("playlist_tracks no null URIs",  pt_null_uris == 0,       f"{pt_null_uris:,} nulls")
    check("playlist_tracks no null pids",  pt_null_pids == 0,       f"{pt_null_pids:,} nulls")
    check("playlist_tracks pos >= 0",      neg_pos == 0,            f"{neg_pos:,} negative pos values")

    print(f"playlist_tracks.parquet: {total_pt:,} rows")
    print(f"  unique pids     : {pt_unique_pids:,}")
    print(f"  unique URIs     : {pt_unique_uris:,}")
    print(f"  pos range       : {min_pos} → {max_pos}\n")

    # ── Cross-table checks via DuckDB JOIN ─────────────────────────────────────
    orphan_tracks = con.execute(f"""
        SELECT COUNT(DISTINCT pt.track_uri)
        FROM read_parquet('{PT}') pt
        LEFT JOIN read_parquet('{TR}') tr USING (track_uri)
        WHERE tr.track_uri IS NULL
    """).fetchone()[0]

    orphan_pids = con.execute(f"""
        SELECT COUNT(DISTINCT pt.pid)
        FROM read_parquet('{PT}') pt
        LEFT JOIN read_parquet('{PL}') pl USING (pid)
        WHERE pl.pid IS NULL
    """).fetchone()[0]

    check("no orphaned track URIs in playlist_tracks", orphan_tracks == 0, f"{orphan_tracks:,} orphans")
    check("no orphaned pids in playlist_tracks",       orphan_pids == 0,   f"{orphan_pids:,} orphans")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("─" * 50)
    print(f"PASSED: {len(passed)}/{len(passed)+len(failed)}")
    for p in passed:
        print(p)
    if failed:
        print(f"\nFAILED: {len(failed)}")
        for f_ in failed:
            print(f_)
        print("\n⚠  Do NOT delete raw MPD until all checks pass.")
    else:
        print("\n✓ All checks passed. Safe to delete or archive raw MPD JSON.")
    print("─" * 50)


if __name__ == "__main__":
    validate()
