"""
Build a FAISS HNSW index over 599K track2vec embeddings.

Index type: IndexHNSWFlat(128, M=16)
  - No training required
  - ~400 MB on disk
  - Query time: <5ms for k=20 at ef=64
  - Recall@20: ~97% vs brute force

Output: embeddings/track2vec_hnsw.faiss  (uploaded to R2)

Usage:
    python src/compute/compute_faiss_index.py
"""

import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"
_HNSW_M    = 16      # neighbours per node — higher = better recall, larger index
_EF_BUILD  = 64      # ef_construction — higher = better recall, slower build


def main():
    import faiss

    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    # ── 1. Download embeddings ────────────────────────────────────────────────
    vecs_path = _CACHE_DIR / "embeddings_track2vec_128.npy"
    if not vecs_path.exists():
        print("Downloading track2vec_128.npy (307 MB)...", flush=True)
        r2.download("embeddings/track2vec_128.npy", vecs_path)
    else:
        print(f"Using cached {vecs_path.name}", flush=True)

    print("Loading vectors...", flush=True)
    vecs = np.load(vecs_path).astype("float32")
    n, d = vecs.shape
    print(f"  {n:,} vectors × {d} dims", flush=True)

    # ── 2. L2-normalize (cosine similarity via inner product after normalising) ─
    print("Normalising to unit length (cosine similarity)...", flush=True)
    faiss.normalize_L2(vecs)

    # ── 3. Build HNSW index ───────────────────────────────────────────────────
    print(f"Building IndexHNSWFlat (M={_HNSW_M}, ef_construction={_EF_BUILD})...", flush=True)
    index = faiss.IndexHNSWFlat(d, _HNSW_M, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = _EF_BUILD

    t0 = time.time()
    index.add(vecs)
    elapsed = time.time() - t0
    print(f"  Added {index.ntotal:,} vectors in {elapsed:.1f}s", flush=True)

    # Set search-time ef (higher = better recall, slower)
    index.hnsw.efSearch = 64

    # ── 4. Quick sanity check ────────────────────────────────────────────────
    print("Sanity check: querying first vector for top-5 neighbours...", flush=True)
    D, I = index.search(vecs[:1], 6)
    print(f"  Nearest neighbours (by cosine sim): indices {I[0].tolist()}", flush=True)
    print(f"  Scores: {[round(float(s), 4) for s in D[0]]}", flush=True)
    assert I[0][0] == 0, "First result should be the query itself"

    # ── 5. Save and upload ────────────────────────────────────────────────────
    out = _CACHE_DIR / "track2vec_hnsw.faiss"
    print(f"Writing index...", flush=True)
    faiss.write_index(index, str(out))
    size_mb = out.stat().st_size / 1e6
    print(f"  Saved: {size_mb:.1f} MB", flush=True)

    r2.upload(out, "embeddings/track2vec_hnsw.faiss")
    r2.usage_summary()
    print("\n✓ FAISS index done")


if __name__ == "__main__":
    main()
