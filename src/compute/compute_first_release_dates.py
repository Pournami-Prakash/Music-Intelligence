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
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from src.compute.mbdump_url import dump_url  # noqa: E402

DUMP_DIR = Path("/tmp/mbdump")
OUT_LOCAL = ROOT / "data" / "processed" / "track_first_release.parquet"
R2_KEY = "enrichment/track_first_release.parquet"

# Each table is streamed from tar straight into `cut`, so the full table never
# lands on disk — only the two columns the join needs. `recording` and `track`
# are multi-GB apiece; trimmed, the whole working set is roughly 2 GB instead of
# ~13 GB. That costs one pass over the archive per table, which is the right
# trade when disk is scarce and bandwidth is not.
#
# `fields` is 1-based (cut's convention) against the raw dump. `cols` is 0-based
# against the *trimmed* file, which is what DuckDB reads.
#
# Raw positions come from the MusicBrainz schema. release_group_meta was checked
# against the 20260815 dump directly: id, release_count, first_release_date_year,
# month, day, rating, rating_count — the year is the third field, not the second,
# and reading the second would have parsed release_count as a year.
TABLES = {
    "recording":          {"archive": "mbdump.tar.bz2",         "fields": "1,2",
                           "cols": {"id": 0, "gid": 1}},
    "track":              {"archive": "mbdump.tar.bz2",         "fields": "3,4",
                           "cols": {"recording": 0, "medium": 1}},
    "medium":             {"archive": "mbdump.tar.bz2",         "fields": "1,2",
                           "cols": {"id": 0, "release": 1}},
    "release":            {"archive": "mbdump.tar.bz2",         "fields": "1,5",
                           "cols": {"id": 0, "release_group": 1}},
    "release_group_meta": {"archive": "mbdump-derived.tar.bz2", "fields": "1,3",
                           "cols": {"release_group": 0, "first_release_date_year": 1}},
}

COLS = {name: spec["cols"] for name, spec in TABLES.items()}


ARCHIVE_DIR = DUMP_DIR / "_archives"


def free_gb(path: Path = DUMP_DIR) -> float:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9


