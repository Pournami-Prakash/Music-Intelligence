"""
Fetch sitewide popularity + trend signals from ListenBrainz API.

What we get:
  - Top recordings (global listen counts) → popularity signal
  - Top artists (global) → validates our MPD artist coverage

ListenBrainz API is free, no key needed.
Rate limit: generous (no hard published limit, but we sleep 0.5s between calls).

Usage:
    python src/enrichment/enrich_listenbrainz.py
    python src/enrichment/enrich_listenbrainz.py --weeks 52   # full year
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

LB_API = "https://api.listenbrainz.org/1"
R2_KEY_POP     = "enrichment/listenbrainz_popularity.parquet"
R2_KEY_ARTISTS = "enrichment/listenbrainz_top_artists.parquet"


def _lb_get(endpoint: str, params: dict = {}) -> dict:
    resp = requests.get(f"{LB_API}{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_top_recordings(count: int = 1000) -> pd.DataFrame:
    """Fetch sitewide top recordings from ListenBrainz."""
    print(f"Fetching top {count:,} recordings from ListenBrainz...")
    rows = []
    offset = 0
    batch = 100  # max per request

    while offset < count:
        try:
            data = _lb_get("/stats/sitewide/recordings", {"count": min(batch, count - offset), "offset": offset, "range": "all_time"})
            recordings = data.get("payload", {}).get("recordings", [])
            if not recordings:
                break
            for rec in recordings:
                rows.append({
                    "track_name":     rec.get("track_name", ""),
                    "artist_name":    rec.get("artist_name", ""),
                    "listen_count":   rec.get("listen_count", 0),
                    "recording_mbid": rec.get("recording_mbid", ""),
                })
            offset += len(recordings)
            time.sleep(0.3)
        except Exception as e:
            print(f"  Warning at offset {offset}: {e}")
            break

    df = pd.DataFrame(rows)
    print(f"  Got {len(df):,} recordings")
    return df


def fetch_top_artists(count: int = 1000) -> pd.DataFrame:
    """Fetch sitewide top artists from ListenBrainz."""
    print(f"Fetching top {count:,} artists from ListenBrainz...")
    rows = []
    offset = 0
    batch = 100

    while offset < count:
        try:
            data = _lb_get("/stats/sitewide/artists", {"count": min(batch, count - offset), "offset": offset, "range": "all_time"})
            artists = data.get("payload", {}).get("artists", [])
            if not artists:
                break
            for a in artists:
                rows.append({
                    "artist_name":  a.get("artist_name", ""),
                    "listen_count": a.get("listen_count", 0),
                    "artist_mbid":  a.get("artist_mbid", ""),
                })
            offset += len(artists)
            time.sleep(0.3)
        except Exception as e:
            print(f"  Warning at offset {offset}: {e}")
            break

    df = pd.DataFrame(rows)
    print(f"  Got {len(df):,} artists")
    return df


def overlap_with_mpd(r2: R2Client, lb_df: pd.DataFrame) -> None:
    """Show overlap using normalized (artist_name, track_name) pairs — avoids false matches on shared titles."""
    tmp = Path(tempfile.gettempdir()) / "tracks_overlap.parquet"
    r2.download("processed/tracks.parquet", tmp)
    mpd = pd.read_parquet(tmp, columns=["artist_name", "track_name"])
    tmp.unlink(missing_ok=True)

    def norm(s: pd.Series) -> pd.Series:
        return s.str.lower().str.strip().fillna("")

    mpd_pairs = set(zip(norm(mpd["artist_name"]), norm(mpd["track_name"])))

    if "track_name" in lb_df.columns and "artist_name" in lb_df.columns:
        lb_pairs = set(zip(norm(lb_df["artist_name"]), norm(lb_df["track_name"])))
        overlap  = mpd_pairs & lb_pairs
        print(f"  MPD ∩ ListenBrainz top-{len(lb_df)} by (artist, track): {len(overlap):,} ({len(overlap)/max(len(lb_pairs),1)*100:.1f}%)")
    elif "artist_name" in lb_df.columns:
        mpd_artists = set(norm(mpd["artist_name"]))
        lb_artists  = set(norm(lb_df["artist_name"]))
        overlap     = mpd_artists & lb_artists
        print(f"  MPD ∩ ListenBrainz top-{len(lb_df)} by artist: {len(overlap):,} ({len(overlap)/max(len(lb_artists),1)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000, help="Number of top recordings/artists to fetch")
    args = parser.parse_args()

    r2 = R2Client()

    # Top recordings
    rec_df = fetch_top_recordings(args.count)
    if not rec_df.empty:
        overlap_with_mpd(r2, rec_df)
        tmp = Path(tempfile.gettempdir()) / "lb_pop.parquet"
        rec_df.to_parquet(tmp, index=False)
        r2.upload(tmp, R2_KEY_POP, delete_after=True)

    time.sleep(0.5)

    # Top artists
    art_df = fetch_top_artists(args.count)
    if not art_df.empty:
        overlap_with_mpd(r2, art_df)
        tmp = Path(tempfile.gettempdir()) / "lb_artists.parquet"
        art_df.to_parquet(tmp, index=False)
        r2.upload(tmp, R2_KEY_ARTISTS, delete_after=True)

    r2.usage_summary()
    print("ListenBrainz enrichment complete.")


if __name__ == "__main__":
    main()
