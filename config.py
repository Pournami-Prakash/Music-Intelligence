"""
Static path configuration for local ingestion scripts.

All R2-backed paths (parquets, embeddings) are handled via src/storage/r2.py.
This file is only used by the one-time ingestion scripts in src/ingestion/.

Set MPD_DIR to point at your local copy of the Spotify Million Playlist Dataset.
The dataset is available via the ACM RecSys Challenge 2018:
https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent

DATA_RAW       = ROOT / "data" / "raw"
DATA_INTERIM   = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"

# Set this to the "data/" folder inside your MPD download, or via MPD_DIR env var.
MPD_DIR = Path(os.environ.get("MPD_DIR", "data/mpd"))

PLAYLISTS_PARQUET       = DATA_PROCESSED / "playlists.parquet"
TRACKS_PARQUET          = DATA_PROCESSED / "tracks.parquet"
PLAYLIST_TRACKS_PARQUET = DATA_PROCESSED / "playlist_tracks.parquet"

EMBEDDINGS_DIR = DATA_PROCESSED / "embeddings"
DUCKDB_PATH    = DATA_PROCESSED / "atlas.duckdb"
