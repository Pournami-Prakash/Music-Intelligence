"""
Re-export the serving "lookup" parquets: sorted by their lookup key and written
with small row groups so DuckDB point/prefix queries prune to a few row groups
instead of decoding a giant column chunk.

These feed the low-memory serving path (see src/app/cache.local_parquet and the
DuckDB queries in routes/tracks, routes/social, routes/discovery, routes/
embeddings). Writing to NEW keys is non-destructive — the originals stay.

Run after the source artifacts change:
    python -m src.compute.export_lookup_artifacts

Requires R2_* creds in the environment / .env.
"""
import os
import sqlite3
import tempfile
import argparse
import gzip
import shutil
from pathlib import Path

import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.storage.r2 import R2Client

ROW_GROUP_SIZE = 65_536
VECTOR_ROW_GROUP_SIZE = 1_024
_TMP = Path(tempfile.gettempdir())


def _fetch(r2: R2Client, key: str) -> Path:
    # Always pull a fresh copy from R2 (source of truth). Reusing a stale /tmp
    # file would silently re-export outdated data after an R2 refresh. Download
    # to a staging path and swap so a mid-download failure can't leave a partial.
    local = _TMP / ("reexport_src_" + key.replace("/", "_"))
    staging = local.with_suffix(local.suffix + ".new")
    r2.download(key, staging)
    staging.replace(local)
    return local


def _write_and_upload(r2: R2Client, df: pd.DataFrame, out_name: str, dest_key: str) -> None:
    out = _TMP / out_name
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        out, row_group_size=ROW_GROUP_SIZE, compression="zstd",
    )
    m = pq.ParquetFile(out).metadata
    print(f"  {dest_key}: rows={m.num_rows:,} row_groups={m.num_row_groups} "
          f"size={os.path.getsize(out) / 1e6:.1f} MB")
    r2.upload(out, dest_key)


TRACK_STATS_TOP_N = 300_000  # local fast-path size for song-passport


def export_track_stats(r2: R2Client) -> None:
    """Point lookup by track name (song-passport).

    Writes two artifacts: the FULL sorted table (kept on R2 only, for the
    obscure-track fallback queried directly over httpfs) and a small top-N
    fast-path table that the API downloads locally (keeps the 512 MB box lean).
    """
    df = pd.read_parquet(_fetch(r2, "computed/track_stats.parquet"))
    df["track_name_lc"] = df["track_name"].astype("string").str.lower()
    df = df.sort_values("track_name_lc", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "track_stats_lookup.parquet", "computed/track_stats_lookup.parquet")

    top = (df.nlargest(TRACK_STATS_TOP_N, "playlist_count")
             .sort_values("track_name_lc", kind="stable").reset_index(drop=True))
    _write_and_upload(r2, top, "track_stats_top.parquet", "computed/track_stats_top.parquet")


def export_artist_ubiquity(r2: R2Client) -> None:
    """Materialize full artist rank/count coverage for serving-time lookups."""
    from src.storage.duckdb_r2 import get_con, R2_PATH

    out = _TMP / "artist_ubiquity_lookup.parquet"
    con = get_con()
    try:
        con.execute(f"""
            COPY (
                WITH counts AS (
                    SELECT t.artist_uri, t.artist_name,
                           COUNT(DISTINCT pt.pid) AS playlist_count
                    FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
                    JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t
                      ON pt.track_uri = t.track_uri
                    WHERE t.artist_name IS NOT NULL
                    GROUP BY t.artist_uri, t.artist_name
                ), ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        ORDER BY playlist_count DESC, artist_name
                    ) AS rank
                    FROM counts
                )
                SELECT artist_uri, artist_name, playlist_count,
                       ROUND(playlist_count / 1000000.0 * 100, 3) AS playlist_pct,
                       rank, lower(artist_name) AS artist_name_lc
                FROM ranked ORDER BY artist_name_lc
            ) TO '{out.as_posix()}' (
                FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {ROW_GROUP_SIZE}
            )
        """)
    finally:
        con.close()
    meta = pq.ParquetFile(out).metadata
    print(f"  computed/artist_ubiquity_lookup.parquet: rows={meta.num_rows:,} "
          f"size={out.stat().st_size / 1e6:.1f} MB")
    r2.upload(out, "computed/artist_ubiquity_lookup.parquet")


