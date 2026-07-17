from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, duck_df, duck_one
from src.app.helpers import _to_list, _resolve_artist_row
from src.storage.duckdb_r2 import R2_PATH

router = APIRouter()


@router.get("/api/search-tracks")
def search_tracks(q: str = "", limit: int = 10):
    if len(q.strip()) < 2:
        return {"results": []}

    q_lower = q.lower().strip()
    limit   = min(limit, 20)
    seen: set[tuple] = set()
    results = []

    # Stream the vocab lookup (sorted by track_name_lc, small row groups) via
    # DuckDB: the prefix predicate prunes row groups, and prefix matches are
    # ranked ahead of substring matches. Avoids the 148 MB resident DataFrame.
    vpath = local_parquet("embeddings/track2vec_vocab_lookup.parquet")
    if vpath is not None:
        safe_q = q_lower.replace("'", "''")
        try:
            # idx is popularity rank (0 = most popular), so ORDER BY pri, idx
            # returns prefix matches first, most-popular version of each first —
            # restoring the ranking the old popularity-ordered vocab gave.
            df = duck_df(f"""
                SELECT track_name, artist_name, track_uri,
                       CASE WHEN track_name_lc LIKE '{safe_q}%' THEN 0 ELSE 1 END AS pri
                FROM read_parquet('{vpath.as_posix()}')
                WHERE track_name_lc LIKE '%{safe_q}%'
                ORDER BY pri, idx
                LIMIT {limit * 4}
            """)
            for _, row in df.iterrows():
                key = (row["track_name"], row["artist_name"])
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "title":  row["track_name"],
                    "artist": row["artist_name"],
                    "uri":    row["track_uri"],
                })
                if len(results) >= limit:
                    break
        except Exception:
            pass

    # Top up from the fuller tracks.parquet: the FAISS vocab only covers
    # embeddable tracks, so many titles are searchable but missing from it.
    if len(results) < limit:
        try:
            safe = q_lower.replace("'", "''")
            df = duck_df(f"""
                SELECT DISTINCT track_name, artist_name, track_uri
                FROM read_parquet('{R2_PATH}/processed/tracks.parquet')
                WHERE lower(track_name) LIKE '{safe}%'
                ORDER BY track_name LIMIT {limit}
            """)
            for _, r in df.iterrows():
                key = (r["track_name"], r["artist_name"])
                if key in seen:
                    continue
                seen.add(key)
                results.append({"title": r["track_name"], "artist": r["artist_name"], "uri": r["track_uri"]})
                if len(results) >= limit:
                    break
        except Exception:
            pass

    return {"results": results}


@router.get("/api/song-passport/{track}")
def song_passport(track: str):
    safe = track.replace("'", "''")
    try:
        _COLS = "track_uri, track_name, artist_name, playlist_count, top_playlist_names"

        # Fast path: the top-300K popular tracks live in a small (~19 MB) local
        # parquet, sorted by track_name_lc with small row groups so this equality
        # filter prunes to ~1 row group. Covers every demo-relevant track.
        rows = None
        ts_path = local_parquet("computed/track_stats_top.parquet")
        if ts_path is not None:
            rows = duck_df(f"""
                SELECT {_COLS} FROM read_parquet('{ts_path.as_posix()}')
                WHERE track_name_lc = lower('{safe}') ORDER BY playlist_count DESC
            """)

        # Miss → query the FULL pre-aggregated table directly from R2 (never
        # downloaded locally). It's sorted by track_name_lc with small row groups,
        # so httpfs predicate pushdown fetches only the matching row group — a tiny
        # read, not the 806 MB raw-table join.
        if rows is None or rows.empty:
            rows = duck_df(f"""
                SELECT {_COLS} FROM read_parquet('{R2_PATH}/computed/track_stats_lookup.parquet')
                WHERE track_name_lc = lower('{safe}') ORDER BY playlist_count DESC
            """)

        if rows is None or rows.empty:
            raise HTTPException(404, detail="track_not_found")
        row           = rows.iloc[0]
        pc            = int(row["playlist_count"])
        artist        = row["artist_name"]
        name          = row["track_name"]
        track_uri     = row["track_uri"]
        names_df      = pd.DataFrame({"name": _to_list(row.get("top_playlist_names"))})
        other_artists = rows["artist_name"].iloc[1:].tolist() if len(rows) > 1 else []

        lb_listen_count: Optional[int] = None
        lb_isrc: Optional[str] = None
        # listenbrainz_lookup is sorted by spotify_track_uri (small row groups),
        # so this point lookup prunes to one group instead of a 195 MB DataFrame.
        lb_path = local_parquet("enrichment/listenbrainz_lookup.parquet")
        if lb_path is not None:
            lb = duck_one(
                f"SELECT listen_count, isrc FROM read_parquet('{lb_path.as_posix()}') "
                f"WHERE spotify_track_uri = ? LIMIT 1", [track_uri],
            )
            if lb is not None:
                v = lb[0]
                lb_listen_count = int(v) if v is not None and int(v) > 0 else None
                isrc_v = lb[1]
                lb_isrc = str(isrc_v) if isrc_v is not None and str(isrc_v) != "nan" else None

        mb_genres: Optional[list] = None
        ag_df = _load_computed("enrichment/artist_genres.parquet")
        if ag_df is not None:
            _ag_r = _resolve_artist_row(ag_df, artist)
            if _ag_r is not None:
                raw_tags = _ag_r.get("tags")
                if raw_tags is not None and not (isinstance(raw_tags, float) and pd.isna(raw_tags)):
                    try:
                        mb_genres = list(raw_tags)[:8] if hasattr(raw_tags, "__iter__") else None
                    except Exception:
                        mb_genres = None

        fma: dict = {}
        fma_df = _load_computed("enrichment/fma_enrichment.parquet")
        if fma_df is not None:
            fma_rows = fma_df[fma_df["track_uri"] == track_uri]
            if not fma_rows.empty:
                r = fma_rows.iloc[0]
                _fma_audio_cols = [
                    "fma_acousticness", "fma_danceability", "fma_energy",
                    "fma_instrumentalness", "fma_liveness", "fma_speechiness",
                    "fma_tempo", "fma_valence",
                ]
                audio = {
                    col.replace("fma_", ""): (round(float(r[col]), 4) if not pd.isna(r.get(col)) else None)
                    for col in _fma_audio_cols
                }
                fma = {
                    "play_count": int(r["fma_play_count"]) if not pd.isna(r.get("fma_play_count")) else None,
                    "audio":      audio,
                    "match_type": r.get("match_type"),
                }

        result: dict = {
            "title":              name,
            "artist":             artist,
            "playlist_count":     pc,
            "pct":                round(pc / 1_000_000 * 100, 3),
            "top_playlist_names": names_df["name"].tolist(),
            "lb_listen_count":    lb_listen_count,
            "isrc":               lb_isrc,
            "genres":             mb_genres,
        }
        if fma:
            result["fma"] = fma
        if other_artists:
            result["version_note"] = (
                f"Multiple artists have a track titled '{name}' "
                f"({', '.join(other_artists[:3])}{'…' if len(other_artists) > 3 else ''} also have this title). "
                f"Showing the most-played version."
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, detail=f"query_failed: {e}")
