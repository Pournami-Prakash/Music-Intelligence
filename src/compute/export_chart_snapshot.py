"""
Export a compact chart-history snapshot for client-side use.

The Listening History page joins a visitor's own plays against chart dates to
work out whether they were early or late on the songs that broke. That join has
to happen in the browser: the page promises the export is never uploaded, so
sending a track list to the server to be matched would break the one guarantee
the feature makes.

So the chart table travels to the client instead of the history travelling to
the server. 7,409 rows is small enough for that to be reasonable, provided it
is not shipped as verbose JSON — hence the array-of-arrays layout and the
stripped `spotify:track:` prefixes.

Row layout (kept positional to avoid repeating six keys 7,409 times):
    [track_id, title, artist, chart_peak, first_charted, peak_date]

Output: frontend/public/data/chart-history.json

Usage:
    python src/compute/export_chart_snapshot.py
"""

import json
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

OUT = ROOT / "frontend" / "public" / "data" / "chart-history.json"
PREFIX = "spotify:track:"


def main() -> int:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"""
        SET s3_region='auto';
        SET s3_endpoint='{os.environ["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com';
        SET s3_access_key_id='{os.environ["R2_ACCESS_KEY_ID"]}';
        SET s3_secret_access_key='{os.environ["R2_SECRET_ACCESS_KEY"]}';
        SET memory_limit='2GB'; SET threads=2;
    """)
    key = f"s3://{os.environ['R2_BUCKET']}/enrichment/chart_history.parquet"

    # release_year comes along so the client can tell a genuine chart debut from
    # a catalogue track re-entering. The chart table starts in 2017, so
    # `first_charted` for anything older is the week it *returned*, which reads
    # as a debut and turns "I played Ain't No Sunshine" into an early call.
    #
    # These are Deezer years and therefore unreliable in one direction: they
    # sometimes report a reissue, making an old song look new. That only ever
    # fails to filter a re-entry, never wrongly filters a real debut, so the
    # signal is worth carrying even though it is imperfect.
    tracks = f"s3://{os.environ['R2_BUCKET']}/processed/canonical_tracks.parquet"
    rows = con.execute(f"""
        SELECT c.uri, c.track_name, c.artist_name, c.chart_peak,
               c.first_charted, c.peak_date,
               TRY_CAST(t.release_year AS INTEGER) AS release_year
        FROM read_parquet('{key}') c
        LEFT JOIN read_parquet('{tracks}') t ON t.spotify_track_uri = c.uri
        WHERE c.uri IS NOT NULL AND c.first_charted IS NOT NULL
        ORDER BY c.first_charted
    """).fetchall()

    compact = []
    with_year = 0
    for uri, title, artist, peak, first_charted, peak_date, release_year in rows:
        track_id = uri[len(PREFIX):] if uri.startswith(PREFIX) else uri
        if release_year:
            with_year += 1
        compact.append([
            track_id,
            title,
            artist,
            int(peak) if peak is not None else None,
            str(first_charted),
            str(peak_date) if peak_date else None,
            int(release_year) if release_year else None,
        ])

    payload = {
        "generated_from": "enrichment/chart_history.parquet",
        "coverage": {
            "from": compact[0][4],
            "to": max(r[4] for r in compact),
            "tracks": len(compact),
        },
        "fields": ["track_id", "title", "artist", "chart_peak", "first_charted", "peak_date", "release_year"],
        "rows": compact,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  {len(compact):,} charted tracks -> {OUT} ({OUT.stat().st_size/1024:.0f} KB)")
    print(f"  coverage {payload['coverage']['from']} .. {payload['coverage']['to']}")
    print(f"  with a release year: {with_year:,} / {len(compact):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
