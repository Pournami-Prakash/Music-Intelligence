"""
Train track2vec embeddings on 66M playlist co-occurrences.

Strategy: Word2Vec skip-gram over playlist sequences.
Each playlist is a sentence; each track_uri is a word.
Co-occurrence within a window of 10 tracks → semantic proximity.

Output (both written to R2:embeddings/):
  track2vec_128.npy       — float32 matrix [vocab_size × 128]
  track2vec_vocab.parquet — uri, track_name, artist_name, idx

Usage:
    python src/embeddings/train_track2vec.py
    python src/embeddings/train_track2vec.py --dims 128 --epochs 5 --workers 4
"""

import argparse
import sys
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from gensim.models import Word2Vec

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY_VECS  = "embeddings/track2vec_128.npy"
R2_KEY_VOCAB = "embeddings/track2vec_vocab.parquet"
# Local cache paths — avoids re-downloading from R2 on every epoch
_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"
_PLAYLIST_CACHE = _CACHE_DIR / "playlist_tracks.parquet"
_TRACKS_CACHE   = _CACHE_DIR / "tracks.parquet"


def _ensure_cache(r2: R2Client) -> None:
    """Download R2 parquets to local disk once. Subsequent epochs read locally."""
    _CACHE_DIR.mkdir(exist_ok=True)
    if not _PLAYLIST_CACHE.exists():
        print("  Downloading playlist_tracks.parquet to local cache...", flush=True)
        r2.download("processed/playlist_tracks.parquet", _PLAYLIST_CACHE)
        size_mb = _PLAYLIST_CACHE.stat().st_size / 1024**2
        print(f"  Cached: {size_mb:.0f} MB at {_PLAYLIST_CACHE}", flush=True)
    else:
        print(f"  Using cached playlist_tracks at {_PLAYLIST_CACHE}", flush=True)

    if not _TRACKS_CACHE.exists():
        print("  Downloading tracks.parquet to local cache...", flush=True)
        r2.download("processed/tracks.parquet", _TRACKS_CACHE)
        size_mb = _TRACKS_CACHE.stat().st_size / 1024**2
        print(f"  Cached: {size_mb:.0f} MB at {_TRACKS_CACHE}", flush=True)
    else:
        print(f"  Using cached tracks at {_TRACKS_CACHE}", flush=True)


class PlaylistCorpus:
    """In-memory corpus for Word2Vec.

    Loads the full playlist_tracks parquet once with a single sorted DuckDB scan,
    encodes track URIs as integer codes (faster iteration, lower memory), and holds
    all 1M playlist sequences in RAM. gensim re-iterates from memory every epoch —
    eliminating the repeated DuckDB sort passes that dominated the original approach.

    Memory: ~1.5 GB for 66M tokens with integer encoding on 16 GB machine.
    """

    def __init__(self):
        print("Loading corpus into memory (one-time DuckDB scan)...", flush=True)
        con = duckdb.connect()
        df = con.execute(f"""
            SELECT pid, track_uri, pos
            FROM read_parquet('{_PLAYLIST_CACHE}')
            ORDER BY pid, pos
        """).df()
        con.close()
        print(f"  {len(df):,} rows loaded", flush=True)

        # Encode URIs as integer codes — smaller Python objects, faster gensim iteration
        df["track_uri"] = df["track_uri"].astype("category")
        self._codes  = dict(enumerate(df["track_uri"].cat.categories))  # int → uri
        df["tok"]    = df["track_uri"].cat.codes

        print(f"  Building {df['pid'].nunique():,} playlist sequences...", flush=True)
        self._sentences: list[list[str]] = [
            grp["tok"].tolist()
            for _, grp in df.groupby("pid", sort=False)
        ]
        del df
        print(f"  Corpus ready: {len(self._sentences):,} playlists in RAM", flush=True)

    @property
    def total(self) -> int:
        return len(self._sentences)

    def __iter__(self):
        return iter(self._sentences)

    def decode_vocab(self, index_to_key: list[int]) -> list[str]:
        """Map integer token IDs back to spotify_track_uri strings."""
        return [self._codes[i] for i in index_to_key]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dims",      type=int, default=128)
    parser.add_argument("--window",    type=int, default=10)
    parser.add_argument("--min-count", type=int, default=5)
    parser.add_argument("--epochs",    type=int, default=3)   # 3 sufficient for 66M-token corpus
    parser.add_argument("--workers",   type=int, default=7)   # leave 1 core for OS
    args = parser.parse_args()

    r2 = R2Client()

    print(f"Track2Vec training")
    print(f"  dims={args.dims}  window={args.window}  min_count={args.min_count}  epochs={args.epochs}  workers={args.workers}")

    print("\nPreparing local cache...")
    _ensure_cache(r2)

    corpus = PlaylistCorpus()
    print(f"  Corpus: {corpus.total:,} playlists in memory")

    print("\nBuilding vocabulary + training...", flush=True)
    model = Word2Vec(
        sentences=corpus,
        vector_size=args.dims,
        window=args.window,
        min_count=args.min_count,
        workers=args.workers,
        sg=1,
        epochs=args.epochs,
        compute_loss=True,
    )

    vocab_size = len(model.wv)
    print(f"\nVocabulary: {vocab_size:,} tracks", flush=True)
    print(f"Final loss: {model.get_latest_training_loss():.2f}", flush=True)

    # Decode integer token IDs back to spotify_track_uri strings
    print("\nBuilding vocab table with track metadata...", flush=True)
    int_keys = [int(k) for k in model.wv.index_to_key]
    uris     = corpus.decode_vocab(int_keys)

    uri_df = pd.DataFrame({"track_uri": uris, "idx": range(len(uris))})

    con = duckdb.connect()
    con.register("uri_table", uri_df)
    meta_df = con.execute(f"""
        SELECT t.track_uri, t.track_name, t.artist_name
        FROM read_parquet('{_TRACKS_CACHE}') t
        INNER JOIN uri_table u ON t.track_uri = u.track_uri
    """).df().drop_duplicates("track_uri")
    con.close()

    vocab_df = uri_df.merge(meta_df, on="track_uri", how="left")
    print(f"  Metadata matched: {vocab_df['track_name'].notna().sum():,} / {len(vocab_df):,}", flush=True)

    # Save embeddings matrix
    vectors = model.wv.vectors
    print(f"\nEmbedding matrix: {vectors.shape}  dtype={vectors.dtype}", flush=True)

    tmp_vecs  = _CACHE_DIR / "track2vec_128.npy"
    tmp_vocab = _CACHE_DIR / "track2vec_vocab.parquet"

    np.save(tmp_vecs, vectors.astype(np.float32))
    vocab_df.to_parquet(tmp_vocab, index=False, compression="zstd")

    print(f"\nUploading to R2...", flush=True)
    r2.upload(tmp_vecs,  R2_KEY_VECS,  delete_after=True)
    r2.upload(tmp_vocab, R2_KEY_VOCAB, delete_after=True)
    r2.usage_summary()

    print(f"\n✓ track2vec done")
    print(f"  R2:{R2_KEY_VECS}   — {vectors.shape}")
    print(f"  R2:{R2_KEY_VOCAB}  — {len(vocab_df):,} rows")
    print(f"\nNext: UMAP projection → Genre Weather (src/embeddings/project_umap.py)")


if __name__ == "__main__":
    main()
