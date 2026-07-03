"""
Build canonical_tracks — the identity spine of the atlas.

Phase 1 (this script): MPD-only canonical tracks with normalized names.
Phase 2 (later):       Enrich with Deezer (ISRC, deezer_id), MusicBrainz (mbid),
                       YaMBDa bridge (yambda_item_id) once ID resolution is solved.

Schema:
    canonical_track_id      — stable hash: md5(spotify_track_uri)
    spotify_track_uri       — from MPD
    track_name              — raw from MPD
    artist_name             — raw from MPD
    album_name              — raw from MPD
    duration_ms             — from MPD
    track_name_norm         — lowercased, punctuation stripped
    artist_name_norm        — lowercased, punctuation stripped
    isrc                    — from Deezer API (Phase 2)
    musicbrainz_recording_mbid — from MusicBrainz (Phase 2)
    deezer_id               — from Deezer API (Phase 2)
    yambda_item_id          — from YaMBDa bridge (Phase 3)
    match_method            — how the cross-platform ID was resolved
    match_confidence        — 0.0–1.0, null until enriched
    source_flags            — bitmask: 1=mpd, 2=deezer, 4=musicbrainz, 8=yambda

Usage:
    python src/ingestion/build_canonical_tracks.py
    python src/ingestion/build_canonical_tracks.py --skip-upload
"""

import argparse
import hashlib
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY = "processed/canonical_tracks.parquet"

# source_flags bitmask
FLAG_MPD          = 1
FLAG_DEEZER       = 2
FLAG_MUSICBRAINZ  = 4
FLAG_YAMBDA       = 8


def normalize(s: pd.Series) -> pd.Series:
    """Lowercase, strip punctuation, collapse whitespace."""
    return (
        s.str.lower()
         .str.replace(r"[^\w\s]", "", regex=True)
         .str.replace(r"\s+", " ", regex=True)
         .str.strip()
         .fillna("")
    )


def stable_id(uri: str) -> str:
    """Deterministic canonical ID from Spotify URI."""
    return hashlib.md5(uri.encode()).hexdigest()


def build(skip_upload: bool = False) -> None:
    print("Building canonical_tracks from MPD via DuckDB → R2...\n")

    con = get_con()

    # Pull tracks from R2 via DuckDB — no full pandas download
    print("Fetching tracks from R2...")
    df = con.execute(f"""
        SELECT
            track_uri,
            track_name,
            artist_name,
            album_name,
            duration_ms
        FROM read_parquet('{R2_PATH}/processed/tracks.parquet')
    """).df()

    print(f"  {len(df):,} tracks loaded")

    # Canonical ID
    df["canonical_track_id"] = df["track_uri"].apply(stable_id)

    # Rename
    df = df.rename(columns={"track_uri": "spotify_track_uri"})

    # Normalized columns
    df["track_name_norm"]  = normalize(df["track_name"])
    df["artist_name_norm"] = normalize(df["artist_name"])

    # Placeholder columns for Phase 2 enrichment
    df["isrc"]                       = None
    df["musicbrainz_recording_mbid"] = None
    df["deezer_id"]                  = None
    df["yambda_item_id"]             = None
    df["match_method"]               = "mpd_only"
    df["match_confidence"]           = None
    df["source_flags"]               = FLAG_MPD

    # Column order
    df = df[[
        "canonical_track_id",
        "spotify_track_uri",
        "track_name",
        "artist_name",
        "album_name",
        "duration_ms",
        "track_name_norm",
        "artist_name_norm",
        "isrc",
        "musicbrainz_recording_mbid",
        "deezer_id",
        "yambda_item_id",
        "match_method",
        "match_confidence",
        "source_flags",
    ]]

    print(f"\nCanonical tracks built: {len(df):,} rows")
    print(f"  Sample IDs:")
    print(df[["canonical_track_id", "spotify_track_uri", "artist_name_norm", "track_name_norm"]].head(5).to_string(index=False))

    # Validate no duplicate canonical IDs
    dupes = df["canonical_track_id"].duplicated().sum()
    if dupes > 0:
        print(f"\n  ⚠ {dupes:,} duplicate canonical IDs — check hash function")
    else:
        print(f"\n  ✓ No duplicate canonical IDs")

    # Save and upload
    tmp = Path(tempfile.gettempdir()) / "canonical_tracks.parquet"
    df.to_parquet(tmp, index=False, compression="zstd")
    size_mb = tmp.stat().st_size / 1024**2
    print(f"  Size: {size_mb:.1f} MB")

    if skip_upload:
        print(f"\nSkipping upload (--skip-upload). File at: {tmp}")
        return

    r2 = R2Client()
    r2.upload(tmp, R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\ncanonical_tracks written to R2:{R2_KEY}")
    print("Next: enrich with Deezer (ISRC) and MusicBrainz (MBID) — see src/enrichment/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()
    build(skip_upload=args.skip_upload)


if __name__ == "__main__":
    main()
