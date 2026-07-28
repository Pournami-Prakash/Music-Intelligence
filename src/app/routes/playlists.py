import random
import re
from collections import Counter
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, duck_all, duck_one, sp
from src.app.helpers import _to_list, _extract_playlist_id
from src.app.models import PlaylistUrlBody

router = APIRouter()

_ROAST_VERDICTS = [
    (90, "Congratulations, this is statistically indistinguishable from 800,000 other playlists."),
    (70, "You and approximately every third person on Spotify had the same idea."),
    (50, "Competently generic. A solid 6/10 in the taxonomy of playlist names."),
    (30, "Some originality detected. Someone might actually remember this title."),
    (0,  "Genuinely rare. Either very creative or very obscure — possibly both."),
]

_NAME_THEME_MAP = {
    "chill": ("mood", ["chill", "calm", "soft", "mellow"]),
    "sad": ("mood", ["sad", "cry", "heartbreak", "melancholy"]),
    "hype": ("mood", ["hype", "energy", "banger", "bops"]),
    "romantic": ("mood", ["love", "romantic", "feelings"]),
    "gym": ("activity", ["gym", "workout", "running", "pump"]),
    "party": ("activity", ["party", "dance", "club", "pregame"]),
    "study": ("activity", ["study", "focus", "reading", "work"]),
    "summer": ("time", ["summer", "sunset", "june", "july"]),
    "nostalgic": ("time", ["throwback", "nostalgia", "old school", "retro"]),
}


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


