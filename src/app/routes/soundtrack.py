import json
import os
import re
import urllib.request
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed
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

_SOUNDTRACK_ROLES = ["opener", "build", "anchor", "peak", "anchor", "wind_down", "closer", "bonus"]

_OLLAMA_URL    = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
_OLLAMA_MODEL  = os.environ.get("OLLAMA_MODEL", "llama3")
_OLLAMA_SYSTEM = """\
You are a music curator assistant. Given a natural language prompt describing a mood, \
activity, or feeling, return a JSON object with exactly these fields:
  "habitat": one of [gym, heartbreak, road_trip, party, study, chill, throwback, sleep]
  "energy":  one of [low, medium, high]
  "playlist_name": a short creative playlist title (max 6 words, no quotes)
  "reasoning": one sentence explaining your choice

Respond with only valid JSON, no markdown, no extra text."""


def _ollama_classify(prompt: str, timeout: int = 25) -> Optional[dict]:
    payload = json.dumps({
        "model":   _OLLAMA_MODEL,
        "prompt":  prompt,
        "system":  _OLLAMA_SYSTEM,
        "stream":  False,
        "options": {"temperature": 0.3, "num_predict": 120},
    }).encode()
    try:
        req = urllib.request.Request(
            f"{_OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read())
        text = raw.get("response", "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        if result.get("habitat") in _SOUNDTRACK_HABITATS:
            return result
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

    llm_result = _ollama_classify(prompt)
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

    if pct_col:
        pool = hab_df[hab_df["playlist_count"] >= 500].nlargest(30, pct_col)
        if energy == "low":
            top_artists = pool.tail(15)["artist_name"].tolist()
        else:
            top_artists = pool.head(20)["artist_name"].tolist()
    else:
        top_artists = stats_df.head(20)["artist_name"].tolist()

    def collect_tracks(names, acc, seen_titles, limit=16):
        for name in names:
            stats_row = stats_df[stats_df["artist_name"] == name]
            if stats_row.empty:
                continue
            raw = stats_row.iloc[0]["top_tracks"]
            try:
                tracks = list(raw) if raw is not None else []
            except TypeError:
                tracks = []
            for t in tracks[:2]:
                if t in seen_titles:
                    continue
                acc.append({"title": t, "artist": name})
                seen_titles.add(t)
            if len(acc) >= limit:
                break
        return acc

    seen = set()
    all_tracks = collect_tracks(top_artists, [], seen)

    # Fallback: some habitats (e.g. road_trip) surface niche artists that have
    # no top_tracks on file, leaving the mix empty. Top up from the overall
    # most-playlisted artists so the gift always returns a full arc.
    if len(all_tracks) < len(_SOUNDTRACK_ROLES):
        collect_tracks(stats_df.head(40)["artist_name"].tolist(), all_tracks, seen)

    selected = all_tracks[:len(_SOUNDTRACK_ROLES)]
    result = {
        "prompt":        prompt,
        "habitat":       best_hab,
        "energy":        energy,
        "playlist_name": f"{playlist_label} — Atlas Mix",
        "tracks": [
            {"role": _SOUNDTRACK_ROLES[i], "title": t["title"], "artist": t["artist"]}
            for i, t in enumerate(selected)
        ],
        "llm_powered": used_llm,
    }
    if reasoning:
        result["reasoning"] = reasoning
    return result
