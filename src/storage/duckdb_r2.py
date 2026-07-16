"""
DuckDB connection pre-configured to query R2 Parquet files directly via httpfs.

Usage:
    from src.storage.duckdb_r2 import get_con, R2_PATH

    con = get_con()
    df = con.execute(f"SELECT COUNT(*) FROM read_parquet('{R2_PATH}/processed/tracks.parquet')").df()
"""

import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

_ACCOUNT_ID  = os.getenv("R2_ACCOUNT_ID", "")
_BUCKET      = os.getenv("R2_BUCKET", "music-intelligence-atlas")
_ACCESS_KEY  = os.getenv("R2_ACCESS_KEY_ID", "")
_SECRET_KEY  = os.getenv("R2_SECRET_ACCESS_KEY", "")

R2_PATH = f"s3://{_BUCKET}"


def get_con() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection wired to R2 via httpfs.

    memory_limit/threads are capped low on purpose: this backend streams big
    local parquets (artist_edges, editorial_playlist_tracks, track_stats) through
    DuckDB, and by default DuckDB's buffer pool would retain hundreds of MB of
    scanned data (sized to 80% of host RAM). Capping it keeps the whole process
    comfortably inside a 512 MB serving box — it spills to a temp dir instead of
    hoarding RAM. Overridable via DUCKDB_MEMORY_LIMIT / DUCKDB_THREADS.
    """
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    mem_limit = os.getenv("DUCKDB_MEMORY_LIMIT", "96MB")
    # threads=1 + no insertion-order preservation keep a query's working-memory
    # small enough to run inside a ~64-96 MB budget on a 512 MB box (DuckDB's own
    # OOM hint). Fewer threads also means fewer allocator arenas → less resident
    # fragmentation. Slower, but the results are cached.
    threads   = os.getenv("DUCKDB_THREADS", "1")

    # R2 credentials go through the secrets manager rather than `SET s3_*`: the
    # SET settings are connection-local and are NOT inherited by con.cursor(),
    # so cursor-based queries (every request path) would fall back to AWS and
    # fail. A secret is instance-global and inherited by all cursors.
    con.execute(f"""
        CREATE SECRET r2 (
            TYPE S3,
            KEY_ID '{_ACCESS_KEY}',
            SECRET '{_SECRET_KEY}',
            ENDPOINT '{_ACCOUNT_ID}.r2.cloudflarestorage.com',
            REGION 'auto',
            URL_STYLE 'path',
            USE_SSL true
        );
    """)
    con.execute(f"""
        SET memory_limit='{mem_limit}';
        SET threads={threads};
        SET preserve_insertion_order=false;
        SET temp_directory='{os.path.join(os.getenv("TMPDIR", "/tmp"), "duckdb_spill")}';
    """)
    return con
