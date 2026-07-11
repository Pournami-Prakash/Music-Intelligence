"""
Build canonical_tracks — the identity spine of the atlas.

Run this ONCE after all enrichment sources are ready (Deezer at minimum).
Do not run incrementally — always rebuild the full table clean.

Schema:
    canonical_track_id      md5(spotify_track_uri)
    spotify_track_uri
    track_name              raw (best available: MPD → editorial)
    artist_name
    album_name
    duration_ms
    track_name_norm         lowercased, punctuation stripped
    artist_name_norm
    isrc                    from Deezer enrichment
    deezer_id               from Deezer enrichment
    yambda_item_id          null until YaMBDa bridge resolved
    match_method            mpd_only | editorial_only | mpd+editorial
    source_flags            bitmask (see FLAGS below)

source_flags bitmask — powers of 2, no reuse:
    1   mpd
    2   deezer (matched + ISRC/ID filled)
    4   editorial (mackorone)
    8   musicbrainz  (reserved — kept in artist_genres.parquet, not here)
    16  yambda       (reserved — bridge not yet built)

Examples:
    1   MPD only
    4   editorial only
    5   MPD + editorial
    3   MPD + Deezer
    7   MPD + editorial + Deezer

Note: MusicBrainz genre tags live in artist_genres.parquet (artist-level),
not embedded here. canonical_tracks is identity-focused only.

Usage:
    python src/ingestion/build_canonical_tracks.py
    python src/ingestion/build_canonical_tracks.py --skip-upload  # dry run
    python src/ingestion/build_canonical_tracks.py --validate-only
"""

import argparse
import hashlib
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
R2_KEY_DEEZER = "enrichment/deezer_tracks.parquet"

# source_flags — powers of 2, never reuse a value
FLAG_MPD        = 1
FLAG_DEEZER     = 2
FLAG_EDITORIAL  = 4
FLAG_MUSICBRAINZ = 8   # reserved — lives in artist_genres.parquet
FLAG_YAMBDA     = 16   # reserved — bridge not yet built


def normalize(s: pd.Series) -> pd.Series:
    return (
        s.str.lower()
         .str.replace(r"[^\w\s]", "", regex=True)
         .str.replace(r"\s+", " ", regex=True)
         .str.strip()
         .fillna("")
    )


def stable_id(uri: str) -> str:
    return hashlib.md5(uri.encode()).hexdigest()


def load_mpd_tracks(con) -> pd.DataFrame:
    print("  Loading MPD tracks from R2...")
    df = con.execute(f"""
        SELECT DISTINCT
            track_uri       AS spotify_track_uri,
            track_name,
            artist_name,
            album_name,
            duration_ms
        FROM read_parquet('{R2_PATH}/processed/tracks.parquet')
    """).df()
    df["_src_mpd"] = True
    print(f"    {len(df):,} unique tracks from MPD")
    return df


def load_editorial_tracks(con) -> pd.DataFrame:
    print("  Loading editorial tracks from R2...")
    df = con.execute(f"""
        SELECT DISTINCT
            track_uri       AS spotify_track_uri,
            track_name,
            artist_name,
            album_name,
            duration_ms
        FROM read_parquet('{R2_PATH}/processed/editorial_playlist_tracks.parquet')
        WHERE track_uri IS NOT NULL
    """).df()
    df.drop_duplicates(subset="spotify_track_uri", keep="first", inplace=True)
    df["_src_editorial"] = True
    print(f"    {len(df):,} unique tracks from editorial playlists")
    return df


DEEZER_EXPECTED_ROWS = 50_000  # matches --top-n in enrich_deezer.py

