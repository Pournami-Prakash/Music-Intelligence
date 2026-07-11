"""
Enrich tracks with LFM-1b (Last.fm 1 Billion) listening event data.

⚠️  STATUS: LFM-1b is permanently unavailable.
    JKU Linz withdrew the dataset due to license issues (confirmed July 2026).
    No download link or mirror exists. This script is kept for reference.

    Alternatives with similar behavioral data:
      - ListenBrainz full dump   → compute_listenbrainz_full.py  (ISRC bridge, running)
      - Echo Nest Taste Profile  → subset of Million Song Dataset, ~2.5 GB
        URL: http://millionsongdataset.com/tasteprofile/
      - Melon Playlist Dataset   → RecSys 2021, Korean platform, similar to MPD
        URL: https://arena.kakao.com/c/7

    If LFM-1b files somehow become available, place them in --data-dir and re-run.

LFM-1b schema (from original paper, Schedl 2016):
  LFM-1b_artists.txt  — artist_id, artist_name
  LFM-1b_tracks.txt   — track_id, track_name, artist_id
  LFM-1b_LEs.txt.gz   — user_id, artist_id, album_id, track_id, timestamp (27 GB)
"""

import argparse
import gzip
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR    = Path(tempfile.gettempdir()) / "track2vec_cache"
_LFM_BASE_URL = "http://www.cp.jku.at/datasets/LFM-1b/"

# LFM-1b file names (download separately — may require filling a form on JKU site)
_TRACKS_FILE  = "LFM-1b_tracks.txt"
_ARTISTS_FILE = "LFM-1b_artists.txt"
_LE_FILE      = "LFM-1b_LEs.txt.gz"   # 27 GB — stream only

_LE_CHUNK     = 5_000_000   # rows per chunk when streaming LE file


def _normalise(s: pd.Series) -> pd.Series:
    return s.fillna("").str.lower().str.strip()


def _load_artists(data_dir: Path) -> pd.DataFrame:
    path = data_dir / _ARTISTS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found.\n"
            f"Download from {_LFM_BASE_URL}{_ARTISTS_FILE}\n"
            f"(JKU may require filling a request form at {_LFM_BASE_URL})"
        )
    # Format: artist_id <tab> artist_name
    df = pd.read_csv(path, sep="\t", header=None, names=["artist_id", "artist_name"],
                     encoding="utf-8", on_bad_lines="skip")
    print(f"  Artists: {len(df):,}", flush=True)
    return df


def _load_tracks(data_dir: Path, artists: pd.DataFrame) -> pd.DataFrame:
    path = data_dir / _TRACKS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found.\n"
            f"Download from {_LFM_BASE_URL}{_TRACKS_FILE}"
        )
    # Format: track_id <tab> artist_id <tab> album_id <tab> track_name
    df = pd.read_csv(path, sep="\t", header=None,
                     names=["lfm_track_id", "artist_id", "album_id", "track_name"],
                     encoding="utf-8", on_bad_lines="skip")
    df = df.merge(artists[["artist_id", "artist_name"]], on="artist_id", how="left")
    print(f"  Tracks: {len(df):,}", flush=True)
    return df


def _match_to_vocab(lfm_tracks: pd.DataFrame, vocab: pd.DataFrame) -> pd.DataFrame:
    """Exact normalised artist+track match. Returns merged DataFrame."""
    lfm_tracks["_title_norm"]  = _normalise(lfm_tracks["track_name"])
    lfm_tracks["_artist_norm"] = _normalise(lfm_tracks["artist_name"])
    vocab["_title_norm"]        = _normalise(vocab["track_name"])
    vocab["_artist_norm"]       = _normalise(vocab["artist_name"])

    matched = vocab.merge(
        lfm_tracks[["lfm_track_id", "_title_norm", "_artist_norm"]],
        on=["_title_norm", "_artist_norm"],
        how="inner",
    )
    print(f"  Exact matches: {len(matched):,}", flush=True)
    return matched