def export_vocab(r2: R2Client) -> None:
    """Prefix search by title + lookups by uri/artist; keep idx (popularity rank)."""
    df = pd.read_parquet(_fetch(r2, "embeddings/track2vec_vocab.parquet"))
    df["track_name_lc"]  = df["track_name"].astype("string").str.lower()
    df["artist_name_lc"] = df["artist_name"].astype("string").str.lower()
    df = df.sort_values("track_name_lc", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "vocab_lookup.parquet", "embeddings/track2vec_vocab_lookup.parquet")


def export_track_search(r2: R2Client) -> None:
    """Build an on-disk FTS5 index over every track without a resident table.

    SQLite is intentionally used here: the serving process can query 2M+ rows
    from disk in milliseconds while keeping only a few pages in memory. The
    embeddable vocabulary rank is retained as a relevance tie-breaker, but no
    source track is excluded.
    """
    from src.storage.duckdb_r2 import get_con, R2_PATH

    out = _TMP / "track_search.sqlite"
    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    try:
        db.executescript("""
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=FILE;
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                uri TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                popularity_rank INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE tracks_fts USING fts5(
                title, artist, content='tracks', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            );
        """)
        con = get_con()
        cur = con.execute(f"""
            SELECT t.track_uri, t.track_name, t.artist_name,
                   COALESCE(v.idx, 2147483647) AS popularity_rank
            FROM read_parquet('{R2_PATH}/processed/tracks.parquet') t
            LEFT JOIN read_parquet('{R2_PATH}/embeddings/track2vec_vocab.parquet') v
              ON t.track_uri = v.track_uri
            WHERE t.track_uri IS NOT NULL AND t.track_name IS NOT NULL
                  AND t.artist_name IS NOT NULL
        """)
        inserted = 0
        while True:
            rows = cur.fetchmany(50_000)
            if not rows:
                break
            db.executemany(
                "INSERT INTO tracks(uri,title,artist,popularity_rank) VALUES(?,?,?,?)",
                rows,
            )
            db.commit()
            inserted += len(rows)
            print(f"    indexed rows: {inserted:,}", flush=True)
        con.close()
        db.execute("INSERT INTO tracks_fts(tracks_fts) VALUES('rebuild')")
        db.execute("CREATE INDEX tracks_popularity_idx ON tracks(popularity_rank)")
        db.execute("PRAGMA optimize")
        db.commit()
    finally:
        db.close()
    print(f"  computed/track_search.sqlite: rows={inserted:,} size={out.stat().st_size / 1e6:.1f} MB")
    r2.upload(out, "computed/track_search.sqlite")
    _gzip_track_search(r2, out)


def _gzip_track_search(r2: R2Client, source: Path) -> None:
    compressed = _TMP / "track_search.sqlite.gz"
    with source.open("rb") as src, gzip.open(compressed, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=4 << 20)
    print(f"  computed/track_search.sqlite.gz: size={compressed.stat().st_size / 1e6:.1f} MB")
    r2.upload(compressed, "computed/track_search.sqlite.gz")


def export_track_search_gzip(r2: R2Client) -> None:
    """Compress an already-built local/R2 search index without rebuilding it."""
    source = _TMP / "track_search.sqlite"
    if not source.exists():
        source = _fetch(r2, "computed/track_search.sqlite")
    _gzip_track_search(r2, source)


