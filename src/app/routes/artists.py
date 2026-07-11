import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import (
    _load_computed, _get_artist_adj, _artist_name_map, sp, _image_cache,
)
from src.app.helpers import _to_list, _resolve_artist_row, _jaccard
from src.app.models import ArtistsBatchBody

router = APIRouter()

HABITAT_KEYWORDS = {
    "gym":        ["gym", "workout", "fitness", "lift", "run", "cardio", "training", "pump"],
    "heartbreak": ["heartbreak", "breakup", "cry", "sad", "broken", "ex", "miss", "gone"],
    "road_trip":  ["road trip", "roadtrip", "drive", "driving", "highway", "cruise", "travel"],
    "party":      ["party", "pregame", "turn up", "banger", "hype", "lit", "club", "dance"],
    "study":      ["study", "focus", "work", "concentrate", "reading", "homework", "lo-fi", "lofi"],
    "chill":      ["chill", "vibe", "relax", "mellow", "ease", "calm", "soft", "ambient"],
    "throwback":  ["throwback", "nostalgia", "classic", "oldies", "retro", "2000s", "90s", "80s"],
    "sleep":      ["sleep", "night", "bedtime", "insomnia", "drift", "dream", "lullaby"],
}


@router.get("/api/artist-image/{artist}")
def artist_image(artist: str):
    key = artist.lower()
    if key in _image_cache:
        return {"artist": artist, "image_url": _image_cache[key]}

    img_df = _load_computed("computed/artist_images.parquet")
    if img_df is not None:
        row = img_df[img_df["artist_name"].str.lower() == key]
        if not row.empty:
            url = row.iloc[0]["image_url"] if pd.notna(row.iloc[0]["image_url"]) else None
            _image_cache[key] = url
            return {"artist": row.iloc[0]["artist_name"], "image_url": url}

    try:
        hits = sp.search_artist(artist, limit=1)
        if hits:
            images = hits[0].get("images") or []
            url = images[0]["url"] if images else None
            _image_cache[key] = url
            return {"artist": hits[0]["name"], "image_url": url, "source": "live"}
    except Exception:
        pass

    return {"artist": artist, "image_url": None}


@router.post("/api/artist-images/batch")
def artist_images_batch(body: ArtistsBatchBody):
    names  = body.artists[:50]
    img_df = _load_computed("computed/artist_images.parquet")
    results = {}

    for name in names:
        key = name.lower()
        if key in _image_cache:
            results[name] = _image_cache[key]
            continue
        if img_df is not None:
            row = img_df[img_df["artist_name"].str.lower() == key]
            if not row.empty:
                url = row.iloc[0]["image_url"] if pd.notna(row.iloc[0]["image_url"]) else None
                _image_cache[key] = url
                results[name] = url
                continue
        results[name] = None

    return {"images": results}


