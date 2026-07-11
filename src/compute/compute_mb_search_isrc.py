"""
Find ISRCs for tracks missing them using MusicBrainz recording search API.

The MBDump approach matched by ISRC key — but many tracks have version suffixes
("Stay (with Alessia Cara)", "- Remastered 2020") that prevent key matching.
The live search API is fuzzy and handles these cases.

Also extracts recording_mbid, useful for ListenBrainz listen count lookup.

Output: enrichment/mb_search_isrc.parquet  (track_uri, isrc, recording_mbid)
        — format compatible with merge_isrc_enrichment.py

Rate: 1 req/s hard limit (MusicBrainz policy). Targets ≥ 50 appearances.
      43K tracks ≈ 12 hours.

Usage:
    python src/compute/compute_mb_search_isrc.py
    python src/compute/compute_mb_search_isrc.py --min-appearances 100
    python src/compute/compute_mb_search_isrc.py --limit 500   # test run
    python src/compute/compute_mb_search_isrc.py --resume
"""

import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP        = Path(tempfile.gettempdir())
_CACHE      = _TMP / "track2vec_cache"
_CHECKPOINT = _TMP / "mb_search_isrc_checkpoint.parquet"
_MB_URL     = "https://musicbrainz.org/ws/2/recording/"
_USER_AGENT = "MusicIntelligenceAtlas/1.0 (useother49@gmail.com)"
_DELAY      = 1.05   # MusicBrainz: max 1 req/s
_CHECKPOINT_EVERY = 500


# ── Title normalisation (same as deezer_search_isrc) ─────────────────────────

_CLEAN_PATTERNS = [
    (r'\s*\(feat\.?\s.*?\)',           ''),
    (r'\s*\(ft\.?\s.*?\)',             ''),
    (r'\s*\(with\s.*?\)',              ''),
    (r'\s*feat\.?\s+[\w\s&,]+',       ''),
    (r'\s*ft\.?\s+[\w\s&,]+',         ''),
    (r'\s*-\s*From\s+["\'].*',        ''),
    (r'\s*\(From\s+.*?\)',             ''),
    (r'\s*\(Original Song.*?\)',       ''),
    (r'\s*\(Original Motion.*?\)',     ''),
    (r'\s*-\s*(Remastered|Remaster).*$',   ''),
    (r'\s*\(.*?(Remastered|Remaster).*?\)', ''),
    (r'\s*-\s*(Radio Edit|Album Version|Explicit|Clean|Edited).*$', ''),
    (r'\s*\(.*?(Radio Edit|Album Version|Explicit Version).*?\)',    ''),
    (r'\s*-\s*(Live|Acoustic|Extended|Instrumental).*$', ''),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _CLEAN_PATTERNS]

def _clean(title: str) -> str:
    for pat, repl in _COMPILED:
        title = pat.sub(repl, title)
    return title.strip()

def _tokens(s: str) -> set[str]:
    return set(re.sub(r"[^\w\s]", "", s.lower()).split())

def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.5


# ── Single MB lookup ──────────────────────────────────────────────────────────

