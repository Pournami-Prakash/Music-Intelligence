"""
Promote recording_mbid + listen_count into canonical_tracks, and add quality flags.

The enrichment data (ListenBrainz, MusicBrainz ISRC search) lives in side tables.
This script joins them into the canonical_tracks spine and writes quality signals:

  recording_mbid  — from listenbrainz_full (primary) + local mb_search_isrc checkpoint
  listen_count    — from listenbrainz_full
  has_isrc        — bool: ISRC is populated
  has_mbid        — bool: recording_mbid is populated
  metadata_complete — bool: artist_name, track_name, isrc all non-empty

Also writes computed/data_manifest.json with row counts and coverage stats
so /api/stats can return live numbers.

Run after all ISRC jobs finish and merge_isrc_enrichment.py has been run.
Safe to run at any time — reads R2, writes R2, does not depend on local state.

Usage:
    python src/compute/promote_mbid_canonical.py
    python src/compute/promote_mbid_canonical.py --dry-run   # compute only, no upload
"""

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP   = Path(tempfile.gettempdir()) / "track2vec_cache"
_CKPT  = Path(tempfile.gettempdir()) / "mb_search_isrc_checkpoint.parquet"


def _download_fresh(r2: R2Client, r2_key: str, local_name: str) -> Path:
    """Always re-download from R2 (bypass local cache)."""
    p = _TMP / local_name
    p.unlink(missing_ok=True)
    r2.download(r2_key, str(p))
    return p