def load_deezer_enrichment(r2: R2Client, allow_partial: bool = False) -> pd.DataFrame | None:
    if not r2.exists(R2_KEY_DEEZER):
        print("  No Deezer enrichment found — skipping (ISRC/deezer_id will be null)")
        return None
    tmp = Path(tempfile.gettempdir()) / "deezer_enrich.parquet"
    r2.download(R2_KEY_DEEZER, tmp)
    df = pd.read_parquet(tmp)[["spotify_track_uri", "deezer_id", "isrc", "matched"]]
    tmp.unlink(missing_ok=True)

    if len(df) < DEEZER_EXPECTED_ROWS:
        pct = len(df) / DEEZER_EXPECTED_ROWS * 100
        msg = f"  ⚠ Deezer file has {len(df):,} rows — expected {DEEZER_EXPECTED_ROWS:,} ({pct:.0f}% complete). Looks like a checkpoint, not a finished run."
        if allow_partial:
            print(msg + " Proceeding anyway (--allow-partial-deezer).")
        else:
            print(msg)
            raise RuntimeError("Deezer enrichment incomplete. Wait for the run to finish, or pass --allow-partial-deezer to use what's available.")

    matched = df["matched"].sum()
    has_isrc = (df["isrc"].str.len() > 0).sum()
    print(f"  Deezer enrichment: {len(df):,} tracks, {matched:,} matched ({matched/len(df)*100:.1f}%), {has_isrc:,} with ISRC")
    return df


