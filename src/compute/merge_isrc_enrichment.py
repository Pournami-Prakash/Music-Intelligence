"""
Merge ISRC enrichment from both Spotify and MBDump jobs into:
  - enrichment/listenbrainz_full.parquet  (add new rows)
  - processed/canonical_tracks.parquet   (fill isrc + recording_mbid columns)

Run AFTER both compute_spotify_isrc.py and compute_mbdump_isrc.py finish.

Usage:
    python src/compute/merge_isrc_enrichment.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"


def main():
    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    # ── Load new ISRC batches ──────────────────────────────────────────────
    frames = []
    for key, fname in [
        ("enrichment/spotify_isrc_batch.parquet",  "spotify_isrc_batch.parquet"),
        ("enrichment/mbdump_isrc_match.parquet",   "mbdump_isrc_match.parquet"),
        ("enrichment/deezer_search_isrc.parquet",  "deezer_search_isrc.parquet"),
        ("enrichment/mb_search_isrc.parquet",      "mb_search_isrc.parquet"),
    ]:
        p = _CACHE_DIR / fname
        p.unlink(missing_ok=True)  # always force fresh download; never use stale local cache
        try:
            r2.download(key, p)
        except Exception:
            print(f"  [SKIP] {key} not in R2 yet", flush=True)
            continue
        df = pd.read_parquet(p)
        # normalise column names: track_uri / spotify_track_uri
        if "spotify_track_uri" in df.columns:
            df = df.rename(columns={"spotify_track_uri": "track_uri"})
        needed = ["track_uri", "isrc", "recording_mbid", "listen_count"]
        for col in needed:
            if col not in df.columns:
                df[col] = None
        frames.append(df[needed])
        print(f"  Loaded {fname}: {len(df):,} rows", flush=True)

    if not frames:
        print("No enrichment batches found — run compute_spotify_isrc.py and/or compute_mbdump_isrc.py first")
        return

    new_enrichment = pd.concat(frames, ignore_index=True)
    # Deduplicate: prefer Spotify (first) over MBDump; keep row with higher listen_count if tie
    new_enrichment = (new_enrichment
                      .sort_values("listen_count", ascending=False)
                      .drop_duplicates("track_uri", keep="first"))
    print(f"\nCombined new enrichment: {len(new_enrichment):,} unique tracks", flush=True)

    # ── Update listenbrainz_full.parquet ───────────────────────────────────
    print("\nUpdating listenbrainz_full.parquet...", flush=True)
    lb_path = _CACHE_DIR / "listenbrainz_full.parquet"
    lb_path.unlink(missing_ok=True)
    r2.download("enrichment/listenbrainz_full.parquet", lb_path)
    lb = pd.read_parquet(lb_path)
    lb = lb.rename(columns={"spotify_track_uri": "track_uri"})

    existing_uris = set(lb["track_uri"])
    new_rows = new_enrichment[~new_enrichment["track_uri"].isin(existing_uris)].copy()
    new_rows = new_rows.rename(columns={"track_uri": "spotify_track_uri"})

    lb_updated = pd.concat([
        lb.rename(columns={"track_uri": "spotify_track_uri"}),
        new_rows
    ], ignore_index=True)

    before = (lb["listen_count"] > 0).sum()
    after  = (lb_updated["listen_count"] > 0).sum()
    print(f"  listenbrainz_full: {len(lb):,} → {len(lb_updated):,} rows", flush=True)
    print(f"  tracks with listen_count: {before:,} → {after:,} (+{after-before:,})", flush=True)

    out_lb = _CACHE_DIR / "listenbrainz_full_merged.parquet"
    lb_updated.to_parquet(out_lb, index=False, compression="zstd")
    r2.upload(out_lb, "enrichment/listenbrainz_full.parquet", delete_after=True)

    # ── Update canonical_tracks.parquet ───────────────────────────────────
    print("\nUpdating canonical_tracks.parquet...", flush=True)
    ct_path = _CACHE_DIR / "canonical_tracks.parquet"
    ct_path.unlink(missing_ok=True)
    r2.download("processed/canonical_tracks.parquet", ct_path)
    ct = pd.read_parquet(ct_path)

    before_isrc = ct["isrc"].notna().sum()

    # Vectorized fill: merge new ISRCs then coalesce (existing wins, fills NaN slots)
    isrc_patch = new_enrichment[["track_uri", "isrc", "recording_mbid"]].rename(
        columns={"track_uri": "spotify_track_uri", "isrc": "isrc_new", "recording_mbid": "recording_mbid_new"}
    )
    ct = ct.merge(isrc_patch, on="spotify_track_uri", how="left")
    ct["isrc"] = ct["isrc"].fillna(ct.pop("isrc_new"))
    if "recording_mbid" not in ct.columns:
        ct["recording_mbid"] = None
    ct["recording_mbid"] = ct["recording_mbid"].fillna(ct.pop("recording_mbid_new"))

    after_isrc = ct["isrc"].notna().sum()
    print(f"  canonical_tracks ISRC fill: {before_isrc:,} → {after_isrc:,} (+{after_isrc-before_isrc:,})", flush=True)

    out_ct = _CACHE_DIR / "canonical_tracks_merged.parquet"
    ct.to_parquet(out_ct, index=False, compression="zstd")
    r2.upload(out_ct, "processed/canonical_tracks.parquet", delete_after=True)

    r2.usage_summary()
    print(f"\n✓ merge complete")


if __name__ == "__main__":
    main()
