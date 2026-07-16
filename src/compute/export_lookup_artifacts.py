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
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.storage.r2 import R2Client

ROW_GROUP_SIZE = 65_536
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


def export_track_stats(r2: R2Client) -> None:
    """Point lookup by track name (song-passport)."""
    df = pd.read_parquet(_fetch(r2, "computed/track_stats.parquet"))
    df["track_name_lc"] = df["track_name"].astype("string").str.lower()
    df = df.sort_values("track_name_lc", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "track_stats_lookup.parquet", "computed/track_stats_lookup.parquet")


def export_vocab(r2: R2Client) -> None:
    """Prefix search by title + lookups by uri/artist; keep idx (popularity rank)."""
    df = pd.read_parquet(_fetch(r2, "embeddings/track2vec_vocab.parquet"))
    df["track_name_lc"]  = df["track_name"].astype("string").str.lower()
    df["artist_name_lc"] = df["artist_name"].astype("string").str.lower()
    df = df.sort_values("track_name_lc", kind="stable").reset_index(drop=True)
    _write_and_upload(r2, df, "vocab_lookup.parquet", "embeddings/track2vec_vocab_lookup.parquet")


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
    r2 = R2Client()
    for step in (export_track_stats, export_vocab, export_listenbrainz, export_editorial_slim):
        print(f"→ {step.__name__}")
        step(r2)
    print("done — all lookup artifacts re-exported to R2.")


if __name__ == "__main__":
    main()
