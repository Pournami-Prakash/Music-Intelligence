"""
Compute per-artist playlist stats from 1M playlists.

Output: R2:computed/artist_stats.parquet
Schema:
    artist_uri        str
    artist_name       str
    playlist_count    int   — distinct playlists containing this artist
    playlist_pct      float — playlist_count / 1M * 100
    rank              int   — rank by playlist_count
    top_tracks        list  — top 5 track names by playlist appearance
    top_co_artists    list  — top 8 co-artist names with overlap_pct

Usage:
    python src/compute/compute_artist_stats.py
    python src/compute/compute_artist_stats.py --top-n 5000
"""

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY = 'computed/artist_stats.parquet'
UBIQUITY_R2_KEY = 'computed/artist_ubiquity_lookup.parquet'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top-n', type=int, default=10_000)
    args = parser.parse_args()

    r2 = R2Client()
    con = get_con()

    print(f"Computing artist stats for top {args.top_n:,} artists via DuckDB...")

    # 1. Playlist count per artist
    print("  Step 1/3: playlist counts...")
    counts = con.execute(f"""
        SELECT
            t.artist_uri,
            t.artist_name,
            COUNT(DISTINCT pt.pid) AS playlist_count
        FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
        JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t
            ON pt.track_uri = t.track_uri
        GROUP BY t.artist_uri, t.artist_name
        ORDER BY playlist_count DESC
    """).df()
    total_playlists = 1_000_000
    counts['playlist_pct'] = (counts['playlist_count'] / total_playlists * 100).round(3)
    counts['rank'] = range(1, len(counts) + 1)
    counts['artist_name_lc'] = counts['artist_name'].astype('string').str.lower()
    full_counts = counts.sort_values('artist_name_lc', kind='stable').reset_index(drop=True)
    ubiquity_tmp = Path(tempfile.gettempdir()) / 'artist_ubiquity_lookup.parquet'
    full_counts.to_parquet(ubiquity_tmp, index=False, compression='zstd', row_group_size=65_536)
    r2.upload(ubiquity_tmp, UBIQUITY_R2_KEY, delete_after=True)
    print(f"    {len(full_counts):,} artists written to R2:{UBIQUITY_R2_KEY}")

    counts = counts.head(args.top_n).copy()
    print(f"    {len(counts):,} rich artist rows retained")
    print(counts.head(5)[['artist_name', 'playlist_count', 'playlist_pct']].to_string(index=False))

    # 2. Top tracks per artist (all top-N artists)
    print("  Step 2/3: top tracks per artist...")
    top_uris = counts['artist_uri'].tolist()
    uri_list = ', '.join(f"'{u}'" for u in top_uris)

    track_counts = con.execute(f"""
        SELECT
            t.artist_uri,
            t.track_name,
            COUNT(DISTINCT pt.pid) AS track_playlist_count
        FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
        JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t
            ON pt.track_uri = t.track_uri
        WHERE t.artist_uri IN ({uri_list})
        GROUP BY t.artist_uri, t.track_name
        ORDER BY t.artist_uri, track_playlist_count DESC
    """).df()

    top_tracks_map = (
        track_counts.groupby('artist_uri')
        .apply(lambda g: g.head(5)['track_name'].tolist(), include_groups=False)
        .to_dict()
    )
    counts['top_tracks'] = counts['artist_uri'].map(top_tracks_map).fillna('').apply(
        lambda x: x if isinstance(x, list) else []
    )

    # 3. Top co-artists — read from already-computed artist_edges.parquet (avoids DuckDB OOM)
    print("  Step 3/3: top co-artists from artist_edges.parquet...")
    import tempfile as _tmp
    edges_tmp = Path(_tmp.gettempdir()) / 'artist_edges_dl.parquet'
    try:
        r2.download('computed/artist_edges.parquet', edges_tmp)
        edges = pd.read_parquet(edges_tmp)
        edges_tmp.unlink(missing_ok=True)

        # Normalise to (artist_uri, co_artist_name, shared_playlists) in both directions
        fwd = edges[['artist_a_uri', 'artist_b_name', 'shared_playlists']].rename(
            columns={'artist_a_uri': 'artist_uri', 'artist_b_name': 'co_artist_name'})
        rev = edges[['artist_b_uri', 'artist_a_name', 'shared_playlists']].rename(
            columns={'artist_b_uri': 'artist_uri', 'artist_a_name': 'co_artist_name'})
        co = pd.concat([fwd, rev], ignore_index=True)
        co = co.sort_values(['artist_uri', 'shared_playlists'], ascending=[True, False])
        print(f"    {len(co):,} co-artist rows loaded from edges table")

        artist_pc = counts.set_index('artist_uri')['playlist_count'].to_dict()

        def top_co(group):
            pc = artist_pc.get(group.name, 1)
            return (
                group.head(8)
                .assign(overlap_pct=lambda g: (g['shared_playlists'] / pc * 100).round(1))
                [['co_artist_name', 'overlap_pct']]
                .to_dict('records')
            )

        co_map = co.groupby('artist_uri').apply(top_co, include_groups=False).to_dict()
        counts['top_co_artists'] = counts['artist_uri'].map(co_map).fillna('').apply(
            lambda x: x if isinstance(x, list) else []
        )
        print(f"    co-artists populated for {sum(counts['top_co_artists'].apply(bool)):,} artists")
    except Exception as e:
        print(f"  ⚠ Could not load artist_edges ({e}), top_co_artists will be empty")
        counts['top_co_artists'] = [[] for _ in range(len(counts))]

    print(f"\n  Final: {len(counts):,} artist rows")

    tmp = Path(tempfile.gettempdir()) / 'artist_stats.parquet'
    counts.to_parquet(tmp, index=False, compression='zstd')
    r2.upload(tmp, R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ Written to R2:{R2_KEY}")


if __name__ == '__main__':
    main()
