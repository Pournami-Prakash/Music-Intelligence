"""
Enrich tracks with Free Music Archive (FMA) metadata.

Downloads fma_metadata.zip (342 MB), extracts:
  - tracks.csv    → play_count, artist name, title, genres, date_created
  - echonest.csv  → audio features (tempo, energy, valence, danceability, etc.)

Join strategy: artist_name + track_name fuzzy match against track2vec vocab.
Falls back to Last.fm artist name match for tracks without exact title match.

Output: enrichment/fma_enrichment.parquet
Columns:
    spotify_track_uri, fma_track_id, fma_play_count,
    fma_genres, fma_tempo, fma_energy, fma_valence,
    fma_danceability, fma_acousticness, fma_instrumentalness,
    match_type  (exact / artist_fuzzy)

Usage:
    python src/compute/compute_fma_enrichment.py
"""

import sys
import tempfile
import zipfile
from pathlib import Path

import requests

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR   = Path(tempfile.gettempdir()) / "track2vec_cache"
_FMA_URL     = "https://os.unil.cloud.switch.ch/fma/fma_metadata.zip"
_FMA_ZIP     = _CACHE_DIR / "fma_metadata.zip"
_FMA_DIR     = _CACHE_DIR / "fma_metadata"

_ECHONEST_FEATURES = [
    "energy", "valence", "danceability", "acousticness",
    "instrumentalness", "liveness", "speechiness", "tempo",
]


def _download_fma():
    if _FMA_ZIP.exists():
        print(f"Using cached FMA metadata zip ({_FMA_ZIP.stat().st_size/1e6:.0f} MB)", flush=True)
        return
    print(f"Downloading FMA metadata (~342 MB)...", flush=True)
    print(f"  URL: {_FMA_URL}", flush=True)

    with requests.get(_FMA_URL, stream=True, timeout=120, verify=False) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(_FMA_ZIP, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"  {downloaded/total*100:.0f}%", end="\r", flush=True)
    print(f"\n  Downloaded: {_FMA_ZIP.stat().st_size/1e6:.0f} MB", flush=True)


def _extract_fma():
    if _FMA_DIR.exists() and (_FMA_DIR / "tracks.csv").exists():
        print("Using cached extracted FMA files", flush=True)
        return
    _FMA_DIR.mkdir(exist_ok=True)
    print("Extracting fma_metadata.zip...", flush=True)
    with zipfile.ZipFile(_FMA_ZIP) as zf:
        for name in ["fma_metadata/tracks.csv", "fma_metadata/echonest.csv",
                     "fma_metadata/genres.csv"]:
            try:
                zf.extract(name, _CACHE_DIR)
                print(f"  Extracted {name}", flush=True)
            except KeyError:
                print(f"  [skip] {name} not in zip", flush=True)


def _load_tracks() -> pd.DataFrame:
    """Load FMA tracks.csv — multi-level header, needs special handling."""
    path = _FMA_DIR / "tracks.csv"
    # FMA uses a multi-level header (2 rows)
    tracks = pd.read_csv(path, header=[0, 1], low_memory=False)
    # Flatten columns: ('track', 'title') → 'track_title'
    tracks.columns = ["_".join(col).strip("_") for col in tracks.columns]
    tracks = tracks.rename_axis("fma_track_id").reset_index()
    tracks["fma_track_id"] = pd.to_numeric(tracks["fma_track_id"], errors="coerce")
    tracks = tracks.dropna(subset=["fma_track_id"])
    tracks["fma_track_id"] = tracks["fma_track_id"].astype(int)
    return tracks


def _load_echonest() -> pd.DataFrame:
    """Load echonest.csv — multi-level header."""
    path = _FMA_DIR / "echonest.csv"
    if not path.exists():
        return pd.DataFrame()
    echo = pd.read_csv(path, header=[0, 1, 2], low_memory=False)
    echo.columns = ["_".join(str(c) for c in col).strip("_") for col in echo.columns]
    echo = echo.rename_axis("fma_track_id").reset_index()
    echo["fma_track_id"] = pd.to_numeric(echo["fma_track_id"], errors="coerce")
    echo = echo.dropna(subset=["fma_track_id"])
    echo["fma_track_id"] = echo["fma_track_id"].astype(int)
    return echo


