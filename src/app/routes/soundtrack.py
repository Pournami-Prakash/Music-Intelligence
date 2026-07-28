import json
import os
import re
import urllib.request
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, duck_slot
from src.app.models import SoundtrackGiftBody

router = APIRouter()

_SOUNDTRACK_HABITATS = {
    "gym":        ["gym", "workout", "fitness", "lift", "run", "cardio", "training", "energy", "pump", "beast"],
    "heartbreak": ["heartbreak", "sad", "cry", "miss", "pain", "hurt", "lonely", "broken", "loss", "grief"],
    "road_trip":  ["road", "drive", "travel", "journey", "highway", "cruise", "adventure", "wanderlust"],
    "party":      ["party", "dance", "club", "pregame", "hype", "lit", "banger", "celebration", "festival"],
    "study":      ["study", "focus", "work", "concentrate", "reading", "productivity", "coding", "deep"],
    "chill":      ["chill", "vibe", "relax", "lofi", "ambient", "calm", "mellow", "easy", "soft", "sunday"],
    "throwback":  ["throwback", "nostalgia", "90s", "80s", "2000s", "old school", "classic", "retro", "childhood"],
    "sleep":      ["sleep", "night", "bedtime", "dream", "drift", "lullaby", "insomnia", "quiet"],
}

_SOUNDTRACK_ROLES = ["opener", "build", "anchor", "peak", "wind_down", "closer"]
_ENERGY_CURVES = {
    "low":    [0.24, 0.32, 0.40, 0.52, 0.36, 0.22],
    "medium": [0.38, 0.52, 0.64, 0.80, 0.54, 0.34],
    "high":   [0.55, 0.70, 0.84, 0.94, 0.72, 0.50],
}
_VALENCE_TARGET = {
    "gym": 0.66, "heartbreak": 0.24, "road_trip": 0.58, "party": 0.78,
    "study": 0.45, "chill": 0.48, "throwback": 0.62, "sleep": 0.30,
}

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
_GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
_LLM_SYSTEM = """\
You are a music curator assistant. Given a natural language prompt describing a mood, \
activity, or feeling, return a JSON object with exactly these fields:
  "habitat": one of [gym, heartbreak, road_trip, party, study, chill, throwback, sleep]
  "energy":  one of [low, medium, high]
  "playlist_name": a short creative playlist title (max 6 words, no quotes)
  "reasoning": one sentence explaining your choice

Respond with only valid JSON, no markdown, no extra text."""


def _parse_llm_json(text: str) -> Optional[dict]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return None
    if result.get("habitat") in _SOUNDTRACK_HABITATS:
        return result
    return None


