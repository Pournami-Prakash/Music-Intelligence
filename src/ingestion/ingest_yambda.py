"""
Ingest YaMBDa dataset from HuggingFace.
https://huggingface.co/datasets/yandex/yambda

YaMBDa: 4.79B user interactions from Yandex Music (May 2025)
- listens: uid, item_id, timestamp, is_organic, played_ratio_pct, track_length_seconds
- likes:   uid, item_id, timestamp, is_organic
- dislikes: uid, item_id, timestamp, is_organic
- embeddings: item_id, embed, normalized_embed (7.72M tracks, CNN contrastive learning)

Available sizes: 50m (dev), 500m (staging), 5b (full)
Embeddings are shared across all sizes — downloaded once from flat/5b.

Usage:
    python src/ingestion/ingest_yambda.py --size 50m
    python src/ingestion/ingest_yambda.py --size 500m --skip-embeddings
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

hf_token = os.getenv("HF_TOKEN")
if hf_token:
    os.environ["HF_TOKEN"] = hf_token

sys.path.append(str(Path(__file__).parent.parent.parent))
from config import DATA_RAW

YAMBDA_DIR = DATA_RAW / "yambda"

SIZES = {
    "50m":  "flat/50m",
    "500m": "flat/500m",
    "5b":   "flat/5b",
}

INTERACTION_FILES = ["listens", "likes", "dislikes"]


# ── Download ──────────────────────────────────────────────────────────────────

def download_interactions(size: str) -> None:
    data_dir = SIZES[size]
    save_dir = YAMBDA_DIR / size
    save_dir.mkdir(parents=True, exist_ok=True)

    for name in INTERACTION_FILES:
        out_path = save_dir / f"{name}.parquet"
        if out_path.exists():
            print(f"  [skip] {name}.parquet already exists")
            continue

        print(f"  → downloading {name}.parquet ({size.upper()})")
        ds = load_dataset(
            "yandex/yambda",
            data_dir=data_dir,
            data_files=f"{name}.parquet",
            split="train",
        )
        df = ds.to_pandas()
        df.to_parquet(out_path, index=False)
        print(f"     saved {len(df):,} rows → {out_path}")


def download_embeddings() -> None:
    """Embeddings are the same across all sizes. Download once from flat/5b."""
    embed_dir = YAMBDA_DIR / "embeddings"
    embed_dir.mkdir(parents=True, exist_ok=True)
    out_path = embed_dir / "embeddings.parquet"

    if out_path.exists():
        print(f"  [skip] embeddings already downloaded")
        return

    print(f"  → downloading embeddings (7.72M tracks, this may take a while)")

    token = os.getenv("HF_TOKEN") or True  # True = use cached login if available

    ds = load_dataset(
        "yandex/yambda",
        data_files="embeddings.parquet",  # root-level, not under flat/5b
        split="train",
        download_mode="force_redownload",
        token=token,
    )
    df = ds.to_pandas()
    df.to_parquet(out_path, index=False)
    print(f"     saved {len(df):,} track embeddings → {out_path}")


# ── Profile ───────────────────────────────────────────────────────────────────

def profile(size: str) -> None:
    save_dir = YAMBDA_DIR / size
    print(f"\n{'─'*50}")
    print(f"YaMBDa {size.upper()} — Data Profile")
    print(f"{'─'*50}")

    for name in INTERACTION_FILES:
        path = save_dir / f"{name}.parquet"
        if not path.exists():
            print(f"\n{name.upper()}: not downloaded")
            continue

        df = pd.read_parquet(path)
        print(f"\n{name.upper()} ({len(df):,} rows)")
        print(f"  Unique users  : {df['uid'].nunique():,}")
        print(f"  Unique tracks : {df['item_id'].nunique():,}")

        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], unit="s")
            print(f"  Date range    : {ts.min().date()} → {ts.max().date()}")

        if "is_organic" in df.columns:
            organic_pct = df["is_organic"].mean() * 100
            print(f"  Organic       : {organic_pct:.1f}%  |  Recommended: {100 - organic_pct:.1f}%")

        if "played_ratio_pct" in df.columns:
            print(f"  Avg play ratio: {df['played_ratio_pct'].mean():.1f}%")
            fully_played = (df["played_ratio_pct"] >= 80).mean() * 100
            skipped      = (df["played_ratio_pct"] <= 20).mean() * 100
            print(f"  Fully played  : {fully_played:.1f}%  |  Skipped (≤20%): {skipped:.1f}%")

    embed_path = YAMBDA_DIR / "embeddings" / "embeddings.parquet"
    if embed_path.exists():
        df = pd.read_parquet(embed_path, columns=["item_id"])
        print(f"\nEMBEDDINGS")
        print(f"  Tracks with embeddings: {len(df):,}")
        # check embed dimension
        df_full = pd.read_parquet(embed_path).head(1)
        if "embed" in df_full.columns:
            embed_dim = len(df_full["embed"].iloc[0])
            print(f"  Embedding dimension   : {embed_dim}")

    print(f"{'─'*50}\n")


# ── Stream (no download) ──────────────────────────────────────────────────────

def stream_sample(size: str = "50m", n: int = 5) -> None:
    """Stream a few rows without downloading — useful for quick inspection."""
    print(f"\nStreaming {n} rows from YaMBDa {size.upper()} listens (no download):")
    ds = load_dataset(
        "yandex/yambda",
        data_dir=SIZES[size],
        data_files="listens.parquet",
        streaming=True,
        split="train",
    )
    for i, row in enumerate(ds.take(n)):
        print(f"  {row}")
        if i >= n - 1:
            break


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest YaMBDa from HuggingFace")
    parser.add_argument(
        "--size",
        choices=["50m", "500m", "5b"],
        default="50m",
        help="Dataset size to download (default: 50m)",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip downloading track embeddings",
    )
    parser.add_argument(
        "--stream-only",
        action="store_true",
        help="Stream a few rows without downloading",
    )
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="Profile already-downloaded data without re-downloading",
    )
    args = parser.parse_args()

    if args.stream_only:
        stream_sample(args.size)
        return

    if args.profile_only:
        profile(args.size)
        return

    print(f"\nYaMBDa ingestion — size: {args.size.upper()}")
    print(f"Output directory: {YAMBDA_DIR}\n")

    download_interactions(args.size)

    if not args.skip_embeddings:
        download_embeddings()

    profile(args.size)


if __name__ == "__main__":
    main()
