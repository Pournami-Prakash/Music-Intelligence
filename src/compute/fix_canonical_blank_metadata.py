"""
Backfill blank track_name / artist_name in canonical_tracks.parquet.

Blank rows in canonical_tracks come from MPD tracks that had no metadata at
ingest time. We try to fill them in priority order from authoritative sources:

  1. deezer_tracks.parquet       — deezer_title / deezer_artist (Deezer API)
  2. editorial_playlist_tracks   — track_name / artist_name (Spotify/mackorone)
  3. Spotify Web API             — URI lookup for remaining bad rows only

Rows that cannot be filled by any source are NOT dropped from the spine —
they get a boolean `needs_metadata=True` flag so they can be filtered at
serve time and investigated later.

Do NOT guess names from playlist context.

Usage:
    python src/compute/fix_canonical_blank_metadata.py --dry-run
    python src/compute/fix_canonical_blank_metadata.py
"""

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client
from src.storage.spotify import SpotifyClient

_TMP = Path(tempfile.gettempdir()) / "track2vec_cache"


def _dl(r2: R2Client, key: str, fname: str) -> pd.DataFrame:
    p = _TMP / fname
    p.unlink(missing_ok=True)
    r2.download(key, str(p))
    return pd.read_parquet(p)


_ARTIST_PLACEHOLDERS = {"artist"}  # literal MPD ingest placeholder only; "Various Artists" is valid


def _blank(series: pd.Series) -> pd.Series:
    return series.fillna("").str.strip() == ""


def _bad_artist(series: pd.Series) -> pd.Series:
    """True for blank OR known-placeholder artist names."""
    cleaned = series.fillna("").str.strip().str.lower()
    return (cleaned == "") | cleaned.isin(_ARTIST_PLACEHOLDERS)


def _fill_from(ct: pd.DataFrame, source: pd.DataFrame,
               src_uri_col: str, src_name_col: str, src_artist_col: str,
               label: str) -> tuple[pd.DataFrame, int, int]:
    """Join source onto ct by URI; fill blank title/artist placeholders."""
    # Build a lookup with only rows that have useful data
    src = source[[src_uri_col, src_name_col, src_artist_col]].copy()
    src = src.rename(columns={src_uri_col: "spotify_track_uri",
                               src_name_col: "_src_name",
                               src_artist_col: "_src_artist"})
    # Keep only rows where at least one field is non-blank
    src = src[~(_blank(src["_src_name"]) & _blank(src["_src_artist"]))]
    src = src.drop_duplicates(subset=["spotify_track_uri"], keep="first")

    n_name_before   = _blank(ct["track_name"]).sum()
    n_artist_before = _bad_artist(ct["artist_name"]).sum()

    ct = ct.merge(src, on="spotify_track_uri", how="left")

    # Fill blanks where source has data
    fill_name   = _blank(ct["track_name"]) & ~_blank(ct["_src_name"])
    fill_artist = _bad_artist(ct["artist_name"]) & ~_bad_artist(ct["_src_artist"])

    ct.loc[fill_name,   "track_name"]  = ct.loc[fill_name,   "_src_name"]
    ct.loc[fill_artist, "artist_name"] = ct.loc[fill_artist, "_src_artist"]

    ct = ct.drop(columns=["_src_name", "_src_artist"])

    n_names_filled   = n_name_before   - _blank(ct["track_name"]).sum()
    n_artists_filled = n_artist_before - _bad_artist(ct["artist_name"]).sum()

    print(f"  [{label}] filled: {n_names_filled:,} track names, {n_artists_filled:,} artist names")
    return ct, int(n_names_filled), int(n_artists_filled)


def _fill_from_spotify(ct: pd.DataFrame) -> tuple[pd.DataFrame, int, int, int]:
    """Fetch exact Spotify track metadata for rows still missing title/artist."""
    still_bad = _blank(ct["track_name"]) | _bad_artist(ct["artist_name"])
    targets = ct.loc[still_bad, ["spotify_track_uri"]].drop_duplicates()
    if targets.empty:
        print("  [spotify api] no remaining bad rows")
        return ct, 0, 0, 0

    try:
        sp = SpotifyClient()
    except Exception as e:
        print(f"  [spotify api] skipped: {e}")
        return ct, 0, 0, len(targets)

    lookups = []
    failures = 0
    print(f"\nLooking up {len(targets):,} remaining bad rows via Spotify API …")
    for uri in targets["spotify_track_uri"].tolist():
        try:
            t = sp.track(uri)
            artists = t.get("artists") or []
            album = t.get("album") or {}
            lookups.append({
                "spotify_track_uri": uri,
                "_src_name": t.get("name"),
                "_src_artist": artists[0].get("name") if artists else None,
                "_src_album": album.get("name"),
                "_src_duration_ms": t.get("duration_ms"),
            })
        except Exception:
            failures += 1

    if not lookups:
        print(f"  [spotify api] no metadata returned; failures: {failures:,}")
        return ct, 0, 0, failures

    src = pd.DataFrame(lookups).drop_duplicates("spotify_track_uri")
    name_before = _blank(ct["track_name"]).sum()
    artist_before = _bad_artist(ct["artist_name"]).sum()

    ct = ct.merge(src, on="spotify_track_uri", how="left")
    fill_name = _blank(ct["track_name"]) & ~_blank(ct["_src_name"])
    fill_artist = _bad_artist(ct["artist_name"]) & ~_bad_artist(ct["_src_artist"])
    fill_album = _blank(ct["album_name"]) & ~_blank(ct["_src_album"]) if "album_name" in ct.columns else pd.Series(False, index=ct.index)
    fill_duration = ct.get("duration_ms", pd.Series(index=ct.index)).isna() & ct["_src_duration_ms"].notna() if "duration_ms" in ct.columns else pd.Series(False, index=ct.index)

    ct.loc[fill_name, "track_name"] = ct.loc[fill_name, "_src_name"]
    ct.loc[fill_artist, "artist_name"] = ct.loc[fill_artist, "_src_artist"]
    if "album_name" in ct.columns:
        ct.loc[fill_album, "album_name"] = ct.loc[fill_album, "_src_album"]
    if "duration_ms" in ct.columns:
        ct.loc[fill_duration, "duration_ms"] = ct.loc[fill_duration, "_src_duration_ms"]

    ct = ct.drop(columns=["_src_name", "_src_artist", "_src_album", "_src_duration_ms"])
    names_filled = int(name_before - _blank(ct["track_name"]).sum())
    artists_filled = int(artist_before - _bad_artist(ct["artist_name"]).sum())
    print(f"  [spotify api] filled: {names_filled:,} track names, {artists_filled:,} artist names; failures: {failures:,}")
    return ct, names_filled, artists_filled, failures


