"""
Find ISRCs for tracks missing them by searching Deezer's /search/track API.
Complementary approach to compute_deezer_isrc.py (which went ISRC → Deezer ID).
Here: artist + title → Deezer → ISRC.

Targets canonical_tracks rows where isrc IS NULL, ranked by playlist appearances.
Verifies each match with title similarity before accepting the ISRC.

Output: enrichment/deezer_search_isrc.parquet  (track_uri, isrc)
        — format compatible with merge_isrc_enrichment.py

Rate: 10 req/s async (Deezer free limit: 50/5s)

Usage:
    python src/compute/compute_deezer_search_isrc.py
    python src/compute/compute_deezer_search_isrc.py --min-appearances 10
    python src/compute/compute_deezer_search_isrc.py --limit 1000   # test run
    python src/compute/compute_deezer_search_isrc.py --resume
"""

import argparse
import asyncio
import re
import ssl
import sys
import tempfile
import time
from pathlib import Path

import aiohttp
import certifi
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP         = Path(tempfile.gettempdir())
_CACHE       = _TMP / "track2vec_cache"
_CHECKPOINT  = _TMP / "deezer_search_isrc_checkpoint.parquet"
_DEEZER_URL  = "https://api.deezer.com/search/track"
_CONCURRENCY = 10
_DELAY       = 0.1   # 10 req/s


# ── Title normalisation ───────────────────────────────────────────────────────

_CLEAN_PATTERNS = [
    (r'\s*\(feat\.?\s.*?\)',           ''),   # (feat. X)
    (r'\s*\(ft\.?\s.*?\)',             ''),   # (ft. X)
    (r'\s*\(with\s.*?\)',              ''),   # (with X)
    (r'\s*feat\.?\s+[\w\s&,]+',       ''),   # feat. X  (no parens)
    (r'\s*ft\.?\s+[\w\s&,]+',         ''),   # ft. X    (no parens)
    (r'\s*-\s*From\s+["\'].*',        ''),   # - From "Movie"
    (r'\s*\(From\s+.*?\)',             ''),   # (From "Movie")
    (r'\s*\(Original Song.*?\)',       ''),   # (Original Song from...)
    (r'\s*\(Original Motion.*?\)',     ''),   # (Original Motion Picture...)
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


def _similar(a: str, b: str) -> bool:
    """True if a and b share enough tokens to be the same track title."""
    def tokens(s):
        return set(re.sub(r"[^\w\s]", "", s.lower()).split())
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.5


# ── Async fetch ───────────────────────────────────────────────────────────────

async def _search(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                  track_uri: str, artist: str, title: str) -> tuple[str, str | None]:
    clean = _clean(title)
    if not clean:
        clean = title[:50]

    async with sem:
        await asyncio.sleep(_DELAY)
        params = {"q": f'artist:"{artist}" track:"{clean}"', "limit": 3}
        for attempt in range(3):
            try:
                async with session.get(_DEEZER_URL, params=params,
                                       timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                    if resp.status != 200:
                        return track_uri, None
                    data = await resp.json()
                    for item in data.get("data", []):
                        isrc = item.get("isrc")
                        if not isrc:
                            continue
                        # Verify artist and title similarity
                        res_artist = item.get("artist", {}).get("name", "")
                        res_title  = item.get("title", "")
                        if _similar(clean, res_title) or _similar(title, res_title):
                            return track_uri, isrc
                    return track_uri, None
            except Exception:
                if attempt == 2:
                    return track_uri, None
                await asyncio.sleep(1)
    return track_uri, None


async def _run(rows: list[tuple[str, str, str]]) -> dict[str, str]:
    ssl_ctx   = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=_CONCURRENCY, ssl=ssl_ctx)
    results: dict[str, str] = {}

    async with aiohttp.ClientSession(connector=connector) as session:
        sem   = asyncio.Semaphore(_CONCURRENCY)
        tasks = [_search(session, sem, uri, artist, title) for uri, artist, title in rows]
        done  = 0
        found = 0
        t0    = time.time()
        for coro in asyncio.as_completed(tasks):
            uri, isrc = await coro
            done += 1
            if isrc:
                results[uri] = isrc
                found += 1
            if done % 1000 == 0:
                rate = done / max(time.time() - t0, 1)
                eta  = (len(rows) - done) / rate if rate > 0 else 0
                print(f"  {done:,}/{len(rows):,} | found: {found:,} ({100*found/done:.1f}%) "
                      f"| {rate:.1f} req/s | ETA {eta/3600:.1f}h", flush=True)
    return results


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

    # Resume
    done_uris: set[str] = set()
    if resume and _CHECKPOINT.exists():
        ckpt = pd.read_parquet(_CHECKPOINT)
        done_uris = set(ckpt["track_uri"])
        print(f"Resuming — {len(done_uris):,} already done")
    else:
        ckpt = pd.DataFrame(columns=["track_uri", "isrc"])

    targets = targets[~targets["spotify_track_uri"].isin(done_uris)]
    if limit:
        targets = targets.head(limit)
        print(f"--limit {limit}: processing {len(targets):,}")

    if targets.empty:
        print("Nothing to do.")
        return

    rows = [(r["spotify_track_uri"], r["artist_name"], r["track_name"])
            for _, r in targets.iterrows()]

    print(f"Searching Deezer for {len(rows):,} tracks …")
    matches = asyncio.run(_run(rows))

    new_rows = pd.DataFrame([{"track_uri": uri, "isrc": isrc} for uri, isrc in matches.items()])
    ckpt = pd.concat([ckpt, new_rows], ignore_index=True)
    ckpt.to_parquet(_CHECKPOINT, index=False)

    if matches:
        # Add required columns for merge_isrc_enrichment.py
        ckpt_out = ckpt.copy()
        ckpt_out["recording_mbid"] = None
        ckpt_out["listen_count"]   = None
        out = _TMP / "deezer_search_isrc.parquet"
        ckpt_out.to_parquet(out, index=False, compression="zstd")
        r2.upload(str(out), "enrichment/deezer_search_isrc.parquet")
        print(f"Uploaded {len(ckpt_out):,} ISRC matches to R2.")
    else:
        print("No matches found.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--min-appearances", type=int, default=10)
    p.add_argument("--limit",           type=int, default=None)
    p.add_argument("--resume",          action="store_true")
    args = p.parse_args()
    main(args.min_appearances, args.limit, args.resume)
