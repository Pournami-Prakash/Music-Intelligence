"""
Expand Deezer coverage by looking up tracks via ISRC using Deezer's free
/track/isrc/{isrc} endpoint (no auth required).

Finds all canonical_tracks rows where isrc IS NOT NULL AND deezer_id IS NULL,
queries Deezer, then patches canonical_tracks.parquet in place and uploads.

Also appends matches to enrichment/deezer_tracks.parquet for the pipeline record.

Rate limit: 50 req / 5s = 10 req/s safe. 652K ISRCs ≈ 18 hours.
Uses asyncio + aiohttp with 10 concurrent requests and a 0.1s delay.

Usage:
    python src/compute/compute_deezer_isrc.py
    python src/compute/compute_deezer_isrc.py --resume           # skip already-done ISRCs
    python src/compute/compute_deezer_isrc.py --limit 10000      # test run
"""

import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path

import ssl

import aiohttp
import certifi
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP           = Path(tempfile.gettempdir())
_CHECKPOINT    = _TMP / "deezer_isrc_checkpoint.parquet"
_DEEZER_URL    = "https://api.deezer.com/track/isrc:{isrc}"
_CONCURRENCY   = 10
_DELAY         = 0.1   # 10 req/s per connection
_SAVE_EVERY    = 1000


async def _fetch_isrc(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                      isrc: str) -> tuple[str, int | None]:
    async with sem:
        await asyncio.sleep(_DELAY)
        url = _DEEZER_URL.format(isrc=isrc)
        for attempt in range(3):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                    if resp.status == 404:
                        return isrc, None
                    if resp.status != 200:
                        return isrc, None
                    data = await resp.json()
                    # Deezer returns {"error": {...}} for not-found even with 200
                    if "error" in data:
                        return isrc, None
                    deezer_id = data.get("id")
                    return isrc, int(deezer_id) if deezer_id else None
            except Exception:
                if attempt == 2:
                    return isrc, None
                await asyncio.sleep(2)
    return isrc, None


