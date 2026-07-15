"""
One-time: push track2vec vectors → Upstash Vector, so the API no longer needs
the 393 MB FAISS index in memory. Doppelganger / Transition query Upstash over HTTP.

  id       = str(idx)  (matches vocab.idx / FAISS position)
  vector   = normalized 128-d track2vec vector (reconstructed from FAISS)
  metadata = {uri, title, artist}

Vectors are already L2-normalized, so Upstash COSINE == the FAISS inner-product
ranking. Idempotent (upsert), resumable via --start.

Usage:  python src/compute/export_vectors_to_upstash.py [--start 0] [--batch 1000]
"""
import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_URL   = os.environ["UPSTASH_VECTOR_REST_URL"].rstrip("/")
_TOKEN = os.environ["UPSTASH_VECTOR_REST_TOKEN"]
_TMP   = Path(tempfile.gettempdir())


def _cached(key: str, name: str) -> Path:
    p = _TMP / name
    if not p.exists():
        print(f"  downloading {key} …", flush=True)
        R2Client().download(key, str(p))
    return p


def main(start: int, batch: int) -> None:
    idx_path   = _cached("embeddings/track2vec_hnsw.faiss", "track2vec_hnsw_check.faiss")
    vocab_path = _cached("embeddings/track2vec_vocab.parquet", "track2vec_vocab_check.parquet")

    index = faiss.read_index(str(idx_path))
    vocab = pd.read_parquet(vocab_path).reset_index(drop=True)
    n = min(index.ntotal, len(vocab))
    print(f"vectors to upsert: {n:,}  (dim={index.d}) — starting at {start:,}", flush=True)

    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"})

    t0 = time.time()
    for lo in range(start, n, batch):
        hi = min(lo + batch, n)
        payload = []
        for i in range(lo, hi):
            v = np.zeros(index.d, dtype="float32")
            index.reconstruct(i, v)
            row = vocab.iloc[i]
            payload.append({
                "id":       str(i),
                "vector":   v.tolist(),
                "metadata": {
                    "uri":    str(row["track_uri"]),
                    "title":  str(row["track_name"]),
                    "artist": str(row["artist_name"]),
                },
            })
        # retry on transient failures
        for attempt in range(4):
            r = sess.post(f"{_URL}/upsert", json=payload, timeout=60)
            if r.status_code == 200:
                break
            wait = 2 * (attempt + 1)
            print(f"  [{lo}] HTTP {r.status_code}: {r.text[:120]} — retry in {wait}s", flush=True)
            time.sleep(wait)
        else:
            print(f"  FAILED at {lo}; resume with --start {lo}", flush=True)
            return

        if (hi // batch) % 20 == 0 or hi == n:
            rate = hi / max(time.time() - t0, 1e-6)
            eta = (n - hi) / rate if rate else 0
            print(f"  {hi:,}/{n:,}  ({rate:.0f}/s, ETA {eta/60:.1f}m)", flush=True)

    print(f"\n✓ upserted {n:,} vectors in {(time.time()-t0)/60:.1f}m", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--batch", type=int, default=1000)
    main(**vars(ap.parse_args()))