def main(dry_run: bool) -> None:
    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)
    t0 = time.time()

    # ── Load canonical_tracks (always fresh from R2) ──────────────────────────
    print("Downloading canonical_tracks …")
    ct_path = _download_fresh(r2, "processed/canonical_tracks.parquet", "ct_promote.parquet")
    ct = pd.read_parquet(ct_path)
    print(f"  canonical_tracks: {len(ct):,} rows, columns: {list(ct.columns)}")

    # Ensure required columns exist
    for col in ("recording_mbid", "listen_count"):
        if col not in ct.columns:
            ct[col] = None

    # ── Source 1: listenbrainz_full ───────────────────────────────────────────
    print("\nDownloading listenbrainz_full …")
    try:
        lb_path = _download_fresh(r2, "enrichment/listenbrainz_full.parquet", "lb_promote.parquet")
        lb = pd.read_parquet(lb_path)
        lb = lb.rename(columns={"spotify_track_uri": "track_uri"})
        # Normalize column names across LB schema variants
        if "track_uri" not in lb.columns and "spotify_track_uri" in lb.columns:
            lb = lb.rename(columns={"spotify_track_uri": "track_uri"})
        lb_uri = lb[["track_uri", "recording_mbid", "listen_count"]].copy()
        lb_uri = lb_uri[lb_uri["track_uri"].notna()].drop_duplicates("track_uri")
        print(f"  listenbrainz_full: {len(lb_uri):,} rows with spotify_track_uri")
        print(f"    recording_mbid filled: {lb_uri['recording_mbid'].notna().sum():,}")
        print(f"    listen_count    filled: {lb_uri['listen_count'].notna().sum():,}")
    except Exception as e:
        print(f"  [SKIP] listenbrainz_full unavailable: {e}")
        lb_uri = pd.DataFrame(columns=["track_uri", "recording_mbid", "listen_count"])

    # ── Source 2: mb_search_isrc local checkpoint ─────────────────────────────
    # The R2 copy (enrichment/mb_search_isrc.parquet) no longer exists;
    # the local checkpoint is the only remaining source.
    print("\nLoading mb_search_isrc checkpoint …")
    mb_uri = pd.DataFrame(columns=["track_uri", "recording_mbid"])
    if _CKPT.exists():
        ckpt = pd.read_parquet(_CKPT)
        if "recording_mbid" in ckpt.columns:
            mb_uri = ckpt[["track_uri", "recording_mbid"]].dropna(subset=["recording_mbid"])
            mb_uri = mb_uri.drop_duplicates("track_uri")
            print(f"  mb_search_isrc checkpoint: {len(mb_uri):,} rows with recording_mbid")
    else:
        print("  [SKIP] no local mb_search_isrc checkpoint found")

    # ── Merge recording_mbid into canonical_tracks ────────────────────────────
    print("\nMerging recording_mbid …")
    before_mbid = ct["recording_mbid"].notna().sum()

    # Step 1: fill from LB by spotify_track_uri
    ct = ct.merge(
        lb_uri[["track_uri", "recording_mbid", "listen_count"]].rename(
            columns={"track_uri": "spotify_track_uri",
                     "recording_mbid": "_mbid_lb",
                     "listen_count":   "_lc_lb"}
        ),
        on="spotify_track_uri", how="left"
    )
    ct["recording_mbid"] = ct["recording_mbid"].fillna(ct.pop("_mbid_lb"))
    ct["listen_count"]   = ct["listen_count"].fillna(ct.pop("_lc_lb"))

    # Step 2: fill remaining gaps from mb_search_isrc by spotify_track_uri
    ct = ct.merge(
        mb_uri.rename(columns={"track_uri": "spotify_track_uri", "recording_mbid": "_mbid_mb"}),
        on="spotify_track_uri", how="left"
    )
    ct["recording_mbid"] = ct["recording_mbid"].fillna(ct.pop("_mbid_mb"))

    after_mbid = ct["recording_mbid"].notna().sum()
    after_lc   = ct["listen_count"].notna().sum()
    print(f"  recording_mbid: {before_mbid:,} → {after_mbid:,} (+{after_mbid - before_mbid:,})")
    print(f"  listen_count  :          → {after_lc:,} tracks with listen data")

    # ── Quality flags ─────────────────────────────────────────────────────────
    print("\nAdding quality flags …")
    ct["has_isrc"] = ct["isrc"].notna() & (ct["isrc"].fillna("") != "")
    ct["has_mbid"] = ct["recording_mbid"].notna() & (ct["recording_mbid"].fillna("") != "")
    ct["metadata_complete"] = (
        ct["track_name"].fillna("").str.strip().ne("") &
        ct["artist_name"].fillna("").str.strip().ne("") &
        ct["has_isrc"]
    )
    print(f"  has_isrc           : {ct['has_isrc'].sum():,} / {len(ct):,} ({100*ct['has_isrc'].mean():.1f}%)")
    print(f"  has_mbid           : {ct['has_mbid'].sum():,} / {len(ct):,} ({100*ct['has_mbid'].mean():.1f}%)")
    print(f"  metadata_complete  : {ct['metadata_complete'].sum():,} / {len(ct):,} ({100*ct['metadata_complete'].mean():.1f}%)")

    # ── Build data manifest ───────────────────────────────────────────────────
    print("\nBuilding data manifest …")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s":    round(time.time() - t0, 1),
        "canonical_tracks": {
            "rows":               len(ct),
            "has_isrc":           int(ct["has_isrc"].sum()),
            "has_isrc_pct":       round(100 * ct["has_isrc"].mean(), 2),
            "has_mbid":           int(ct["has_mbid"].sum()),
            "has_mbid_pct":       round(100 * ct["has_mbid"].mean(), 2),
            "has_deezer":         int(ct["deezer_id"].notna().sum()),
            "has_listen_count":   int(after_lc),
            "metadata_complete":  int(ct["metadata_complete"].sum()),
            "metadata_complete_pct": round(100 * ct["metadata_complete"].mean(), 2),
        },
    }

    # Read artist_stats for manifest (force fresh — don't use stale local cache)
    try:
        ast_path = _download_fresh(r2, "computed/artist_stats.parquet", "artist_stats.parquet")
        ast = pd.read_parquet(ast_path)
        manifest["artist_stats"] = {
            "rows": len(ast),
            "top_artist": ast.iloc[0]["artist_name"] if len(ast) else None,
        }
    except Exception as e:
        print(f"  [WARN] artist_stats unavailable: {e}")

    # Read editorial_playlists for manifest (force fresh)
    try:
        ep_path  = _download_fresh(r2, "processed/editorial_playlists.parquet",        "editorial_playlists.parquet")
        ept_path = _download_fresh(r2, "processed/editorial_playlist_tracks.parquet",  "editorial_playlist_tracks.parquet")
        ep  = pd.read_parquet(ep_path)
        ept = pd.read_parquet(ept_path)
        manifest["editorial"] = {
            "playlists":    len(ep),
            "track_rows":   len(ept),
            "unique_tracks": ept["track_uri"].nunique() if "track_uri" in ept.columns else None,
        }
    except Exception as e:
        print(f"  [WARN] editorial data unavailable: {e}")

    manifest["mpd"] = {
        "playlists":           1_000_000,
        "playlist_track_rows": 66_346_428,
    }

    print(f"  manifest: {json.dumps(manifest, indent=2)[:400]} …")

    if dry_run:
        print("\n[dry-run] skipping upload.")
        return

    # ── Upload canonical_tracks ───────────────────────────────────────────────
    print("\nUploading canonical_tracks …")
    out_ct = _TMP / "canonical_tracks_promoted.parquet"
    ct.to_parquet(out_ct, index=False, compression="zstd")
    size_mb = out_ct.stat().st_size / 1024 ** 2
    print(f"  size: {size_mb:.1f} MB")
    r2.upload(str(out_ct), "processed/canonical_tracks.parquet")
    out_ct.unlink(missing_ok=True)

    # ── Upload data manifest ──────────────────────────────────────────────────
    print("Uploading data_manifest.json …")
    manifest_path = _TMP / "data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    r2.upload(str(manifest_path), "computed/data_manifest.json")
    manifest_path.unlink(missing_ok=True)

    r2.usage_summary()
    elapsed = time.time() - t0
    print(f"\n✓ promote_mbid_canonical done in {elapsed/60:.1f}m")
    print(f"  recording_mbid coverage: {after_mbid:,} / {len(ct):,} ({100*after_mbid/len(ct):.1f}%)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Compute only, skip upload")
    args = p.parse_args()
    main(dry_run=args.dry_run)
