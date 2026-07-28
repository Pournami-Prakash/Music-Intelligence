import os
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import (
    _load_computed, lastfm_lookup, sp, _image_cache,
)
from src.app.graph import resolve_artist, artist_neighbors
from src.app.rcache import ttl_cache
from src.app.telemetry import record_event
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
        return {"artist": artist, "image_url": _image_cache[key],
                "source": "memory_cache" if _image_cache[key] else "placeholder"}

    img_df = _load_computed("computed/artist_images.parquet")
    if img_df is not None:
        row = img_df[img_df["artist_name"].str.lower() == key]
        if not row.empty:
            url = row.iloc[0]["image_url"] if pd.notna(row.iloc[0]["image_url"]) else None
            _image_cache[key] = url
            return {"artist": row.iloc[0]["artist_name"], "image_url": url,
                    "source": "cached_artifact" if url else "placeholder"}

    try:
        hits = sp.search_artist(artist, limit=1)
        if hits:
            images = hits[0].get("images") or []
            url = images[0]["url"] if images else None
            _image_cache[key] = url
            return {"artist": hits[0]["name"], "image_url": url, "source": "live"}
    except Exception:
        pass

    initials = "".join(part[0] for part in artist.split()[:2] if part).upper()
    return {"artist": artist, "image_url": None, "source": "placeholder", "initials": initials}


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

    return {"images": results, "meta": {"source": "cached_artifact", "live_lookup": False}}


@router.get("/api/artist-ubiquity/{artist}")
def artist_ubiquity(artist: str, artist_uri: Optional[str] = None):
    from src.app.cache import duck_df, local_parquet

    df = _load_computed("computed/artist_stats.parquet")
    if df is not None:
        r = _resolve_artist_row(df, artist, artist_uri)
        if r is not None:
            record_event("artist_ubiquity", "rich_lookup")
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
                "detail_level": "full",
            }

    # Long-tail rank/counts are precomputed offline into a slim lookup. This
    # restores all-artist coverage without the 806 MB serving-time join.
    try:
        lookup = local_parquet("computed/artist_ubiquity_lookup.parquet")
        if lookup is None:
            raise HTTPException(503, detail="artist_lookup_not_ready")
        result = duck_df(
            f"SELECT artist_name, artist_uri, playlist_count, playlist_pct, rank "
            f"FROM read_parquet('{lookup.as_posix()}') "
            f"WHERE artist_name_lc = lower(?) "
            f"OR (? IS NOT NULL AND artist_uri = ?) ORDER BY rank LIMIT 1",
            [artist, artist_uri, artist_uri],
        )
        if result.empty:
            result = duck_df(
                f"SELECT artist_name, artist_uri, playlist_count, playlist_pct, rank "
                f"FROM read_parquet('{lookup.as_posix()}') "
                f"WHERE artist_name_lc LIKE '%' || lower(?) || '%' ORDER BY rank LIMIT 1",
                [artist],
            )
        if result.empty:
            raise HTTPException(404, detail="artist_not_found")
        row = result.iloc[0]
        record_event("artist_ubiquity", "full_rank_lookup")
        return {
            "artist":         row["artist_name"],
            "artist_uri":     row["artist_uri"],
            "playlist_count": int(row["playlist_count"]),
            "pct":            float(row["playlist_pct"]),
            "rank":           int(row["rank"]),
            "top_tracks":     [],
            "co_artists":     [],
            "detail_level":   "rank_only",
            "note":           "Rank and reach use the full artist table; track and co-artist details cover the top 10,000.",
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
                "method_version": "distinct-artist-playlist-v2",
                "evidence": {
                    "metric": "Distinct playlists containing the artist whose titles match each context",
                    "population": f"{int(r['playlist_count']):,} playlists containing the artist",
                    "source": "Playlist titles and track membership",
                    "limitations": ["Categories can overlap", "Title context does not describe every listener's use"],
                },
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
@ttl_cache()
def compass(artist: str):
    canonical = resolve_artist(artist)
    if canonical is None:
        raise HTTPException(404, detail="artist_not_found")

    nbrs = artist_neighbors(canonical)
    if not nbrs:
        raise HTTPException(404, detail="artist_not_found")

    top = sorted(nbrs.items(), key=lambda x: -x[1])[:12]
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
    return {
        "center": {"title": canonical, "artist": canonical},
        "neighbors": neighbors,
        "method": "Shared-playlist count normalized to the strongest displayed neighbor",
        "evidence": {
            "metric": "Relative shared-playlist count",
            "population": "Twelve strongest co-occurrence neighbors",
            "source": "Artist playlist co-occurrence graph",
            "limitations": ["Relative strength is not statistical correlation"],
        },
    }


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
    percentile = round((1 - (rank - 1) / total) * 100, 1)
    score      = percentile

    top_co = _to_list(r.get("top_co_artists"))
    colony = [
        {"name": c["co_artist_name"], "overlap_pct": c["overlap_pct"]}
        for c in top_co[:5]
    ]

    _lf = lastfm_lookup(r["artist_name"])
    listeners = _lf["listeners"] if _lf else None

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
        "status":         "top_decile"         if score >= 90 else
                          "high_reach"          if score >= 75 else
                          "above_median_reach"  if score >= 50 else
                          "focused_reach",
        "method":         "Playlist-reach percentile among the 10,000-artist comparison set",
        "evidence": {
            "metric": "Percentile rank by number of playlists containing the artist",
            "population": f"{total:,} most-playlisted artists",
            "source": "One-million-playlist corpus",
            "limitations": ["Reach is not artistic importance, influence, or listener popularity"],
        },
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

    higher_reach = sorted(
        [c for c in candidates if c["playlist_count"] > artist_pc * 1.2],
        key=lambda x: -x["similarity"],
    )[:limit]
    lower_reach = sorted(
        [c for c in candidates if c["playlist_count"] < artist_pc * 0.8],
        key=lambda x: -x["similarity"],
    )[:limit]
    peers = sorted(
        [c for c in candidates if c not in higher_reach and c not in lower_reach],
        key=lambda x: -x["similarity"],
    )[:limit]

    _lf = lastfm_lookup(artist_name)
    lastfm_similar: list[str] = _lf["similar_artists"][:8] if _lf else []
    lastfm_listeners: Optional[int] = _lf["listeners"] if _lf else None

    return {
        "artist":         artist_name,
        "artist_tags":    sorted(artist_tags)[:8],
        "listeners":      lastfm_listeners,
        "lastfm_similar": lastfm_similar,
        "higher_reach": [
            {"name": a["name"], "similarity": a["similarity"],
             "shared_tags": a["shared_tags"], "playlist_count": a["playlist_count"]}
            for a in higher_reach
        ],
        "lower_reach": [
            {"name": d["name"], "similarity": d["similarity"],
             "shared_tags": d["shared_tags"], "playlist_count": d["playlist_count"]}
            for d in lower_reach
        ],
        "peers": [
            {"name": p["name"], "similarity": p["similarity"], "shared_tags": p["shared_tags"]}
            for p in peers
        ],
        "method": "Jaccard similarity across artist tags, split by relative playlist reach",
        "evidence": {
            "metric": "Shared-tag Jaccard similarity",
            "population": "Artists with genre/tag enrichment and playlist reach",
            "source": "Last.fm/MusicBrainz-style tags and playlist counts",
            "limitations": ["This does not infer chronology, influence, or artistic descent"],
        },
    }
