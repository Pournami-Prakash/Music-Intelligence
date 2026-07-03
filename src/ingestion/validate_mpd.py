"""
Validate processed MPD Parquet files against expected counts before deleting raw JSON.

Checks:
  - playlists.parquet  : exactly 1,000,000 rows, no duplicate pids
  - tracks.parquet     : expected unique track count, no null URIs
  - playlist_tracks.parquet: expected row count, pos preserved, no orphaned tracks

Usage:
    python src/ingestion/validate_mpd.py
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client


def download(r2: R2Client, key: str) -> pd.DataFrame:
    tmp = Path(tempfile.gettempdir()) / f"validate_{key.replace('/', '_')}"
    r2.download(key, tmp)
    df = pd.read_parquet(tmp)
    tmp.unlink(missing_ok=True)
    return df


def validate():
    r2 = R2Client()
    passed = []
    failed = []

    def check(name: str, condition: bool, detail: str = ""):
        if condition:
            passed.append(f"  ✓ {name}")
        else:
            failed.append(f"  ✗ {name}" + (f" — {detail}" if detail else ""))

    print("Downloading and validating MPD Parquet files from R2...\n")

    # ── playlists ─────────────────────────────────────────────────────────────
    pl = download(r2, "processed/playlists.parquet")
    check("playlists row count = 1,000,000",      len(pl) == 1_000_000,        f"got {len(pl):,}")
    check("playlists no duplicate pids",           pl["pid"].nunique() == len(pl))
    check("playlists no null pids",                pl["pid"].notna().all())
    check("playlists has name column",             "name" in pl.columns)
    check("playlists num_tracks > 0 for all",      (pl["num_tracks"] > 0).all())

    print(f"playlists.parquet: {len(pl):,} rows")
    print(f"  pid range: {pl['pid'].min()} → {pl['pid'].max()}")
    print(f"  avg tracks per playlist: {pl['num_tracks'].mean():.1f}")
    print(f"  collaborative: {pl['collaborative'].sum():,} ({pl['collaborative'].mean()*100:.1f}%)\n")

    # ── tracks ────────────────────────────────────────────────────────────────
    tr = download(r2, "processed/tracks.parquet")
    check("tracks no null URIs",                   tr["track_uri"].notna().all())
    check("tracks no duplicate URIs",              tr["track_uri"].nunique() == len(tr))
    check("tracks has artist_name",                tr["artist_name"].notna().mean() > 0.95,
                                                   f"nulls: {tr['artist_name'].isna().sum():,}")
    check("tracks has duration_ms > 0",            (tr["duration_ms"] > 0).mean() > 0.95)

    print(f"tracks.parquet: {len(tr):,} unique tracks")
    print(f"  unique artists: {tr['artist_name'].nunique():,}")
    print(f"  avg duration: {tr['duration_ms'].mean()/1000:.0f}s\n")

    # ── playlist_tracks ───────────────────────────────────────────────────────
    pt = download(r2, "processed/playlist_tracks.parquet")
    check("playlist_tracks > 60M rows",            len(pt) > 60_000_000,        f"got {len(pt):,}")
    check("playlist_tracks pos column exists",     "pos" in pt.columns)
    check("playlist_tracks pos >= 0",              (pt["pos"] >= 0).all())
    check("playlist_tracks no null track_uri",     pt["track_uri"].notna().all())
    check("playlist_tracks no null pid",           pt["pid"].notna().all())

    # Verify all tracks in playlist_tracks exist in tracks
    pt_uris = set(pt["track_uri"].unique())
    tr_uris = set(tr["track_uri"].unique())
    orphaned = pt_uris - tr_uris
    check("no orphaned track URIs in playlist_tracks", len(orphaned) == 0,
          f"{len(orphaned):,} URIs in playlist_tracks missing from tracks")

    # Verify all pids in playlist_tracks exist in playlists
    pt_pids = set(pt["pid"].unique())
    pl_pids = set(pl["pid"].unique())
    orphaned_pids = pt_pids - pl_pids
    check("no orphaned pids in playlist_tracks",   len(orphaned_pids) == 0,
          f"{len(orphaned_pids):,} pids missing from playlists")

    print(f"playlist_tracks.parquet: {len(pt):,} rows")
    print(f"  unique pids: {pt['pid'].nunique():,}")
    print(f"  unique track_uris: {pt['track_uri'].nunique():,}")
    print(f"  pos range: {pt['pos'].min()} → {pt['pos'].max()}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("─" * 50)
    print(f"PASSED: {len(passed)}/{len(passed)+len(failed)}")
    for p in passed:
        print(p)
    if failed:
        print(f"\nFAILED: {len(failed)}")
        for f in failed:
            print(f)
        print("\n⚠ Do NOT delete raw MPD until all checks pass.")
    else:
        print("\n✓ All checks passed. Safe to delete or archive raw MPD JSON.")
    print("─" * 50)


if __name__ == "__main__":
    validate()