def _aggregate_le(data_dir: Path, matched_ids: set[int]) -> pd.DataFrame:
    """Stream LFM-1b_LEs.txt.gz and aggregate for matched track IDs only."""
    le_path = data_dir / _LE_FILE
    if not le_path.exists():
        print(f"\n[SKIP] {_LE_FILE} not found — skipping listen count aggregation.", flush=True)
        print(f"  To get listen counts, download {_LFM_BASE_URL}{_LE_FILE} (~27 GB)", flush=True)
        return pd.DataFrame(columns=["lfm_track_id", "lfm_total_listens",
                                     "lfm_unique_listeners", "lfm_repeat_ratio"])

    print(f"\nStreaming {_LE_FILE} (~27 GB, this takes a while)...", flush=True)
    # LE format: user_id <tab> artist_id <tab> album_id <tab> track_id <tab> timestamp
    user_track_counts: dict[tuple[int,int], int] = {}  # (user_id, track_id) → count

    total_rows = 0
    matched_rows = 0

    opener = gzip.open if le_path.suffix == ".gz" else open

    with opener(le_path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            try:
                user_id  = int(parts[0])
                track_id = int(parts[3])
            except ValueError:
                continue

            total_rows += 1
            if track_id in matched_ids:
                matched_rows += 1
                key = (user_id, track_id)
                user_track_counts[key] = user_track_counts.get(key, 0) + 1

            if total_rows % 50_000_000 == 0:
                print(f"  {total_rows/1e9:.2f}B rows scanned, "
                      f"{matched_rows:,} matched", flush=True)

    print(f"  Done. {total_rows:,} total rows, {matched_rows:,} matched", flush=True)

    # Aggregate per track
    from collections import defaultdict
    track_total:  dict[int, int] = defaultdict(int)
    track_users:  dict[int, set] = defaultdict(set)

    for (user_id, track_id), count in user_track_counts.items():
        track_total[track_id] += count
        track_users[track_id].add(user_id)

    records = []
    for tid in track_total:
        total    = track_total[tid]
        unique   = len(track_users[tid])
        repeated = sum(1 for (u, t), c in user_track_counts.items()
                       if t == tid and c > 1)
        records.append({
            "lfm_track_id":      tid,
            "lfm_total_listens": total,
            "lfm_unique_listeners": unique,
            "lfm_repeat_ratio":  round(repeated / unique, 4) if unique else 0,
        })

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="/tmp/lfm1b",
                        help="Directory containing LFM-1b files")
    parser.add_argument("--skip-le", action="store_true",
                        help="Skip the 27 GB listening events file (metadata only)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    _CACHE_DIR.mkdir(exist_ok=True)
    r2 = R2Client()

    # ── Check files exist, print instructions if not ──────────────────────────
    missing = []
    for f in [_ARTISTS_FILE, _TRACKS_FILE]:
        if not (data_dir / f).exists():
            missing.append(f)
    if missing:
        print(f"\n{'='*60}", flush=True)
        print("LFM-1b files not found. Download them from:", flush=True)
        print(f"  {_LFM_BASE_URL}", flush=True)
        print(f"\nFiles needed (place in {data_dir}):", flush=True)
        for f in missing:
            print(f"  {f}", flush=True)
        if not args.skip_le:
            print(f"  {_LE_FILE}  (optional, 27 GB — for listen counts)", flush=True)
        print(f"\nNote: JKU may require filling a data request form on their website.", flush=True)
        print("="*60, flush=True)
        sys.exit(1)

    # ── Load vocab ────────────────────────────────────────────────────────────
    vocab_path = _CACHE_DIR / "track2vec_vocab.parquet"
    if not vocab_path.exists():
        r2.download("embeddings/track2vec_vocab.parquet", vocab_path)
    vocab = pd.read_parquet(vocab_path)
    print(f"track2vec vocab: {len(vocab):,} tracks", flush=True)

    # ── Load LFM-1b metadata ──────────────────────────────────────────────────
    print("\nLoading LFM-1b metadata...", flush=True)
    artists   = _load_artists(data_dir)
    lfm_tracks = _load_tracks(data_dir, artists)

    # ── Match to our vocab ────────────────────────────────────────────────────
    print("\nMatching to track2vec vocab...", flush=True)
    matched = _match_to_vocab(lfm_tracks, vocab)

    if matched.empty:
        print("[WARN] No matches found — check encoding/normalisation", flush=True)
        return

    matched_ids = set(matched["lfm_track_id"].tolist())
    print(f"  {len(matched_ids):,} unique LFM track IDs matched", flush=True)

    # ── Aggregate listening events ────────────────────────────────────────────
    if not args.skip_le:
        le_agg = _aggregate_le(data_dir, matched_ids)
    else:
        print("\n[--skip-le] Skipping listen event aggregation", flush=True)
        le_agg = pd.DataFrame(columns=["lfm_track_id", "lfm_total_listens",
                                       "lfm_unique_listeners", "lfm_repeat_ratio"])

    # ── Join and save ─────────────────────────────────────────────────────────
    result = matched[["track_uri", "lfm_track_id"]].copy()
    result["match_type"] = "exact"

    if not le_agg.empty:
        result = result.merge(le_agg, on="lfm_track_id", how="left")
        result["lfm_total_listens"]    = result["lfm_total_listens"].fillna(0).astype(int)
        result["lfm_unique_listeners"] = result["lfm_unique_listeners"].fillna(0).astype(int)
        result["lfm_repeat_ratio"]     = result["lfm_repeat_ratio"].fillna(0)

    result = result.drop_duplicates("track_uri")

    local_out = _CACHE_DIR / "lfm1b_enrichment.parquet"
    result.to_parquet(local_out, index=False, compression="zstd")
    size_kb = local_out.stat().st_size / 1024
    print(f"\nSaved: {len(result):,} rows ({size_kb:.0f} KB)", flush=True)

    r2.upload(local_out, "enrichment/lfm1b_enrichment.parquet")
    r2.usage_summary()
    print(f"\n✓ LFM-1b enrichment done — {len(result):,} tracks enriched")
    if not le_agg.empty:
        with_counts = (result["lfm_total_listens"] > 0).sum()
        print(f"  {with_counts:,} tracks with listen counts")


if __name__ == "__main__":
    main()