def export_vector_lookup(r2: R2Client) -> None:
    """Write the full embedding matrix as an idx-sorted R2 point-lookup table.

    Small row groups let the API fetch an obscure query vector without loading
    the 300+ MB matrix or FAISS index. Upstash remains the fast candidate index.
    """
    vocab = pd.read_parquet(_fetch(r2, "embeddings/track2vec_vocab.parquet"),
                            columns=["idx", "track_uri"])
    vec_path = _fetch(r2, "embeddings/track2vec_128.npy")
    vectors = np.load(vec_path, mmap_mode="r")
    vocab = vocab.sort_values("idx", kind="stable").reset_index(drop=True)
    if len(vocab) != len(vectors):
        raise ValueError(f"vocab/vector length mismatch: {len(vocab):,} != {len(vectors):,}")

    out = _TMP / "track2vec_vectors_lookup.parquet"
    writer = None
    try:
        for start in range(0, len(vocab), 25_000):
            stop = min(start + 25_000, len(vocab))
            block = np.asarray(vectors[start:stop], dtype="float32")
            vector_col = pa.FixedSizeListArray.from_arrays(
                pa.array(block.reshape(-1), type=pa.float32()), block.shape[1]
            )
            table = pa.table({
                "idx": pa.array(vocab["idx"].iloc[start:stop].to_numpy(), type=pa.int64()),
                "track_uri": pa.array(vocab["track_uri"].iloc[start:stop].astype(str)),
                "vector": vector_col,
            })
            if writer is None:
                writer = pq.ParquetWriter(out, table.schema, compression="zstd")
            writer.write_table(table, row_group_size=VECTOR_ROW_GROUP_SIZE)
    finally:
        if writer is not None:
            writer.close()
    print(f"  embeddings/track2vec_vectors_lookup.parquet: rows={len(vocab):,} "
          f"size={out.stat().st_size / 1e6:.1f} MB")
    r2.upload(out, "embeddings/track2vec_vectors_lookup.parquet")


def export_listenbrainz(r2: R2Client) -> None:
    """Point lookup by spotify_track_uri (song-passport listen count + isrc)."""
    df = pd.read_parquet(_fetch(r2, "enrichment/listenbrainz_full.parquet"))
    df = df.sort_values("spotify_track_uri", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "listenbrainz_lookup.parquet", "enrichment/listenbrainz_lookup.parquet")


def export_editorial_slim(r2: R2Client) -> None:
    """3-column slim editorial track list (forensics + mood-contradiction).

    Drops the wide columns (uris, album, dates) — 233 MB → ~50 MB — and strips
    the placeholder rows the same way src/app/cache._load_computed does.
    """
    df = pd.read_parquet(_fetch(r2, "processed/editorial_playlist_tracks.parquet"),
                         columns=["playlist_id", "track_name", "artist_name"])
    bad_name  = df["artist_name"].fillna("").str.strip()
    bad_title = df["track_name"].fillna("").str.strip()
    mask = ((bad_name == "") | (bad_name.str.lower() == "artist")) & (bad_title == "")
    df = df[~mask].sort_values("playlist_id", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "editorial_tracks_slim.parquet", "processed/editorial_tracks_slim.parquet")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only", nargs="+",
        choices=["track_stats", "artist_ubiquity", "vocab", "track_search", "track_search_gzip",
                 "vector_lookup", "listenbrainz", "editorial_slim"],
        help="Export only the named artifacts (default: all).",
    )
    args = parser.parse_args()
    r2 = R2Client()
    steps = {
        "track_stats": export_track_stats,
        "artist_ubiquity": export_artist_ubiquity,
        "vocab": export_vocab,
        "track_search": export_track_search,
        "track_search_gzip": export_track_search_gzip,
        "vector_lookup": export_vector_lookup,
        "listenbrainz": export_listenbrainz,
        "editorial_slim": export_editorial_slim,
    }
    selected = args.only or list(steps)
    for name in selected:
        step = steps[name]
        print(f"→ {step.__name__}")
        step(r2)
    print("done — all lookup artifacts re-exported to R2.")


if __name__ == "__main__":
    main()
