"""
Fill empty artist_genres tags using artist_lastfm tags as fallback.

Of the 1,876 artists with no MusicBrainz tags, 1,620 already have
tags in artist_lastfm — this script merges them in-place.

Output: enrichment/artist_genres.parquet (updated in R2)
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP = Path(tempfile.gettempdir())


def _is_empty(x) -> bool:
    if x is None:
        return True
    try:
        return len(list(x)) == 0
    except TypeError:
        return True


def main():
    r2 = R2Client()

    print("Downloading artist_genres.parquet …")
    genres_path = _TMP / "artist_genres_merge.parquet"
    r2.download("enrichment/artist_genres.parquet", str(genres_path))
    genres_df = pd.read_parquet(genres_path)

    print("Downloading artist_lastfm.parquet …")
    lastfm_path = _TMP / "artist_lastfm_merge.parquet"
    r2.download("enrichment/artist_lastfm.parquet", str(lastfm_path))
    lastfm_df = pd.read_parquet(lastfm_path)

    # Build lastfm tag lookup: lowercase name → tags list
    lastfm_tags: dict[str, list[str]] = {}
    for _, row in lastfm_df.iterrows():
        raw = row.get("tags")
        if raw is None:
            continue
        try:
            tags = list(raw)
        except TypeError:
            continue
        if tags:
            lastfm_tags[row["artist_name"].lower()] = tags

    empty_mask = genres_df["tags"].apply(_is_empty)
    n_empty_before = int(empty_mask.sum())
    print(f"Artists with empty tags before merge: {n_empty_before} / {len(genres_df)}")

    filled = 0
    for idx, row in genres_df[empty_mask].iterrows():
        name_lower = row["artist_name"].lower()
        if name_lower in lastfm_tags:
            genres_df.at[idx, "tags"] = np.array(lastfm_tags[name_lower], dtype=object)
            filled += 1

    empty_after = int(genres_df["tags"].apply(_is_empty).sum())
    print(f"Filled via lastfm fallback: {filled}")
    print(f"Still empty after merge:   {n_empty_before - filled} (truly tagless)")
    print(f"Total empty now:           {empty_after} / {len(genres_df)}")

    # Normalize tags column to Python lists so PyArrow schema is consistent
    def _to_list(x):
        if x is None:
            return []
        try:
            arr = np.asarray(x)
            if arr.ndim == 0:
                return [str(arr.item())] if arr.item() else []
            return list(arr)
        except (TypeError, ValueError):
            return []

    genres_df["tags"] = genres_df["tags"].apply(_to_list)

    out_path = _TMP / "artist_genres_updated.parquet"
    genres_df.to_parquet(out_path, index=False)
    print(f"\nUploading updated artist_genres.parquet …")
    r2.upload(str(out_path), "enrichment/artist_genres.parquet")
    print("Done.")


if __name__ == "__main__":
    main()
