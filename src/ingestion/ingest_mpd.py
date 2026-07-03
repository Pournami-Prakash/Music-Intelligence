"""
Phase 1: Ingest Spotify Million Playlist Dataset (MPD) → Parquet → R2.

Reads 1,000 JSON slice files (~31 GB) without loading all into memory.
Produces three normalized Parquet tables:
  - playlists.parquet       (1M rows)
  - tracks.parquet          (2.2M unique tracks)
  - playlist_tracks.parquet (66M rows — playlist/track/position)

After writing, uploads to R2 and deletes local copies to free disk space.

Usage:
    python src/ingestion/ingest_mpd.py
    python src/ingestion/ingest_mpd.py --skip-upload   # local only
    python src/ingestion/ingest_mpd.py --dry-run       # count files, no write
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import MPD_DIR, DATA_PROCESSED
from src.storage.r2 import R2Client

# ── Schemas ───────────────────────────────────────────────────────────────────

PLAYLIST_SCHEMA = pa.schema([
    pa.field("pid",              pa.int32()),
    pa.field("name",             pa.string()),
    pa.field("num_tracks",       pa.int32()),
    pa.field("num_albums",       pa.int32()),
    pa.field("num_followers",    pa.int32()),
    pa.field("num_edits",        pa.int32()),
    pa.field("duration_ms",      pa.int64()),
    pa.field("collaborative",    pa.bool_()),
    pa.field("modified_at",      pa.int64()),
    pa.field("num_artists",      pa.int32()),
    pa.field("description",      pa.string()),
])

TRACK_SCHEMA = pa.schema([
    pa.field("track_uri",        pa.string()),
    pa.field("track_name",       pa.string()),
    pa.field("artist_uri",       pa.string()),
    pa.field("artist_name",      pa.string()),
    pa.field("album_uri",        pa.string()),
    pa.field("album_name",       pa.string()),
    pa.field("duration_ms",      pa.int32()),
])

PT_SCHEMA = pa.schema([
    pa.field("pid",              pa.int32()),
    pa.field("track_uri",        pa.string()),
    pa.field("pos",              pa.int16()),
])

# ── Parse one JSON slice ───────────────────────────────────────────────────────

def parse_slice(path: Path) -> tuple[list, list, list]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    playlists, tracks, pt_rows = [], [], []

    for pl in data["playlists"]:
        pid = pl["pid"]
        playlists.append({
            "pid":           pid,
            "name":          pl.get("name", ""),
            "num_tracks":    pl.get("num_tracks", 0),
            "num_albums":    pl.get("num_albums", 0),
            "num_followers": pl.get("num_followers", 0),
            "num_edits":     pl.get("num_edits", 0),
            "duration_ms":   pl.get("duration_ms", 0),
            "collaborative": str(pl.get("collaborative", "false")).lower() == "true",
            "modified_at":   pl.get("modified_at", 0),
            "num_artists":   pl.get("num_artists", 0),
            "description":   pl.get("description", ""),
        })

        for track in pl.get("tracks", []):
            uri = track["track_uri"]
            tracks.append({
                "track_uri":   uri,
                "track_name":  track.get("track_name", ""),
                "artist_uri":  track.get("artist_uri", ""),
                "artist_name": track.get("artist_name", ""),
                "album_uri":   track.get("album_uri", ""),
                "album_name":  track.get("album_name", ""),
                "duration_ms": track.get("duration_ms", 0),
            })
            pt_rows.append({
                "pid":       pid,
                "track_uri": uri,
                "pos":       track.get("pos", 0),
            })

    return playlists, tracks, pt_rows


# ── Main ingestion ─────────────────────────────────────────────────────────────

def ingest(skip_upload: bool = False, dry_run: bool = False) -> None:
    json_files = sorted(MPD_DIR.glob("mpd.slice.*.json"))
    if not json_files:
        raise FileNotFoundError(f"No MPD JSON files found in {MPD_DIR}")

    print(f"Found {len(json_files):,} JSON slices in {MPD_DIR}")

    if dry_run:
        print("Dry run — exiting without writing.")
        return

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    pl_path  = DATA_PROCESSED / "playlists.parquet"
    tr_path  = DATA_PROCESSED / "tracks.parquet"
    pt_path  = DATA_PROCESSED / "playlist_tracks.parquet"

    # Use ParquetWriter for streaming writes — never load all 31 GB into memory
    pl_writer = pq.ParquetWriter(pl_path,  PLAYLIST_SCHEMA, compression="zstd")
    pt_writer = pq.ParquetWriter(pt_path,  PT_SCHEMA,       compression="zstd")

    seen_tracks: dict[str, dict] = {}  # track_uri → track dict (dedup)

    total_playlists = 0
    total_pt_rows   = 0

    for json_file in tqdm(json_files, desc="Ingesting MPD slices", unit="slice"):
        pl_rows, tr_rows, pt_rows = parse_slice(json_file)

        # Write playlist batch
        pl_batch = pa.RecordBatch.from_pylist(pl_rows, schema=PLAYLIST_SCHEMA)
        pl_writer.write_batch(pl_batch)

        # Write playlist_tracks batch
        pt_batch = pa.RecordBatch.from_pylist(pt_rows, schema=PT_SCHEMA)
        pt_writer.write_batch(pt_batch)

        # Dedup tracks in memory (2.2M unique tracks — fits easily)
        for t in tr_rows:
            if t["track_uri"] not in seen_tracks:
                seen_tracks[t["track_uri"]] = t

        total_playlists += len(pl_rows)
        total_pt_rows   += len(pt_rows)

    pl_writer.close()
    pt_writer.close()

    # Write deduplicated tracks table
    print(f"\nWriting {len(seen_tracks):,} unique tracks → {tr_path}")
    tr_df = pd.DataFrame(seen_tracks.values())
    tr_df.to_parquet(tr_path, index=False, compression="zstd")

    print(f"\n{'─'*50}")
    print(f"MPD ingestion complete")
    print(f"  Playlists      : {total_playlists:,}")
    print(f"  Unique tracks  : {len(seen_tracks):,}")
    print(f"  Track-playlist : {total_pt_rows:,}")
    print(f"  playlists.parquet      : {pl_path.stat().st_size/1024**2:.1f} MB")
    print(f"  tracks.parquet         : {tr_path.stat().st_size/1024**2:.1f} MB")
    print(f"  playlist_tracks.parquet: {pt_path.stat().st_size/1024**2:.1f} MB")
    print(f"{'─'*50}\n")

    if skip_upload:
        print("Skipping R2 upload (--skip-upload set).")
        return

    # Upload to R2 and free local disk
    r2 = R2Client()
    r2.usage_summary()

    for local_path, r2_key in [
        (pl_path,  "processed/playlists.parquet"),
        (tr_path,  "processed/tracks.parquet"),
        (pt_path,  "processed/playlist_tracks.parquet"),
    ]:
        r2.upload(local_path, r2_key, delete_after=True)

    r2.usage_summary()
    print("All Parquet files uploaded to R2 and removed locally.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest MPD JSON → Parquet → R2")
    parser.add_argument("--skip-upload", action="store_true", help="Write Parquet locally but don't upload to R2")
    parser.add_argument("--dry-run",     action="store_true", help="Count files only, no writes")
    args = parser.parse_args()

    ingest(skip_upload=args.skip_upload, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
