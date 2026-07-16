from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, con
from src.app.helpers import _to_list, _resolve_artist_row
from src.storage.duckdb_r2 import R2_PATH

router = APIRouter()


@router.get("/api/search-tracks")
def search_tracks(q: str = "", limit: int = 10):
    if len(q.strip()) < 2:
        return {"results": []}

    vocab = _load_computed("embeddings/track2vec_vocab.parquet")
    if vocab is None:
        safe = q.replace("'", "''")
        try:
            df = con.execute(f"""
                SELECT DISTINCT t.track_name, t.artist_name, t.track_uri
                FROM read_parquet('{R2_PATH}/processed/tracks.parquet') t
                WHERE lower(t.track_name) LIKE lower('{safe}%')
                ORDER BY t.track_name LIMIT {min(limit, 20)}
            """).df()
            return {"results": [
                {"title": r["track_name"], "artist": r["artist_name"], "uri": r["track_uri"]}
                for _, r in df.iterrows()
            ]}
        except Exception:
            return {"results": []}

    q_lower = q.lower().strip()
    limit   = min(limit, 20)
    seen: set[tuple] = set()
    results = []

    for mask_fn in [
        lambda n: n.startswith(q_lower),
        lambda n: q_lower in n and not n.startswith(q_lower),
    ]:
        for _, row in vocab[vocab["track_name"].str.lower().str.contains(q_lower, na=False, regex=False)].iterrows():
            name_lower = row["track_name"].lower()
            if not mask_fn(name_lower):
                continue
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
        if len(results) >= limit:
            break

    # Top up from the fuller tracks.parquet: the FAISS vocab only covers
    # embeddable tracks, so many titles are searchable but missing from it.
    if len(results) < limit:
        try:
            safe = q_lower.replace("'", "''")
            df = con.execute(f"""
                SELECT DISTINCT track_name, artist_name, track_uri
                FROM read_parquet('{R2_PATH}/processed/tracks.parquet')
                WHERE lower(track_name) LIKE '{safe}%'
                ORDER BY track_name LIMIT {limit}
            """).df()
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
        # Stream the (big) track_stats parquet from local disk via DuckDB rather
        # than loading the whole ~840 MB DataFrame into memory.
        ts_path = local_parquet("computed/track_stats.parquet")
        rows = None
        if ts_path is not None:
            rows = con.execute(f"""
                SELECT track_uri, track_name, artist_name, playlist_count, top_playlist_names
                FROM read_parquet('{ts_path.as_posix()}')
                WHERE lower(track_name) = lower('{safe}')
                ORDER BY playlist_count DESC
            """).df()
        if rows is not None and not rows.empty:
            row           = rows.iloc[0]
            pc            = int(row["playlist_count"])
            artist        = row["artist_name"]
            name          = row["track_name"]
            track_uri     = row["track_uri"]
            names_df      = pd.DataFrame({"name": _to_list(row.get("top_playlist_names"))})
            other_artists = rows["artist_name"].iloc[1:].tolist() if len(rows) > 1 else []
        else:
            combined_df = con.execute(f"""
                WITH matched AS (
                    SELECT t.track_uri, t.track_name, t.artist_name, pt.pid
                    FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
                    JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t ON pt.track_uri = t.track_uri
                    WHERE lower(t.track_name) = lower('{safe}')
                )
                SELECT
                    m.track_uri, m.track_name, m.artist_name,
                    COUNT(DISTINCT m.pid)              AS playlist_count,
                    list(p.name ORDER BY p.name)[1:10] AS top_names
                FROM matched m
                JOIN read_parquet('{R2_PATH}/processed/playlists.parquet') p ON m.pid = p.pid
                WHERE p.name IS NOT NULL AND length(trim(p.name)) > 0
                GROUP BY m.track_uri, m.track_name, m.artist_name
                ORDER BY playlist_count DESC LIMIT 1
            """).df()
            if combined_df.empty:
                raise HTTPException(404, detail="track_not_found")
            pc            = int(combined_df.iloc[0]["playlist_count"])
            artist        = combined_df.iloc[0]["artist_name"]
            name          = combined_df.iloc[0]["track_name"]
            track_uri     = combined_df.iloc[0]["track_uri"]
            names_df      = pd.DataFrame({"name": combined_df.iloc[0]["top_names"] or []})
            other_artists = combined_df["artist_name"].iloc[1:].tolist() if len(combined_df) > 1 else []

        lb_listen_count: Optional[int] = None
        lb_isrc: Optional[str] = None
        lb_df = _load_computed("enrichment/listenbrainz_full.parquet")
        if lb_df is not None:
            lb_rows = lb_df[lb_df["spotify_track_uri"] == track_uri]
            if not lb_rows.empty:
                v = lb_rows.iloc[0]["listen_count"]
                lb_listen_count = int(v) if pd.notna(v) and int(v) > 0 else None
                isrc_v = lb_rows.iloc[0].get("isrc")
                lb_isrc = str(isrc_v) if isrc_v and not pd.isna(isrc_v) else None

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
