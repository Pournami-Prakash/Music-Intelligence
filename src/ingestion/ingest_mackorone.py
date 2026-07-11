"""
Ingest mackorone/spotify-playlist-archive editorial playlists → Parquet → R2.

18,106 curated Spotify playlists scraped 2021–2026 with full track history.
Complements MPD (user playlists 2010-2017) with editorial + temporal signal.

Produces:
  - editorial_playlists.parquet      : playlist metadata
  - editorial_playlist_tracks.parquet: track history with date_added/removed

Track URLs → Spotify URIs: https://open.spotify.com/track/{id} → spotify:track:{id}

Usage:
    python src/ingestion/ingest_mackorone.py
    python src/ingestion/ingest_mackorone.py --skip-upload
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

ARCHIVE_DIR = Path(__file__).parent.parent.parent / "data/raw/spotify-playlist-archive/playlists/cumulative"
R2_KEY_PL   = "processed/editorial_playlists.parquet"
R2_KEY_PT   = "processed/editorial_playlist_tracks.parquet"


def spotify_uri(url: str) -> str:
    """https://open.spotify.com/track/{id} → spotify:track:{id}"""
    return "spotify:track:" + url.rstrip("/").split("/")[-1]


def ingest(skip_upload: bool = False) -> None:
    json_files = sorted(ARCHIVE_DIR.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {ARCHIVE_DIR}")

    print(f"Found {len(json_files):,} editorial playlists in mackorone archive\n")

    pl_rows  = []
    pt_rows  = []
    skipped  = 0

    for path in tqdm(json_files, desc="Parsing playlists", unit="playlist"):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            skipped += 1
            continue

        playlist_url = d.get("url", "")
        playlist_id  = playlist_url.rstrip("/").split("/")[-1] if playlist_url else path.stem

        pl_rows.append({
            "playlist_id":        playlist_id,
            "name":               d.get("name", ""),
            "description":        d.get("description", ""),
            "url":                playlist_url,
            "date_first_scraped": d.get("date_first_scraped", ""),
            "num_tracks":         len(d.get("tracks", [])),
        })

        for track in d.get("tracks", []):
            track_url = track.get("url", "")
            if not track_url:
                continue

            artists = track.get("artists", [])
            artist_name = artists[0]["name"] if artists else ""
            artist_url  = artists[0].get("url", "") if artists else ""
            artist_uri  = "spotify:artist:" + artist_url.rstrip("/").split("/")[-1] if artist_url else ""

            album = track.get("album", {})
            album_name = album.get("name", "") if album else ""
            album_url  = album.get("url", "") if album else ""
            album_uri  = "spotify:album:" + album_url.rstrip("/").split("/")[-1] if album_url else ""

            pt_rows.append({
                "playlist_id":    playlist_id,
                "track_uri":      spotify_uri(track_url),
                "track_name":     track.get("name", ""),
                "artist_name":    artist_name,
                "artist_uri":     artist_uri,
                "album_name":     album_name,
                "album_uri":      album_uri,
                "duration_ms":    track.get("duration_ms", 0),
                "date_added":     track.get("date_added", ""),
                "date_removed":   track.get("date_removed", ""),
                "date_added_asterisk": track.get("date_added_asterisk", False),
            })

    pl_df = pd.DataFrame(pl_rows)
    pt_df = pd.DataFrame(pt_rows)

    print(f"\n{'─'*50}")
    print(f"mackorone ingestion complete")
    print(f"  Playlists      : {len(pl_df):,}  (skipped: {skipped})")
    print(f"  Track entries  : {len(pt_df):,}")
    print(f"  Unique tracks  : {pt_df['track_uri'].nunique():,}")
    print(f"  Unique artists : {pt_df['artist_name'].nunique():,}")
    print(f"  Tracks with date_added   : {pt_df['date_added'].ne('').sum():,}")
    print(f"  Tracks with date_removed : {pt_df['date_removed'].notna().sum():,}")
    print(f"{'─'*50}\n")

    # Validate: drop placeholder rows before writing
    _bad_name  = pt_df["artist_name"].fillna("").str.strip()
    _bad_title = pt_df["track_name"].fillna("").str.strip()
    _placeholders = ((_bad_name == "") | (_bad_name.str.lower() == "artist")) & (_bad_title == "")
    n_placeholder = _placeholders.sum()
    if n_placeholder:
        print(f"  [validate] dropping {n_placeholder:,} placeholder rows (blank artist+title)")
        pt_df = pt_df[~_placeholders].copy()
    _blank_uri = pt_df["track_uri"].fillna("").str.strip() == ""
    if _blank_uri.any():
        print(f"  [validate] dropping {_blank_uri.sum():,} rows with blank track_uri")
        pt_df = pt_df[~_blank_uri].copy()
    blank_pct = (pt_df["artist_name"].fillna("").str.strip() == "").mean() * 100
    if blank_pct > 5.0:
        raise ValueError(f"[validate] {blank_pct:.1f}% of rows still have blank artist_name — check source data")

    # Write to temp parquet
    tmp_pl = Path(tempfile.gettempdir()) / "editorial_playlists.parquet"
    tmp_pt = Path(tempfile.gettempdir()) / "editorial_playlist_tracks.parquet"
    pl_df.to_parquet(tmp_pl, index=False, compression="zstd")
    pt_df.to_parquet(tmp_pt, index=False, compression="zstd")

    print(f"  editorial_playlists.parquet      : {tmp_pl.stat().st_size/1024**2:.1f} MB")
    print(f"  editorial_playlist_tracks.parquet: {tmp_pt.stat().st_size/1024**2:.1f} MB\n")

    if skip_upload:
        print(f"Skipping upload (--skip-upload).")
        return

    r2 = R2Client()
    r2.upload(tmp_pl, R2_KEY_PL, delete_after=True)
    r2.upload(tmp_pt, R2_KEY_PT, delete_after=True)
    r2.usage_summary()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()
    ingest(skip_upload=args.skip_upload)


if __name__ == "__main__":
    main()
