"""
Enrich top artists with Last.fm data: listener counts, playcounts, tags, similar artists.

Uses artist.getInfo (no user auth, just API key).
Rate limit: ~5 req/s safe. 10K artists ≈ 35 minutes.

Output: enrichment/artist_lastfm.parquet
Columns:
    artist_name, listeners, playcount, tags (list), similar_artists (list),
    lastfm_url, image_url

Usage:
    python src/compute/compute_lastfm_enrichment.py
    python src/compute/compute_lastfm_enrichment.py --top-n 5000
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR  = Path(tempfile.gettempdir()) / "track2vec_cache"
_LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"
_DELAY      = 0.22   # ~4.5 req/s — safely under the 5/s limit
_CHECKPOINT = 500


def _get_artist_info(session: requests.Session, api_key: str, artist_name: str) -> dict | None:
    params = {
        "method":      "artist.getInfo",
        "artist":      artist_name,
        "api_key":     api_key,
        "format":      "json",
        "autocorrect": 1,
    }
    for attempt in range(3):
        try:
            resp = session.get(_LASTFM_URL, params=params, timeout=10)
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                return None  # artist not found

            a = data.get("artist", {})
            stats = a.get("stats", {})

            tags = [t["name"] for t in (a.get("tags") or {}).get("tag", [])]
            similar = [s["name"] for s in (a.get("similar") or {}).get("artist", [])]

            # Best image: extralarge → large → medium
            images = a.get("image", [])
            image_url = None
            for img in reversed(images):
                if img.get("#text"):
                    image_url = img["#text"]
                    break

            return {
                "artist_name":     artist_name,
                "lastfm_name":     a.get("name", artist_name),
                "listeners":       int(stats.get("listeners", 0)),
                "playcount":       int(stats.get("playcount", 0)),
                "tags":            tags[:10],
                "similar_artists": similar[:10],
                "lastfm_url":      a.get("url"),
                "image_url":       image_url,
            }
        except requests.RequestException:
            time.sleep(2)
    return None


def _save_and_upload(results: list[dict], local_path: Path, r2: R2Client, r2_key: str):
    df = pd.DataFrame(results)
    df.to_parquet(local_path, index=False, compression="zstd")
    size_kb = local_path.stat().st_size / 1024
    print(f"  [checkpoint] {len(df):,} rows ({size_kb:.0f} KB) → uploading...", flush=True)
    r2.upload(local_path, r2_key)
    print(f"  [checkpoint] uploaded", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10_000)
    args = parser.parse_args()

    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] LASTFM_API_KEY not set in .env")
        sys.exit(1)

    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    # Load top-N artists by playlist count
    stats_path = _CACHE_DIR / "computed_artist_stats.parquet"
    if not stats_path.exists():
        print("Downloading artist_stats.parquet...", flush=True)
        r2.download("computed/artist_stats.parquet", stats_path)
    top_artists = pd.read_parquet(stats_path).head(args.top_n)["artist_name"].tolist()
    print(f"Artists to enrich: {len(top_artists):,}", flush=True)

    # Resume from existing partial
    r2_key = "enrichment/artist_lastfm.parquet"
    local_path = _CACHE_DIR / "artist_lastfm.parquet"
    results: list[dict] = []
    done_set: set[str] = set()

    try:
        r2.download(r2_key, local_path)
        existing = pd.read_parquet(local_path)
        results = existing.to_dict("records")
        done_set = {r["artist_name"] for r in results}
        print(f"Resuming: {len(done_set):,} artists already fetched", flush=True)
    except Exception:
        print("Starting fresh", flush=True)

    remaining = [a for a in top_artists if a not in done_set]
    print(f"Remaining: {len(remaining):,}", flush=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "MusicIntelligenceAtlas/1.0"})

    found_listeners = sum(1 for r in results if r.get("listeners", 0) > 0)

    for i, name in enumerate(remaining):
        info = _get_artist_info(session, api_key, name)
        if info:
            results.append(info)
            if info["listeners"] > 0:
                found_listeners += 1
        else:
            results.append({
                "artist_name": name, "lastfm_name": name,
                "listeners": 0, "playcount": 0,
                "tags": [], "similar_artists": [],
                "lastfm_url": None, "image_url": None,
            })

        time.sleep(_DELAY)

        if (i + 1) % 200 == 0:
            total_done = len(done_set) + i + 1
            pct = total_done / len(top_artists) * 100
            print(f"  {total_done:,}/{len(top_artists):,} ({pct:.0f}%) — "
                  f"{found_listeners:,} with listener data", flush=True)

        if (i + 1) % _CHECKPOINT == 0:
            _save_and_upload(results, local_path, r2, r2_key)

    # Final save
    _save_and_upload(results, local_path, r2, r2_key)
    r2.usage_summary()

    found = sum(1 for r in results if r.get("listeners", 0) > 0)
    tagged = sum(1 for r in results if r.get("tags"))
    print(f"\n✓ {len(results):,} artists — {found:,} with listeners, {tagged:,} with tags")


if __name__ == "__main__":
    main()
