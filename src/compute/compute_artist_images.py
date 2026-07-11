"""
Fetch artist images using the Deezer public API (no auth, no API key).

GET https://api.deezer.com/search/artist?q={name}&limit=1
  → data[0].picture_xl  (1000×1000px)

~50 req/s allowed. 10K artists in ~3-4 minutes.

Usage:
    python src/compute/compute_artist_images.py
    python src/compute/compute_artist_images.py --top-n 5000
"""

import argparse
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

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"
_DEEZER_BASE = "https://api.deezer.com"
_DELAY = 0.05          # 50ms → ~20 req/s (conservative; Deezer allows ~50)
_MAX_RETRIES = 3


def _deezer_artist_image(session: requests.Session, artist_name: str) -> str | None:
    url = f"{_DEEZER_BASE}/search/artist"
    for attempt in range(_MAX_RETRIES):
        try:
            resp = session.get(url, params={"q": artist_name, "limit": 1}, timeout=10)
            if resp.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            items = resp.json().get("data") or []
            if items:
                # prefer picture_xl, fall back to picture_big / picture
                for key in ("picture_xl", "picture_big", "picture_medium", "picture"):
                    img = items[0].get(key)
                    if img and not img.endswith("images/misc/questions.png"):
                        return img
            return None
        except requests.RequestException:
            time.sleep(1)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10_000)
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Resume from existing partial R2 file (default: on)")
    args = parser.parse_args()

    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    # Load top-N artists from artist_stats
    stats_path = _CACHE_DIR / "computed_artist_stats.parquet"
    if not stats_path.exists():
        print("Downloading artist_stats.parquet...", flush=True)
        r2.download("computed/artist_stats.parquet", stats_path)
    top_artists = pd.read_parquet(stats_path).head(args.top_n)["artist_name"].tolist()
    print(f"Artists to process: {len(top_artists):,}", flush=True)

    # Resume from existing partial
    results: dict[str, str | None] = {}
    partial_path = _CACHE_DIR / "artist_images_r2.parquet"
    r2_key = "computed/artist_images.parquet"

    if args.resume:
        try:
            r2.download(r2_key, partial_path)
            existing = pd.read_parquet(partial_path)
            for _, row in existing.iterrows():
                results[row["artist_name"]] = row.get("image_url")
            print(f"Resuming: {len(results):,} artists already fetched", flush=True)
        except Exception:
            print("No existing partial found — starting fresh", flush=True)

    remaining = [a for a in top_artists if a not in results]
    print(f"Remaining: {len(remaining):,}", flush=True)

    session = requests.Session()
    session.headers.update({"Accept-Language": "en"})

    checkpoint_every = 500
    found = sum(1 for v in results.values() if v)

    for i, name in enumerate(remaining):
        img = _deezer_artist_image(session, name)
        results[name] = img
        if img:
            found += 1
        time.sleep(_DELAY)

        if (i + 1) % 100 == 0:
            pct = found / len(results) * 100
            print(f"  {i+1:,}/{len(remaining):,} — {found:,} with images ({pct:.1f}%)", flush=True)

        # Checkpoint to R2 every N artists
        if (i + 1) % checkpoint_every == 0:
            _save_and_upload(results, top_artists, partial_path, r2, r2_key)

    # Final save
    _save_and_upload(results, top_artists, partial_path, r2, r2_key)
    r2.usage_summary()

    total = len([a for a in top_artists if a in results])
    found_final = sum(1 for a in top_artists if results.get(a))
    print(f"\n✓ Done: {total:,} artists — {found_final:,} with images ({found_final/total*100:.1f}%)")


def _save_and_upload(results, top_artists, local_path, r2, r2_key):
    rows = [{"artist_name": a, "image_url": results.get(a)} for a in top_artists if a in results]
    df = pd.DataFrame(rows)
    df.to_parquet(local_path, index=False, compression="zstd")
    size_kb = local_path.stat().st_size / 1024
    print(f"  [checkpoint] {len(df):,} rows saved ({size_kb:.0f} KB) → uploading...", flush=True)
    r2.upload(local_path, r2_key)
    print(f"  [checkpoint] uploaded to R2", flush=True)


if __name__ == "__main__":
    main()
