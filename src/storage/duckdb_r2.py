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
    """Return a DuckDB connection wired to R2 via httpfs."""
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""
        SET s3_endpoint='{_ACCOUNT_ID}.r2.cloudflarestorage.com';
        SET s3_access_key_id='{_ACCESS_KEY}';
        SET s3_secret_access_key='{_SECRET_KEY}';
        SET s3_region='auto';
        SET s3_use_ssl=true;
        SET s3_url_style='path';
    """)
    return con