@router.get("/api/artist-ubiquity/{artist}")
def artist_ubiquity(artist: str, artist_uri: Optional[str] = None):
    from src.app.cache import con
    from src.storage.duckdb_r2 import R2_PATH

    df = _load_computed("computed/artist_stats.parquet")
    if df is not None:
        r = _resolve_artist_row(df, artist, artist_uri)
        if r is not None:
            return {
                "artist":         r["artist_name"],
                "artist_uri":     r.get("artist_uri"),
                "playlist_count": int(r["playlist_count"]),
                "pct":            float(r["playlist_pct"]),
                "rank":           int(r["rank"]),
                "top_tracks":     _to_list(r.get("top_tracks")),
                "co_artists": [
                    {"name": c["co_artist_name"], "overlap_pct": c["overlap_pct"]}
                    for c in _to_list(r.get("top_co_artists"))
                ],
            }

    try:
        result = con.execute(f"""
            SELECT t.artist_name,
                   COUNT(DISTINCT pt.pid) AS playlist_count
            FROM read_parquet('{R2_PATH}/processed/playlist_tracks.parquet') pt
            JOIN read_parquet('{R2_PATH}/processed/tracks.parquet') t
                 ON pt.track_uri = t.track_uri
            WHERE lower(t.artist_name) = lower('{artist.replace("'", "''")}')
            GROUP BY t.artist_name
            LIMIT 1
        """).df()
        if result.empty:
            raise HTTPException(404, detail="artist_not_found")
        pc = int(result.iloc[0]["playlist_count"])
        return {
            "artist":         result.iloc[0]["artist_name"],
            "playlist_count": pc,
            "pct":            round(pc / 1_000_000 * 100, 3),
            "rank":           None,
            "top_tracks":     [],
            "co_artists":     [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, detail=f"query_failed: {e}")


@router.get("/api/artist-habitat/{artist}")
def artist_habitat(artist: str, artist_uri: Optional[str] = None):
    hab_df = _load_computed("computed/artist_habitat.parquet")
    if hab_df is not None:
        r = _resolve_artist_row(hab_df, artist, artist_uri)
        if r is not None:
            habitats = {
                h: {"count": int(r[h]), "pct": float(r[f"{h}_pct"])}
                for h in HABITAT_KEYWORDS
                if h in r.index and f"{h}_pct" in r.index
            }
            return {
                "artist":         r["artist_name"],
                "playlist_count": int(r["playlist_count"]),
                "habitats":       habitats,
            }

    stats_df = _load_computed("computed/artist_stats.parquet")
    if stats_df is None:
        raise HTTPException(503, detail="not_ready")
    r = _resolve_artist_row(stats_df, artist, artist_uri)
    if r is None:
        raise HTTPException(404, detail="artist_not_found")
    return {
        "artist":         r["artist_name"],
        "playlist_count": int(r["playlist_count"]),
        "habitats":       {k: None for k in HABITAT_KEYWORDS},
        "note":           "run compute_artist_habitat.py to populate habitat scores",
    }


@router.get("/api/compass/{artist}")
def compass(artist: str):
    adj = _get_artist_adj()
    if not adj:
        raise HTTPException(503, detail="not_ready")

    canonical = _artist_name_map.get(artist.lower())
    if not canonical or canonical not in adj:
        raise HTTPException(404, detail="artist_not_found")

    top = sorted(adj[canonical].items(), key=lambda x: -x[1])[:12]
    max_shared = top[0][1] if top else 1
    neighbors = [
        {
            "title":    name,
            "artist":   name,
            "strength": round(shared / max_shared, 3),
            "shared":   shared,
        }
        for name, shared in top
    ]
    return {"center": {"title": canonical, "artist": canonical}, "neighbors": neighbors}


@router.get("/api/basicness/{query}")
def basicness(query: str):
    df = _load_computed("computed/artist_stats.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    r = _resolve_artist_row(df, query)
    if r is None:
        raise HTTPException(404, detail="not_found")

    percentile = round((1 - (int(r["rank"]) - 1) / len(df)) * 100, 1)
    return {
        "query":            r["artist_name"],
        "percentile":       percentile,
        "pct_of_playlists": float(r["playlist_pct"]),
        "rank":             int(r["rank"]),
        "total_artists":    len(df),
    }


@router.get("/api/main-character/{query}")
def main_character(query: str):
    df = _load_computed("computed/artist_stats.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    row = df[df["artist_name"].str.lower() == query.lower()]
    if row.empty:
        row = df[df["artist_name"].str.lower().str.contains(query.lower(), na=False)]
    if row.empty:
        raise HTTPException(404, detail="artist_not_found")

    r          = row.iloc[0]
    pct        = float(r["playlist_pct"])
    rank       = int(r["rank"])
    total      = len(df)
    score      = min(99.0, round(math.log1p(pct) / math.log1p(20.334) * 96, 1))
    percentile = round((1 - (rank - 1) / total) * 100, 1)

    top_co = _to_list(r.get("top_co_artists"))
    colony = [
        {"name": c["co_artist_name"], "overlap_pct": c["overlap_pct"]}
        for c in top_co[:5]
    ]

    lastfm_df = _load_computed("enrichment/artist_lastfm.parquet")
    listeners = None
    if lastfm_df is not None:
        lrow = lastfm_df[lastfm_df["artist_name"].str.lower() == r["artist_name"].lower()]
        if not lrow.empty:
            v = lrow.iloc[0].get("listeners") or 0
            listeners = int(v) if v else None

    return {
        "artist":         r["artist_name"],
        "score":          score,
        "percentile":     percentile,
        "playlist_count": int(r["playlist_count"]),
        "pct":            pct,
        "rank":           rank,
        "listeners":      listeners,
        "top_tracks":     list(r["top_tracks"])[:5] if r["top_tracks"] is not None else [],
        "colony":         colony,
        "status":         "critical_overload" if score >= 90 else
                          "dominant"          if score >= 75 else
                          "strong_presence"   if score >= 50 else
                          "niche",
    }


@router.get("/api/ancestry/{artist}")
def ancestry(artist: str, limit: int = 5):
    genres_df = _load_computed("enrichment/artist_genres.parquet")
    stats_df  = _load_computed("computed/artist_stats.parquet")
    if genres_df is None or stats_df is None:
        raise HTTPException(503, detail="not_ready")

    if "tags" in genres_df.columns:
        genres_df = genres_df.rename(columns={"tags": "genres"})

    r = _resolve_artist_row(genres_df, artist)
    if r is None:
        raise HTTPException(404, detail="artist_not_found")

    artist_name = r["artist_name"]
    try:
        artist_tags = set(list(r["genres"]) if r["genres"] is not None else [])
    except TypeError:
        artist_tags = set()

    stats_pc_map = stats_df.set_index("artist_name")["playlist_count"].to_dict()
    artist_pc    = stats_pc_map.get(artist_name, 0)

    scores = []
    for _, other in genres_df[genres_df["artist_name"] != artist_name].iterrows():
        try:
            other_tags = set(list(other["genres"]) if other["genres"] is not None else [])
        except TypeError:
            other_tags = set()
        sim = _jaccard(artist_tags, other_tags)
        if sim < 0.05:
            continue
        other_pc = stats_pc_map.get(other["artist_name"])
        if other_pc is None:
            continue
        scores.append({
            "name":           other["artist_name"],
            "similarity":     round(sim, 3),
            "playlist_count": int(other_pc),
            "shared_tags":    sorted(artist_tags & other_tags)[:4],
        })

    scores.sort(key=lambda x: -x["similarity"])
    candidates = scores[:60]

    ancestors = sorted(
        [c for c in candidates if c["playlist_count"] > artist_pc * 1.2],
        key=lambda x: -x["similarity"],
    )[:limit]
    descendants = sorted(
        [c for c in candidates if c["playlist_count"] < artist_pc * 0.8],
        key=lambda x: -x["similarity"],
    )[:limit]
    peers = sorted(
        [c for c in candidates if c not in ancestors and c not in descendants],
        key=lambda x: -x["similarity"],
    )[:limit]

    lastfm_df = _load_computed("enrichment/artist_lastfm.parquet")
    lastfm_similar: list[str] = []
    lastfm_listeners: Optional[int] = None
    if lastfm_df is not None:
        lrow = lastfm_df[lastfm_df["artist_name"].str.lower() == artist_name.lower()]
        if not lrow.empty:
            raw_sim = lrow.iloc[0].get("similar_artists")
            try:
                lastfm_similar = list(raw_sim)[:8] if raw_sim is not None else []
            except TypeError:
                lastfm_similar = []
            lastfm_listeners = int(lrow.iloc[0].get("listeners") or 0) or None

    return {
        "artist":         artist_name,
        "artist_tags":    sorted(artist_tags)[:8],
        "listeners":      lastfm_listeners,
        "lastfm_similar": lastfm_similar,
        "ancestors": [
            {"name": a["name"], "similarity": a["similarity"],
             "shared_tags": a["shared_tags"], "playlist_count": a["playlist_count"]}
            for a in ancestors
        ],
        "descendants": [
            {"name": d["name"], "similarity": d["similarity"],
             "shared_tags": d["shared_tags"], "playlist_count": d["playlist_count"]}
            for d in descendants
        ],
        "peers": [
            {"name": p["name"], "similarity": p["similarity"], "shared_tags": p["shared_tags"]}
            for p in peers
        ],
    }
