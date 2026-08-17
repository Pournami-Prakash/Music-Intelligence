"""
Pre-compute era_tracks.parquet: tracks with a release year and playlist counts.

Joins release years onto track_stats (playlist_count for 2.26M tracks) so
time_capsule can rank an era by how far its tracks travelled.

Release years, best source first
--------------------------------
MusicBrainz first-release dates (enrichment/track_first_release.parquet) are the
date of the release *group*, so they describe the work rather than whichever
pressing a metadata provider happens to hold. Deezer years fill the gaps, but
report reissues: they dated Aerosmith's "Dream On" (1973) to 2023 and Michael
Jackson's "Beat It" (1982) to 2024.

MusicBrainz is better, not perfect. It resolves some recordings to a later
re-release too: "It Wasn't Me" (Shaggy, 2000) comes back as 2020 while carrying
22,736 appearances in playlists that all predate October 2017.

The consistency guard
---------------------
That last case is why the guard is not a Deezer workaround but a rule about the
data as a whole. A track appearing in MPD playlists existed by October 2017, so
any release year after that contradicts its own playlist count, whichever source
supplied it. Rows that disagree with themselves are dropped rather than ranked.

Tracks genuinely released after 2017 reach this table through the editorial
archive and have no MPD appearances at all, so they cannot be ranked by playlist
reach and are excluded by the same rule. A post-2017 era needs a different
metric, not a better date.

Output: R2:computed/era_tracks.parquet
Schema:
    track_name      str
    artist_name     str
    release_year    int
    playlist_count  int
    year_source     str   'musicbrainz' | 'deezer'

Usage:
    python src/compute/compute_era_tracks.py            # build locally
    python src/compute/compute_era_tracks.py --upload   # publish to R2
"""

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
from src.storage.r2 import R2Client  # noqa: E402

R2_KEY = "computed/era_tracks.parquet"
FIRST_RELEASE_KEY = "enrichment/track_first_release.parquet"
LOCAL_FIRST_RELEASE = ROOT / "data" / "processed" / "track_first_release.parquet"

# The playlist corpus stops in October 2017; see the module docstring.
CORPUS_RELEASE_CUTOFF = 2017


def load_first_release(r2: R2Client, tmp: Path) -> pd.DataFrame | None:
    """MusicBrainz years, from disk if the build just produced them, else R2."""
    if LOCAL_FIRST_RELEASE.exists():
        print(f"Using local {LOCAL_FIRST_RELEASE.name} …")
        return pd.read_parquet(LOCAL_FIRST_RELEASE)
    try:
        path = tmp / "era_fr.parquet"
        r2.download(FIRST_RELEASE_KEY, path)
        df = pd.read_parquet(path)
        path.unlink(missing_ok=True)
        return df
    except Exception as exc:
        print(f"  no MusicBrainz years available ({exc}); Deezer only", flush=True)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true", help="publish to R2")
    args = ap.parse_args()

    r2 = R2Client()
    tmp = Path(tempfile.gettempdir())

    print("Downloading canonical_tracks …")
    ct_path = tmp / "era_ct.parquet"
    r2.download("processed/canonical_tracks.parquet", ct_path)
    ct = pd.read_parquet(ct_path, columns=["spotify_track_uri", "release_year", "recording_mbid"])
    ct_path.unlink(missing_ok=True)
    ct["release_year"] = pd.to_numeric(ct["release_year"], errors="coerce").astype("Int64")
    print(f"  {len(ct):,} tracks, {ct['release_year'].notna().sum():,} with a Deezer year")

    fr = load_first_release(r2, tmp)
    if fr is not None:
        fr = fr.rename(columns={"first_release_year": "mb_year"})
        ct = ct.merge(fr, on="recording_mbid", how="left")
        ct["mb_year"] = pd.to_numeric(ct["mb_year"], errors="coerce").astype("Int64")
        print(f"  {ct['mb_year'].notna().sum():,} with a MusicBrainz year")
    else:
        ct["mb_year"] = pd.Series([pd.NA] * len(ct), dtype="Int64")

    # MusicBrainz first, Deezer as fallback.
    ct["year_source"] = ct["mb_year"].notna().map({True: "musicbrainz", False: "deezer"})
    ct["release_year"] = ct["mb_year"].fillna(ct["release_year"])
    ct = ct[ct["release_year"].notna()].copy()
    print(f"  {len(ct):,} tracks with a year from either source")

    print("Downloading track_stats …")
    ts_path = tmp / "era_ts.parquet"
    r2.download("computed/track_stats.parquet", ts_path)
    ts = pd.read_parquet(ts_path, columns=["track_uri", "track_name", "artist_name", "playlist_count"])
    ts_path.unlink(missing_ok=True)
    print(f"  {len(ts):,} tracks with playlist_count")

    merged = ct.merge(
        ts.rename(columns={"track_uri": "spotify_track_uri"}),
        on="spotify_track_uri", how="inner",
    )
    print(f"  {len(merged):,} tracks with both a year and a playlist count")

    # Self-contradiction: a playlist count earned before October 2017 cannot
    # belong to a track released later, so the year is wrong regardless of who
    # supplied it.
    impossible = merged["release_year"] > CORPUS_RELEASE_CUTOFF
    by_source = merged.loc[impossible, "year_source"].value_counts().to_dict()
    print(f"  dropping {impossible.sum():,} rows dated after {CORPUS_RELEASE_CUTOFF} "
          f"while holding playlist appearances {by_source}")
    out = merged.loc[~impossible].copy()

    out = out[["track_name", "artist_name", "release_year", "playlist_count", "year_source"]]
    out["release_year"] = out["release_year"].astype(int)
    out = out.sort_values("playlist_count", ascending=False)
    print(f"  {len(out):,} rows kept")

    print("  by source:", out["year_source"].value_counts().to_dict())
    print("  by decade:")
    dist = out["release_year"].floordiv(10).mul(10).value_counts().sort_index()
    for decade, count in dist.items():
        print(f"    {decade}s: {count:,}")

    out_path = tmp / "era_tracks.parquet"
    out.to_parquet(out_path, index=False, compression="zstd")
    size_mb = out_path.stat().st_size / 1024**2

    local_copy = ROOT / "data" / "processed" / "era_tracks.parquet"
    local_copy.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(local_copy, index=False, compression="zstd")
    print(f"\n  wrote {local_copy} ({size_mb:.1f} MB)")

    if args.upload:
        print(f"Uploading → R2:{R2_KEY} …")
        r2.upload(str(out_path), R2_KEY, delete_after=True)
        print(f"  published {len(out):,} rows")
    else:
        out_path.unlink(missing_ok=True)
        print("  (not uploaded; pass --upload to publish to R2)")


if __name__ == "__main__":
    main()
