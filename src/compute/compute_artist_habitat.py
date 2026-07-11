"""
Compute habitat scores for each artist in the top 10K.

For each artist, counts how many playlists they appear in that match each
habitat category (gym, heartbreak, road_trip, party, study, chill, throwback, sleep)
based on playlist title keyword matching.

Reads:
  R2:processed/playlist_tracks.parquet  — pid, track_uri
  R2:processed/playlists.parquet        — pid, name
  R2:processed/tracks.parquet           — track_uri, artist_name
  R2:computed/artist_stats.parquet      — artist_name, playlist_count (for top-10K list)

Output:
  R2:computed/artist_habitat.parquet
    artist_name, playlist_count, gym, heartbreak, road_trip, party,
    study, chill, throwback, sleep   (raw counts)
    + gym_pct, heartbreak_pct, ... (pct of artist's playlists in that habitat)

Usage:
    python src/compute/compute_artist_habitat.py
    python src/compute/compute_artist_habitat.py --top-n 5000
"""

import argparse
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"

HABITATS = {
    "gym":        ["gym", "workout", "fitness", "lift", "run", "cardio", "training", "pump"],
    "heartbreak": ["heartbreak", "breakup", "cry", "sad", "broken", "ex", "miss", "gone"],
    "road_trip":  ["road trip", "roadtrip", "drive", "driving", "highway", "cruise", "travel"],
    "party":      ["party", "pregame", "turn up", "banger", "hype", "lit", "club", "dance"],
    "study":      ["study", "focus", "work", "concentrate", "reading", "homework", "lo-fi", "lofi"],
    "chill":      ["chill", "vibe", "relax", "mellow", "ease", "calm", "soft", "ambient"],
    "throwback":  ["throwback", "nostalgia", "classic", "oldies", "retro", "2000s", "90s", "80s"],
    "sleep":      ["sleep", "night", "bedtime", "insomnia", "drift", "dream", "lullaby"],
}


def _ensure_cache(r2: R2Client) -> None:
    _CACHE_DIR.mkdir(exist_ok=True)
    for key, fname in [
        ("processed/playlist_tracks.parquet", "playlist_tracks.parquet"),
        ("processed/playlists.parquet",        "playlists.parquet"),
        ("processed/tracks.parquet",            "tracks.parquet"),
    ]:
        local = _CACHE_DIR / fname
        if not local.exists():
            print(f"  Downloading {key}...", flush=True)
            r2.download(key, local)
        else:
            print(f"  Using cached {fname}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=10_000,
                        help="Limit to top-N artists by playlist count (default: 10000)")
    args = parser.parse_args()

    r2 = R2Client()
    _ensure_cache(r2)

    # Load top-N artist list
    print(f"\nLoading top-{args.top_n} artists from artist_stats...", flush=True)
    stats_path = Path(tempfile.gettempdir()) / "computed_artist_stats.parquet"
    if not stats_path.exists():
        r2.download("computed/artist_stats.parquet", stats_path)
    stats_df = pd.read_parquet(stats_path).head(args.top_n)
    artist_names = set(stats_df["artist_name"].str.lower())
    print(f"  {len(artist_names):,} artists", flush=True)

    # Build playlist → habitat label via DuckDB (keyword matching on title)
    print("\nBuilding habitat labels for playlists...", flush=True)
    con = duckdb.connect()

    playlists_path = _CACHE_DIR / "playlists.parquet"
    playlists = con.execute(
        f"SELECT pid, lower(name) AS name_lower FROM read_parquet('{playlists_path}') WHERE name IS NOT NULL"
    ).df()

    for habitat, keywords in HABITATS.items():
        pattern = "|".join(keywords)
        playlists[habitat] = playlists["name_lower"].str.contains(pattern, regex=True, na=False).astype(int)

    print(f"  {len(playlists):,} playlists labelled", flush=True)
    for h in HABITATS:
        print(f"    {h}: {playlists[h].sum():,} playlists", flush=True)

    # Join: playlist_tracks → tracks → filter to top-N artists → join habitat labels
    print("\nJoining tracks to playlists...", flush=True)
    pt_path = _CACHE_DIR / "playlist_tracks.parquet"
    tr_path = _CACHE_DIR / "tracks.parquet"

    # Use DuckDB for the join — faster than pandas merge on 66M rows
    con.register("playlists_hab", playlists)
    joined = con.execute(f"""
        SELECT t.artist_name, ph.*
        FROM read_parquet('{pt_path}') pt
        JOIN read_parquet('{tr_path}') t ON pt.track_uri = t.track_uri
        JOIN playlists_hab ph ON pt.pid = ph.pid
    """).df()

    print(f"  Joined {len(joined):,} rows", flush=True)
    con.close()

    # Filter to top-N artists
    joined = joined[joined["artist_name"].str.lower().isin(artist_names)]
    print(f"  After top-N filter: {len(joined):,} rows, {joined['artist_name'].nunique():,} artists", flush=True)

    # Aggregate: per artist, count distinct playlists per habitat
    # We use the pid column to count distinct playlists
    print("\nAggregating habitat counts per artist...", flush=True)
    habitat_cols = list(HABITATS.keys())

    agg = (
        joined
        .groupby("artist_name")
        .agg(
            playlist_count=("pid", "nunique"),
            **{h: (h, "sum") for h in habitat_cols}
        )
        .reset_index()
    )

    # Add percentage columns
    for h in habitat_cols:
        agg[f"{h}_pct"] = (agg[h] / agg["playlist_count"].clip(lower=1) * 100).round(2)

    # Sort by playlist_count
    agg = agg.sort_values("playlist_count", ascending=False).reset_index(drop=True)
    print(f"  {len(agg):,} artists with habitat data", flush=True)
    print("\nSample (top 5 by gym_pct, min 1000 playlists):")
    sample = agg[agg["playlist_count"] >= 1000].nlargest(5, "gym_pct")
    print(sample[["artist_name", "playlist_count", "gym", "gym_pct", "party", "party_pct"]].to_string(index=False))

    # Save and upload
    print("\nSaving and uploading...", flush=True)
    out = _CACHE_DIR / "artist_habitat.parquet"
    agg.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024**2
    print(f"  artist_habitat.parquet: {size_mb:.1f} MB", flush=True)

    r2.upload(out, "computed/artist_habitat.parquet", delete_after=True)
    r2.usage_summary()

    print(f"\n✓ artist_habitat done — {len(agg):,} artists × {len(habitat_cols)} habitats")
    print("  Next: wire /api/artist-habitat/{artist} to computed/artist_habitat.parquet")


if __name__ == "__main__":
    main()
