"""
Data quality audit across all key R2 artifacts.

Checks:
  - row counts and null coverage for each artifact
  - duplicate primary keys
  - blank/null title and artist in canonical_tracks
  - orphan references (editorial playlist IDs not in playlists table)
  - artist name collisions (same lowercase name, different rows)
  - enrichment coverage: ISRC, MBID, deezer_id, listen_count
  - stale artifact timestamps (from data_manifest.json if present)
  - artist_stats completeness (top_tracks empty for high-rank artists)

Outputs a text report to stdout. Exit 0 always (non-fatal — this is a report, not a gate).

Usage:
    python src/compute/check_data_quality.py
    python src/compute/check_data_quality.py --verbose
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP = Path(tempfile.gettempdir()) / "track2vec_cache"
_SEP = "─" * 60


def _dl(r2: R2Client, key: str, fname: str) -> pd.DataFrame | None:
    """Download fresh from R2."""
    p = _TMP / fname
    p.unlink(missing_ok=True)
    try:
        r2.download(key, str(p))
        return pd.read_parquet(p)
    except Exception as e:
        print(f"  [SKIP] {key}: {e}")
        return None


def _check_cols(df: pd.DataFrame, label: str, required: list[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  [WARN] {label}: missing columns {missing}")


def _null_report(df: pd.DataFrame, cols: list[str], label: str) -> None:
    for col in cols:
        if col not in df.columns:
            continue
        if pd.api.types.is_bool_dtype(df[col]):
            n = df[col].fillna(False).sum()
            label_suffix = " true"
        else:
            n = df[col].notna().sum()
            label_suffix = ""
        pct = 100 * n / max(len(df), 1)
        flag = "" if pct >= 80 else "  ⚠" if pct >= 20 else "  ✗"
        print(f"    {(col + label_suffix):30s}: {n:>8,} / {len(df):,} ({pct:5.1f}%){flag}")


def main(verbose: bool) -> None:
    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)
    issues: list[str] = []

    # ── data_manifest.json ────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("data_manifest.json")
    print(_SEP)
    mp = _TMP / "data_manifest.json"
    mp.unlink(missing_ok=True)
    manifest = None
    try:
        r2.download("computed/data_manifest.json", str(mp))
        manifest = json.loads(mp.read_text())
        print(f"  generated_at : {manifest.get('generated_at', 'unknown')}")
        ct_m = manifest.get("canonical_tracks", {})
        print(f"  has_isrc_pct : {ct_m.get('has_isrc_pct', 'n/a')}%")
        print(f"  has_mbid_pct : {ct_m.get('has_mbid_pct', 'n/a')}%")
        print(f"  metadata_complete_pct: {ct_m.get('metadata_complete_pct', 'n/a')}%")
    except Exception as e:
        print(f"  [MISSING] data_manifest.json not found: {e}")
        issues.append("data_manifest.json not yet generated — run promote_mbid_canonical.py")

    # ── canonical_tracks ──────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("canonical_tracks.parquet")
    print(_SEP)
    ct = _dl(r2, "processed/canonical_tracks.parquet", "ct_qa.parquet")
    if ct is not None:
        print(f"  rows: {len(ct):,}")
        print(f"  columns: {list(ct.columns)}")
        _check_cols(ct, "canonical_tracks",
                    ["spotify_track_uri", "track_name", "artist_name", "isrc"])
        _null_report(ct, ["track_name", "artist_name", "isrc", "deezer_id",
                           "recording_mbid", "listen_count", "has_isrc", "has_mbid",
                           "metadata_complete"], "canonical_tracks")

        # Duplicate primary keys
        dup_uris = ct["spotify_track_uri"].duplicated().sum()
        if dup_uris:
            issues.append(f"canonical_tracks: {dup_uris:,} duplicate spotify_track_uri")
            print(f"  [✗] duplicate spotify_track_uri: {dup_uris:,}")
        else:
            print(f"  [✓] no duplicate spotify_track_uri")

        # Blank names (truly empty strings, not the 'artist' placeholder)
        blank_title  = ct["track_name"].fillna("").str.strip().eq("").sum()
        blank_artist = ct["artist_name"].fillna("").str.strip().eq("").sum()
        # "Various Artists" is valid; only the literal string "artist" is an MPD ingest placeholder
        placeholder_artist = ct["artist_name"].fillna("").str.strip().str.lower().eq("artist").sum()
        if blank_title:
            issues.append(f"canonical_tracks: {blank_title:,} blank track_name")
            print(f"  [✗] blank track_name     : {blank_title:,}")
        else:
            print(f"  [✓] no blank track_name")
        if blank_artist:
            issues.append(f"canonical_tracks: {blank_artist:,} blank artist_name")
            print(f"  [✗] blank artist_name    : {blank_artist:,}")
        else:
            print(f"  [✓] no blank artist_name")
        if placeholder_artist:
            issues.append(f"canonical_tracks: {placeholder_artist:,} artist_name='artist' placeholder")
            print(f"  [✗] placeholder artist   : {placeholder_artist:,}")

        # needs_metadata flag
        if "needs_metadata" in ct.columns:
            n_flagged     = int(ct["needs_metadata"].fillna(False).sum())
            truly_blank   = (ct["track_name"].fillna("").str.strip().eq("") |
                             ct["artist_name"].fillna("").str.strip().eq(""))
            n_truly_blank = int(truly_blank.sum())
            # Rows with artist='artist' placeholder but non-blank track_name
            placeholder_only = int((
                ct["artist_name"].fillna("").str.strip().str.lower().eq("artist")
                & ~ct["artist_name"].fillna("").str.strip().eq("")  # exclude truly blank
                & ~truly_blank  # not already counted in truly_blank
            ).sum())
            n_unflagged = n_truly_blank + placeholder_only - n_flagged
            print(f"  needs_metadata column    : present")
            print(f"  needs_metadata=True      : {n_flagged:,}")
            print(f"    of which truly blank   : {n_truly_blank:,}")
            print(f"    of which placeholder   : {n_flagged - n_truly_blank:,}  (artist_name='artist', track filled)")
            if n_unflagged > 0:
                issues.append(
                    f"canonical_tracks: {n_unflagged:,} bad rows not yet flagged needs_metadata — "
                    f"re-run fix_canonical_blank_metadata.py"
                )
                print(f"  [✗] unflagged bad rows   : {n_unflagged:,}  (re-run fix_canonical_blank_metadata.py)")
        else:
            issues.append("canonical_tracks: needs_metadata column missing — run fix_canonical_blank_metadata.py")
            print(f"  [✗] needs_metadata column: missing")

    # ── artist_stats ──────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("artist_stats.parquet")
    print(_SEP)
    ast = _dl(r2, "computed/artist_stats.parquet", "ast_qa.parquet")
    if ast is not None:
        print(f"  rows: {len(ast):,}")
        _null_report(ast, ["artist_name", "artist_uri", "playlist_count", "rank",
                            "top_tracks", "top_co_artists"], "artist_stats")

        # Name collisions
        name_counts = ast["artist_name"].str.lower().value_counts()
        dupes = name_counts[name_counts > 1]
        if not dupes.empty:
            issues.append(f"artist_stats: {len(dupes):,} lowercase name collisions")
            print(f"  [✗] lowercase name collisions: {len(dupes):,}")
            if verbose:
                for name, count in dupes.head(10).items():
                    print(f"      '{name}': {count} rows")
        else:
            print(f"  [✓] no lowercase name collisions")

        # top_tracks empty for high-rank artists
        if "top_tracks" in ast.columns and "rank" in ast.columns:
            top5k = ast[ast["rank"] <= 5000]
            tt_empty = top5k["top_tracks"].apply(
                lambda x: x is None or (hasattr(x, "__len__") and len(x) == 0)
            ).sum()
            if tt_empty:
                issues.append(f"artist_stats: {tt_empty:,} artists in top-5K with empty top_tracks")
                print(f"  [✗] top_tracks empty for {tt_empty:,} artists in rank ≤5K")
            # ranks 5001-10000
            bot5k = ast[ast["rank"] > 5000]
            tt_empty_bot = bot5k["top_tracks"].apply(
                lambda x: x is None or (hasattr(x, "__len__") and len(x) == 0)
            ).sum()
            if tt_empty_bot:
                print(f"  [⚠] top_tracks empty for {tt_empty_bot:,} artists in rank >5K (known gap)")

    # ── editorial_playlist_tracks ─────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("editorial_playlist_tracks.parquet")
    print(_SEP)
    ept = _dl(r2, "processed/editorial_playlist_tracks.parquet", "ept_qa.parquet")
    ep  = _dl(r2, "processed/editorial_playlists.parquet",       "ep_qa.parquet")
    if ept is not None:
        print(f"  rows: {len(ept):,}")
        _null_report(ept, ["track_uri", "track_name", "artist_name",
                            "artist_uri", "date_added"], "editorial_playlist_tracks")

        # Placeholder rows
        bad_name  = ept["artist_name"].fillna("").str.strip()
        bad_title = ept["track_name"].fillna("").str.strip()
        n_placeholder = (((bad_name == "") | (bad_name.str.lower() == "artist"))
                         & (bad_title == "")).sum()
        if n_placeholder:
            issues.append(f"editorial_playlist_tracks: {n_placeholder:,} placeholder rows in R2")
            print(f"  [✗] placeholder rows in R2: {n_placeholder:,}")
        else:
            print(f"  [✓] no placeholder rows")

        # Orphan playlist references
        if ep is not None:
            pid_col = "playlist_id" if "playlist_id" in ept.columns else "pid"
            if pid_col in ept.columns:
                ep_pid_col = "playlist_id" if "playlist_id" in ep.columns else "pid"
                known_pids = set(ep[ep_pid_col].dropna()) if ep_pid_col in ep.columns else set()
                track_pids  = set(ept[pid_col].dropna())
                orphan_pids = track_pids - known_pids
                if orphan_pids:
                    issues.append(f"editorial: {len(orphan_pids):,} track playlist IDs not in playlists table")
                    print(f"  [✗] orphan playlist IDs: {len(orphan_pids):,}")
                missing_pids = known_pids - track_pids
                if missing_pids:
                    print(f"  [⚠] playlists with no track rows: {len(missing_pids):,}")

    if ep is not None:
        print(f"\n  editorial_playlists rows: {len(ep):,}")

    # ── artist_genres ─────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("artist_genres.parquet")
    print(_SEP)
    ag = _dl(r2, "enrichment/artist_genres.parquet", "ag_qa.parquet")
    if ag is not None:
        print(f"  rows: {len(ag):,}")
        tags_col = "tags" if "tags" in ag.columns else "genres"
        if tags_col in ag.columns:
            empty_tags = ag[tags_col].apply(
                lambda x: x is None or (hasattr(x, "__len__") and len(x) == 0)
            ).sum()
            print(f"  artists with empty tags: {empty_tags:,} / {len(ag):,}")
            if empty_tags > 0:
                issues.append(f"artist_genres: {empty_tags:,} artists with empty tags")

    # ── listenbrainz_full ─────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("listenbrainz_full.parquet")
    print(_SEP)
    lb = _dl(r2, "enrichment/listenbrainz_full.parquet", "lb_qa.parquet")
    if lb is not None:
        print(f"  rows: {len(lb):,}")
        _null_report(lb, ["recording_mbid", "listen_count", "isrc"], "listenbrainz_full")
        if "listen_count" in lb.columns:
            n_zero = (lb["listen_count"].fillna(0) <= 0).sum()
            print(f"  zero/null listen_count: {n_zero:,}")
            if n_zero > 10_000:
                issues.append(f"listenbrainz_full: {n_zero:,} rows with nonpositive listen_count")

    # ── deezer_tracks ─────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("deezer_tracks.parquet")
    print(_SEP)
    dt = _dl(r2, "enrichment/deezer_tracks.parquet", "dt_qa.parquet")
    if dt is not None:
        print(f"  rows: {len(dt):,}")
        uri_col = "spotify_track_uri" if "spotify_track_uri" in dt.columns else "track_uri"
        if uri_col in dt.columns:
            dup_uris = dt[uri_col].duplicated().sum()
            if dup_uris:
                issues.append(f"deezer_tracks: {dup_uris:,} duplicate {uri_col}")
                print(f"  [✗] duplicate {uri_col}: {dup_uris:,}")
            else:
                print(f"  [✓] no duplicate {uri_col}")
        _null_report(dt, ["isrc", "deezer_id", uri_col], "deezer_tracks")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("ISSUES SUMMARY")
    print(_SEP)
    if issues:
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("  No issues found.")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", action="store_true", help="Show extra detail (e.g. collision names)")
    args = p.parse_args()
    main(verbose=args.verbose)
