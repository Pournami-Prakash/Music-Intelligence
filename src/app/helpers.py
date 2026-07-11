"""Pure helper functions shared across route modules."""

import re
from typing import Optional

import numpy as np
import pandas as pd


_MIN_SUBSTR_LEN = 3  # queries shorter than this skip fuzzy substring matching


def _to_list(x) -> list:
    """Coerce a parquet column value (numpy array, list, or None) to a plain Python list."""
    if x is None:
        return []
    try:
        return list(x)
    except TypeError:
        return []


def _resolve_artist_row(
    df: pd.DataFrame,
    name: str,
    uri: Optional[str] = None,
) -> Optional[pd.Series]:
    """Return the best-matching row for an artist from any artist-keyed dataframe.

    Resolution order:
      1. Exact artist_uri match (unambiguous)
      2. Exact lowercase name match
      3. Substring match (only for queries >= _MIN_SUBSTR_LEN chars)
    When multiple rows match, the one with the highest playlist_count wins.
    """
    if uri and "artist_uri" in df.columns:
        row = df[df["artist_uri"] == uri]
        if not row.empty:
            if "playlist_count" in row.columns:
                row = row.sort_values("playlist_count", ascending=False)
            return row.iloc[0]

    row = df[df["artist_name"].str.lower() == name.lower()]
    if row.empty and len(name) >= _MIN_SUBSTR_LEN:
        row = df[df["artist_name"].str.lower().str.contains(
            re.escape(name.lower()), na=False)]
    if row.empty:
        return None

    if "playlist_count" in row.columns:
        row = row.sort_values("playlist_count", ascending=False)
    return row.iloc[0]


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _extract_playlist_id(url: str) -> Optional[str]:
    """Extract a Spotify playlist ID from a full URL or a bare 22-character ID."""
    m = re.search(r"playlist[/:]([A-Za-z0-9]{22})", url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9]{22}", url.strip()):
        return url.strip()
    return None


def _uri_to_vec(uri: str, index, vocab: pd.DataFrame) -> Optional[np.ndarray]:
    """Look up a track URI in the FAISS vocab and reconstruct its embedding vector."""
    row = vocab[vocab["track_uri"] == uri]
    if row.empty:
        return None
    idx = int(row.iloc[0]["idx"])
    vec = np.zeros((1, index.d), dtype="float32")
    index.reconstruct(idx, vec[0])
    return vec
