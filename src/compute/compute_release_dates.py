"""
Enrich canonical_tracks with release_date + release_year via Deezer track API.

Covers tracks that already have a deezer_id (~300K rows, 8.3% of spine).
No auth required. Deezer public API: GET https://api.deezer.com/track/{id}

Rate limit: ~50 req/s official; we use 20 concurrent workers to stay safe.
Runtime: ~300K tracks / (20 workers × ~10 req/s effective) ≈ 25 min.

Checkpoints every 10K rows so it's resumable with --resume.

Usage:
    python src/compute/compute_release_dates.py --dry-run
    python src/compute/compute_release_dates.py
    python src/compute/compute_release_dates.py --resume   # skip already-fetched rows
"""

import argparse
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR   = Path(tempfile.gettempdir()) / "track2vec_cache"
_CKPT        = _CACHE_DIR / "release_dates_checkpoint.parquet"
_API_BASE    = "https://api.deezer.com/track/{}"
_WORKERS     = 20
_CKPT_EVERY  = 10_000


def _fetch(deezer_id: int) -> tuple[int, str | None]:
    try:
        r = requests.get(_API_BASE.format(int(deezer_id)), timeout=8)
        if r.status_code != 200:
            return deezer_id, None
        data = r.json()
        if "error" in data:
            return deezer_id, None
        return deezer_id, data.get("release_date")  # "YYYY-MM-DD" or None
    except Exception:
        return deezer_id, None


def main(dry_run: bool, resume: bool) -> None:
    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    print("Downloading canonical_tracks …")
    ct_path = _CACHE_DIR / "ct_release.parquet"
    ct_path.unlink(missing_ok=True)
    r2.download("processed/canonical_tracks.parquet", ct_path)
    ct = pd.read_parquet(ct_path)

    targets = ct[ct["deezer_id"].notna()][["spotify_track_uri", "deezer_id"]].copy()
    targets["deezer_id"] = targets["deezer_id"].astype("int64")
    print(f"  tracks with deezer_id : {len(targets):,} / {len(ct):,}")

    # Load checkpoint
    done: dict[int, str | None] = {}
    if resume and _CKPT.exists():
        ckpt = pd.read_parquet(_CKPT)
        done = dict(zip(ckpt["deezer_id"].astype("int64"), ckpt["release_date"]))
        print(f"  resuming — {len(done):,} already fetched")
        targets = targets[~targets["deezer_id"].isin(done)]
        print(f"  remaining            : {len(targets):,}")

    if dry_run:
        print(f"\n[dry-run] would query Deezer for {len(targets):,} tracks ({len(done):,} already done)")
        sample = targets.head(3)["deezer_id"].tolist()
        print(f"  sample deezer_ids: {sample}")
        for did in sample:
            _, rd = _fetch(did)
            print(f"    {did} → {rd}")
        return

    if targets.empty:
        print("Nothing to fetch — all tracks already processed.")
    else:
        print(f"\nFetching release dates for {len(targets):,} tracks ({_WORKERS} workers) …")
        t0 = time.time()
        ids = targets["deezer_id"].tolist()
        batch_done = 0

        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futures = {pool.submit(_fetch, did): did for did in ids}
            for fut in as_completed(futures):
                did, rd = fut.result()
                done[did] = rd
                batch_done += 1
                if batch_done % _CKPT_EVERY == 0:
                    _save_checkpoint(done)
                    elapsed = time.time() - t0
                    rate = batch_done / elapsed
                    remaining = (len(ids) - batch_done) / rate
                    print(f"  {batch_done:,} / {len(ids):,}  ({rate:.0f} req/s)  ETA {remaining/60:.1f} min", flush=True)

        elapsed = time.time() - t0
        print(f"\nDone in {elapsed/60:.1f} min")

    _save_checkpoint(done)
    filled = sum(1 for v in done.values() if v)
    print(f"  filled  : {filled:,} / {len(done):,}  ({100*filled/max(len(done),1):.1f}%)")

    # Merge back into canonical_tracks
    print("\nPatching canonical_tracks …")
    date_map = pd.DataFrame([
        {"deezer_id": int(k), "release_date": v}
        for k, v in done.items() if v
    ])
    # ct["deezer_id"] is stored as string in the parquet; coerce both sides to float64
    date_map["deezer_id"] = date_map["deezer_id"].astype("float64")
    ct["deezer_id"] = pd.to_numeric(ct["deezer_id"], errors="coerce")

    ct = ct.merge(date_map, on="deezer_id", how="left",
                  suffixes=("_old", ""))
    if "release_date_old" in ct.columns:
        ct["release_date"] = ct["release_date"].fillna(ct.pop("release_date_old"))
    ct["release_year"] = pd.to_datetime(
        ct["release_date"], errors="coerce"
    ).dt.year.astype("Int64")

    n_dated = ct["release_date"].notna().sum()
    print(f"  release_date populated: {n_dated:,} / {len(ct):,} ({100*n_dated/len(ct):.1f}%)")
    print(f"  release_year populated: {ct['release_year'].notna().sum():,}")

    out = _CACHE_DIR / "canonical_tracks_dated.parquet"
    ct.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024**2
    print(f"\nUploading {size_mb:.1f} MB → processed/canonical_tracks.parquet …")
    r2.upload(str(out), "processed/canonical_tracks.parquet")
    out.unlink(missing_ok=True)
    print("Done.")


def _save_checkpoint(done: dict) -> None:
    df = pd.DataFrame([{"deezer_id": k, "release_date": v} for k, v in done.items()])
    df.to_parquet(_CKPT, index=False, compression="zstd")
    print(f"  [ckpt] {len(done):,} rows saved to {_CKPT}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume",  action="store_true", help="Skip already-fetched deezer_ids")
    args = p.parse_args()
    main(dry_run=args.dry_run, resume=args.resume)