def fetch_archive(archive: str) -> Path:
    """Download an archive to disk, resuming if a previous attempt was cut short.

    Piping the download straight into tar failed twice on `track`, both times
    with "truncated bzip2 input". `track` is the largest member and sits late in
    the archive, so the transfer has to survive longest before reaching it, and
    a stream gives back everything on any drop. MetaBrainz serves byte ranges
    (HTTP 206), so downloading to a file with -C - turns a dropped connection
    into a resume instead of a restart.

    Costs 7.4 GB of disk while it runs; the archive is removed after extraction.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    url = dump_url(archive)
    target = ARCHIVE_DIR / archive

    expected = 0
    try:
        head = requests.head(url, allow_redirects=True, timeout=30)
        expected = int(head.headers.get("content-length", 0))
    except Exception:
        pass

    have = target.stat().st_size if target.exists() else 0
    if expected and have == expected:
        print(f"  archive already complete: {archive} ({have/1e9:.1f} GB)", flush=True)
        return target
    if have:
        print(f"  resuming {archive} at {have/1e9:.1f} / {expected/1e9:.1f} GB", flush=True)

    need = (expected - have) / 1e9 + 1 if expected else 9.0
    if free_gb() < need:
        print(f"[ERROR] {free_gb():.1f} GB free, need ~{need:.1f} GB for {archive}", flush=True)
        sys.exit(1)

    # --retry covers transient drops; -C - resumes from whatever is on disk.
    cmd = (
        f"curl -L --fail --retry 8 --retry-delay 5 --retry-all-errors "
        f"-C - --speed-time 60 --speed-limit 1024 "
        f"-o '{target}' '{url}'"
    )
    if subprocess.run(cmd, shell=True, executable="/bin/bash").returncode != 0:
        print(f"[ERROR] download of {archive} failed; rerun to resume from "
              f"{target.stat().st_size/1e9 if target.exists() else 0:.1f} GB", flush=True)
        sys.exit(1)

    got = target.stat().st_size
    if expected and got != expected:
        print(f"[ERROR] {archive} is {got:,} bytes, expected {expected:,}", flush=True)
        sys.exit(1)
    print(f"  downloaded {archive} ({got/1e9:.1f} GB)", flush=True)
    return target


def _field_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return len(fh.readline().rstrip("\n").split("\t"))


def trim_in_place(table: str) -> None:
    """Cut a full-width dump table down to the columns the join needs.

    Self-healing rather than trusting a flag: an already-trimmed file is left
    alone, and a full-width one left over from an earlier run is trimmed now.
    That matters because the trimmed and untrimmed layouts differ, so reading a
    stale full-width file with trimmed column indexes silently returns the wrong
    field (release_count instead of a release year) rather than failing.
    """
    spec = TABLES[table]
    path = DUMP_DIR / table
    want = len(spec["cols"])
    have = _field_count(path)
    if have <= want:
        return

    tmp = path.with_suffix(".trim")
    cmd = f"cut -f{spec['fields']} '{path}' > '{tmp}'"
    if subprocess.run(cmd, shell=True, executable="/bin/bash").returncode != 0:
        tmp.unlink(missing_ok=True)
        print(f"[ERROR] failed trimming {table}", flush=True)
        sys.exit(1)
    before = path.stat().st_size
    tmp.replace(path)
    print(f"  trimmed {table}: {before/1e6:.0f} -> {path.stat().st_size/1e6:.0f} MB "
          f"({have} -> {want} fields, {free_gb():.1f} GB free)", flush=True)


def extract() -> None:
    """Pull every needed table in a single pass per archive, then trim.

    An earlier version streamed each table separately through `tar -O | cut`, so
    the untrimmed data never touched disk (~2 GB peak instead of ~13 GB). That
    was safe on a 95%-full volume but decompressed the 7.4 GB bzip2 archive once
    per table, and bzip2 decompression — not download — is the slow part. One
    pass writes all four tables and trims them immediately afterwards, which is
    roughly four times faster at the cost of a higher peak.
    """
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Free disk: {free_gb():.1f} GB", flush=True)

    by_archive: dict[str, list[str]] = {}
    for table, spec in TABLES.items():
        if (DUMP_DIR / table).exists():
            trim_in_place(table)
            print(f"  cached: {table} ({(DUMP_DIR / table).stat().st_size/1e6:.0f} MB)", flush=True)
            continue
        by_archive.setdefault(spec["archive"], []).append(table)

    if not by_archive:
        return

    # The untrimmed tables land whole before trimming, so refuse to start
    # without headroom rather than filling the volume mid-extract.
    needed = 18.0
    if free_gb() < needed:
        print(f"[ERROR] {free_gb():.1f} GB free; need ~{needed:.0f} GB for a single-pass "
              f"extract. Free space, or use a per-table streaming extract.", flush=True)
        sys.exit(1)

    for archive, tables in by_archive.items():

        # One table left: stream it through cut so the untrimmed copy never
        # lands. Per-table streaming only wastes work when several tables are
        # wanted, because each one costs a full decompression of the archive.
        if len(tables) == 1:
            table = tables[0]
            spec = TABLES[table]
            part = (DUMP_DIR / table).with_suffix(".part")
            local = fetch_archive(archive)
            print(f"\nExtracting {table} from {archive} (trimmed in flight)", flush=True)
            cmd = (
                f"set -o pipefail; tar -xOjf '{local}' mbdump/{table}"
                f" | cut -f{spec['fields']} > '{part}'"
            )
            if subprocess.run(cmd, shell=True, executable="/bin/bash").returncode != 0:
                part.unlink(missing_ok=True)
                print(f"[ERROR] failed extracting {table} from {archive}", flush=True)
                sys.exit(1)
            part.rename(DUMP_DIR / table)
            print(f"  {table}: {(DUMP_DIR / table).stat().st_size/1e6:.0f} MB "
                  f"({free_gb():.1f} GB free)", flush=True)
            continue

        # Several tables: one decompression, extracted into a staging directory
        # so a truncated stream cannot leave a partial table sitting where the
        # next run would mistake it for a complete cache. A 7.2 GB half-written
        # `track` is indistinguishable from a good one by existence alone.
        staging = DUMP_DIR / ".staging"
        subprocess.run(f"rm -rf '{staging}'", shell=True)
        staging.mkdir(parents=True, exist_ok=True)
        members = " ".join(f"mbdump/{t}" for t in tables)
        local = fetch_archive(archive)
        print(f"\nExtracting from {archive}: {', '.join(tables)}", flush=True)
        cmd = (
            f"set -o pipefail; tar -xjf '{local}' -C '{staging}' "
            f"--strip-components=1 {members}"
        )
        proc = subprocess.run(cmd, shell=True, executable="/bin/bash",
                              stderr=subprocess.PIPE, text=True)
        failed = proc.returncode != 0
        truncated: set[str] = set()
        if failed:
            # tar names the member it died on ("track: truncated bzip2 input"),
            # which is the only reliable way to tell which file is short: tar
            # writes members in archive order, not the order they were
            # requested, so position in `tables` says nothing. Everything else
            # it finished is complete and worth keeping.
            print(proc.stderr.strip(), flush=True)
            for line in proc.stderr.splitlines():
                name = line.split(":", 1)[0].strip()
                if name in tables:
                    truncated.add(name)
            if not truncated:
                truncated = set(tables)   # cannot tell: trust none of them
            print(f"[ERROR] stream truncated during {archive}; "
                  f"discarding {', '.join(sorted(truncated))}", flush=True)

        for t in tables:
            produced = staging / t
            if not produced.exists() or t in truncated:
                continue
            produced.replace(DUMP_DIR / t)
            print(f"  extracted {t}: {(DUMP_DIR / t).stat().st_size/1e6:.0f} MB", flush=True)
            trim_in_place(t)

        subprocess.run(f"rm -rf '{staging}'", shell=True)
        if failed:
            sys.exit(1)


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
        missing = [t for t in TABLES if not (DUMP_DIR / t).exists()]
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
