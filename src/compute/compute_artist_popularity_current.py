"""
Build a *current* artist-popularity table to sit alongside the 2017 playlist spine.

Why this exists
---------------
`computed/artist_stats.parquet` ranks artists by appearances in the Million
Playlist Dataset, which stops in October 2017. That is a fine measure of how
playlist culture looked then, and a poor one for "how big is this artist" now:
Olivia Rodrigo lands at rank #57,262 because she arrived in 2021, not because
nobody listens to her.

This joins three sources that are refreshed rather than frozen:

  enrichment/listenbrainz_full.parquet   per-track listen counts  (757K tracks)
  enrichment/artist_lastfm.parquet       listeners + playcount    (33K artists)
  enrichment/chart_history.parquet       chart peaks 2017-2026    (7.4K tracks)

Honest limits, carried into the artifact so the serving layer can state them:

  * ListenBrainz and Last.fm measure *their own users*, who are a small,
    self-selected, scrobbling population. They are current, not representative.
    MPD measured a million Spotify playlists, which is broad but frozen.
  * Neither is "true popularity". They answer different questions, so this
    writes a new artifact instead of overwriting artist_stats.
  * Track-level listens are summed to the artist via canonical_tracks, so an
    artist's coverage depends on how many of their tracks carry an ISRC/MBID.

Output: computed/artist_popularity_current.parquet
    artist_name, lb_listens, lb_tracks, lastfm_listeners, lastfm_playcount,
    charted_tracks, best_chart_peak, last_charted, current_rank, current_pct

Usage:
    python src/compute/compute_artist_popularity_current.py            # local only
    python src/compute/compute_artist_popularity_current.py --upload   # push to R2
"""

import argparse
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

OUT_LOCAL = ROOT / "data" / "processed" / "artist_popularity_current.parquet"
R2_KEY = "computed/artist_popularity_current.parquet"


