"""
Enrich 47K ISRC-bearing tracks with ListenBrainz listen counts.

Pipeline (fast path — MusicBrainz database dump):
  1. Stream mbdump.tar.bz2 via curl (7 GB stream, ~375 MB extracted)
     Extracts only: mbdump/isrc  +  mbdump/recording
  2. Join our 47K ISRCs → recording_mbid via the dump tables (seconds)
  3. Batch-query ListenBrainz popularity API (1K MBIDs/request, minutes)
  4. Upload result to R2

Output: enrichment/listenbrainz_full.parquet
Columns: spotify_track_uri, isrc, recording_mbid, listen_count

Usage:
    python src/compute/compute_listenbrainz_full.py
    python src/compute/compute_listenbrainz_full.py --skip-dump  # if dump already extracted
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

_CACHE_DIR   = Path(tempfile.gettempdir()) / "track2vec_cache"
_DUMP_DIR    = Path("/tmp/mbdump")
# Resolved at call time: MetaBrainz rotates full exports and deletes old ones,
# so a pinned snapshot path eventually 404s. See src/compute/mbdump_url.py.
_DUMP_URL    = None  # set by _resolve_dump_url() on first use
_LB_URL      = "https://api.listenbrainz.org/1/popularity/recording"
_LB_BATCH    = 1000


# ── Phase 1: stream-extract isrc + recording tables from MBDump ──────────────

def extract_mbdump():
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    isrc_path = _DUMP_DIR / "isrc"
    rec_path  = _DUMP_DIR / "recording"

    if isrc_path.exists() and rec_path.exists():
        print(f"Using cached MBDump tables in {_DUMP_DIR}", flush=True)
        return

    from src.compute.mbdump_url import dump_url
    url = dump_url("mbdump.tar.bz2")

    print("Streaming MusicBrainz dump (7 GB) — extracting isrc + recording only...", flush=True)
    print(f"  URL: {url}", flush=True)
    print(f"  Saving to: {_DUMP_DIR}", flush=True)
    print("  This downloads ~7 GB but only writes ~375 MB to disk.\n", flush=True)

    # curl handles SSL correctly on macOS; pipe into tar for streaming extraction
    cmd = (
        f"curl -sL --fail '{url}'"
        f" | tar -xjf - -C {_DUMP_DIR} --strip-components=1"
        f" mbdump/isrc mbdump/recording"
    )
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print("[ERROR] curl | tar failed. Check network or URL.", flush=True)
        sys.exit(1)

    sizes = {f.name: f.stat().st_size / 1e6 for f in [isrc_path, rec_path] if f.exists()}
    print(f"\n  Extracted: {sizes}", flush=True)


# ── Phase 2: join ISRCs → recording_mbid ─────────────────────────────────────

def build_isrc_map() -> pd.DataFrame:
    """
    MBDump table schemas (tab-separated, no header):
      isrc:      id  recording(int)  isrc(str)  source  edits_pending
      recording: id  gid(UUID)       name       artist_credit  ...
    """
    print("\nLoading MBDump isrc table...", flush=True)
    isrc_df = pd.read_csv(
        _DUMP_DIR / "isrc",
        sep="\t", header=None,
        names=["id", "recording_id", "isrc", "source", "edits_pending"],
        usecols=["recording_id", "isrc"],
        dtype={"recording_id": "int32", "isrc": "str"},
    )
    print(f"  {len(isrc_df):,} ISRC entries in MusicBrainz", flush=True)

    print("Loading MBDump recording table (id + gid only)...", flush=True)
    rec_df = pd.read_csv(
        _DUMP_DIR / "recording",
        sep="\t", header=None,
        names=["id", "gid", "name", "artist_credit", "length",
               "comment", "edits_pending", "last_updated", "video"],
        usecols=["id", "gid"],
        dtype={"id": "int32", "gid": "str"},
    )
    print(f"  {len(rec_df):,} recordings in MusicBrainz", flush=True)

    # Join: isrc → recording_id → gid
    merged = isrc_df.merge(rec_df, left_on="recording_id", right_on="id", how="inner")
    merged = merged[["isrc", "gid"]].rename(columns={"gid": "recording_mbid"})
    merged = merged.drop_duplicates("isrc")   # keep one MBID per ISRC
    print(f"  {len(merged):,} unique ISRC → MBID mappings built", flush=True)
    return merged


# ── Phase 3: ListenBrainz popularity ─────────────────────────────────────────

def mbids_to_listencounts(mbids: list[str], token: str) -> dict[str, int]:
    out = {}
    headers = {
        "Accept": "application/json",
        "Authorization": f"Token {token}",
    }
    for i in range(0, len(mbids), _LB_BATCH):
        batch = mbids[i : i + _LB_BATCH]
        try:
            resp = requests.post(
                _LB_URL,
                json={"recording_mbids": batch},
                timeout=30,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("payload", [])
                for item in items:
                    out[item["recording_mbid"]] = item.get("total_listen_count", 0)
            else:
                print(f"  [LB {resp.status_code}] {resp.text[:120]}", flush=True)
        except Exception as e:
            print(f"  [LB batch error] {e}", flush=True)
        if (i // _LB_BATCH + 1) % 10 == 0:
            print(f"  LB: {i + len(batch):,} / {len(mbids):,} queried", flush=True)
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dump", action="store_true",
                        help="Skip dump download if already extracted to /tmp/mbdump")
    args = parser.parse_args()

    _CACHE_DIR.mkdir(exist_ok=True)
    r2 = R2Client()

    # ── Load our ISRCs ────────────────────────────────────────────────────────
    dz_path = _CACHE_DIR / "enrichment_deezer_tracks.parquet"
    if not dz_path.exists():
        print("Downloading deezer enrichment...", flush=True)
        r2.download("enrichment/deezer_tracks.parquet", dz_path)

    dz = pd.read_parquet(dz_path)
    dz = dz[dz["isrc"].notna() & (dz["isrc"] != "")].drop_duplicates("isrc")
    our_isrcs = set(dz["isrc"].tolist())
    print(f"Our ISRCs: {len(our_isrcs):,}", flush=True)

    # ── Phase 1: extract MBDump ───────────────────────────────────────────────
    if not args.skip_dump:
        extract_mbdump()

    # ── Phase 2: join ─────────────────────────────────────────────────────────
    print("\n[Phase 2] Joining ISRCs → recording_mbid...", flush=True)
    isrc_map = build_isrc_map()

    our_map = isrc_map[isrc_map["isrc"].isin(our_isrcs)]
    print(f"  Our ISRCs matched: {len(our_map):,} / {len(our_isrcs):,} "
          f"({len(our_map)/len(our_isrcs)*100:.1f}%)", flush=True)

    # Merge with deezer to get spotify_track_uri
    result = dz[["spotify_track_uri", "isrc"]].merge(our_map, on="isrc", how="left")

    # ── Phase 3: ListenBrainz listen counts ───────────────────────────────────
    lb_token = os.environ.get("LISTENBRAINZ_TOKEN", "").strip()
    if not lb_token:
        print("[ERROR] LISTENBRAINZ_TOKEN not set in .env", flush=True)
        sys.exit(1)

    all_mbids = result["recording_mbid"].dropna().tolist()
    print(f"\n[Phase 3] Querying ListenBrainz for {len(all_mbids):,} MBIDs...", flush=True)
    counts = mbids_to_listencounts(all_mbids, lb_token)
    print(f"  {len(counts):,} listen counts returned", flush=True)

    result["listen_count"] = result["recording_mbid"].map(counts).fillna(0).astype(int)

    # ── Save ──────────────────────────────────────────────────────────────────
    local_out = _CACHE_DIR / "listenbrainz_full.parquet"
    result.to_parquet(local_out, index=False, compression="zstd")
    size_kb = local_out.stat().st_size / 1024

    has_mbid   = result["recording_mbid"].notna().sum()
    has_counts = (result["listen_count"] > 0).sum()
    print(f"\nResult: {len(result):,} rows | {has_mbid:,} with MBID | "
          f"{has_counts:,} with listen_count | {size_kb:.0f} KB", flush=True)

    top = result[result["listen_count"] > 0].nlargest(10, "listen_count")
    print("\nTop 10 by listen count:")
    for _, row in top.iterrows():
        print(f"  {row['listen_count']:>10,}  {row['isrc']}  {row['recording_mbid']}")

    r2.upload(local_out, "enrichment/listenbrainz_full.parquet")
    r2.usage_summary()
    print(f"\n✓ listenbrainz_full done — {len(result):,} tracks, "
          f"{has_counts:,} with listen counts")


if __name__ == "__main__":
    main()
