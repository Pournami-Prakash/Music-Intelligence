"""
Pre-compute track_stats.parquet — per-track playlist counts + top names.

song_passport currently scans 806 MB playlist_tracks.parquet live on every call
via DuckDB R2 httpfs (~14-17s per request).  Running this script once materialises
the same data into a ~60 MB parquet that main.py can load at startup and query
instantly (<1ms per lookup).

Output: R2:computed/track_stats.parquet
Schema:
    track_uri            str   (spotify:track:...)
    track_name           str
    artist_name          str
    playlist_count       int
    top_playlist_names   list[str]  (up to 10 playlist names)

Runtime: ~3-5 min (one full DuckDB scan of playlist_tracks.parquet via R2 httpfs).

Usage:
    python src/compute/compute_track_stats.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY = "computed/track_stats.parquet"


def main() -> None:
    r2 = R2Client()
    con = get_con()

    print("Scanning playlist_tracks + tracks + playlists via DuckDB (one pass) …")
    print("  This reads ~900 MB from R2 and will take 3-5 min.")

    df = con.execute(f"""
        WITH matched AS (
            SELECT
                t.track_uri,
                t.track_name,
                t.artist_name,
                pt.pid
            FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
            JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t
                ON pt.track_uri = t.track_uri
        )
        SELECT
            m.track_uri,
            m.track_name,
            m.artist_name,
            COUNT(DISTINCT m.pid)                         AS playlist_count,
            list(p.name ORDER BY p.name)[1:10]            AS top_playlist_names
        FROM matched m
        JOIN read_parquet('{R2_PATH}/processed/playlists.parquet') p
            ON m.pid = p.pid
        WHERE p.name IS NOT NULL AND length(trim(p.name)) > 0
        GROUP BY m.track_uri, m.track_name, m.artist_name
        ORDER BY playlist_count DESC
    """).df()

    print(f"  {len(df):,} tracks with playlist coverage")
    print(f"  Top by count:")
    for _, r in df.head(5).iterrows():
        print(f"    {r['track_name']} — {r['artist_name']}  ({r['playlist_count']:,} playlists)")

    out = Path(tempfile.gettempdir()) / "track_stats.parquet"
    df.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024**2
    print(f"\nUploading {size_mb:.1f} MB → R2:{R2_KEY} …")
    r2.upload(str(out), R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ track_stats.parquet: {len(df):,} rows, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
