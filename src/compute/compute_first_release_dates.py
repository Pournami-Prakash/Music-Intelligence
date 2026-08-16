"""
Authoritative first-release years from the MusicBrainz dump.

Why
---
`computed/era_tracks.parquet` takes release_year from Deezer, which reports the
edition it happens to hold: reissues and remasters. That put Aerosmith's "Dream
On" (1973) in the 2020s carrying 13,558 pre-2017 playlist appearances, "Beat It"
(1982) as 2024, "Wannabe" (1996) as 2023. The serving layer currently drops
anything dated after the corpus cutoff (src/app/routes/discovery.py), which
stops the false claims but also throws away real post-2017 tracks and leaves
within-decade drift untouched.

MusicBrainz records the first release date of a release *group* (the work, not
the pressing), which is the number we actually want.

Path through the dumps
----------------------
    recording          gid (MBID) -> id                 mbdump          7.4 GB
    track              recording  -> medium             mbdump
    medium             id         -> release            mbdump
    release            id         -> release_group      mbdump
    release_group_meta release_group -> first_release_date_year
                                                        mbdump-derived  510 MB

Only those five tables are extracted; the archives stream through tar and are
never written to disk whole. Peak disk is a few GB of extracted tables, and the
join runs in DuckDB rather than pandas so it stays inside a laptop's memory.

Expect this to take a couple of hours, most of it downloading 7.9 GB.

Output: enrichment/track_first_release.parquet
    recording_mbid, first_release_year

Usage:
    python src/compute/compute_first_release_dates.py                # local only
    python src/compute/compute_first_release_dates.py --upload       # publish
    python src/compute/compute_first_release_dates.py --skip-extract # reuse /tmp/mbdump
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.compute.mbdump_url import dump_url  # noqa: E402

DUMP_DIR = Path("/tmp/mbdump")
OUT_LOCAL = ROOT / "data" / "processed" / "track_first_release.parquet"
R2_KEY = "enrichment/track_first_release.parquet"

# table -> archive it lives in
NEEDED = {
    "recording": "mbdump.tar.bz2",
    "track": "mbdump.tar.bz2",
    "medium": "mbdump.tar.bz2",
    "release": "mbdump.tar.bz2",
    "release_group_meta": "mbdump-derived.tar.bz2",
}

# Column positions in the MusicBrainz TSV exports. The dumps carry no header,
# so these are indexes into the documented schema rather than names.
COLS = {
    "recording":          {"id": 0, "gid": 1},
    "track":              {"id": 0, "recording": 2, "medium": 3},
    "medium":             {"id": 0, "release": 1},
    "release":            {"id": 0, "release_group": 4},
    # release_group_meta is: id, release_count, first_release_date_year,
    # first_release_date_month, first_release_date_day, rating, rating_count.
    # Verified against the 20260815 dump — the year is index 2; index 1 is
    # release_count, which reads as a plausible-looking small integer and would
    # have been silently dropped by the sanity range below.
    "release_group_meta": {"release_group": 0, "first_release_date_year": 2},
}


def extract() -> None:
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    by_archive: dict[str, list[str]] = {}
    for table, archive in NEEDED.items():
        if (DUMP_DIR / table).exists():
            size = (DUMP_DIR / table).stat().st_size / 1e6
            print(f"  cached: {table} ({size:.0f} MB)", flush=True)
            continue
        by_archive.setdefault(archive, []).append(table)

    for archive, tables in by_archive.items():
        url = dump_url(archive)
        members = " ".join(f"mbdump/{t}" for t in tables)
        print(f"\nStreaming {archive} for: {', '.join(tables)}", flush=True)
        print(f"  {url}", flush=True)
        cmd = (
            f"curl -sL --fail '{url}'"
            f" | tar -xjf - -C {DUMP_DIR} --strip-components=1 {members}"
        )
        if subprocess.run(cmd, shell=True).returncode != 0:
            print(f"[ERROR] failed extracting {tables} from {archive}", flush=True)
            sys.exit(1)
        for t in tables:
            print(f"  extracted {t} ({(DUMP_DIR / t).stat().st_size / 1e6:.0f} MB)", flush=True)


def tsv(table: str) -> str:
    """DuckDB reader for a headerless MusicBrainz TSV, with \\N as NULL.

    The column count is left to DuckDB rather than declared. Hardcoding widths
    means encoding a second set of assumptions about a schema that already
    caught me out once (see release_group_meta above), and a wrong width fails
    the read outright. Positions are still asserted, but only the ones used.
    """
    projection = ", ".join(f"column{pos} AS {name}" for name, pos in COLS[table].items())
    return (
        f"(SELECT {projection} FROM read_csv('{DUMP_DIR / table}', "
        f"delim='\t', header=false, quote='', escape='', nullstr='\\N', "
        f"all_varchar=true, null_padding=true, ignore_errors=true))"
    )


def build(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("SET memory_limit='3GB'; SET threads=2; SET preserve_insertion_order=false;")
    print("\nJoining recording -> track -> medium -> release -> release_group_meta…", flush=True)
    con.execute(f"""
        CREATE OR REPLACE TABLE first_release AS
        SELECT r.gid AS recording_mbid,
               MIN(TRY_CAST(rgm.first_release_date_year AS INTEGER)) AS first_release_year
        FROM {tsv('recording')} r
        JOIN {tsv('track')}   t   ON t.recording = r.id
        JOIN {tsv('medium')}  m   ON m.id = t.medium
        JOIN {tsv('release')} rel ON rel.id = m.release
        JOIN {tsv('release_group_meta')} rgm ON rgm.release_group = rel.release_group
        WHERE rgm.first_release_date_year IS NOT NULL
        GROUP BY r.gid
        -- MusicBrainz carries a little junk (years like 20 and 3036) and some
        -- scheduled future releases; ~1,100 rows in total. Anything outside a
        -- plausible window is dropped rather than trusted.
        HAVING MIN(TRY_CAST(rgm.first_release_date_year AS INTEGER))
               BETWEEN 1900 AND YEAR(CURRENT_DATE) + 1
    """)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true", help="publish to R2")
    ap.add_argument("--skip-extract", action="store_true", help="reuse tables already in /tmp/mbdump")
    args = ap.parse_args()

    if not args.skip_extract:
        extract()
    else:
        missing = [t for t in NEEDED if not (DUMP_DIR / t).exists()]
        if missing:
            print(f"[ERROR] --skip-extract but missing: {', '.join(missing)}", flush=True)
            return 1

    con = duckdb.connect()
    build(con)

    n = con.execute("SELECT count(*) FROM first_release").fetchone()[0]
    print(f"  recordings with a first-release year: {n:,}")
    print("  year spread:")
    # Integer-divide explicitly: DuckDB's `/` is float division, so
    # (year / 10) * 10 returns the year back rather than its decade.
    for decade, count in con.execute("""
        SELECT (first_release_year // 10) * 10 AS decade, count(*)
        FROM first_release GROUP BY decade ORDER BY decade
    """).fetchall():
        print(f"    {int(decade)}s  {count:,}")

    OUT_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY first_release TO '{OUT_LOCAL}' (FORMAT parquet, COMPRESSION zstd)")
    print(f"  wrote {OUT_LOCAL} ({OUT_LOCAL.stat().st_size / 1e6:.1f} MB)")

    if args.upload:
        from src.storage.r2 import R2Client
        R2Client().upload(str(OUT_LOCAL), R2_KEY)
        print(f"  uploaded -> {R2_KEY}")
    else:
        print("  (not uploaded; pass --upload to publish to R2)")

    print("\nNext: join recording_mbid into canonical_tracks to replace the Deezer")
    print("release_year, rebuild computed/era_tracks.parquet, then relax")
    print("CORPUS_RELEASE_CUTOFF in src/app/routes/discovery.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
