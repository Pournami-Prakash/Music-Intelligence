"""
Deduplicate enrichment/deezer_tracks.parquet in R2 using a best-row-wins sort.

Dedup key: spotify_track_uri
Winner priority (descending): matched=True > has_isrc > has_deezer_id

By default writes to a staged key (enrichment/deezer_tracks_deduped.parquet)
so you can inspect before promoting over the canonical key.

Usage:
    # Stage only — inspect before promoting
    python src/compute/dedup_deezer_tracks.py

    # Stage and immediately promote to canonical key
    python src/compute/dedup_deezer_tracks.py --promote

    # Dry-run: show counts only, no uploads
    python src/compute/dedup_deezer_tracks.py --dry-run

    # Promote a previously staged output without re-downloading
    python src/compute/dedup_deezer_tracks.py --promote-only
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

_TMP             = Path(tempfile.gettempdir())
_STAGED_KEY      = "enrichment/deezer_tracks_deduped.parquet"
_CANONICAL_KEY   = "enrichment/deezer_tracks.parquet"
_LOCAL_RAW       = _TMP / "deezer_tracks_dedup_raw.parquet"
_LOCAL_DEDUPED   = _TMP / "deezer_tracks_dedup_out.parquet"


def _audit(df: pd.DataFrame, label: str) -> None:
    uri_col = "spotify_track_uri" if "spotify_track_uri" in df.columns else "track_uri"
    dups = df[uri_col].duplicated().sum()
    n_matched = df["matched"].fillna(False).astype(bool).sum() if "matched" in df.columns else "n/a"
    n_isrc    = df["isrc"].notna().sum() if "isrc" in df.columns else "n/a"
    n_did     = df["deezer_id"].notna().sum() if "deezer_id" in df.columns else "n/a"
    print(f"  {label}:")
    print(f"    rows            : {len(df):,}")
    print(f"    dup {uri_col:17s}: {dups:,}")
    print(f"    matched=True    : {n_matched:,}" if isinstance(n_matched, int) else f"    matched=True    : {n_matched}")
    print(f"    has isrc        : {n_isrc:,}" if isinstance(n_isrc, int) else f"    has isrc        : {n_isrc}")
    print(f"    has deezer_id   : {n_did:,}" if isinstance(n_did, int) else f"    has deezer_id   : {n_did}")


def _dedup(df: pd.DataFrame) -> pd.DataFrame:
    uri_col = "spotify_track_uri" if "spotify_track_uri" in df.columns else "track_uri"

    df = df.copy()
    df["_matched"] = df["matched"].fillna(False).astype(bool).astype(int) \
        if "matched" in df.columns else 0
    df["_has_isrc"] = df["isrc"].notna().astype(int) \
        if "isrc" in df.columns else 0
    df["_has_did"]  = df["deezer_id"].notna().astype(int) \
        if "deezer_id" in df.columns else 0

    out = (df
           .sort_values(["_matched", "_has_isrc", "_has_did"], ascending=False)
           .drop(columns=["_matched", "_has_isrc", "_has_did"])
           .drop_duplicates(subset=[uri_col], keep="first")
           .reset_index(drop=True))
    return out


def main(dry_run: bool, promote: bool, promote_only: bool) -> None:
    r2 = R2Client()

    if not promote_only:
        print(f"Downloading {_CANONICAL_KEY} from R2 …")
        _LOCAL_RAW.unlink(missing_ok=True)
        r2.download(_CANONICAL_KEY, str(_LOCAL_RAW))
        df_raw = pd.read_parquet(_LOCAL_RAW)

        print()
        _audit(df_raw, "before dedup")

        n_before = len(df_raw)
        df_clean = _dedup(df_raw)
        n_after  = len(df_clean)
        n_removed = n_before - n_after

        print()
        _audit(df_clean, "after dedup")
        print(f"\n  removed: {n_removed:,} duplicate rows")

        if n_removed == 0:
            print("\nNo duplicates found — R2 is already clean.")
            if not promote_only:
                return

        if dry_run:
            print("\n[dry-run] skipping all uploads.")
            return

        df_clean.to_parquet(_LOCAL_DEDUPED, index=False, compression="zstd")
        size_mb = _LOCAL_DEDUPED.stat().st_size / 1024**2

        print(f"\nUploading staged output ({size_mb:.1f} MB) → {_STAGED_KEY}")
        r2.upload(str(_LOCAL_DEDUPED), _STAGED_KEY)
        print(f"  staged: {_STAGED_KEY}")

    if promote or promote_only:
        if not _LOCAL_DEDUPED.exists():
            # Fresh shell / process: download staged key from R2 rather than failing
            print(f"  [promote] no local file — downloading staged key from R2 …")
            try:
                r2.download(_STAGED_KEY, str(_LOCAL_DEDUPED))
            except Exception as e:
                print(f"  [ERROR] could not download staged key {_STAGED_KEY}: {e}")
                print("  Run without --promote-only first to stage a deduped output.")
                sys.exit(1)

        print(f"\nPromoting staged → {_CANONICAL_KEY} …")
        r2.upload(str(_LOCAL_DEDUPED), _CANONICAL_KEY)
        print(f"  canonical key updated: {_CANONICAL_KEY}")
    else:
        print(f"\nTo promote to canonical key, re-run with --promote")
        print(f"  python src/compute/dedup_deezer_tracks.py --promote-only")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run",      action="store_true",
                   help="Report counts only; skip all uploads")
    p.add_argument("--promote",      action="store_true",
                   help="After staging, also overwrite the canonical R2 key")
    p.add_argument("--promote-only", action="store_true",
                   help="Skip download/dedup; just promote the last staged output")
    args = p.parse_args()
    main(dry_run=args.dry_run, promote=args.promote, promote_only=args.promote_only)