def main(dry_run: bool, backup: bool) -> None:
    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)

    print("Downloading canonical_tracks.parquet …")
    ct = _dl(r2, "processed/canonical_tracks.parquet", "ct_meta_fix.parquet")
    n_rows = len(ct)

    blank_name_before        = _blank(ct["track_name"]).sum()
    blank_artist_before      = _blank(ct["artist_name"]).sum()
    placeholder_artist_before = (
        ct["artist_name"].fillna("").str.strip().str.lower().isin(_ARTIST_PLACEHOLDERS)
        & ~_blank(ct["artist_name"])  # exclude truly blank (already counted above)
    ).sum()
    print(f"  rows : {n_rows:,}")
    print(f"  blank track_name          : {blank_name_before:,}")
    print(f"  blank artist_name         : {blank_artist_before:,}")
    print(f"  placeholder artist_name   : {placeholder_artist_before:,}")

    if blank_name_before == 0 and blank_artist_before == 0 and placeholder_artist_before == 0:
        print("\nNo blank or placeholder metadata — nothing to do.")
        return

    # ── Source 1: deezer_tracks (Deezer API names) ────────────────────────────
    print("\nDownloading deezer_tracks.parquet …")
    dt = _dl(r2, "enrichment/deezer_tracks.parquet", "dt_meta_fix.parquet")
    ct, _, _ = _fill_from(ct, dt,
                           src_uri_col="spotify_track_uri",
                           src_name_col="deezer_title",
                           src_artist_col="deezer_artist",
                           label="deezer_tracks (deezer_title/artist)")

    # ── Source 2: editorial_playlist_tracks (Spotify API via mackorone) ───────
    print("\nDownloading editorial_playlist_tracks.parquet …")
    ept = _dl(r2, "processed/editorial_playlist_tracks.parquet", "ept_meta_fix.parquet")
    uri_col = "track_uri" if "track_uri" in ept.columns else "spotify_track_uri"
    ct, _, _ = _fill_from(ct, ept,
                           src_uri_col=uri_col,
                           src_name_col="track_name",
                           src_artist_col="artist_name",
                           label="editorial_playlist_tracks")

    # ── Source 3: Spotify API exact URI lookup for remaining bad rows ─────────
    ct, _, _, _ = _fill_from_spotify(ct)

    # ── Final audit ───────────────────────────────────────────────────────────
    blank_name_after        = _blank(ct["track_name"]).sum()
    blank_artist_after      = _blank(ct["artist_name"]).sum()
    placeholder_artist_after = (
        ct["artist_name"].fillna("").str.strip().str.lower().isin(_ARTIST_PLACEHOLDERS)
        & ~_blank(ct["artist_name"])
    ).sum()

    print(f"\n  blank track_name  after        : {blank_name_after:,}  "
          f"(filled {blank_name_before - blank_name_after:,})")
    print(f"  blank artist_name after        : {blank_artist_after:,}  "
          f"(filled {blank_artist_before - blank_artist_after:,})")
    print(f"  placeholder artist_name after  : {placeholder_artist_after:,}  "
          f"(filled {placeholder_artist_before - placeholder_artist_after:,})")

    # ── Flag unfillable rows (blank OR known-placeholder artist) ─────────────
    still_blank = _blank(ct["track_name"]) | _bad_artist(ct["artist_name"])
    n_unfillable = still_blank.sum()

    ct["needs_metadata"] = still_blank

    n_flagged = ct["needs_metadata"].sum()
    print(f"\n  unfillable (needs_metadata=True) : {n_unfillable:,}")
    print(f"  total flagged in column          : {n_flagged:,}")

    if n_unfillable:
        sample = ct[still_blank][["spotify_track_uri", "track_name", "artist_name"]].head(5)
        print("\n  Sample unfillable rows:")
        print(sample.to_string(index=False))

    if dry_run:
        print("\n[dry-run] skipping upload.")
        return

    if backup:
        src = _TMP / "ct_meta_fix.parquet"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_key = f"backups/processed/canonical_tracks.before_meta_fix.{stamp}.parquet"
        print(f"\nBacking up original canonical_tracks → R2:{backup_key} …")
        r2.upload(str(src), backup_key)

    out = _TMP / "canonical_tracks_meta_fixed.parquet"
    ct.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024 ** 2
    print(f"\nUploading {size_mb:.1f} MB → processed/canonical_tracks.parquet …")
    r2.upload(str(out), "processed/canonical_tracks.parquet")
    out.unlink(missing_ok=True)
    print("Done.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Report counts only; skip upload")
    p.add_argument("--no-backup", action="store_true",
                   help="Skip timestamped R2 backup before upload")
    args = p.parse_args()
    main(dry_run=args.dry_run, backup=not args.no_backup)
