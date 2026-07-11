import random
import re
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed
from src.app.helpers import _to_list

router = APIRouter()

_ROAST_VERDICTS = [
    (90, "Congratulations, this is statistically indistinguishable from 800,000 other playlists."),
    (70, "You and approximately every third person on Spotify had the same idea."),
    (50, "Competently generic. A solid 6/10 in the taxonomy of playlist names."),
    (30, "Some originality detected. Someone might actually remember this title."),
    (0,  "Genuinely rare. Either very creative or very obscure — possibly both."),
]


@router.get("/api/playlist-language")
def playlist_language(filter: str = "all", limit: int = 60):
    df = _load_computed("computed/playlist_title_terms.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    if filter != "all":
        df = df[df["theme"] == filter]
    rows = df.head(limit)
    return {
        "words": [
            {
                "word":     r["term"],
                "freq":     int(r["count"]),
                "pct":      float(r["pct"]),
                "cat":      r["theme"],
                "examples": _to_list(r.get("example_titles")),
            }
            for _, r in rows.iterrows()
        ],
        "total_playlists": 1_000_000,
    }


@router.get("/api/trend-explorer/{term}")
def trend_explorer(term: str):
    df = _load_computed("computed/playlist_title_terms.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    normalized = term.lower().replace("-", " ")
    row = df[df["term"].str.lower() == normalized]
    if row.empty:
        row = df[df["term"].str.lower() == term.lower()]
    if row.empty:
        raise HTTPException(404, detail="term_not_found")

    r = row.iloc[0]
    related = (
        df[(df["theme"] == r["theme"]) & (df["term"] != r["term"])]
        .head(8)["term"]
        .tolist()
    )
    return {
        "term":     r["term"],
        "count":    int(r["count"]),
        "pct":      float(r["pct"]),
        "theme":    r["theme"],
        "examples": _to_list(r.get("example_titles")),
        "related":  related,
    }


@router.get("/api/mood-map/clusters")
def mood_map_clusters():
    df = _load_computed("computed/mood_map_clusters.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    clusters = [
        {
            "id":          r["id"],
            "label":       r["label"],
            "color":       r["color"],
            "count":       int(r["count"]),
            "pct":         float(r["pct"]),
            "top_terms":   _to_list(r.get("top_terms")),
            "description": r.get("description", ""),
        }
        for _, r in df.iterrows()
    ]
    return {"clusters": clusters, "total_playlists": 1_000_000}


@router.get("/api/genre-weather/regions")
def genre_regions(limit: int = 30):
    df = _load_computed("embeddings/genre_umap_clusters.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    merged = (
        df.groupby("genre_label", as_index=False)
        .agg(
            track_count=("track_count", "sum"),
            cx=("cx", "mean"),
            cy=("cy", "mean"),
            color=("color", "first"),
            cluster_count=("cluster_id", "count"),
        )
        .sort_values("track_count", ascending=False)
        .head(limit)
    )

    genres = [
        {
            "id":            row["genre_label"].lower().replace(" ", "_"),
            "label":         row["genre_label"],
            "color":         row["color"],
            "track_count":   int(row["track_count"]),
            "cx":            round(float(row["cx"]), 4),
            "cy":            round(float(row["cy"]), 4),
            "cluster_count": int(row["cluster_count"]),
        }
        for _, row in merged.iterrows()
    ]
    return {
        "genres":         genres,
        "total_clusters": int(len(df)),
        "total_tracks":   int(df["track_count"].sum()),
    }


@router.get("/api/genre-weather/clusters")
def genre_clusters():
    df = _load_computed("embeddings/genre_umap_clusters.parquet")
    if df is None:
        raise HTTPException(503, detail="not_ready")

    clusters = [
        {
            "cluster_id":  int(row["cluster_id"]),
            "label":       row["genre_label"],
            "cx":          round(float(row["cx"]), 4),
            "cy":          round(float(row["cy"]), 4),
            "track_count": int(row["track_count"]),
            "color":       row["color"],
        }
        for _, row in df.iterrows()
    ]
    return {"clusters": clusters}


@router.get("/api/roast")
def roast(title: str = "vibes"):
    terms_df = _load_computed("computed/playlist_title_terms.parquet")
    if terms_df is None:
        raise HTTPException(503, detail="not_ready")

    words = [w.strip().lower() for w in re.split(r"[\s,/&]+", title) if len(w.strip()) > 2]
    if not words:
        raise HTTPException(400, detail="title_too_short")

    term_lookup  = {r["term"]: r for _, r in terms_df.iterrows()}
    counts_series = terms_df["count"]
    total_terms   = len(terms_df)

    # Playlist-term frequencies are heavily long-tailed, so a raw count/max ratio
    # rates everything below the single top term as "original". Use a percentile
    # rank instead: the share of terms this word is as-common-as or rarer than.
    def pct_rank(c):
        return round(float((counts_series <= c).sum()) / total_terms * 100, 1)

    hits, misses = [], []
    for word in words:
        if word in term_lookup:
            row = term_lookup[word]
            hits.append({
                "word":  word,
                "count": int(row["count"]),
                "pct":   float(row["pct"]),
                "theme": row["theme"],
                "score": pct_rank(int(row["count"])),
            })
        else:
            misses.append(word)

    # A title is only as generic as its words; unrecognised words count as 0
    # (they make a title more original).
    genericness = round(sum(h["score"] for h in hits) / max(len(words), 1), 1)
    verdict     = next(v for threshold, v in _ROAST_VERDICTS if genericness >= threshold)

    examples = []
    for h in sorted(hits, key=lambda x: -x["score"])[:2]:
        row = terms_df[terms_df["term"] == h["word"]]
        if not row.empty:
            examples.extend(_to_list(row.iloc[0].get("example_titles"))[:3])

    # Similar-title ceiling = the rarest word every copy must share (bottleneck).
    # Any unrecognised word means exact twins are effectively nil.
    similar_count = 0 if (misses or not hits) else int(min(h["count"] for h in hits))

    return {
        "title":         title,
        "genericness":   genericness,
        "verdict":       verdict,
        "word_scores":   hits,
        "rare_words":    misses,
        "similar_count": similar_count,
        "examples":      list(set(examples))[:5],
    }


@router.get("/api/name-generator")
def name_generator(theme: Optional[str] = None, count: int = 8):
    terms_df = _load_computed("computed/playlist_title_terms.parquet")
    if terms_df is None:
        raise HTTPException(503, detail="not_ready")

    count = min(count, 20)

    if theme and theme != "all":
        pool = terms_df[terms_df["theme"] == theme]
        if pool.empty:
            pool = terms_df
    else:
        pool = terms_df

    p25 = pool["count"].quantile(0.25)
    p75 = pool["count"].quantile(0.75)
    mid = pool[(pool["count"] >= p25) & (pool["count"] <= p75)]
    if len(mid) < 10:
        mid = pool

    words = mid["term"].tolist()

    def _cap(w: str) -> str:
        return " ".join(p.capitalize() for p in w.split())

    names: set[str] = set()
    attempts = 0
    while len(names) < count and attempts < 200:
        attempts += 1
        if len(words) >= 2:
            w1, w2    = random.sample(words, 2)
            candidate = f"{_cap(w1)} {_cap(w2)}"
        else:
            candidate = _cap(random.choice(words))
        if len(candidate) > 4:
            names.add(candidate)

    return {
        "theme":  theme or "all",
        "names":  list(names)[:count],
        "source": f"{len(pool):,} real playlist terms",
    }
