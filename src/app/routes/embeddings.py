import numpy as np

from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, _load_faiss, _chart_for_track
from src.app.helpers import _uri_to_vec

router = APIRouter()


def _normalize_l2(vec: np.ndarray) -> None:
    try:
        import faiss
    except Exception:
        raise HTTPException(503, detail="faiss_index_not_ready")
    faiss.normalize_L2(vec)


@router.get("/api/transition-finder")
def transition_finder(from_uri: str, to_uri: str = "", to_artist: str = "", limit: int = 5):
    index, vocab = _load_faiss()
    if index is None:
        raise HTTPException(503, detail="faiss_index_not_ready")

    src_vec = _uri_to_vec(from_uri, index, vocab)
    if src_vec is None:
        raise HTTPException(404, detail="source_track_not_found")

    if to_uri:
        tgt_vec = _uri_to_vec(to_uri, index, vocab)
        if tgt_vec is None:
            raise HTTPException(404, detail="target_track_not_found")
    elif to_artist:
        artist_rows = vocab[vocab["artist_name"].str.lower() == to_artist.lower()]
        if artist_rows.empty:
            artist_rows = vocab[vocab["artist_name"].str.lower().str.contains(to_artist.lower(), na=False)]
        if artist_rows.empty:
            raise HTTPException(404, detail="target_artist_not_found")
        vecs = []
        for idx in artist_rows["idx"].tolist()[:30]:
            v = np.zeros(index.d, dtype="float32")
            index.reconstruct(int(idx), v)
            vecs.append(v)
        tgt_vec = np.mean(vecs, axis=0, keepdims=True).astype("float32")
        _normalize_l2(tgt_vec)
    else:
        raise HTTPException(400, detail="provide to_uri or to_artist")

    mid_vec = ((src_vec + tgt_vec) / 2).astype("float32")
    _normalize_l2(mid_vec)

    src_uri_set = {from_uri, to_uri}
    _, I = index.search(mid_vec, limit + 20)

    results = []
    for i in I[0]:
        if i < 0:
            continue
        row = vocab.iloc[int(i)]
        uri = row["track_uri"]
        if uri in src_uri_set:
            continue
        ch = _chart_for_track(uri)
        results.append({
            "uri":        uri,
            "title":      row["track_name"],
            "artist":     row["artist_name"],
            "chart_peak": int(ch["chart_peak"]) if ch else None,
        })
        if len(results) >= limit:
            break

    src_row = vocab[vocab["track_uri"] == from_uri].iloc[0]
    to_row  = vocab[vocab["track_uri"] == to_uri] if to_uri else None
    to_info = (
        {"uri": to_uri, "title": to_row.iloc[0]["track_name"], "artist": to_row.iloc[0]["artist_name"]}
        if to_uri and to_row is not None and not to_row.empty
        else {"uri": to_uri, "title": None, "artist": to_artist or None}
    )
    return {
        "from":    {"uri": from_uri, "title": src_row["track_name"], "artist": src_row["artist_name"]},
        "to":      to_info,
        "bridges": results,
    }


@router.get("/api/doppelganger/{artist}")
def doppelganger(artist: str, limit: int = 5):
    index, vocab = _load_faiss()
    if index is None:
        raise HTTPException(503, detail="faiss_index_not_ready")

    artist_rows = vocab[vocab["artist_name"].str.lower() == artist.lower()]
    if artist_rows.empty:
        artist_rows = vocab[vocab["artist_name"].str.lower().str.contains(artist.lower(), na=False)]
    if artist_rows.empty:
        raise HTTPException(404, detail="artist_not_found")

    artist_name = artist_rows.iloc[0]["artist_name"]
    query_idxs  = artist_rows["idx"].tolist()[:50]

    vecs = []
    for idx in query_idxs:
        v = np.zeros(index.d, dtype="float32")
        index.reconstruct(int(idx), v)
        vecs.append(v)

    centroid = np.mean(vecs, axis=0, keepdims=True).astype("float32")
    _normalize_l2(centroid)

    D, I = index.search(centroid, min(1500, index.ntotal))

    artist_scores: dict[str, list[float]] = {}
    for dist, idx in zip(D[0], I[0]):
        if idx < 0:
            continue
        row = vocab.iloc[int(idx)]
        a   = row["artist_name"]
        if a.lower() == artist_name.lower():
            continue
        artist_scores.setdefault(a, []).append(float(dist))

    # A single stray track near the centroid is usually noise; genuine
    # doppelgängers have several tracks in the neighborhood. Rank by how many
    # tracks land nearby, then by average closeness — falling back to
    # single-track matches only if we don't have enough multi-track ones.
    def _artist_score(sims):
        return sum(sorted(sims, reverse=True)[:3]) / min(3, len(sims))

    multi = sorted(
        ((a, _artist_score(s), len(s)) for a, s in artist_scores.items() if len(s) >= 2),
        key=lambda x: (-x[2], -x[1]),
    )
    ranked = [(a, sc) for a, sc, _ in multi[:limit]]
    if len(ranked) < limit:
        singles = sorted(
            ((a, _artist_score(s)) for a, s in artist_scores.items() if len(s) == 1),
            key=lambda x: -x[1],
        )
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
        "track_count":   len(query_idxs),
        "doppelgangers": [
            {"name": name, "similarity": round(score, 4), "tags": _tags(name)}
            for name, score in ranked
        ],
    }
