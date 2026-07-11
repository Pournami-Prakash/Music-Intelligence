"""
Enrich MPD tracks with ISRCs via MusicBrainz dump title+artist matching.

Strategy (zero API calls after dump extraction):
  1. Re-stream MBDump to extract mbdump/artist_credit (if not already present)
     artist_credit schema: id, name (text like "The Beatles"), artist_count, ...
  2. Join: recording(name, artist_credit_id) → artist_credit(id → name)
     → full lookup table: normalized(track_name, artist_name) → (recording_id, mbid)
  3. Join: recording_id → isrc table → ISRC
  4. Match our 2.26M MPD tracks by normalized (title, artist) — exact match first
  5. Query ListenBrainz for new MBIDs not in listenbrainz_full
  6. Upload enrichment/mbdump_isrc_match.parquet

Usage:
    python src/compute/compute_mbdump_isrc.py
    python src/compute/compute_mbdump_isrc.py --skip-extract  # if artist_credit already at /tmp/mbdump
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"
_DUMP_DIR  = Path("/tmp/mbdump")
_DUMP_URL  = ("https://data.metabrainz.org/pub/musicbrainz/data/fullexport"
               "/20260704-002053/mbdump.tar.bz2")
_LB_URL    = "https://api.listenbrainz.org/1/popularity/recording"
_LB_BATCH  = 1000


def extract_artist_credit():
    ac_path = _DUMP_DIR / "artist_credit"
    if ac_path.exists():
        print(f"  Using cached artist_credit ({ac_path.stat().st_size/1e6:.0f} MB)", flush=True)
        return
    print("Streaming MBDump to extract artist_credit...", flush=True)
    print(f"  (7 GB stream — only writes artist_credit to disk)\n", flush=True)
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    cmd = (f"curl -sL --fail '{_DUMP_URL}'"
           f" | tar -xjf - -C {_DUMP_DIR} --strip-components=1 mbdump/artist_credit")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("[ERROR] curl | tar failed", flush=True)
        sys.exit(1)
    print(f"  Extracted: {ac_path.stat().st_size/1e6:.0f} MB", flush=True)


def build_mb_lookup() -> pd.DataFrame:
    """
    Build a lookup DataFrame:
      normalized_title × normalized_artist → (recording_id, recording_mbid, isrc)
    """
    print("Loading isrc table...", flush=True)
    isrc_df = pd.read_csv(
        _DUMP_DIR / "isrc",
        sep="\t", header=None,
        names=["id", "recording_id", "isrc", "source", "edits_pending"],
        usecols=["recording_id", "isrc"],
        dtype={"recording_id": "int32", "isrc": "str"},
    )
    isrc_df = isrc_df.drop_duplicates("recording_id")   # one ISRC per recording
    print(f"  {len(isrc_df):,} ISRC entries", flush=True)

    print("Loading recording table...", flush=True)
    rec_df = pd.read_csv(
        _DUMP_DIR / "recording",
        sep="\t", header=None,
        names=["id", "gid", "name", "artist_credit", "length",
               "comment", "edits_pending", "last_updated", "video"],
        usecols=["id", "gid", "name", "artist_credit"],
        dtype={"id": "int32", "gid": "str", "name": "str", "artist_credit": "int32"},
    )
    print(f"  {len(rec_df):,} recordings", flush=True)

    print("Loading artist_credit table...", flush=True)
    ac_df = pd.read_csv(
        _DUMP_DIR / "artist_credit",
        sep="\t", header=None,
        names=["id", "name", "artist_count", "ref_count", "created", "last_updated", "edits_pending"],
        usecols=["id", "name"],
        dtype={"id": "int32", "name": "str"},
    )
    print(f"  {len(ac_df):,} artist credits", flush=True)

    # Join recording → artist name
    print("Joining recording → artist_credit...", flush=True)
    rec_with_artist = rec_df.merge(
        ac_df.rename(columns={"id": "artist_credit", "name": "artist_name"}),
        on="artist_credit", how="inner"
    )

    # Join → ISRC (only keep recordings that have ISRCs)
    print("Joining → ISRC...", flush=True)
    lookup = rec_with_artist.merge(isrc_df, left_on="id", right_on="recording_id", how="inner")
    lookup = lookup[["id", "gid", "name", "artist_name", "isrc"]].rename(
        columns={"id": "recording_id", "gid": "recording_mbid",
                 "name": "track_name_mb", "artist_name": "artist_name_mb"}
    )

    # Normalize for matching
    lookup["key"] = (
        lookup["track_name_mb"].str.lower().str.strip()
        + "|||"
        + lookup["artist_name_mb"].str.lower().str.strip()
    )
    lookup = lookup.drop_duplicates("key")   # first ISRC wins per (title, artist)
    print(f"  {len(lookup):,} unique (title, artist) entries with ISRCs", flush=True)
    return lookup


def lb_listen_counts(mbids: list[str], token: str) -> dict[str, int]:
    out = {}
    headers = {"Accept": "application/json", "Authorization": f"Token {token}"}
    for i in range(0, len(mbids), _LB_BATCH):
        batch = mbids[i: i + _LB_BATCH]
        try:
            resp = requests.post(_LB_URL, json={"recording_mbids": batch},
                                 headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("payload", [])
                for item in items:
                    out[item["recording_mbid"]] = item.get("total_listen_count", 0)
        except Exception as e:
            print(f"  [LB error] {e}", flush=True)
        if (i // _LB_BATCH + 1) % 10 == 0:
            print(f"  LB: {i + len(batch):,} / {len(mbids):,}", flush=True)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-extract", action="store_true",
                        help="Skip dump extraction if artist_credit already at /tmp/mbdump")
    args = parser.parse_args()

    _CACHE_DIR.mkdir(exist_ok=True)
    r2 = R2Client()

    # ── Extract artist_credit from MBDump ───────────────────────────────────
    if not args.skip_extract:
        extract_artist_credit()
    else:
        if not (_DUMP_DIR / "artist_credit").exists():
            print("[ERROR] --skip-extract set but artist_credit not found", flush=True)
            sys.exit(1)

    # ── Build MusicBrainz lookup ────────────────────────────────────────────
    print("\nBuilding MusicBrainz title+artist lookup...", flush=True)
    mb_lookup = build_mb_lookup()

    # ── Load MPD tracks ─────────────────────────────────────────────────────
    print("\nLoading MPD tracks without ISRCs...", flush=True)
    ct_path = _CACHE_DIR / "canonical_tracks.parquet"
    if not ct_path.exists():
        r2.download("processed/canonical_tracks.parquet", ct_path)
    ct = pd.read_parquet(ct_path)

    no_isrc = ct[ct["isrc"].isna() & ct["track_name"].notna() & ct["artist_name"].notna()].copy()
    print(f"  {len(no_isrc):,} MPD tracks without ISRC", flush=True)

    # Normalize
    no_isrc["key"] = (
        no_isrc["track_name"].str.lower().str.strip()
        + "|||"
        + no_isrc["artist_name"].str.lower().str.strip()
    )

    # ── Exact match ─────────────────────────────────────────────────────────
    print("Exact matching (title + artist)...", flush=True)
    # Drop no_isrc's own isrc column (all NaN) to avoid isrc_x / isrc_y collision
    matched = no_isrc.drop(columns=["isrc"], errors="ignore").merge(
        mb_lookup[["key", "isrc", "recording_mbid"]],
        on="key", how="inner"
    )
    print(f"  Matched: {len(matched):,} / {len(no_isrc):,} "
          f"({len(matched)/len(no_isrc)*100:.1f}%)", flush=True)

    result = matched[["spotify_track_uri", "isrc", "recording_mbid"]].copy()
    result.columns = ["track_uri", "isrc", "recording_mbid"]

    # ── ListenBrainz listen counts ──────────────────────────────────────────
    lb_token = os.environ.get("LISTENBRAINZ_TOKEN", "").strip()
    if not lb_token:
        print("[WARN] LISTENBRAINZ_TOKEN not set — skipping listen counts", flush=True)
        result["listen_count"] = 0
    else:
        lb_path = _CACHE_DIR / "listenbrainz_full.parquet"
        if not lb_path.exists():
            r2.download("enrichment/listenbrainz_full.parquet", lb_path)
        existing_lb = pd.read_parquet(lb_path)
        known_mbids = set(existing_lb["recording_mbid"].dropna())

        new_mbids = [m for m in result["recording_mbid"].dropna() if m not in known_mbids]
        print(f"\nNew MBIDs to query on ListenBrainz: {len(new_mbids):,}", flush=True)

        if new_mbids:
            counts = lb_listen_counts(new_mbids, lb_token)
            print(f"  {len(counts):,} listen counts returned", flush=True)
            result["listen_count"] = result["recording_mbid"].map(counts).fillna(0).astype(int)
        else:
            print("  All MBIDs already in listenbrainz_full", flush=True)
            result["listen_count"] = 0

    # ── Save and upload ────────────────────────────────────────────────────
    out_path = _CACHE_DIR / "mbdump_isrc_match.parquet"
    result.to_parquet(out_path, index=False, compression="zstd")
    size_kb = out_path.stat().st_size / 1024
    print(f"\nSaved: {size_kb:.0f} KB  rows: {len(result):,}", flush=True)

    r2.upload(out_path, "enrichment/mbdump_isrc_match.parquet", delete_after=False)
    r2.usage_summary()

    with_counts = (result["listen_count"] > 0).sum()
    print(f"\n✓ mbdump_isrc done — {len(result):,} tracks matched, "
          f"{with_counts:,} with listen counts")


if __name__ == "__main__":
    main()
