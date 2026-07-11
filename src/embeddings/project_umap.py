"""
Project track2vec embeddings to 2D via UMAP, then cluster with HDBSCAN.

Reads:
  R2:embeddings/track2vec_128.npy        — float32 [vocab_size × 128]
  R2:embeddings/track2vec_vocab.parquet  — track_uri, track_name, artist_name, idx
  R2:computed/artist_genres.parquet      — artist_uri, artist_name, genres (list)

Output:
  R2:embeddings/genre_umap.parquet
    track_uri, track_name, artist_name, x, y,
    cluster_id, genre_label, top_genre

  R2:embeddings/genre_umap_clusters.parquet
    cluster_id, genre_label, cx, cy, track_count, color

Usage:
    python src/embeddings/project_umap.py
    python src/embeddings/project_umap.py --sample 150000  # subsample for speed
"""

import argparse
import sys
import tempfile
from pathlib import Path
from collections import Counter

import hdbscan
import numpy as np
import pandas as pd
from umap.umap_ import UMAP
import umap.umap_ as _umap_mod

# umap-learn 0.5.7 uses force_all_finite which was removed in sklearn 1.6.
# Patch check_array inside umap's own namespace so calls within umap hit the shim.
_orig_check_array = _umap_mod.check_array
def _patched_check_array(*args, force_all_finite=None, **kwargs):
    if force_all_finite is not None:
        kwargs.setdefault("ensure_all_finite", force_all_finite)
    return _orig_check_array(*args, **kwargs)
_umap_mod.check_array = _patched_check_array
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"

GENRE_COLORS = {
    "pop":          "#F9C74F",
    "hip hop":      "#FB923C",
    "rap":          "#FB923C",
    "rock":         "#C084FC",
    "indie":        "#A78BFA",
    "electronic":   "#62A8FF",
    "dance":        "#60D4F5",
    "r&b":          "#FF5C8A",
    "soul":         "#FF5C8A",
    "jazz":         "#34D399",
    "classical":    "#94A3B8",
    "metal":        "#F87171",
    "country":      "#FBBF24",
    "folk":         "#86EFAC",
    "latin":        "#FCA5A5",
    "k-pop":        "#E879F9",
}

DEFAULT_COLOR = "#64748B"


