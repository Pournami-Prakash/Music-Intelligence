"""
Expand artist_lastfm.parquet to cover all FAISS vocab artists with >= 3 tracks.

The doppelganger endpoint shows tags for similar artists, but currently only
the top-10K artists (from artist_stats) have lastfm data. This script fills the
gap for the remaining ~22K artists that appear in the FAISS embedding space.

Rate limit: ~4.5 req/s → ~22K artists ≈ 1.4 hours.
Appends results to enrichment/artist_lastfm.parquet.

Usage:
    python src/compute/expand_lastfm_faiss.py
    python src/compute/expand_lastfm_faiss.py --min-tracks 5   # only artists with >=5 tracks
    python src/compute/expand_lastfm_faiss.py --limit 1000      # test run
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

_TMP        = Path(tempfile.gettempdir())
_LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"
_DELAY      = 0.22   # ~4.5 req/s
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
                return None
            a      = data.get("artist", {})
            stats  = a.get("stats", {})
            tags   = [t["name"] for t in (a.get("tags") or {}).get("tag", [])]
            similar = [s["name"] for s in (a.get("similar") or {}).get("artist", [])]
            images  = a.get("image", [])
            image_url = next((img["#text"] for img in reversed(images) if img.get("#text")), None)
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


def main(min_tracks: int, limit: int | None) -> None:
    api_key = os.environ.get("LASTFM_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] LASTFM_API_KEY not set in .env")
        sys.exit(1)

    r2 = R2Client()

    # Load FAISS vocab to get all artists
    vocab_path = _TMP / "track2vec_vocab_lfm.parquet"
    if not vocab_path.exists():
        print("Downloading track2vec_vocab.parquet …")
        r2.download("embeddings/track2vec_vocab.parquet", str(vocab_path))
    vocab = pd.read_parquet(vocab_path)
    vocab_counts = vocab.groupby("artist_name").size().reset_index(name="track_count")
    candidates = vocab_counts[vocab_counts["track_count"] >= min_tracks]["artist_name"].tolist()
    print(f"FAISS artists with >= {min_tracks} tracks: {len(candidates):,}")

    # Load existing lastfm to skip already-done artists
    lastfm_path = _TMP / "artist_lastfm_expand.parquet"
    if not lastfm_path.exists():
        print("Downloading existing artist_lastfm.parquet …")
        r2.download("enrichment/artist_lastfm.parquet", str(lastfm_path))
    existing = pd.read_parquet(lastfm_path)
    existing_lower = set(existing["artist_name"].str.lower())
    print(f"Existing lastfm entries: {len(existing):,}")

    # Filter to new artists only
    todo = [a for a in candidates if a.lower() not in existing_lower]
    print(f"New artists to query: {len(todo):,}")

    if limit:
        todo = todo[:limit]
        print(f"--limit {limit}: processing {len(todo):,}")

    if not todo:
        print("Nothing to do — all FAISS artists already in lastfm.")
        return

    session = requests.Session()
    results_new: list[dict] = []
    found = 0
    t0 = time.time()

    for i, artist_name in enumerate(todo):
        time.sleep(_DELAY)
        info = _get_artist_info(session, api_key, artist_name)
        if info:
            results_new.append(info)
            found += 1

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate    = (i + 1) / elapsed
            eta_s   = (len(todo) - i - 1) / rate if rate > 0 else 0
            print(f"  {i+1:,}/{len(todo):,} | found: {found:,} ({100*found/(i+1):.1f}%) "
                  f"| {rate:.1f} req/s | ETA {eta_s/60:.0f}m", flush=True)

        if (i + 1) % _CHECKPOINT == 0 and results_new:
            combined = pd.concat([existing, pd.DataFrame(results_new)], ignore_index=True)
            combined.to_parquet(lastfm_path, index=False, compression="zstd")

    elapsed = time.time() - t0
    print(f"\nDone: {len(todo):,} queried in {elapsed/60:.0f}m | {found:,} found ({100*found/len(todo):.1f}%)")

    if not results_new:
        print("No new data found.")
        return

    combined = pd.concat([existing, pd.DataFrame(results_new)], ignore_index=True)
    combined.to_parquet(lastfm_path, index=False, compression="zstd")
    print(f"artist_lastfm total rows: {len(combined):,}")

    print("Uploading artist_lastfm.parquet …")
    r2.upload(str(lastfm_path), "enrichment/artist_lastfm.parquet")
    print("Done.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min-tracks", type=int, default=3,   help="Min tracks in FAISS vocab to include artist")
    p.add_argument("--limit",      type=int, default=None, help="Process only first N artists (for testing)")
    args = p.parse_args()
    main(min_tracks=args.min_tracks, limit=args.limit)
