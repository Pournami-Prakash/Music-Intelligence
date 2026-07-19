"""
Doppelganger + Transition Finder — track2vec similarity over Upstash Vector.

The 393 MB FAISS index no longer lives in the API. Upstash holds the popular
candidate index; missing query vectors are point-read from an idx-sorted R2
Parquet artifact. This preserves long-tail query coverage without resident RAM.
"""
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException

from src.app.cache import local_parquet, duck_one, duck_all, lastfm_lookup, _chart_for_track
from src.app.upstash import upstash_ready, upstash_fetch_vectors, upstash_query
from src.app.rcache import ttl_cache
from src.app.telemetry import record_event
from src.storage.duckdb_r2 import R2_PATH

router = APIRouter()

_VOCAB_KEY = "embeddings/track2vec_vocab_lookup.parquet"


def _vpath() -> Optional[str]:
    p = local_parquet(_VOCAB_KEY)
    return p.as_posix() if p is not None else None


def _vocab_by_uri(uri: str) -> Optional[dict]:
    """{idx, track_name, artist_name} for a track URI, streamed via DuckDB."""
    path = _vpath()
    if path is None:
        return None
    r = duck_one(
        f"SELECT idx, track_name, artist_name FROM read_parquet('{path}') WHERE track_uri = ? LIMIT 1",
        [uri],
    )
    return {"idx": int(r[0]), "track_name": r[1], "artist_name": r[2]} if r else None


def _vocab_by_artist(name: str, limit: int) -> tuple[Optional[str], list[int]]:
    """(canonical_artist_name, [idx...]) for an artist — exact then substring."""
    path = _vpath()
    if path is None:
        return None, []
    rows = duck_all(
        f"SELECT idx, artist_name FROM read_parquet('{path}') WHERE artist_name_lc = lower(?) LIMIT {int(limit)}",
        [name],
    )
    if not rows:
        rows = duck_all(
            f"SELECT idx, artist_name FROM read_parquet('{path}') WHERE artist_name_lc LIKE '%' || lower(?) || '%' LIMIT {int(limit)}",
            [name],
        )
    if not rows:
        return None, []
    return rows[0][1], [int(r[0]) for r in rows]


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return (v / n).astype("float32") if n > 0 else v.astype("float32")


def _vectors_for_ids(ids: list[str]) -> tuple[dict[str, np.ndarray], str]:
    """Fetch popular vectors from Upstash and point-read any misses from R2."""
    vecs = upstash_fetch_vectors(ids)
    upstash_count = len(vecs)
    missing = [int(i) for i in ids if i not in vecs]
    if missing:
        id_sql = ",".join(str(i) for i in missing[:50])
        try:
            rows = duck_all(
                f"SELECT idx, vector FROM read_parquet("
                f"'{R2_PATH}/embeddings/track2vec_vectors_lookup.parquet') "
                f"WHERE idx IN ({id_sql})"
            )
            for idx, vector in rows:
                # The R2 artifact stores the raw Word2Vec matrix; Upstash was
                # exported from the normalized FAISS index. Normalize here so
                # mixed fast-path/fallback centroids stay in the same space.
                vecs[str(idx)] = _normalize(np.asarray(vector, dtype="float32"))
        except Exception as exc:
            print(f"  [vectors] R2 fallback failed: {exc}", flush=True)
    if len(vecs) == upstash_count:
        return vecs, "upstash"
    return vecs, "mixed" if upstash_count else "r2_fallback"


@router.get("/api/transition-finder")
def transition_finder(from_uri: str, to_uri: str = "", to_artist: str = "", limit: int = 5):
    if not upstash_ready():
        raise HTTPException(503, detail="vector_index_not_ready")

    src = _vocab_by_uri(from_uri)
    if src is None:
        raise HTTPException(404, detail="source_track_not_found")
    src_id = str(src["idx"])

    tgt_title: Optional[str] = None
    tgt_artist: Optional[str] = None
    if to_uri:
        t = _vocab_by_uri(to_uri)
        if t is None:
            raise HTTPException(404, detail="target_track_not_found")
        tgt_ids = [str(t["idx"])]
        tgt_title, tgt_artist = t["track_name"], t["artist_name"]
    elif to_artist:
        canon, idxs = _vocab_by_artist(to_artist, 30)
        if not idxs:
            raise HTTPException(404, detail="target_artist_not_found")
        tgt_ids = [str(i) for i in idxs]
        tgt_artist = canon
    else:
        raise HTTPException(400, detail="provide to_uri or to_artist")

    vecs, vector_source = _vectors_for_ids([src_id] + tgt_ids)
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

    record_event("transition", vector_source)
    to_info = ({"uri": to_uri, "title": tgt_title, "artist": tgt_artist}
               if to_uri else {"uri": to_uri, "title": None, "artist": to_artist or None})
    return {
        "from":    {"uri": from_uri, "title": src["track_name"], "artist": src["artist_name"]},
        "to":      to_info,
        "bridges": bridges,
        "meta": {"query_vectors": vector_source, "candidate_scope": "popular_10k"},
    }


@router.get("/api/doppelganger/{artist}")
@ttl_cache()
def doppelganger(artist: str, limit: int = 5):
    if not upstash_ready():
        raise HTTPException(503, detail="vector_index_not_ready")

    artist_name, idxs = _vocab_by_artist(artist, 50)
    if not idxs:
        raise HTTPException(404, detail="artist_not_found")

    query_ids = [str(i) for i in idxs]
    vecs, vector_source = _vectors_for_ids(query_ids)

    if not vecs:
        record_event("doppelganger", "query_vectors_unavailable")
        return {"artist": artist_name, "track_count": 0, "doppelgangers": [],
                "note": "query_vectors_unavailable",
                "meta": {"query_vectors": "unavailable", "candidate_scope": "popular_10k"}}

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

    def _tags(name: str) -> list[str]:
        lf = lastfm_lookup(name)
        return lf["tags"][:5] if lf else []

    record_event("doppelganger", vector_source)
    return {
        "artist":        artist_name,
        "track_count":   len(vecs),
        "doppelgangers": [{"name": n, "similarity": round(sc, 4), "tags": _tags(n)} for n, sc in ranked],
        "meta": {"query_vectors": vector_source, "candidate_scope": "popular_10k"},
    }