@router.post("/api/playlist-profile")
def playlist_profile(body: PlaylistUrlBody):
    playlist_id = _extract_playlist_id(body.playlist_url)
    if not playlist_id:
        raise HTTPException(400, detail="invalid_playlist_url")
    import_mode = "spotify_api"
    try:
        info = sp.playlist_info(playlist_id)
        tracks = sp.playlist_tracks(playlist_id, limit=500)
    except Exception:
        try:
            info, tracks = sp.playlist_embed(playlist_id)
            import_mode = "public_embed_preview"
        except Exception:
            raise HTTPException(400, detail="playlist_import_failed")
    if not tracks:
        raise HTTPException(404, detail="playlist_empty")

    terms_df = _load_computed("computed/playlist_title_terms.parquet")
    if terms_df is None:
        raise HTTPException(503, detail="not_ready")

    title_text = (info.get("name") or "").casefold().replace("’", "'")
    title_tokens = [
        token[:-2] if token.endswith("'s") else token
        for token in re.findall(r"[a-z0-9']+", title_text)
        if len(token) > 1
    ]
    term_lookup = {
        str(row["term"]).casefold(): row
        for _, row in terms_df.iterrows()
    }
    title_terms = []
    for token in dict.fromkeys(title_tokens):
        row = term_lookup.get(token)
        if row is None:
            title_terms.append({
                "word": token, "known": False, "count": 0, "pct": 0, "theme": None,
            })
        else:
            title_terms.append({
                "word": token,
                "known": True,
                "count": int(row["count"]),
                "pct": float(row["pct"]),
                "theme": row["theme"],
            })

    artist_counts = Counter(
        track["artist"] for track in tracks if track.get("artist")
    )
    total = len(tracks)
    followers = info.get("followers") or {}
    owner = info.get("owner") or {}
    return {
        "playlist": {
            "id": playlist_id,
            "name": info.get("name") or "Untitled playlist",
            "description": info.get("description") or "",
            "owner": owner.get("display_name") or owner.get("id"),
            "followers": followers.get("total"),
            "track_count": total,
            "import_mode": import_mode,
        },
        "title_terms": title_terms,
        "top_artists": [
            {
                "artist": artist,
                "tracks": count,
                "pct": round(count / total * 100, 1),
            }
            for artist, count in artist_counts.most_common(10)
        ],
        "tracks": tracks[:20],
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
    first = df.iloc[0]
    total = int(first.get("total_playlists", 1_000_000))
    unique_matched = int(first.get("unique_matched_titles", sum(c["count"] for c in clusters)))
    assignment_count = int(first.get("assignment_count", sum(c["count"] for c in clusters)))
    return {
        "clusters": clusters,
        "total_playlists": total,
        "unique_matched_titles": unique_matched,
        "assignment_count": assignment_count,
        "categories_overlap": bool(first.get("categories_overlap", True)),
        "method_version": first.get("method_version", "legacy-keywords"),
        "evidence": {
            "metric": "Distinct playlist titles matching bounded mood or listening-context terms",
            "population": f"{total:,} playlist titles",
            "source": "Playlist-title corpus",
            "limitations": ["Categories may overlap", "This does not analyse the audio or lyrics"],
        },
    }


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

    word_examples = []
    for h in sorted(hits, key=lambda x: -x["score"])[:2]:
        row = terms_df[terms_df["term"] == h["word"]]
        if not row.empty:
            word_examples.extend(_to_list(row.iloc[0].get("example_titles"))[:3])

    normalized_title = re.sub(r"[^\w]+", " ", title.lower()).strip()
    exact_count = 0
    exact_examples: list[str] = []
    playlists_path = local_parquet("processed/playlists.parquet")
    if playlists_path is not None and normalized_title:
        normalizer = "lower(trim(regexp_replace(name, '[^[:alnum:]]+', ' ', 'g')))"
        exact = duck_one(
            f"SELECT count(*) FROM read_parquet('{playlists_path.as_posix()}') "
            f"WHERE {normalizer} = ?",
            [normalized_title],
        )
        exact_count = int(exact[0]) if exact else 0
        exact_examples = [
            str(row[0]) for row in duck_all(
                f"SELECT DISTINCT name FROM read_parquet('{playlists_path.as_posix()}') "
                f"WHERE {normalizer} = ? ORDER BY name LIMIT 5",
                [normalized_title],
            )
        ]

    return {
        "title":         title,
        "normalized_title": normalized_title,
        "genericness":   genericness,
        "verdict":       verdict,
        "word_scores":   hits,
        "rare_words":    misses,
        "exact_match_count": exact_count,
        "exact_examples": exact_examples,
        "word_examples": list(dict.fromkeys(word_examples))[:5],
        # Compatibility aliases for older clients. They now carry exact-title
        # evidence rather than a word-frequency ceiling.
        "similar_count": exact_count,
        "examples": exact_examples,
        "method": "Exact normalized-title count plus per-word corpus percentiles",
        "evidence": {
            "metric": "Exact normalized title matches and term-frequency percentiles",
            "population": "One million playlist titles",
            "source": "Playlist-title corpus",
            "limitations": ["Genericness is a playful term-frequency index, not a quality judgment"],
        },
    }


@router.get("/api/name-generator")
def name_generator(theme: Optional[str] = None, count: int = 8):
    terms_df = _load_computed("computed/playlist_title_terms.parquet")
    if terms_df is None:
        raise HTTPException(503, detail="not_ready")

    count = min(count, 20)

    requested_theme = (theme or "all").strip().lower()
    corpus_theme, requested_anchors = _NAME_THEME_MAP.get(
        requested_theme, (requested_theme if requested_theme in {"mood", "activity", "time", "identity", "genre", "other"} else "all", [])
    )
    pool = terms_df if corpus_theme == "all" else terms_df[terms_df["theme"] == corpus_theme]
    if pool.empty:
        raise HTTPException(400, detail="unknown_name_theme")

    p25 = pool["count"].quantile(0.25)
    p75 = pool["count"].quantile(0.75)
    mid = pool[(pool["count"] >= p25) & (pool["count"] <= p75)]
    if len(mid) < 10:
        mid = pool

    words = [str(word) for word in mid["term"].tolist()]
    available = set(str(word) for word in terms_df["term"].tolist())
    anchors = [anchor for anchor in requested_anchors if anchor in available]
    if not anchors:
        anchors = words[: min(12, len(words))]
    if not words or not anchors:
        raise HTTPException(503, detail="name_terms_not_ready")

    def _cap(w: str) -> str:
        return " ".join(p.capitalize() for p in w.split())

    # Deterministic generation makes results testable and reproducible. Each
    # name includes a theme anchor and a real companion term from the same
    # corpus category; no claim is made that the full generated phrase existed.
    rng = random.Random(f"{requested_theme}:{count}")
    names: list[str] = []
    attempts = 0
    while len(names) < count and attempts < 300:
        attempts += 1
        anchor = rng.choice(anchors)
        companion = rng.choice(words)
        if companion == anchor:
            continue
        pair = [anchor, companion] if attempts % 2 else [companion, anchor]
        candidate = " ".join(_cap(word) for word in pair)
        if len(candidate) > 4 and candidate not in names:
            names.append(candidate)

    return {
        "theme": requested_theme,
        "corpus_theme": corpus_theme,
        "names": names[:count],
        "source": f"{len(pool):,} real playlist terms",
        "method": "Each generated name combines a requested-theme anchor with a real term from the matching corpus category.",
        "anchors": anchors,
        "evidence": {
            "metric": "New combinations of observed playlist-title terms",
            "population": f"{len(pool):,} terms in the {corpus_theme} category",
            "source": "Playlist-title term corpus",
            "limitations": ["Generated phrases are new combinations and are not claimed to be existing playlist titles"],
        },
    }