def connect():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""
        SET s3_region='auto';
        SET s3_endpoint='{os.environ["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com';
        SET s3_access_key_id='{os.environ["R2_ACCESS_KEY_ID"]}';
        SET s3_secret_access_key='{os.environ["R2_SECRET_ACCESS_KEY"]}';
    """)
    # Keep the join inside a small memory envelope; this runs on laptops.
    con.execute("SET memory_limit='2GB'; SET threads=2;")
    return con


def build(con) -> None:
    b = os.environ["R2_BUCKET"]
    src = lambda key: f"read_parquet('s3://{b}/{key}')"  # noqa: E731

    con.execute(f"""
    CREATE OR REPLACE TABLE artist_popularity_current AS
    WITH lb AS (
        -- Track listens summed to the artist. canonical_tracks carries the
        -- artist name; listenbrainz_full carries the count.
        SELECT c.artist_name,
               SUM(l.listen_count)::BIGINT AS lb_listens,
               COUNT(*)::INTEGER           AS lb_tracks
        FROM {src('enrichment/listenbrainz_full.parquet')} l
        JOIN {src('processed/canonical_tracks.parquet')} c
          ON c.spotify_track_uri = l.spotify_track_uri
        WHERE c.artist_name IS NOT NULL
          AND l.listen_count IS NOT NULL
        GROUP BY c.artist_name
    ),
    lfm AS (
        SELECT artist_name,
               MAX(listeners)::BIGINT AS lastfm_listeners,
               MAX(playcount)::BIGINT AS lastfm_playcount
        FROM {src('enrichment/artist_lastfm.parquet')}
        WHERE artist_name IS NOT NULL
        GROUP BY artist_name
    ),
    charts AS (
        SELECT artist_name,
               COUNT(*)::INTEGER      AS charted_tracks,
               MIN(chart_peak)::INTEGER AS best_chart_peak,   -- 1 is the best peak
               MAX(last_charted)      AS last_charted
        FROM {src('enrichment/chart_history.parquet')}
        WHERE artist_name IS NOT NULL
        GROUP BY artist_name
    ),
    joined AS (
        SELECT COALESCE(lb.artist_name, lfm.artist_name, charts.artist_name) AS artist_name,
               COALESCE(lb.lb_listens, 0)        AS lb_listens,
               COALESCE(lb.lb_tracks, 0)         AS lb_tracks,
               COALESCE(lfm.lastfm_listeners, 0) AS lastfm_listeners,
               COALESCE(lfm.lastfm_playcount, 0) AS lastfm_playcount,
               COALESCE(charts.charted_tracks, 0) AS charted_tracks,
               charts.best_chart_peak,
               charts.last_charted
        FROM lb
        FULL OUTER JOIN lfm    ON lb.artist_name = lfm.artist_name
        FULL OUTER JOIN charts ON COALESCE(lb.artist_name, lfm.artist_name) = charts.artist_name
    ),
    pctiles AS (
        -- Listens (plays) and listeners (unique people) are different units on
        -- different scales, so they cannot be ranked against each other
        -- directly: doing that floated artists missing from Last.fm to the top
        -- on raw play counts. Each signal is converted to a percentile within
        -- its own population first, which is unit-free and comparable. Where
        -- both exist they agree at ~0.73 rank correlation, which is why
        -- averaging them is reasonable rather than arbitrary.
        SELECT *,
               CASE WHEN lb_listens > 0
                    THEN PERCENT_RANK() OVER (
                           PARTITION BY (lb_listens > 0) ORDER BY lb_listens)
               END AS lb_pct,
               CASE WHEN lastfm_listeners > 0
                    THEN PERCENT_RANK() OVER (
                           PARTITION BY (lastfm_listeners > 0) ORDER BY lastfm_listeners)
               END AS lfm_pct
        FROM joined
        WHERE artist_name IS NOT NULL
    ),
    scored AS (
        SELECT *,
               -- Mean of whichever signals the artist actually has.
               (COALESCE(lb_pct, 0) + COALESCE(lfm_pct, 0))
                 / NULLIF((CASE WHEN lb_pct IS NULL THEN 0 ELSE 1 END)
                        + (CASE WHEN lfm_pct IS NULL THEN 0 ELSE 1 END), 0) AS score,
               (CASE WHEN lb_pct IS NULL THEN 0 ELSE 1 END)
             + (CASE WHEN lfm_pct IS NULL THEN 0 ELSE 1 END) AS signal_count
        FROM pctiles
    )
    SELECT artist_name, lb_listens, lb_tracks, lastfm_listeners, lastfm_playcount,
           charted_tracks, best_chart_peak, last_charted,
           signal_count::INTEGER AS signal_count,
           ROUND(100.0 * score, 4) AS current_pct,
           ROW_NUMBER() OVER (ORDER BY score DESC, artist_name)::INTEGER AS current_rank
    FROM scored
    WHERE score IS NOT NULL
    ORDER BY current_rank
    """)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true",
                    help="upload to R2 (otherwise writes locally only)")
    args = ap.parse_args()

    con = connect()
    print("Building current artist popularity from ListenBrainz + Last.fm + charts…", flush=True)
    build(con)

    n = con.execute("SELECT count(*) FROM artist_popularity_current").fetchone()[0]
    print(f"  rows: {n:,}")
    print("  top 10 by current signal:")
    for name, rank, lfm, lb in con.execute("""
        SELECT artist_name, current_rank, lastfm_listeners, lb_listens
        FROM artist_popularity_current ORDER BY current_rank LIMIT 10
    """).fetchall():
        print(f"    #{rank:<4} {name[:34]:<34} lastfm={lfm:>12,}  lb={lb:>10,}")

    OUT_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY artist_popularity_current TO '{OUT_LOCAL}' (FORMAT parquet, COMPRESSION zstd)")
    print(f"  wrote {OUT_LOCAL} ({OUT_LOCAL.stat().st_size/1e6:.1f} MB)")

    if args.upload:
        from src.storage.r2 import R2Client
        R2Client().upload(str(OUT_LOCAL), R2_KEY)
        print(f"  uploaded -> {R2_KEY}")
    else:
        print("  (not uploaded; pass --upload to publish to R2)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
