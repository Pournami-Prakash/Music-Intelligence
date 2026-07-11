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
from src.storage.duckdb_r2 import get_con, R2_PATH

mb.set_useragent("MusicIntelligenceAtlas", "0.1", "https://github.com/music-intelligence-atlas")

R2_KEY_TAGS     = "enrichment/artist_tags.parquet"
R2_KEY_PROGRESS = "enrichment/artist_tags_progress.json"
RATE_LIMIT_SEC  = 1.1  # slightly over 1 sec to stay safe


def get_top_artists(top_n: int) -> pd.DataFrame:
    """Use DuckDB over R2 to aggregate top-N artists by playlist frequency — no full download."""
    con = get_con()
    df = con.execute(f"""
        SELECT
            tr.artist_uri,
            tr.artist_name,
            COUNT(*) AS playlist_appearances
        FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
        JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') tr
            USING (track_uri)
        GROUP BY tr.artist_uri, tr.artist_name
        ORDER BY playlist_appearances DESC
        LIMIT {top_n}
    """).df()
    print(f"Top {top_n} artists selected (covers {df['playlist_appearances'].sum():,} track-playlist rows)")
    return df


def query_artist_tags(artist_name: str) -> list[str]:
    """Query MusicBrainz for an artist and return their genre tags.

    The search response itself often includes tag-list, saving a second API call.
    Falls back to get_artist_by_id only if the search returns no tags.
    Raises on API errors so the caller can log and retry.
    """
    result = mb.search_artists(artist=artist_name, limit=1)
    artists = result.get("artist-list", [])
    if not artists:
        return []

    artist = artists[0]

    # Tags are frequently present in the search result — use them first
    search_tags = artist.get("tag-list", [])
    tags = [t["name"] for t in search_tags if int(t.get("count", 0)) >= 1]
    if tags:
        return tags

    # Fall back to a detail call if search had no tags
    mbid = artist["id"]
    detail = mb.get_artist_by_id(mbid, includes=["tags"])
    detail_tags = detail.get("artist", {}).get("tag-list", [])
    return [t["name"] for t in detail_tags if int(t.get("count", 0)) >= 1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n",  type=int, default=10_000)
    parser.add_argument("--resume", action="store_true", help="Skip already-queried artists")
    parser.add_argument("--retag",  action="store_true", help="Re-query tags for existing artist list (keeps URIs, re-fetches tags)")
    args = parser.parse_args()

    r2 = R2Client()

    if args.retag and r2.exists(R2_KEY_TAGS):
        # Re-use existing artist list without hitting DuckDB again
        tmp = Path(tempfile.gettempdir()) / "tags_retag.parquet"
        r2.download(R2_KEY_TAGS, tmp)
        artists_df = pd.read_parquet(tmp)[["artist_uri", "artist_name"]].copy()
        artists_df["playlist_appearances"] = 0
        tmp.unlink(missing_ok=True)
        print(f"Retag mode: re-querying tags for {len(artists_df):,} existing artists")
    else:
        print(f"Loading top {args.top_n:,} artists from R2 via DuckDB...")
        artists_df = get_top_artists(args.top_n)

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

        try:
            tags = query_artist_tags(name)
        except Exception as e:
            tqdm.write(f"  ⚠ {name}: {e}")
            tags = []
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
