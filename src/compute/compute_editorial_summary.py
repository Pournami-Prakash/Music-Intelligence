"""
Pre-compute editorial_removed.parquet — removed tracks with playlist name pre-joined.

editorial_graveyard and forgotten_hits only use rows where date_removed IS NOT NULL.
That's ~10-20% of the full 222 MB editorial_playlist_tracks.parquet.
Materialising those rows here reduces cold start from ~5s → ~0.1s.

Output: R2:computed/editorial_removed.parquet
Schema:
    track_name     str
    artist_name    str
    playlist_id    str
    playlist_name  str
    date_added     str   (ISO date string)
    date_removed   str   (ISO date string)
    days_on        int   (clipped ≥ 0)

Usage:
    python src/compute/compute_editorial_summary.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

R2_KEY = "computed/editorial_removed.parquet"


def main() -> None:
    r2 = R2Client()
    tmp = Path(tempfile.gettempdir())

    print("Downloading editorial_playlist_tracks.parquet …")
    tracks_path = tmp / "ept_dl.parquet"
    r2.download("processed/editorial_playlist_tracks.parquet", tracks_path)
    tracks_df = pd.read_parquet(tracks_path)
    tracks_path.unlink(missing_ok=True)
    print(f"  {len(tracks_df):,} rows total")

    print("Downloading editorial_playlists.parquet …")
    playlists_path = tmp / "ep_dl.parquet"
    r2.download("processed/editorial_playlists.parquet", playlists_path)
    playlists_df = pd.read_parquet(playlists_path)
    playlists_path.unlink(missing_ok=True)
    print(f"  {len(playlists_df):,} playlists")

    tracks_df["date_added"]   = pd.to_datetime(tracks_df["date_added"],   errors="coerce")
    tracks_df["date_removed"] = pd.to_datetime(tracks_df["date_removed"], errors="coerce")

    removed = tracks_df[tracks_df["date_removed"].notna()].copy()
    print(f"  {len(removed):,} removed rows ({100*len(removed)/len(tracks_df):.1f}%)")

    removed["days_on"] = (removed["date_removed"] - removed["date_added"]).dt.days.clip(lower=0).astype("Int64")

    pl_names = playlists_df[["playlist_id", "name"]].rename(columns={"name": "playlist_name"})
    removed = removed.merge(pl_names, on="playlist_id", how="left")

    keep = ["track_name", "artist_name", "playlist_id", "playlist_name",
            "date_added", "date_removed", "days_on"]
    keep = [c for c in keep if c in removed.columns]
    out = removed[keep].copy()

    # Store dates as ISO strings to keep parquet schema simple
    out["date_added"]   = out["date_added"].dt.strftime("%Y-%m-%d")
    out["date_removed"] = out["date_removed"].dt.strftime("%Y-%m-%d")

    out_path = tmp / "editorial_removed.parquet"
    out.to_parquet(out_path, index=False, compression="zstd")
    size_mb = out_path.stat().st_size / 1024**2
    print(f"\nUploading {size_mb:.1f} MB → R2:{R2_KEY} …")
    r2.upload(str(out_path), R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ editorial_removed.parquet: {len(out):,} rows, {size_mb:.1f} MB")
    print("  Update main.py: editorial_graveyard + forgotten_hits → computed/editorial_removed.parquet")


if __name__ == "__main__":
    main()