def _mb_search(session: requests.Session, artist: str, title: str) -> tuple[str | None, str | None]:
    """Returns (isrc, recording_mbid) or (None, None)."""
    clean = _clean(title)
    if not clean:
        clean = title[:50]

    # Escape special chars for Lucene query syntax
    def esc(s):
        return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r'\\\1', s)

    query = f'artist:"{esc(artist)}" AND recording:"{esc(clean)}"'

    for attempt in range(3):
        try:
            resp = session.get(
                _MB_URL,
                params={"query": query, "fmt": "json", "limit": 5},
                headers={"User-Agent": _USER_AGENT},
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if resp.status_code != 200:
                return None, None
            data = resp.json()
            for rec in data.get("recordings", []):
                if int(rec.get("score", 0)) < 70:
                    continue
                isrcs = rec.get("isrcs", [])
                if not isrcs:
                    continue
                rec_title  = rec.get("title", "")
                rec_artist = (rec.get("artist-credit") or [{}])[0].get("artist", {}).get("name", "")
                if _similar(clean, rec_title) and _similar(artist, rec_artist):
                    return isrcs[0], rec.get("id")
            return None, None
        except requests.RequestException:
            time.sleep(2)
    return None, None


# ── Main ──────────────────────────────────────────────────────────────────────

def main(min_appearances: int, limit: int | None, resume: bool) -> None:
    r2 = R2Client()

    print("Loading canonical_tracks …")
    ct_path = _CACHE / "canonical_tracks.parquet"
    if not ct_path.exists():
        r2.download("processed/canonical_tracks.parquet", str(ct_path))
    ct = pd.read_parquet(ct_path)

    print("Loading playlist_tracks for frequency rank …")
    pt_path = _CACHE / "playlist_tracks.parquet"
    if not pt_path.exists():
        r2.download("processed/playlist_tracks.parquet", str(pt_path))
    freq = (pd.read_parquet(pt_path)
            .groupby("track_uri").size()
            .reset_index(name="appearances"))

    ranked = (ct.merge(freq, left_on="spotify_track_uri", right_on="track_uri", how="inner")
               .sort_values("appearances", ascending=False))
    targets = ranked[ranked["isrc"].isna() & (ranked["appearances"] >= min_appearances)]
    print(f"Targets (no ISRC, >= {min_appearances} appearances): {len(targets):,}")

    done_uris: set[str] = set()
    if resume and _CHECKPOINT.exists():
        ckpt = pd.read_parquet(_CHECKPOINT)
        done_uris = set(ckpt["track_uri"])
        print(f"Resuming — {len(done_uris):,} already done")
    else:
        ckpt = pd.DataFrame(columns=["track_uri", "isrc", "recording_mbid"])

    targets = targets[~targets["spotify_track_uri"].isin(done_uris)]
    if limit:
        targets = targets.head(limit)
        print(f"--limit {limit}: processing {len(targets):,}")

    if targets.empty:
        print("Nothing to do.")
        return

    print(f"Searching MusicBrainz for {len(targets):,} tracks at ~1 req/s …")
    if len(targets) > 0:
        print(f"Estimated time: {len(targets)/3600:.1f}h")

    session  = requests.Session()
    new_rows = []
    found    = 0
    t0       = time.time()

    for i, (_, row) in enumerate(targets.iterrows()):
        time.sleep(_DELAY)
        uri    = row["spotify_track_uri"]
        isrc, mbid = _mb_search(session, row["artist_name"], row["track_name"])
        if isrc:
            new_rows.append({"track_uri": uri, "isrc": isrc, "recording_mbid": mbid})
            found += 1

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate    = (i + 1) / elapsed
            eta     = (len(targets) - i - 1) / rate if rate > 0 else 0
            print(f"  {i+1:,}/{len(targets):,} | found: {found:,} ({100*found/(i+1):.1f}%) "
                  f"| {rate:.2f} req/s | ETA {eta/3600:.1f}h", flush=True)

        if (i + 1) % _CHECKPOINT_EVERY == 0 and new_rows:
            ckpt = pd.concat([ckpt, pd.DataFrame(new_rows)], ignore_index=True)
            new_rows = []
            ckpt.to_parquet(_CHECKPOINT, index=False)

    if new_rows:
        ckpt = pd.concat([ckpt, pd.DataFrame(new_rows)], ignore_index=True)

    ckpt.to_parquet(_CHECKPOINT, index=False)
    elapsed = time.time() - t0
    print(f"\nDone: {len(targets):,} searched in {elapsed/60:.0f}m | {found:,} found ({100*found/max(len(targets),1):.1f}%)")

    if ckpt.empty or "isrc" not in ckpt.columns:
        print("No matches to upload.")
        return

    out = ckpt[ckpt["isrc"].notna()].copy()
    out["listen_count"] = None
    out_path = _TMP / "mb_search_isrc.parquet"
    out.to_parquet(out_path, index=False, compression="zstd")
    r2.upload(str(out_path), "enrichment/mb_search_isrc.parquet")
    print(f"Uploaded {len(out):,} ISRC matches to R2.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min-appearances", type=int, default=50)
    p.add_argument("--limit",           type=int, default=None)
    p.add_argument("--resume",          action="store_true")
    args = p.parse_args()
    main(args.min_appearances, args.limit, args.resume)
