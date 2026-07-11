"""
Cluster 1M playlist titles into mood/context regions.

Strategy:
  1. Build a TF-IDF vector for each playlist title (from playlist_title_terms counts)
  2. OR: use keyword-category assignments from HABITATS/mood buckets
  3. Count playlists per mood bucket and produce cluster summaries

Since the playlist_title_terms table already categorises terms by theme,
we use those themes as mood regions and count playlists per region.

Reads:
  R2:processed/playlists.parquet         — pid, name
  R2:computed/playlist_title_terms.parquet — term, theme, count

Output:
  R2:computed/mood_map_clusters.parquet
    id, label, color, count, top_terms, description

Usage:
    python src/compute/compute_mood_map.py
"""

import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_CACHE_DIR = Path(tempfile.gettempdir()) / "track2vec_cache"

MOOD_KEYWORDS = {
    "late_night":  {
        "label": "Late Night", "color": "#6C8EF5",
        "keywords": ["night", "midnight", "late", "insomnia", "dark", "after hours", "2am", "3am",
                     "evening", "after dark", "nighttime", "4am", "nocturnal", "moonlight",
                     "dusk", "sleepless", "stars", "quiet hours", "stillness"],
        "description": "After-midnight energy — introspective, slow, atmospheric.",
    },
    "energy":      {
        "label": "Energy / Hype", "color": "#E8A838",
        "keywords": ["gym", "workout", "hype", "banger", "pump", "motivation", "energy", "lit", "beast mode"],
        "description": "High-intensity playlists built for movement and momentum.",
    },
    "heartbreak":  {
        "label": "Heartbreak", "color": "#E06C75",
        "keywords": ["heartbreak", "sad", "cry", "breakup", "miss", "pain", "hurt", "lonely", "broken"],
        "description": "Grief, loss, and the long tail of a relationship ending.",
    },
    "chill":       {
        "label": "Chill / Ambient", "color": "#7AB89A",
        "keywords": ["chill", "vibe", "relax", "lofi", "lo-fi", "ambient", "calm", "mellow", "easy"],
        "description": "Low-stakes background listening — coffee shops, work, and Sunday mornings.",
    },
    "identity":    {
        "label": "Identity / Culture", "color": "#C678DD",
        "keywords": ["black", "latina", "pride", "culture", "soul", "roots", "heritage", "afro"],
        "description": "Playlists as cultural identity and community signal.",
    },
    "nostalgia":   {
        "label": "Nostalgia", "color": "#56B6C2",
        "keywords": ["throwback", "nostalgia", "90s", "80s", "2000s", "old school", "classic", "retro", "childhood"],
        "description": "Era-specific playlists that trade in memory and longing.",
    },
    "party":       {
        "label": "Party", "color": "#FB923C",
        "keywords": ["party", "dance", "club", "pregame", "turn up", "summer", "festival", "bounce"],
        "description": "Social, communal listening built for shared spaces.",
    },
    "focus":       {
        "label": "Focus / Study", "color": "#34D399",
        "keywords": ["study", "focus", "concentrate", "work", "reading", "homework", "deep work", "coding"],
        "description": "Cognitive background — music as environment, not subject.",
    },
    "road_trip":   {
        "label": "Road Trip", "color": "#FBBF24",
        "keywords": ["road trip", "drive", "highway", "travel", "journey", "wanderlust", "cruise"],
        "description": "Motion playlists — built for forward momentum and open windows.",
    },
}


def main():
    r2 = R2Client()
    _CACHE_DIR.mkdir(exist_ok=True)

    playlists_path = _CACHE_DIR / "playlists.parquet"
    if not playlists_path.exists():
        print("Downloading playlists.parquet...", flush=True)
        r2.download("processed/playlists.parquet", playlists_path)

    print("Loading playlist names...", flush=True)
    con = duckdb.connect()
    playlists = con.execute(
        f"SELECT pid, lower(name) AS name_lower FROM read_parquet('{playlists_path}') WHERE name IS NOT NULL"
    ).df()
    print(f"  {len(playlists):,} playlists", flush=True)

    # Label each playlist by matching mood keywords
    for mood_id, meta in MOOD_KEYWORDS.items():
        pattern = "|".join(meta["keywords"])
        playlists[mood_id] = playlists["name_lower"].str.contains(pattern, regex=True, na=False)

    # Build cluster summary
    records = []
    for mood_id, meta in MOOD_KEYWORDS.items():
        count = int(playlists[mood_id].sum())

        # Top terms within this mood bucket (terms that appear in matched playlist names)
        matched_names = playlists[playlists[mood_id]]["name_lower"]
        word_freq: dict[str, int] = {}
        for name in matched_names:
            for word in name.split():
                word = word.strip(".,!?\"'()[]")
                if len(word) > 3:
                    word_freq[word] = word_freq.get(word, 0) + 1
        top_terms = sorted(word_freq, key=lambda w: -word_freq[w])[:8]

        records.append({
            "id":          mood_id,
            "label":       meta["label"],
            "color":       meta["color"],
            "count":       count,
            "pct":         round(count / len(playlists) * 100, 2),
            "top_terms":   top_terms,
            "description": meta["description"],
        })
        print(f"  {meta['label']:20s}: {count:>8,} playlists ({count/len(playlists)*100:.1f}%)")

    result = pd.DataFrame(records).sort_values("count", ascending=False)
    print(f"\nTotal clustered: {result['count'].sum():,} playlist-category assignments")

    out = _CACHE_DIR / "mood_map_clusters.parquet"
    result.to_parquet(out, index=False, compression="zstd")
    size = out.stat().st_size / 1024
    print(f"\nSaved: {size:.0f} KB", flush=True)

    r2.upload(out, "computed/mood_map_clusters.parquet", delete_after=True)
    r2.usage_summary()

    print("\n✓ mood_map_clusters done")
    print("  Next: wire /api/mood-map/clusters to computed/mood_map_clusters.parquet")

    con.close()


if __name__ == "__main__":
    main()
