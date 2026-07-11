"""
Patch artist_genres.parquet: fill empty tag rows using the Last.fm API.

Only queries artists whose tags list is empty or None — skips artists
that already have tags. Safe to re-run (idempotent).

Rate limit: Last.fm allows ~5 req/s; we use 0.22s delay (safe at ~4.5 req/s).

Usage:
    python src/compute/patch_artist_genres_lastfm.py --dry-run
    python src/compute/patch_artist_genres_lastfm.py
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP      = Path(tempfile.gettempdir()) / "track2vec_cache"
_DELAY    = 0.22   # ~4.5 req/s, safely under Last.fm 5 req/s limit
_MAX_TAGS = 10
_API_URL  = "https://ws.audioscrobbler.com/2.0/"


def _fetch_tags(artist_name: str, api_key: str) -> list[str]:
    try:
        r = requests.get(_API_URL, params={
            "method":      "artist.gettoptags",
            "artist":      artist_name,
            "api_key":     api_key,
            "format":      "json",
            "autocorrect": 1,
        }, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        tags = data.get("toptags", {}).get("tag", [])
        return [t["name"].lower() for t in tags[:_MAX_TAGS] if int(t.get("count", 0)) > 0]
    except Exception:
        return []


def main(dry_run: bool) -> None:
    api_key = os.environ.get("LASTFM_API_KEY", "")
    if not api_key:
        print("LASTFM_API_KEY not set in .env — aborting.")
        sys.exit(1)

    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)

    print("Downloading artist_genres.parquet …")
    p = _TMP / "artist_genres_patch.parquet"
    p.unlink(missing_ok=True)
    r2.download("enrichment/artist_genres.parquet", str(p))
    ag = pd.read_parquet(p)

    empty_mask = ag["tags"].apply(
        lambda x: x is None or (hasattr(x, "__len__") and len(x) == 0)
    )
    targets = ag[empty_mask].copy()
    print(f"  total rows   : {len(ag):,}")
    print(f"  empty tags   : {len(targets):,}")

    if targets.empty:
        print("Nothing to patch.")
        return

    if dry_run:
        print(f"\n[dry-run] would query Last.fm for {len(targets):,} artists:")
        print(targets["artist_name"].head(10).to_string(index=False))
        return

    filled = 0
    still_empty = 0

    print(f"\nQuerying Last.fm for {len(targets):,} artists …")
    t0 = time.time()
    for idx, row in targets.iterrows():
        tags = _fetch_tags(row["artist_name"], api_key)
        if tags:
            ag.at[idx, "tags"] = tags
            filled += 1
        else:
            still_empty += 1
        time.sleep(_DELAY)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  filled       : {filled:,}")
    print(f"  still empty  : {still_empty:,}  (not in Last.fm)")

    out = _TMP / "artist_genres_patched.parquet"
    ag.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024**2
    print(f"\nUploading {size_mb:.1f} MB → enrichment/artist_genres.parquet …")
    r2.upload(str(out), "enrichment/artist_genres.parquet")
    out.unlink(missing_ok=True)
    print("Done.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
