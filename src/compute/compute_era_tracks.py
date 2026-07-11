"""
Pre-compute era_tracks.parquet — tracks with known release_year + playlist counts.

Joins canonical_tracks (has release_year for 124K tracks via Deezer API)
with track_stats (has playlist_count for 2.26M tracks) so time_capsule can
show real-era results for 90s / 2000s / early 2010s where editorial
playlist date_added data doesn't exist (mackorone scraping started ~2017).

Output: R2:computed/era_tracks.parquet
Schema:
    track_name      str
    artist_name     str
    release_year    int   (e.g. 1994)
    playlist_count  int

~124K rows, ~4 MB.

Usage:
    python src/compute/compute_era_tracks.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

R2_KEY = "computed/era_tracks.parquet"


def main() -> None:
    r2 = R2Client()
    tmp = Path(tempfile.gettempdir())

    print("Downloading canonical_tracks …")
    ct_path = tmp / "era_ct.parquet"
    r2.download("processed/canonical_tracks.parquet", ct_path)
    ct = pd.read_parquet(ct_path, columns=["spotify_track_uri", "release_year"])
    ct_path.unlink(missing_ok=True)
    ct = ct[ct["release_year"].notna()].copy()
    ct["release_year"] = ct["release_year"].astype("Int64")
    print(f"  {len(ct):,} tracks with release_year")

    print("Downloading track_stats …")
    ts_path = tmp / "era_ts.parquet"
    r2.download("computed/track_stats.parquet", ts_path)
    ts = pd.read_parquet(ts_path, columns=["track_uri", "track_name", "artist_name", "playlist_count"])
    ts_path.unlink(missing_ok=True)
    print(f"  {len(ts):,} tracks with playlist_count")

    print("Joining …")
    merged = ct.merge(
        ts.rename(columns={"track_uri": "spotify_track_uri"}),
        on="spotify_track_uri", how="inner"
    )
    out = merged[["track_name", "artist_name", "release_year", "playlist_count"]].copy()
    out = out.sort_values("playlist_count", ascending=False)
    print(f"  {len(out):,} tracks with both release_year and playlist_count")

    decade_dist = out["release_year"].dropna().astype(int).floordiv(10).mul(10).value_counts().sort_index()
    print("  By decade:")
    for decade, count in decade_dist.items():
        print(f"    {decade}s: {count:,}")

    out_path = tmp / "era_tracks.parquet"
    out.to_parquet(out_path, index=False, compression="zstd")
    size_mb = out_path.stat().st_size / 1024**2
    print(f"\nUploading {size_mb:.1f} MB → R2:{R2_KEY} …")
    r2.upload(str(out_path), R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ era_tracks.parquet: {len(out):,} rows, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