def build(skip_upload: bool = False, validate_only: bool = False, allow_partial_deezer: bool = False) -> None:
    print("Building canonical_tracks (MPD + editorial + Deezer)...\n")
    r2 = R2Client()
    con = get_con()

    # 1. Load both track sources
    mpd = load_mpd_tracks(con)
    editorial = load_editorial_tracks(con)

    # 2. Union on spotify_track_uri — MPD metadata wins on conflict
    print("\n  Merging MPD + editorial...")
    merged = pd.merge(
        mpd, editorial,
        on="spotify_track_uri",
        how="outer",
        suffixes=("_mpd", "_edit"),
    )
    # Prefer MPD metadata where available
    for col in ["track_name", "artist_name", "album_name", "duration_ms"]:
        mpd_col  = f"{col}_mpd"
        edit_col = f"{col}_edit"
        if mpd_col in merged.columns:
            merged[col] = merged[mpd_col].combine_first(merged[edit_col])
            merged.drop(columns=[mpd_col, edit_col], inplace=True)

    merged["_src_mpd"]       = merged["_src_mpd"].fillna(False)
    merged["_src_editorial"] = merged["_src_editorial"].fillna(False)

    mpd_only  = (merged["_src_mpd"] & ~merged["_src_editorial"]).sum()
    edit_only = (~merged["_src_mpd"] & merged["_src_editorial"]).sum()
    both      = (merged["_src_mpd"] & merged["_src_editorial"]).sum()
    print(f"    MPD-only: {mpd_only:,}  editorial-only: {edit_only:,}  both: {both:,}  total: {len(merged):,}")

    # 3. source_flags
    merged["source_flags"] = (
        merged["_src_mpd"].astype(int) * FLAG_MPD +
        merged["_src_editorial"].astype(int) * FLAG_EDITORIAL
    )
    merged.drop(columns=["_src_mpd", "_src_editorial"], inplace=True)

    # 4. Canonical ID + normalized columns
    merged["canonical_track_id"] = merged["spotify_track_uri"].apply(stable_id)
    merged["track_name_norm"]    = normalize(merged["track_name"].fillna(""))
    merged["artist_name_norm"]   = normalize(merged["artist_name"].fillna(""))
    merged["match_method"] = "mpd_only"
    mask_edit_only = merged["source_flags"] == FLAG_EDITORIAL
    mask_both      = merged["source_flags"] == (FLAG_MPD | FLAG_EDITORIAL)
    merged.loc[mask_edit_only, "match_method"] = "editorial_only"
    merged.loc[mask_both,      "match_method"] = "mpd+editorial"

    # 5. Merge Deezer enrichment
    merged["isrc"]      = None
    merged["deezer_id"] = None
    print()
    deezer = load_deezer_enrichment(r2, allow_partial=allow_partial_deezer)
    if deezer is not None:
        deezer_matched = deezer[deezer["matched"]].copy()
        deezer_matched["isrc"]      = deezer_matched["isrc"].replace("", None)
        deezer_matched["deezer_id"] = deezer_matched["deezer_id"].replace("", None)
        merged = merged.merge(
            deezer_matched[["spotify_track_uri", "isrc", "deezer_id"]],
            on="spotify_track_uri",
            how="left",
            suffixes=("", "_dz"),
        )
        merged["isrc"]      = merged["isrc_dz"].combine_first(merged["isrc"])
        merged["deezer_id"] = merged["deezer_id_dz"].combine_first(merged["deezer_id"])
        merged.drop(columns=["isrc_dz", "deezer_id_dz"], errors="ignore", inplace=True)
        # OR deezer flag where matched
        deezer_uris = set(deezer_matched["spotify_track_uri"])
        merged.loc[merged["spotify_track_uri"].isin(deezer_uris), "source_flags"] |= FLAG_DEEZER

    # 6. Reserved columns
    merged["yambda_item_id"] = None

    # 7. Final column order
    merged = merged[[
        "canonical_track_id",
        "spotify_track_uri",
        "track_name",
        "artist_name",
        "album_name",
        "duration_ms",
        "track_name_norm",
        "artist_name_norm",
        "isrc",
        "deezer_id",
        "yambda_item_id",
        "match_method",
        "source_flags",
    ]]

    # 8. Validation report
    print("\n--- Canonical Tracks Validation ---")
    print(f"  Total rows:               {len(merged):,}")
    print(f"  MPD-only      (flags=1):  {(merged['source_flags'] == 1).sum():,}")
    print(f"  Editorial-only (flags=4): {(merged['source_flags'] == 4).sum():,}")
    print(f"  Both          (flags=5):  {(merged['source_flags'] == 5).sum():,}")
    print(f"  Deezer matched (flag&2):  {(merged['source_flags'] & FLAG_DEEZER > 0).sum():,}")
    isrc_count = merged['isrc'].notna().sum()
    print(f"  ISRC filled:              {isrc_count:,} ({isrc_count/len(merged)*100:.1f}%)")
    deezer_count = merged['deezer_id'].notna().sum()
    print(f"  Deezer ID filled:         {deezer_count:,} ({deezer_count/len(merged)*100:.1f}%)")
    dup_uri  = merged["spotify_track_uri"].duplicated().sum()
    dup_id   = merged["canonical_track_id"].duplicated().sum()
    dup_isrc = merged["isrc"].dropna().duplicated().sum()
    null_artist = merged["artist_name"].isna().sum()
    null_title  = merged["track_name"].isna().sum()
    print(f"  Duplicate spotify_uri:    {dup_uri:,}  {'✓' if dup_uri == 0 else '⚠ PROBLEM'}")
    print(f"  Duplicate canonical_id:   {dup_id:,}  {'✓' if dup_id == 0 else '⚠ PROBLEM'}")
    print(f"  Duplicate ISRC:           {dup_isrc:,}  (expected — same recording, diff versions)")
    print(f"  Null artist_name:         {null_artist:,}")
    print(f"  Null track_name:          {null_title:,}")

    if dup_uri > 0 or dup_id > 0:
        print("\n  ⚠ Duplicate URIs/IDs found — do not upload until resolved")
        if validate_only:
            return
        raise ValueError("Duplicate canonical IDs — aborting upload")

    print("\n  ✓ Validation passed")

    if validate_only:
        print("  (--validate-only: skipping write)")
        return

    # 9. Save and upload
    tmp = Path(tempfile.gettempdir()) / "canonical_tracks_v2.parquet"
    merged.to_parquet(tmp, index=False, compression="zstd")
    size_mb = tmp.stat().st_size / 1024**2
    print(f"\n  Size: {size_mb:.1f} MB")

    if skip_upload:
        print(f"  (--skip-upload: file at {tmp})")
        return

    r2.upload(tmp, R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ canonical_tracks written to R2:{R2_KEY}")
    print("  Next: train track2vec on 66M co-occurrences (src/embeddings/train_track2vec.py)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-upload",          action="store_true")
    parser.add_argument("--validate-only",         action="store_true")
    parser.add_argument("--allow-partial-deezer", action="store_true",
                        help="Proceed even if Deezer enrichment looks like a checkpoint")
    args = parser.parse_args()
    build(
        skip_upload=args.skip_upload,
        validate_only=args.validate_only,
        allow_partial_deezer=args.allow_partial_deezer,
    )


if __name__ == "__main__":
    main()
