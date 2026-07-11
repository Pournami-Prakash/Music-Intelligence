"""
Enrich canonical_tracks with Deezer IDs and ISRCs.

Strategy:
  1. Pull top-N tracks by playlist frequency via DuckDB over R2
  2. Search Deezer public API by (artist_name, track_name) — no auth required
  3. Extract deezer_id + isrc
  4. Write results to R2:enrichment/deezer_tracks.parquet
  5. A separate join step will merge back into canonical_tracks

Deezer public API: ~50 req/sec allowed, no key needed.
Top 50K tracks covers ~85% of all playlist co-occurrences.

Usage:
    python src/enrichment/enrich_deezer.py
    python src/enrichment/enrich_deezer.py --top-n 10000
    python src/enrichment/enrich_deezer.py --top-n 50000 --resume
"""

import argparse
import sys
import time
import tempfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client
from src.storage.duckdb_r2 import get_con, R2_PATH

R2_KEY_OUT     = "enrichment/deezer_tracks.parquet"
DEEZER_SEARCH  = "https://api.deezer.com/search"
RATE_LIMIT_SEC = 0.06   # ~16 req/sec — well under 50/sec limit
CHECKPOINT_N   = 1_000
SESSION        = requests.Session()
SESSION.headers["User-Agent"] = "MusicIntelligenceAtlas/0.1"


def get_top_tracks(top_n: int) -> pd.DataFrame:
    """Top-N tracks by playlist frequency, with normalized names for matching."""
    con = get_con()
    df = con.execute(f"""
        SELECT
            ct.spotify_track_uri,
            ct.track_name,
            ct.artist_name,
            ct.track_name_norm,
            ct.artist_name_norm,
            COUNT(pt.track_uri) AS playlist_appearances
        FROM read_parquet('{R2_PATH}/processed/canonical_tracks.parquet') ct
        JOIN read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
            ON ct.spotify_track_uri = pt.track_uri
        GROUP BY
            ct.spotify_track_uri, ct.track_name, ct.artist_name,
            ct.track_name_norm, ct.artist_name_norm
        ORDER BY playlist_appearances DESC
        LIMIT {top_n}
    """).df()
    print(f"Top {top_n:,} tracks selected (covers {df['playlist_appearances'].sum():,} track-playlist rows)")
    return df


def search_deezer(artist: str, track: str) -> dict | None:
    """Search Deezer for a track. Returns dict with deezer_id and isrc, or None."""
    try:
        q = f'artist:"{artist}" track:"{track}"'
        resp = SESSION.get(DEEZER_SEARCH, params={"q": q, "limit": 1}, timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if not data:
            # Fallback: plain text search
            resp2 = SESSION.get(DEEZER_SEARCH, params={"q": f"{artist} {track}", "limit": 1}, timeout=5)
            if resp2.status_code != 200:
                return None
            data = resp2.json().get("data", [])
        if not data:
            return None
        hit = data[0]
        return {
            "deezer_id": str(hit.get("id", "")),
            "isrc":      hit.get("isrc", ""),
            "deezer_title":  hit.get("title", ""),
            "deezer_artist": hit.get("artist", {}).get("name", ""),
        }
    except Exception:
        return None


def _save_checkpoint(results: list[dict], r2: R2Client) -> None:
    df = pd.DataFrame(results)
    tmp = Path(tempfile.gettempdir()) / "deezer_checkpoint.parquet"
    df.to_parquet(tmp, index=False, compression="zstd")
    r2.upload(tmp, R2_KEY_OUT)
    tmp.unlink(missing_ok=True)
    print(f"  [checkpoint] {len(results):,} tracks saved → R2:{R2_KEY_OUT}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n",  type=int, default=50_000)
    parser.add_argument("--resume", action="store_true", help="Skip already-searched tracks")
    args = parser.parse_args()

    r2 = R2Client()

    print(f"Loading top {args.top_n:,} tracks from R2 via DuckDB...")
    tracks_df = get_top_tracks(args.top_n)

    # Load already-done URIs if resuming
    done_uris: set[str] = set()
    existing_results: list[dict] = []
    if args.resume and r2.exists(R2_KEY_OUT):
        tmp = Path(tempfile.gettempdir()) / "deezer_resume.parquet"
        r2.download(R2_KEY_OUT, tmp)
        existing_df = pd.read_parquet(tmp)
        done_uris = set(existing_df["spotify_track_uri"])
        existing_results = existing_df.to_dict("records")
        tmp.unlink(missing_ok=True)
        print(f"Resuming: {len(done_uris):,} tracks already done")

    results = list(existing_results)
    new_count = 0

    for _, row in tqdm(tracks_df.iterrows(), total=len(tracks_df), desc="Deezer enrichment"):
        uri = row["spotify_track_uri"]
        if uri in done_uris:
            continue

        hit = search_deezer(row["artist_name"], row["track_name"])
        record = {
            "spotify_track_uri": uri,
            "track_name":        row["track_name"],
            "artist_name":       row["artist_name"],
            "deezer_id":         hit["deezer_id"]  if hit else "",
            "isrc":              hit["isrc"]        if hit else "",
            "deezer_title":      hit["deezer_title"]  if hit else "",
            "deezer_artist":     hit["deezer_artist"] if hit else "",
            "matched":           hit is not None,
        }
        results.append(record)
        new_count += 1
        time.sleep(RATE_LIMIT_SEC)

        if new_count % CHECKPOINT_N == 0:
            _save_checkpoint(results, r2)

    _save_checkpoint(results, r2)
    matched = sum(1 for r in results if r["matched"])
    print(f"\nDone. {len(results):,} tracks processed — {matched:,} matched ({matched/len(results)*100:.1f}%)")
    print(f"Results → R2:{R2_KEY_OUT}")


if __name__ == "__main__":
    main()
