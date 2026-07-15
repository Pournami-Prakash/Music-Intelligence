"""
Doppelganger + Transition Finder — track2vec similarity over Upstash Vector.

The 393 MB FAISS index no longer lives in the API. Vectors are in Upstash
(top ~10K most-popular tracks on the free tier); the API keeps only the 21 MB
vocab (uri/artist ↔ id lookups) in memory. Endpoints degrade to an empty result
for artists whose tracks aren't in the vector index (obscure long tail).
"""
import numpy as np
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, _chart_for_track
from src.app.upstash import upstash_ready, upstash_fetch_vectors, upstash_query

router = APIRouter()


def _vocab():
    return _load_computed("embeddings/track2vec_vocab.parquet")


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return (v / n).astype("float32") if n > 0 else v.astype("float32")


@router.get("/api/transition-finder")
def transition_finder(from_uri: str, to_uri: str = "", to_artist: str = "", limit: int = 5):
    if not upstash_ready():
        raise HTTPException(503, detail="vector_index_not_ready")
    vocab = _vocab()
    if vocab is None:
        raise HTTPException(503, detail="not_ready")

    src_rows = vocab[vocab["track_uri"] == from_uri]
    if src_rows.empty:
        raise HTTPException(404, detail="source_track_not_found")
    src_id = str(int(src_rows.iloc[0]["idx"]))

    tgt_rows = None
    if to_uri:
        tgt_rows = vocab[vocab["track_uri"] == to_uri]
        if tgt_rows.empty:
            raise HTTPException(404, detail="target_track_not_found")
        tgt_ids = [str(int(tgt_rows.iloc[0]["idx"]))]
    elif to_artist:
        arows = vocab[vocab["artist_name"].str.lower() == to_artist.lower()]
        if arows.empty:
            arows = vocab[vocab["artist_name"].str.lower().str.contains(to_artist.lower(), na=False)]
        if arows.empty:
            raise HTTPException(404, detail="target_artist_not_found")
        tgt_ids = [str(int(i)) for i in arows["idx"].tolist()[:30]]
    else:
        raise HTTPException(400, detail="provide to_uri or to_artist")

    vecs = upstash_fetch_vectors([src_id] + tgt_ids)
    if src_id not in vecs:
        raise HTTPException(404, detail="source_track_not_in_index")
    tgt_list = [vecs[i] for i in tgt_ids if i in vecs]
    if not tgt_list:
        raise HTTPException(404, detail="target_not_in_index")

    mid = _normalize(((vecs[src_id] + np.mean(tgt_list, axis=0)) / 2).astype("float32"))

    exclude = {from_uri, to_uri}
    bridges = []
    for item in upstash_query(mid, top_k=limit + 20):
        md = item.get("metadata") or {}
        uri = md.get("uri")
        if uri in exclude:
            continue
        ch = _chart_for_track(uri)
        bridges.append({"uri": uri, "title": md.get("title"), "artist": md.get("artist"),
                        "chart_peak": int(ch["chart_peak"]) if ch else None})
        if len(bridges) >= limit:
            break

    src = src_rows.iloc[0]
    to_info = ({"uri": to_uri, "title": tgt_rows.iloc[0]["track_name"], "artist": tgt_rows.iloc[0]["artist_name"]}
               if to_uri and tgt_rows is not None else {"uri": to_uri, "title": None, "artist": to_artist or None})
    return {
        "from":    {"uri": from_uri, "title": src["track_name"], "artist": src["artist_name"]},
        "to":      to_info,
        "bridges": bridges,
    }


@router.get("/api/doppelganger/{artist}")
def doppelganger(artist: str, limit: int = 5):
    if not upstash_ready():
        raise HTTPException(503, detail="vector_index_not_ready")
    vocab = _vocab()
    if vocab is None:
        raise HTTPException(503, detail="not_ready")

    arows = vocab[vocab["artist_name"].str.lower() == artist.lower()]
    if arows.empty:
        arows = vocab[vocab["artist_name"].str.lower().str.contains(artist.lower(), na=False)]
    if arows.empty:
        raise HTTPException(404, detail="artist_not_found")

    artist_name = arows.iloc[0]["artist_name"]
    query_ids = [str(int(i)) for i in arows["idx"].tolist()[:50]]
    vecs = upstash_fetch_vectors(query_ids)

    # Artist's tracks aren't in the (popular-tracks) vector index → clean empty result.
    if not vecs:
        return {"artist": artist_name, "track_count": 0, "doppelgangers": [], "note": "not_in_vector_index"}

    centroid = _normalize(np.mean(list(vecs.values()), axis=0).astype("float32"))

    artist_scores: dict[str, list[float]] = {}
    for item in upstash_query(centroid, top_k=1000):
        md = item.get("metadata") or {}
        a = md.get("artist")
        if not a or a.lower() == artist_name.lower():
            continue
        artist_scores.setdefault(a, []).append(float(item.get("score", 0.0)))

    # Rank by neighbourhood density (multiple nearby tracks = a real match),
    # then closeness; fall back to single-track matches to fill the list.
    def _score(sims):
        return sum(sorted(sims, reverse=True)[:3]) / min(3, len(sims))

    multi = sorted(((a, _score(s), len(s)) for a, s in artist_scores.items() if len(s) >= 2),
                   key=lambda x: (-x[2], -x[1]))
    ranked = [(a, sc) for a, sc, _ in multi[:limit]]
    if len(ranked) < limit:
        singles = sorted(((a, _score(s)) for a, s in artist_scores.items() if len(s) == 1),
                         key=lambda x: -x[1])
        ranked += singles[:limit - len(ranked)]

    lastfm_df = _load_computed("enrichment/artist_lastfm.parquet")

    def _tags(name: str) -> list[str]:
        if lastfm_df is None:
            return []
        lrow = lastfm_df[lastfm_df["artist_name"].str.lower() == name.lower()]
        if lrow.empty:
            return []
        raw = lrow.iloc[0].get("tags")
        try:
            return list(raw)[:5] if raw is not None else []
        except TypeError:
            return []

    return {
        "artist":        artist_name,
        "track_count":   len(vecs),
        "doppelgangers": [{"name": n, "similarity": round(sc, 4), "tags": _tags(n)} for n, sc in ranked],
    }
