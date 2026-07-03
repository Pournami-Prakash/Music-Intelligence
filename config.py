from pathlib import Path

ROOT = Path(__file__).parent

# Data paths
DATA_RAW        = ROOT / "data" / "raw"
DATA_INTERIM    = ROOT / "data" / "interim"
DATA_PROCESSED  = ROOT / "data" / "processed"

# Source dataset — update this to point at your MPD location
MPD_DIR = Path("/Users/pournami/SpotifyAnalysis/spotify_million_playlist_dataset/data")

# Parquet outputs
PLAYLISTS_PARQUET       = DATA_PROCESSED / "playlists.parquet"
TRACKS_PARQUET          = DATA_PROCESSED / "tracks.parquet"
PLAYLIST_TRACKS_PARQUET = DATA_PROCESSED / "playlist_tracks.parquet"

# Embeddings
EMBEDDINGS_DIR = DATA_PROCESSED / "embeddings"

# DuckDB
DUCKDB_PATH = DATA_PROCESSED / "atlas.duckdb"