def _normalise(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().str.strip()


def main():
    _CACHE_DIR.mkdir(exist_ok=True)
    r2 = R2Client()

    # ── 1. Download + extract FMA metadata ───────────────────────────────────
    _download_fma()
    _extract_fma()

    # ── 2. Load FMA tables ────────────────────────────────────────────────────
    print("Loading FMA tracks.csv...", flush=True)
    tracks = _load_tracks()
    print(f"  {len(tracks):,} FMA tracks", flush=True)

    print("Loading echonest.csv...", flush=True)
    echo = _load_echonest()
    print(f"  {len(echo):,} FMA tracks with Echonest features", flush=True)

    # ── 3. Load our track2vec vocab ───────────────────────────────────────────
    vocab_path = _CACHE_DIR / "track2vec_vocab.parquet"
    if not vocab_path.exists():
        print("Downloading track2vec vocab...", flush=True)
        r2.download("embeddings/track2vec_vocab.parquet", vocab_path)
    vocab = pd.read_parquet(vocab_path)   # track_uri, track_name, artist_name
    print(f"  track2vec vocab: {len(vocab):,} tracks", flush=True)

    # ── 4. Identify FMA columns (confirmed multi-level header schema) ─────────
    # After flattening: ('track','title') → 'track_title', ('artist','name') → 'artist_name'
    title_col  = "track_title"
    artist_col = "artist_name"
    play_col   = "track_listens"
    genre_col  = "track_genre_top"
    lang_col   = "track_language_code"

    available = [c for c in [title_col, artist_col, play_col, genre_col, lang_col]
                 if c in tracks.columns]
    missing   = [c for c in [title_col, artist_col] if c not in tracks.columns]
    print(f"\nFMA columns found: {available}", flush=True)

    if missing:
        print(f"[WARN] Expected columns missing: {missing}", flush=True)
        print(f"  Available columns (first 30): {list(tracks.columns[:30])}", flush=True)
        # Fallback: try to detect
        title_col  = next((c for c in tracks.columns if "title" in c), None)
        artist_col = next((c for c in tracks.columns if "artist" in c and "name" in c), None)
        play_col   = next((c for c in tracks.columns if "listens" in c), None)
        genre_col  = next((c for c in tracks.columns if "genre_top" in c), None)
        if not title_col or not artist_col:
            print("[ERROR] Cannot find title/artist columns.")
            sys.exit(1)

    # Normalise for matching
    tracks["_title_norm"]  = _normalise(tracks[title_col])
    tracks["_artist_norm"] = _normalise(tracks[artist_col])
    vocab["_title_norm"]   = _normalise(vocab["track_name"])
    vocab["_artist_norm"]  = _normalise(vocab["artist_name"])

    # ── 5. Join: exact artist+title match ────────────────────────────────────
    print("\nJoining on normalised artist + title...", flush=True)
    merged = vocab.merge(
        tracks[["fma_track_id", "_title_norm", "_artist_norm",
                play_col or "fma_track_id",
                *(c for c in [genre_col] if c)]],
        on=["_title_norm", "_artist_norm"],
        how="inner",
    )
    merged["match_type"] = "exact"
    print(f"  Exact matches: {len(merged):,}", flush=True)

    # Artist-only fuzzy: match any track under the same artist
    unmatched_uris = set(vocab["track_uri"]) - set(merged["track_uri"])
    vocab_unmatched = vocab[vocab["track_uri"].isin(unmatched_uris)]

    artist_map = tracks.groupby("_artist_norm").agg(
        fma_track_id=(  "fma_track_id", "first"),
        **({play_col:   (play_col, "sum")} if play_col else {}),
    ).reset_index()

    artist_merged = vocab_unmatched.merge(
        artist_map, on="_artist_norm", how="inner"
    )
    artist_merged["match_type"] = "artist_fuzzy"
    print(f"  Artist-fuzzy matches: {len(artist_merged):,}", flush=True)

    combined = pd.concat([merged, artist_merged], ignore_index=True)

    # ── 6. Join Echonest audio features ──────────────────────────────────────
    if not echo.empty:
        echo_cols = [c for c in echo.columns if any(f in c for f in _ECHONEST_FEATURES)]
        echo_slim = echo[["fma_track_id"] + echo_cols].copy()
        # Rename to flat feature names
        rename = {c: c.split("_")[-1] for c in echo_cols}
        echo_slim = echo_slim.rename(columns=rename)
        echo_slim.columns = ["fma_track_id"] + [f"fma_{c}" for c in
                                                  echo_slim.columns[1:]]
        combined = combined.merge(echo_slim, on="fma_track_id", how="left")

    # ── 7. Final output ───────────────────────────────────────────────────────
    keep = ["track_uri", "fma_track_id", "match_type"]
    if play_col and play_col in combined.columns:
        combined = combined.rename(columns={play_col: "fma_play_count"})
        keep.append("fma_play_count")
    if genre_col and genre_col in combined.columns:
        combined = combined.rename(columns={genre_col: "fma_genres"})
        keep.append("fma_genres")
    fma_feat_cols = [c for c in combined.columns if c.startswith("fma_") and c not in keep]
    keep += fma_feat_cols

    result = combined[[c for c in keep if c in combined.columns]].drop_duplicates("track_uri")
    print(f"\nFinal: {len(result):,} tracks enriched with FMA data", flush=True)

    local_out = _CACHE_DIR / "fma_enrichment.parquet"
    result.to_parquet(local_out, index=False, compression="zstd")
    size_kb = local_out.stat().st_size / 1024
    print(f"Saved: {size_kb:.0f} KB", flush=True)

    r2.upload(local_out, "enrichment/fma_enrichment.parquet")
    r2.usage_summary()
    print(f"\n✓ FMA enrichment done — {len(result):,} tracks")
    print(f"  exact: {(result['match_type']=='exact').sum():,}  "
          f"artist_fuzzy: {(result['match_type']=='artist_fuzzy').sum():,}")


if __name__ == "__main__":
    main()
