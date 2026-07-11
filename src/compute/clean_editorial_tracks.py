"""
Filter bad rows out of editorial_playlist_tracks.parquet in R2 and re-upload.

Removes:
  - rows where artist_name is blank or the literal string "artist"
    AND track_name is blank (ingestion placeholder rows)
  - rows where track_uri is blank (unresolvable tracks)

Reports counts before and after so you can audit the cleanup.

Safe to run multiple times (idempotent).

Usage:
    python src/compute/clean_editorial_tracks.py
    python src/compute/clean_editorial_tracks.py --dry-run
"""

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP = Path(tempfile.gettempdir()) / "track2vec_cache"


def main(dry_run: bool) -> None:
    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)

    print("Downloading editorial_playlist_tracks …")
    p = _TMP / "editorial_playlist_tracks_clean.parquet"
    p.unlink(missing_ok=True)
    r2.download("processed/editorial_playlist_tracks.parquet", str(p))
    ept = pd.read_parquet(p)

    n_before = len(ept)
    print(f"  rows before: {n_before:,}")
    print(f"  unique playlists: {ept['playlist_id'].nunique() if 'playlist_id' in ept.columns else '?':,}")
    print(f"  unique track URIs: {ept['track_uri'].nunique() if 'track_uri' in ept.columns else '?':,}")

    # Audit blanks before filtering
    bad_name  = ept["artist_name"].fillna("").str.strip()
    bad_title = ept["track_name"].fillna("").str.strip()
    bad_uri   = ept["track_uri"].fillna("").str.strip() if "track_uri" in ept.columns else pd.Series([""] * len(ept))

    n_blank_artist = (bad_name == "").sum()
    n_placeholder  = (bad_name.str.lower() == "artist").sum()
    n_blank_title  = (bad_title == "").sum()
    n_blank_uri    = (bad_uri == "").sum()

    print(f"\n  blank artist_name  : {n_blank_artist:,}")
    print(f"  'artist' placeholder: {n_placeholder:,}")
    print(f"  blank track_name   : {n_blank_title:,}")
    print(f"  blank track_uri    : {n_blank_uri:,}")

    # Filter: remove rows where (empty/placeholder artist AND empty title) OR empty URI
    mask_bad_meta = ((bad_name == "") | (bad_name.str.lower() == "artist")) & (bad_title == "")
    mask_bad_uri  = bad_uri == ""
    mask_drop     = mask_bad_meta | mask_bad_uri

    n_drop = mask_drop.sum()
    print(f"\n  rows to drop: {n_drop:,}")

    ept_clean = ept[~mask_drop].copy()
    n_after = len(ept_clean)
    print(f"  rows after : {n_after:,}")
    print(f"  net removed: {n_before - n_after:,} ({100*(n_before-n_after)/max(n_before,1):.2f}%)")

    if n_drop == 0:
        print("\nNo bad rows found — R2 is already clean.")
        return

    if dry_run:
        print("\n[dry-run] skipping upload.")
        return

    out = _TMP / "editorial_playlist_tracks_cleaned.parquet"
    ept_clean.to_parquet(out, index=False, compression="zstd")
    print(f"\nUploading {out.stat().st_size/1024**2:.1f} MB …")
    r2.upload(str(out), "processed/editorial_playlist_tracks.parquet")
    out.unlink(missing_ok=True)
    print("Done.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
