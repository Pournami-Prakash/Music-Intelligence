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


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for already-normalized or raw vectors."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def _vectors_for_ids(ids: list[str]) -> tuple[dict[str, np.ndarray], str]:
    """Fetch interactive query vectors from Upstash.

    The former R2 fallback could hold a request open for more than a minute
    while reading scattered vector rows. Interactive pages now use the bounded
    popular index and report unavailable coverage immediately.
    """
    vecs = upstash_fetch_vectors(ids)
    return vecs, "upstash" if vecs else "unavailable"


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

    source_vec = _normalize(vecs[src_id])
    target_vec = _normalize(np.mean(tgt_list, axis=0).astype("float32"))
    mid = _normalize((source_vec + target_vec).astype("float32"))

    # Build a candidate pool around the start, midpoint, and destination, then
    # optimize an ordered three-stage route. The former implementation returned
    # independent midpoint neighbors and displayed them as sequential bridges.
    candidate_items: dict[str, dict] = {}
    for query_vec in (source_vec, mid, target_vec):
        for item in upstash_query(query_vec, top_k=40):
            item_id = str(item.get("id"))
            md = item.get("metadata") or {}
            if not item_id or item_id in {src_id, *tgt_ids}:
                continue
            if md.get("uri") in {from_uri, to_uri}:
                continue
            candidate_items[item_id] = item

    candidate_vecs, _ = _vectors_for_ids(list(candidate_items))
    if not candidate_vecs:
        raise HTTPException(404, detail="no_transition_candidates")

    stages = min(3, max(1, int(limit)))
    beam: list[tuple[float, list[str], str | None]] = [(0.0, [], None)]
    for stage in range(1, stages + 1):
        alpha = stage / (stages + 1)
        stage_target = _normalize(((1 - alpha) * source_vec + alpha * target_vec).astype("float32"))
        expanded: list[tuple[float, list[str], str]] = []
        for cost, path, previous_id in beam:
            previous_vec = source_vec if previous_id is None else candidate_vecs[previous_id]
            for candidate_id, candidate_vec in candidate_vecs.items():
                if candidate_id in path:
                    continue
                adjacent_cost = 1 - _cosine(previous_vec, candidate_vec)
                progress_cost = 1 - _cosine(candidate_vec, stage_target)
                expanded.append((
                    cost + adjacent_cost * 0.7 + progress_cost * 0.3,
                    path + [candidate_id],
                    candidate_id,
                ))
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:60]

    ranked_paths = sorted(
        (
            cost + (1 - _cosine(candidate_vecs[last_id], target_vec)) * 0.8,
            path,
        )
        for cost, path, last_id in beam
    )
    best_cost, best_path = ranked_paths[0]
    bridges = []
    previous_vec = source_vec
    adjacent_scores = []
    for index, candidate_id in enumerate(best_path):
        item = candidate_items[candidate_id]
        md = item.get("metadata") or {}
        candidate_vec = candidate_vecs[candidate_id]
        adjacent = _cosine(previous_vec, candidate_vec)
        adjacent_scores.append(adjacent)
        ch = _chart_for_track(md.get("uri"))
        bridges.append({
            "uri": md.get("uri"),
            "title": md.get("title"),
            "artist": md.get("artist"),
            "chart_peak": int(ch["chart_peak"]) if ch else None,
            "transition_similarity": round(adjacent, 4),
            "stage": index + 1,
        })
        previous_vec = candidate_vec
    adjacent_scores.append(_cosine(previous_vec, target_vec))

    record_event("transition", vector_source)
    to_info = ({"uri": to_uri, "title": tgt_title, "artist": tgt_artist}
               if to_uri else {"uri": to_uri, "title": None, "artist": to_artist or None})
    return {
        "from":    {"uri": from_uri, "title": src["track_name"], "artist": src["artist_name"]},
        "to":      to_info,
        "bridges": bridges,
        "route_score": round(sum(adjacent_scores) / len(adjacent_scores), 4),
        "meta": {
            "query_vectors": vector_source,
            "candidate_scope": "popular_10k",
            "candidate_count": len(candidate_vecs),
            "method": "beam-optimized ordered path across three interpolation stages",
            "objective_cost": round(best_cost, 4),
        },
        "evidence": {
            "metric": "Average cosine similarity between each adjacent track in the ordered route",
            "population": "Popular 10,000-track embedding candidate index",
            "source": "Track2vec co-occurrence embeddings",
            "limitations": ["Similarity reflects playlist context, not beatmatching or harmonic key"],
        },
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
    for item in upstash_query(centroid, top_k=300):
        md = item.get("metadata") or {}
        a = md.get("artist")
        if not a or a.lower() == artist_name.lower():
            continue
        artist_scores.setdefault(a, []).append(float(item.get("score", 0.0)))

    # Displayed similarity is the ranking metric. Support count remains useful
    # evidence, but must not silently reorder a lower-similarity artist above a
    # higher-similarity one.
    def _score(sims):
        return sum(sorted(sims, reverse=True)[:3]) / min(3, len(sims))

    subject_lf = lastfm_lookup(artist_name)
    subject_tags = {
        str(tag).strip().lower() for tag in (subject_lf["tags"][:8] if subject_lf else [])
        if str(tag).strip()
    }

    ranked_candidates = []
    embedding_shortlist = sorted(
        artist_scores.items(), key=lambda item: -_score(item[1])
    )[:60]
    for candidate_name, similarities in embedding_shortlist:
        candidate_lf = lastfm_lookup(candidate_name)
        tags = candidate_lf["tags"][:8] if candidate_lf else []
        candidate_tags = {str(tag).strip().lower() for tag in tags if str(tag).strip()}
        union = subject_tags | candidate_tags
        tag_similarity = len(subject_tags & candidate_tags) / len(union) if union else 0.0
        embedding_similarity = _score(similarities)
        # Artist-level tags stabilize sparse query-vector coverage; embedding
        # similarity remains the dominant signal.
        combined = embedding_similarity * 0.72 + tag_similarity * 0.28
        ranked_candidates.append({
            "name": candidate_name,
            "similarity": combined,
            "embedding_similarity": embedding_similarity,
            "tag_similarity": tag_similarity,
            "support_tracks": len(similarities),
            "tags": tags[:5],
        })

    ranked = sorted(
        ranked_candidates,
        key=lambda item: (-item["similarity"], -item["support_tracks"], item["name"]),
    )[:limit]

    record_event("doppelganger", vector_source)
    return {
        "artist":        artist_name,
        "track_count":   len(vecs),
        "doppelgangers": [
            {
                **item,
                "similarity": round(item["similarity"], 4),
                "embedding_similarity": round(item["embedding_similarity"], 4),
                "tag_similarity": round(item["tag_similarity"], 4),
            }
            for item in ranked
        ],
        "meta": {
            "query_vectors": vector_source,
            "candidate_scope": "popular_10k",
            "method": "72% track-embedding proximity plus 28% artist-tag Jaccard similarity",
        },
        "evidence": {
            "metric": "Hybrid artist similarity from track embeddings and shared tags",
            "population": "Popular 10,000-track candidate index",
            "source": "Track co-occurrence embeddings",
            "limitations": [f"Only {len(vecs)} query tracks had vectors in the interactive index"],
        },
    }
