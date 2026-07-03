"""
Enrich MPD artists with genre tags from MusicBrainz API.

Strategy:
  1. Find top N artists by playlist frequency (covers ~85% of playlists)
  2. Query MusicBrainz API at 1 req/sec (rate limit)
  3. Save artist → genre tags mapping to R2

Rate limit: 1 req/sec without commercial license.
Top 10K artists → ~3 hours. Resumable if interrupted.

Usage:
    python src/enrichment/enrich_musicbrainz.py
    python src/enrichment/enrich_musicbrainz.py --top-n 5000
    python src/enrichment/enrich_musicbrainz.py --top-n 10000 --resume
"""

import argparse
import json
import sys
import time
import tempfile
from pathlib import Path

import musicbrainzngs as mb
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

mb.set_useragent("MusicIntelligenceAtlas", "0.1", "https://github.com/music-intelligence-atlas")

R2_KEY_TAGS     = "enrichment/artist_tags.parquet"
R2_KEY_PROGRESS = "enrichment/artist_tags_progress.json"
RATE_LIMIT_SEC  = 1.1  # slightly over 1 sec to stay safe


def get_top_artists(r2: R2Client, top_n: int) -> pd.DataFrame:
    """Load playlist_tracks + tracks from R2, return top-N artists by playlist frequency."""
    tmp_pt = Path(tempfile.gettempdir()) / "pt_tmp.parquet"
    tmp_tr = Path(tempfile.gettempdir()) / "tr_tmp.parquet"

    r2.download("processed/playlist_tracks.parquet", tmp_pt)
    r2.download("processed/tracks.parquet", tmp_tr)

    pt = pd.read_parquet(tmp_pt, columns=["track_uri"])
    tr = pd.read_parquet(tmp_tr, columns=["track_uri", "artist_name", "artist_uri"])

    tmp_pt.unlink(missing_ok=True)
    tmp_tr.unlink(missing_ok=True)

    freq = pt.merge(tr, on="track_uri")
    artist_freq = (
        freq.groupby(["artist_uri", "artist_name"])
        .size()
        .reset_index(name="playlist_appearances")
        .sort_values("playlist_appearances", ascending=False)
        .head(top_n)
    )

    print(f"Top {top_n} artists selected (covers {artist_freq['playlist_appearances'].sum():,} track-playlist rows)")
    return artist_freq


def query_artist_tags(artist_name: str) -> list[str]:
    """Query MusicBrainz for an artist and return their genre tags."""
    try:
        result = mb.search_artists(artist=artist_name, limit=1)
        artists = result.get("artist-list", [])
        if not artists:
            return []

        mbid = artists[0]["id"]
        detail = mb.get_artist_by_id(mbid, includes=["tags", "user-tags"])
        tags = detail.get("artist", {}).get("tag-list", [])
        return [t["name"] for t in tags if int(t.get("count", 0)) >= 1]

    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n",  type=int, default=10_000)
    parser.add_argument("--resume", action="store_true", help="Skip already-queried artists")
    args = parser.parse_args()

    r2 = R2Client()

    print(f"Loading top {args.top_n:,} artists from R2...")
    artists_df = get_top_artists(r2, args.top_n)

    # Load existing results if resuming
    done: dict[str, list[str]] = {}
    if args.resume and r2.exists(R2_KEY_TAGS):
        tmp = Path(tempfile.gettempdir()) / "tags_resume.parquet"
        r2.download(R2_KEY_TAGS, tmp)
        existing = pd.read_parquet(tmp)
        done = dict(zip(existing["artist_uri"], existing["tags"]))
        tmp.unlink(missing_ok=True)
        print(f"Resuming: {len(done):,} artists already done")

    results = []
    skipped = 0

    for _, row in tqdm(artists_df.iterrows(), total=len(artists_df), desc="MusicBrainz enrichment"):
        uri  = row["artist_uri"]
        name = row["artist_name"]

        if uri in done:
            results.append({"artist_uri": uri, "artist_name": name, "tags": done[uri]})
            skipped += 1
            continue

        tags = query_artist_tags(name)
        results.append({"artist_uri": uri, "artist_name": name, "tags": tags})
        time.sleep(RATE_LIMIT_SEC)

        # Checkpoint every 500 artists
        if len(results) % 500 == 0 and len(results) > skipped:
            _save_checkpoint(results, r2)

    _save_checkpoint(results, r2)
    print(f"\nDone. {len(results):,} artists enriched → R2:{R2_KEY_TAGS}")


def _save_checkpoint(results: list[dict], r2: R2Client) -> None:
    df = pd.DataFrame(results)
    tmp = Path(tempfile.gettempdir()) / "artist_tags_checkpoint.parquet"
    df.to_parquet(tmp, index=False)
    r2.upload(tmp, R2_KEY_TAGS)
    tmp.unlink(missing_ok=True)
    print(f"  [checkpoint] {len(results):,} artists saved to R2")


if __name__ == "__main__":
    main()