def _groq_classify(prompt: str, timeout: int = 12) -> Optional[dict]:
    if not _GROQ_API_KEY:
        return None
    payload = json.dumps({
        "model": _GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 160,
        "response_format": {"type": "json_object"},
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {_GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read())
        text = raw["choices"][0]["message"]["content"]
        return _parse_llm_json(text)
    except Exception:
        pass
    return None


@router.post("/api/soundtrack-gift")
def soundtrack_gift(body: SoundtrackGiftBody):
    prompt   = body.prompt.strip()
    hab_df   = _load_computed("computed/artist_habitat.parquet")
    stats_df = _load_computed("computed/artist_stats.parquet")
    if hab_df is None or stats_df is None:
        raise HTTPException(503, detail="not_ready")

    llm_result = _groq_classify(prompt)
    if llm_result:
        best_hab       = llm_result["habitat"]
        energy         = llm_result.get("energy", "medium")
        playlist_label = llm_result.get("playlist_name", best_hab.replace("_", " ").title())
        reasoning      = llm_result.get("reasoning", "")
        used_llm       = True
    else:
        prompt_lower = prompt.lower()
        habitat_scores: dict[str, int] = {
            hab: sum(1 for kw in keywords if kw in prompt_lower)
            for hab, keywords in _SOUNDTRACK_HABITATS.items()
        }
        best_hab       = max(habitat_scores, key=lambda h: habitat_scores[h])
        best_score     = habitat_scores[best_hab]
        playlist_label = best_hab.replace("_", " ").title() if best_score > 0 else "Your Soundtrack"
        best_hab       = best_hab if best_score > 0 else "chill"
        energy         = "medium"
        reasoning      = ""
        used_llm       = False

    pct_col = f"{best_hab}_pct" if f"{best_hab}_pct" in hab_df.columns else None
    if pct_col is None:
        raise HTTPException(503, detail="soundtrack_context_not_ready")

    # Start with artists whose playlist-title habitat evidence matches the brief.
    # Gather a broad pool because only a subset of corpus tracks has independently
    # matched FMA audio features.
    # FMA coverage is sparse (~3.3K audio rows), so keep the full eligible
    # artist set and let the local DuckDB join reduce it to independently
    # measured candidates. This remains a disk-backed lookup, not a network scan.
    pool = hab_df[hab_df["playlist_count"] >= 100].nlargest(10_000, pct_col)
    habitat_pct = pool.set_index("artist_name")[pct_col].to_dict()
    # Build the lookup once. Filtering the full stats frame once per artist made
    # this an accidental O(artists²) path and dominated endpoint latency.
    stats_lookup = stats_df.drop_duplicates("artist_name").set_index("artist_name")
    candidate_rows = []
    for artist_name in pool["artist_name"].tolist():
        if artist_name not in stats_lookup.index:
            continue
        try:
            raw_tracks = stats_lookup.at[artist_name, "top_tracks"]
            tracks = list(raw_tracks) if raw_tracks is not None else []
        except (TypeError, ValueError):
            tracks = []
        for title in tracks[:5]:
            candidate_rows.append({
                "title": str(title),
                "artist": artist_name,
                "habitat_pct": float(habitat_pct.get(artist_name, 0)),
            })

    vocab_path = local_parquet("embeddings/track2vec_vocab_lookup.parquet")
    fma_path = local_parquet("enrichment/fma_enrichment.parquet")
    if vocab_path is None or fma_path is None or not candidate_rows:
        raise HTTPException(503, detail="soundtrack_audio_coverage_insufficient")

    with duck_slot() as cur:
        cur.register("gift_candidates", pd.DataFrame(candidate_rows))
        candidates = cur.execute(f"""
            SELECT
                c.title,
                c.artist,
                c.habitat_pct,
                v.track_uri AS uri,
                f.fma_energy AS energy,
                f.fma_valence AS valence,
                f.fma_tempo AS tempo,
                f.match_type
            FROM gift_candidates c
            JOIN read_parquet('{vocab_path.as_posix()}') v
              ON lower(v.artist_name) = lower(c.artist)
             AND lower(v.track_name) = lower(c.title)
            JOIN read_parquet('{fma_path.as_posix()}') f
              ON f.track_uri = v.track_uri
            WHERE f.fma_energy IS NOT NULL
              AND f.fma_valence IS NOT NULL
            QUALIFY row_number() OVER (
                PARTITION BY v.track_uri ORDER BY c.habitat_pct DESC
            ) = 1
        """).df()

    if len(candidates) < len(_SOUNDTRACK_ROLES):
        raise HTTPException(503, detail="soundtrack_audio_coverage_insufficient")

    energy_key = energy if energy in _ENERGY_CURVES else "medium"
    curve = _ENERGY_CURVES[energy_key]
    valence_target = _VALENCE_TARGET[best_hab]
    max_habitat = max(float(candidates["habitat_pct"].max()), 1.0)

    # Beam-search a six-track arc. Each stage is tied to an explicit target
    # energy; adjacent energy jumps and repeated artists are penalized.
    beam: list[tuple[float, list[int]]] = [(0.0, [])]
    for target_energy in curve:
        expanded: list[tuple[float, list[int]]] = []
        for cost, path in beam:
            previous_energy = float(candidates.iloc[path[-1]]["energy"]) if path else target_energy
            previous_artists = {str(candidates.iloc[i]["artist"]) for i in path}
            for idx, row in candidates.iterrows():
                if idx in path:
                    continue
                stage_cost = (
                    abs(float(row["energy"]) - target_energy) * 0.52
                    + abs(float(row["valence"]) - valence_target) * 0.18
                    + abs(float(row["energy"]) - previous_energy) * 0.16
                    + (1 - float(row["habitat_pct"]) / max_habitat) * 0.14
                    + (0.12 if str(row["artist"]) in previous_artists else 0)
                )
                expanded.append((cost + stage_cost, path + [int(idx)]))
        expanded.sort(key=lambda state: state[0])
        beam = expanded[:80]

    best_cost, best_path = beam[0]
    selected = candidates.loc[best_path].reset_index(drop=True)
    result = {
        "prompt":        prompt,
        "habitat":       best_hab,
        "energy":        energy,
        "playlist_name": f"{playlist_label} — Atlas Mix",
        "tracks": [
            {
                "role": _SOUNDTRACK_ROLES[i],
                "title": row["title"],
                "artist": row["artist"],
                "uri": row["uri"],
                "energy": round(float(row["energy"]), 3),
                "valence": round(float(row["valence"]), 3),
                "tempo": round(float(row["tempo"]), 1) if pd.notna(row["tempo"]) else None,
                "target_energy": curve[i],
                "selection_reason": (
                    f"{row['habitat_pct']:.1f}% {best_hab.replace('_', ' ')} title-context reach; "
                    f"audio energy {float(row['energy']):.2f} near stage target {curve[i]:.2f}"
                ),
            }
            for i, (_, row) in enumerate(selected.iterrows())
        ],
        "llm_powered": used_llm,
        "route_score": round(max(0.0, 1 - best_cost / len(_SOUNDTRACK_ROLES)), 3),
        "meta": {
            "candidate_count": int(len(candidates)),
            "audio_source": "FMA matched audio features",
            "method": "context-filtered six-stage energy-curve beam search",
        },
        "evidence": {
            "metric": "Playlist-title context relevance plus stage energy, valence, and adjacent-energy fit",
            "population": f"{len(candidates):,} context-matched tracks with FMA audio coverage",
            "source": "Artist habitat counts, corpus top tracks, and FMA audio features",
            "limitations": ["FMA audio coverage is partial", "This does not perform harmonic-key beatmatching"],
        },
    }
    if reasoning:
        result["reasoning"] = reasoning
    return result