def genre_to_color(genre: str) -> str:
    g = genre.lower()
    for key, color in GENRE_COLORS.items():
        if key in g:
            return color
    return DEFAULT_COLOR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample",    type=int, default=None,
                        help="Subsample N tracks for UMAP (default: all)")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--min-dist",    type=float, default=0.1)
    parser.add_argument("--min-cluster-size", type=int, default=200)
    args = parser.parse_args()

    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    # 1. Load embeddings
    print("Loading track2vec embeddings...", flush=True)
    vecs_path  = _CACHE_DIR / "track2vec_128.npy"
    vocab_path = _CACHE_DIR / "track2vec_vocab.parquet"

    if not vecs_path.exists():
        print("  Downloading track2vec_128.npy from R2...", flush=True)
        r2.download("embeddings/track2vec_128.npy", vecs_path)
    if not vocab_path.exists():
        print("  Downloading track2vec_vocab.parquet from R2...", flush=True)
        r2.download("embeddings/track2vec_vocab.parquet", vocab_path)

    vectors = np.load(vecs_path)          # [vocab_size, 128]
    vocab   = pd.read_parquet(vocab_path) # track_uri, track_name, artist_name, idx
    print(f"  {len(vectors):,} tracks × {vectors.shape[1]} dims", flush=True)

    # 2. Load artist genres
    print("Loading artist genres...", flush=True)
    genres_path = _CACHE_DIR / "artist_genres.parquet"
    if not genres_path.exists():
        print("  Downloading artist_genres.parquet from R2...", flush=True)
        r2.download("enrichment/artist_genres.parquet", genres_path)
    genres_df = pd.read_parquet(genres_path)
    # genres column may be a list or comma-separated string
    if "tags" in genres_df.columns:
        genres_df = genres_df.rename(columns={"tags": "genres"})
    if genres_df["genres"].dtype == object:
        def top_genre(g):
            if g is None:
                return None
            try:
                items = list(g)  # handles list, np.ndarray, and other iterables
                return items[0] if items else None
            except TypeError:
                return str(g).split(",")[0].strip() if g else None
        genres_df["top_genre"] = genres_df["genres"].apply(top_genre)
    print(f"  {len(genres_df):,} artists with genre data", flush=True)

    # 3. Join genre onto vocab
    vocab = vocab.merge(
        genres_df[["artist_name", "top_genre"]].drop_duplicates("artist_name"),
        on="artist_name", how="left"
    )

    # 4. Subsample if requested
    if args.sample and args.sample < len(vectors):
        print(f"Subsampling {args.sample:,} tracks...", flush=True)
        idx = np.random.choice(len(vectors), args.sample, replace=False)
        idx.sort()
        vectors = vectors[idx]
        vocab   = vocab.iloc[idx].reset_index(drop=True)

    # 5. UMAP projection
    print(f"Running UMAP ({len(vectors):,} tracks, n_neighbors={args.n_neighbors}, min_dist={args.min_dist})...", flush=True)
    reducer = UMAP(
        n_components=2,
        n_neighbors=args.n_neighbors,
        min_dist=args.min_dist,
        metric="cosine",
        n_jobs=-1,      # use all cores; drop random_state so numba can parallelize
        verbose=True,
    )
    embedding = reducer.fit_transform(vectors)  # [N, 2]
    print(f"  UMAP done — shape {embedding.shape}", flush=True)

    # 6. HDBSCAN clustering
    print(f"Clustering with HDBSCAN (min_cluster_size={args.min_cluster_size})...", flush=True)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=args.min_cluster_size,
        min_samples=10,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embedding)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    noise_pct  = (labels == -1).mean() * 100
    print(f"  {n_clusters} clusters found, {noise_pct:.1f}% noise", flush=True)

    # 7. Label each cluster by most common genre
    vocab["x"]          = embedding[:, 0]
    vocab["y"]          = embedding[:, 1]
    vocab["cluster_id"] = labels

    def label_cluster(group):
        genres = group["top_genre"].dropna().tolist()
        if not genres:
            return "Unknown"
        return Counter(genres).most_common(1)[0][0].title()

    cluster_labels = (
        vocab[vocab["cluster_id"] >= 0]
        .groupby("cluster_id")
        .apply(label_cluster)
        .rename("genre_label")
    )
    vocab = vocab.merge(cluster_labels, on="cluster_id", how="left")
    vocab["genre_label"] = vocab["genre_label"].fillna("Unknown")

    # 8. Build cluster summary table
    cluster_summary = []
    for cid in sorted(set(labels)):
        if cid == -1:
            continue
        mask  = vocab["cluster_id"] == cid
        group = vocab[mask]
        label = group["genre_label"].iloc[0]
        cx    = float(group["x"].mean())
        cy    = float(group["y"].mean())
        color = genre_to_color(label)
        cluster_summary.append({
            "cluster_id":  int(cid),
            "genre_label": label,
            "cx": cx,
            "cy": cy,
            "track_count": int(mask.sum()),
            "color": color,
        })
    clusters_df = pd.DataFrame(cluster_summary)
    print(f"\nTop clusters:", flush=True)
    for _, row in clusters_df.nlargest(10, "track_count").iterrows():
        print(f"  {row['genre_label']:20s}  {row['track_count']:>7,} tracks", flush=True)

    # 9. Save and upload
    print("\nSaving outputs...", flush=True)
    out_points   = _CACHE_DIR / "genre_umap.parquet"
    out_clusters = _CACHE_DIR / "genre_umap_clusters.parquet"

    keep_cols = ["track_uri", "track_name", "artist_name", "x", "y",
                 "cluster_id", "genre_label", "top_genre"]
    vocab[keep_cols].to_parquet(out_points, index=False, compression="zstd")
    clusters_df.to_parquet(out_clusters, index=False, compression="zstd")

    size_pts = out_points.stat().st_size / 1024**2
    size_cl  = out_clusters.stat().st_size / 1024**2
    print(f"  genre_umap.parquet:          {size_pts:.1f} MB", flush=True)
    print(f"  genre_umap_clusters.parquet: {size_cl:.2f} MB", flush=True)

    print("\nUploading to R2...", flush=True)
    r2.upload(out_points,   "embeddings/genre_umap.parquet",          delete_after=True)
    r2.upload(out_clusters, "embeddings/genre_umap_clusters.parquet", delete_after=True)
    r2.usage_summary()

    print("\n✓ UMAP projection done")
    print(f"  {len(vocab):,} tracks projected")
    print(f"  {n_clusters} genre clusters")
    print("\nNext: wire /api/genre-weather/regions to genre_umap_clusters.parquet")


if __name__ == "__main__":
    main()
