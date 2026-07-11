"""
Process downloaded Spotify chart CSVs into chart_history.parquet.

Input:  /tmp/spotify_charts_csv/regional-global-weekly-*.csv
Output: enrichment/chart_history.parquet (uploaded to R2)

Per-track columns produced:
    track_uri, track_name, artist_name,
    chart_peak,        -- best rank ever achieved (1 = #1)
    peak_date,         -- date of that peak
    first_charted,     -- first week it appeared
    last_charted,      -- last week it appeared
    total_weeks,       -- number of weeks it charted
    max_streams_week,  -- highest single-week stream count
    total_chart_streams -- sum of streams across all charted weeks

Usage:
    python src/compute/compute_chart_history.py
    python src/compute/compute_chart_history.py --csv-dir /tmp/spotify_charts_csv
"""

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_DEFAULT_CSV_DIR = Path("/tmp/spotify_charts_csv")
_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"


def parse_date_from_filename(fname: str) -> str:
    """regional-global-weekly-2024-01-04.csv → '2024-01-04'"""
    return fname.replace("regional-global-weekly-", "").replace(".csv", "")


def load_all_csvs(csv_dir: Path) -> pd.DataFrame:
    files = sorted(csv_dir.glob("regional-global-weekly-*.csv"))
    if not files:
        raise FileNotFoundError(f"No chart CSVs found in {csv_dir}. Run download_chart_csvs.py first.")

    print(f"Loading {len(files)} weekly chart files...", flush=True)
    chunks = []
    for f in files:
        try:
            df = pd.read_csv(f)
            # skip placeholders (header-only) and HTML files accidentally saved
            if df.empty or "uri" not in df.columns or len(df) < 10:
                continue
            df["chart_date"] = parse_date_from_filename(f.name)
            chunks.append(df)
        except Exception as e:
            print(f"  [skip] {f.name}: {e}")

    if not chunks:
        raise ValueError("All CSV files were empty or malformed.")

    combined = pd.concat(chunks, ignore_index=True)
    print(f"  {len(combined):,} chart rows from {len(chunks)} weeks", flush=True)
    return combined


def build_chart_history(df: pd.DataFrame) -> pd.DataFrame:
    # Normalise
    df["chart_date"] = pd.to_datetime(df["chart_date"])
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    df["streams"] = pd.to_numeric(df["streams"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["uri", "rank"])

    # Flatten multi-artist names to first artist
    df["artist_name"] = df["artist_names"].str.split(",").str[0].str.strip()

    # Aggregate per track URI
    agg = df.groupby("uri").agg(
        track_name       = ("track_name",   "first"),
        artist_name      = ("artist_name",  "first"),
        chart_peak       = ("rank",         "min"),        # best = lowest number
        total_weeks      = ("uri",          "count"),
        max_streams_week = ("streams",      "max"),
        total_chart_streams = ("streams",   "sum"),
        first_charted    = ("chart_date",   "min"),
        last_charted     = ("chart_date",   "max"),
    ).reset_index()

    # Peak date: the week where rank was at its lowest
    peak_rows = df.loc[df.groupby("uri")["rank"].idxmin(), ["uri", "chart_date"]]
    peak_rows = peak_rows.rename(columns={"chart_date": "peak_date"})
    agg = agg.merge(peak_rows, on="uri", how="left")

    # Tidy types
    agg["chart_peak"] = agg["chart_peak"].astype(int)
    agg["total_weeks"] = agg["total_weeks"].astype(int)
    agg["first_charted"] = agg["first_charted"].dt.date.astype(str)
    agg["last_charted"]  = agg["last_charted"].dt.date.astype(str)
    agg["peak_date"]     = agg["peak_date"].dt.date.astype(str)

    # Sort by total chart presence
    agg = agg.sort_values("total_chart_streams", ascending=False).reset_index(drop=True)
    return agg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default=str(_DEFAULT_CSV_DIR))
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    raw = load_all_csvs(csv_dir)

    print("Building chart history...", flush=True)
    history = build_chart_history(raw)

    n_tracks = len(history)
    n_number_ones = (history["chart_peak"] == 1).sum()
    date_range = f"{history['first_charted'].min()} → {history['last_charted'].max()}"
    print(f"  {n_tracks:,} unique tracks | {n_number_ones} reached #1 | {date_range}")

    # Save locally
    _CACHE_DIR.mkdir(exist_ok=True)
    local = _CACHE_DIR / "chart_history.parquet"
    history.to_parquet(local, index=False, compression="zstd")
    size_kb = local.stat().st_size / 1024
    print(f"  Saved: {size_kb:.0f} KB", flush=True)

    # Upload to R2
    r2 = R2Client()
    r2.upload(local, "enrichment/chart_history.parquet")
    r2.usage_summary()
    print("\n✓ chart_history done")


if __name__ == "__main__":
    main()