async def _run(isrcs: list[str]) -> dict[str, int]:
    sem     = asyncio.Semaphore(_CONCURRENCY)
    results: dict[str, int] = {}

    ssl_ctx   = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(limit=_CONCURRENCY, ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks   = [_fetch_isrc(session, sem, isrc) for isrc in isrcs]
        done    = 0
        matched = 0
        t0      = time.time()

        for coro in asyncio.as_completed(tasks):
            isrc, deezer_id = await coro
            done += 1
            if deezer_id:
                results[isrc] = deezer_id
                matched += 1

            if done % 500 == 0:
                elapsed = time.time() - t0
                rate    = done / elapsed
                eta_s   = (len(isrcs) - done) / rate if rate > 0 else 0
                print(f"  {done:,}/{len(isrcs):,} | matched: {matched:,} ({100*matched/done:.1f}%) "
                      f"| {rate:.1f} req/s | ETA {eta_s/3600:.1f}h", flush=True)

    return results


def main(limit: int | None, resume: bool) -> None:
    r2 = R2Client()

    print("Downloading canonical_tracks.parquet …")
    ct_path = _TMP / "canonical_tracks_deezer.parquet"
    r2.download("processed/canonical_tracks.parquet", str(ct_path))
    ct = pd.read_parquet(ct_path)

    candidates = ct[ct["isrc"].notna() & ct["deezer_id"].isna()].copy()
    print(f"Candidates (isrc present, deezer_id missing): {len(candidates):,}")

    if resume and _CHECKPOINT.exists():
        done_df = pd.read_parquet(_CHECKPOINT)
        done_isrcs = set(done_df["isrc"])
        candidates = candidates[~candidates["isrc"].isin(done_isrcs)]
        print(f"Resuming — {len(done_isrcs):,} already done, {len(candidates):,} remaining")
    else:
        done_df = pd.DataFrame(columns=["isrc", "deezer_id"])

    if limit:
        candidates = candidates.head(limit)
        print(f"--limit {limit}: processing {len(candidates):,} rows")

    isrcs = candidates["isrc"].tolist()
    if not isrcs:
        print("Nothing to do.")
        return

    print(f"Querying Deezer for {len(isrcs):,} ISRCs …")
    t_start = time.time()
    matches = asyncio.run(_run(isrcs))
    elapsed = time.time() - t_start
    print(f"\nFinished {len(isrcs):,} lookups in {elapsed/60:.1f} min")
    print(f"Matches found: {len(matches):,} / {len(isrcs):,} ({100*len(matches)/len(isrcs):.1f}%)")

    # Save checkpoint
    new_rows = pd.DataFrame([
        {"isrc": isrc, "deezer_id": deezer_id}
        for isrc, deezer_id in matches.items()
    ])
    done_df = pd.concat([done_df, new_rows], ignore_index=True)
    done_df.to_parquet(_CHECKPOINT, index=False)

    if not matches:
        print("No new Deezer IDs found — nothing to upload.")
        return

    # Patch canonical_tracks in memory
    # canonical_tracks stores deezer_id as string
    isrc_to_deezer = {
        isrc: str(int(did))
        for isrc, did in done_df.dropna(subset=["deezer_id"]).set_index("isrc")["deezer_id"].items()
    }
    mask = ct["isrc"].isin(isrc_to_deezer) & ct["deezer_id"].isna()
    ct.loc[mask, "deezer_id"] = ct.loc[mask, "isrc"].map(isrc_to_deezer)
    print(f"canonical_tracks deezer_id now: {ct['deezer_id'].notna().sum():,} ({100*ct['deezer_id'].notna().mean():.1f}%)")

    print("Uploading canonical_tracks.parquet …")
    updated_path = _TMP / "canonical_tracks_deezer_updated.parquet"
    ct.to_parquet(updated_path, index=False, compression="zstd")
    r2.upload(str(updated_path), "processed/canonical_tracks.parquet")

    # Append new matches to deezer_tracks.parquet for pipeline record
    print("Updating deezer_tracks.parquet …")
    dt_path = _TMP / "deezer_tracks_existing.parquet"
    r2.download("enrichment/deezer_tracks.parquet", str(dt_path))
    dt = pd.read_parquet(dt_path)

    # Build new rows from candidates + matches
    new_dt_rows = []
    for _, row in ct[mask].iterrows():
        isrc = row["isrc"]
        if isrc in isrc_to_deezer:
            new_dt_rows.append({
                "spotify_track_uri": row["spotify_track_uri"],
                "track_name":        row["track_name"],
                "artist_name":       row["artist_name"],
                "deezer_id":         isrc_to_deezer[isrc],
                "isrc":              isrc,
                "deezer_title":      None,
                "deezer_artist":     None,
                "matched":           True,
            })
    if new_dt_rows:
        dt = pd.concat([dt, pd.DataFrame(new_dt_rows)], ignore_index=True)
        # Quality sort before dedup: prefer rows that are matched with ISRC and deezer_id present
        dt["_has_isrc"]  = dt["isrc"].notna().astype(int)
        dt["_has_did"]   = dt["deezer_id"].notna().astype(int)
        dt["_matched"]   = dt.get("matched", pd.Series(False, index=dt.index)).fillna(False).astype(int)
        dt = (dt.sort_values(["_matched", "_has_isrc", "_has_did"], ascending=False)
                .drop(columns=["_has_isrc", "_has_did", "_matched"])
                .drop_duplicates(subset=["spotify_track_uri"], keep="first"))
        dt_out = _TMP / "deezer_tracks_updated.parquet"
        dt.to_parquet(dt_out, index=False, compression="zstd")
        r2.upload(str(dt_out), "enrichment/deezer_tracks.parquet")
        print(f"deezer_tracks.parquet: {len(dt):,} total rows (best-row-wins dedup)")

    print("\nDone.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit",  type=int, default=None, help="Process only first N ISRCs (for testing)")
    p.add_argument("--resume", action="store_true",    help="Skip ISRCs already in checkpoint")
    args = p.parse_args()
    main(limit=args.limit, resume=args.resume)
