"""
Compute artist-artist co-occurrence graph for Six Degrees + Compass.

Strategy:
  - Take top N artists (default 2000) by playlist frequency
  - For each playlist, collect the set of artists (from top N only)
  - Generate all artist pairs per playlist, count shared playlists
  - Filter to pairs with >= min_shared playlists
  - Write adjacency list to R2: computed/artist_edges.parquet

This is a one-time overnight compute. BFS over the resulting table is O(hops × degree).

Output: R2:computed/artist_edges.parquet
Schema:
    artist_a_uri    str
    artist_b_uri    str
    artist_a_name   str
    artist_b_name   str
    shared_playlists int

Usage:
    python src/compute/compute_artist_edges.py
    python src/compute/compute_artist_edges.py --top-n 1000 --min-shared 5
"""

import argparse
import sys
import tempfile
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY = 'computed/artist_edges.parquet'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top-n',     type=int, default=2000, help='Top N artists to include')
    parser.add_argument('--min-shared',type=int, default=10,   help='Minimum shared playlists for an edge')
    args = parser.parse_args()

    r2 = R2Client()
    con = get_con()

    # 1. Get top N artist URIs
    print(f"Loading top {args.top_n} artists...")
    artists_df = con.execute(f"""
        SELECT
            t.artist_uri,
            t.artist_name,
            COUNT(DISTINCT pt.pid) AS playlist_count
        FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
        JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t ON pt.track_uri = t.track_uri
        GROUP BY t.artist_uri, t.artist_name
        ORDER BY playlist_count DESC
        LIMIT {args.top_n}
    """).df()
    artist_uri_to_name = dict(zip(artists_df['artist_uri'], artists_df['artist_name']))
    top_uris = set(artists_df['artist_uri'])
    print(f"  {len(top_uris):,} artists loaded")

    # 2. Get (playlist_id, artist_uri) for top artists only
    uri_list = ', '.join(f"'{u}'" for u in top_uris)
    print("Loading (playlist_id, artist_uri) pairs from R2...")
    pairs_df = con.execute(f"""
        SELECT DISTINCT pt.pid, t.artist_uri
        FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
        JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t ON pt.track_uri = t.track_uri
        WHERE t.artist_uri IN ({uri_list})
    """).df()
    print(f"  {len(pairs_df):,} (playlist, artist) pairs loaded")

    # 3. Group by playlist → set of artists
    print("Grouping artists by playlist...")
    playlist_artists = pairs_df.groupby('pid')['artist_uri'].apply(set)
    playlists_with_multiple = playlist_artists[playlist_artists.apply(len) >= 2]
    print(f"  {len(playlists_with_multiple):,} playlists with ≥2 top artists")

    # 4. Count pairs
    print("Counting artist pairs...")
    edge_counts: dict[tuple, int] = defaultdict(int)
    for artist_set in tqdm(playlists_with_multiple, desc="Pair counting"):
        artists = sorted(artist_set)
        for a, b in combinations(artists, 2):
            edge_counts[(a, b)] += 1

    print(f"  {len(edge_counts):,} raw pairs found")

    # 5. Filter and build dataframe
    edges = [
        {
            'artist_a_uri':     a,
            'artist_b_uri':     b,
            'artist_a_name':    artist_uri_to_name.get(a, a),
            'artist_b_name':    artist_uri_to_name.get(b, b),
            'shared_playlists': count,
        }
        for (a, b), count in edge_counts.items()
        if count >= args.min_shared
    ]
    edges_df = pd.DataFrame(edges).sort_values('shared_playlists', ascending=False)
    print(f"  {len(edges_df):,} edges after filtering (min_shared={args.min_shared})")
    print(edges_df.head(10)[['artist_a_name', 'artist_b_name', 'shared_playlists']].to_string(index=False))

    # 6. Save
    tmp = Path(tempfile.gettempdir()) / 'artist_edges.parquet'
    edges_df.to_parquet(tmp, index=False, compression='zstd')
    r2.upload(tmp, R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ Written to R2:{R2_KEY}")
    print(f"  Graph: {len(top_uris):,} nodes · {len(edges_df):,} edges")
    print("  BFS for Six Degrees will run over this table in-memory.")


if __name__ == '__main__':
    main()
