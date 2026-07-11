"""
Enrich artist_habitat.parquet with Last.fm tag-based habitat signals.

The existing artist_habitat.parquet uses only playlist-title keyword matching
(e.g. a playlist called "workout banger" → gym signal for its artists).
Last.fm user-applied tags (chillout, ambient, 80s, dance, etc.) add a second
orthogonal signal and extend coverage from 10K → ~30K artists.

Strategy:
  - For artists in BOTH datasets: blend playlist_pct (0.7) + tag_pct (0.3)
  - For artists in Last.fm ONLY: create rows with tag-only pct, count=0
  - For artists in habitat ONLY (no Last.fm tags): keep as-is

Tag → habitat mapping is deliberately conservative (exact/substring match on
high-confidence terms) to avoid diluting strong playlist signal.

Output: R2:computed/artist_habitat.parquet (updated in-place)

Usage:
    python src/compute/compute_lastfm_habitat_signal.py
    python src/compute/compute_lastfm_habitat_signal.py --dry-run
"""

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.r2 import R2Client

_TMP = Path(tempfile.gettempdir()) / "track2vec_cache"

HABITATS = ["gym", "heartbreak", "road_trip", "party", "study", "chill", "throwback", "sleep"]

# Tags to habitat mapping — terms chosen where Last.fm signal is strong and
# genre/tag maps cleanly to a context.
_TAG_HABITATS: dict[str, set[str]] = {
    "gym": {
        "workout", "gym", "exercise", "fitness", "training", "energetic",
        "metal", "hard rock", "heavy metal", "thrash metal", "metalcore",
        "power metal", "nu metal", "punk", "hardcore", "punk rock",
    },
    "heartbreak": {
        "melancholic", "sad", "emotional", "melancholy", "bittersweet",
        "longing", "heartbreak", "emo", "slowcore", "sadcore", "dark",
    },
    "road_trip": {
        "summer", "country", "americana", "indie folk", "folk rock",
        "southern rock", "classic rock", "roots rock", "country rock",
    },
    "party": {
        "dance", "disco", "club", "edm", "house", "techno", "electro",
        "dancehall", "electro house", "drum and bass", "dubstep", "party",
        "reggaeton", "afrobeats", "afropop", "eurodance", "trance",
    },
    "study": {
        "relaxing", "relax", "calm", "peaceful", "classical", "piano",
        "post-classical", "instrumental", "acoustic", "neo-classical",
        "focus", "jazz", "neoclassical",
    },
    "chill": {
        "chillout", "chill", "lo-fi", "easy listening", "lounge",
        "trip-hop", "downtempo", "chillwave", "indie pop", "soft",
        "bossa nova", "nu jazz", "smooth jazz",
    },
    "throwback": {
        "80s", "90s", "oldies", "retro", "nostalgia", "vintage", "classic",
        "classic rock", "synth-pop", "new wave", "80s pop", "80s rock",
        "80s metal", "90s hip hop", "golden age hip hop",
    },
    "sleep": {
        "ambient", "drone", "meditation", "new age", "post-rock",
        "dark ambient", "field recording", "atmospheric", "space ambient",
        "deep ambient", "sleep", "soundscape",
    },
}

# Weight for blending: playlist signal is primary, tag is secondary.
_PLAYLIST_WEIGHT = 0.7
_TAG_WEIGHT = 0.3
# Synthetic pct assigned when a tag fully matches a habitat (scale to ~playlist pcts)
_TAG_MATCH_PCT = 40.0


def _tags_to_habitat_pcts(tags_array) -> dict[str, float]:
    """Given a numpy array / list of tags, return habitat→pct dict."""
    if tags_array is None:
        return {h: 0.0 for h in HABITATS}
    tags_lower = {t.lower() for t in tags_array if t}
    pcts: dict[str, float] = {}
    for h in HABITATS:
        matched = tags_lower & _TAG_HABITATS[h]
        # Scale by fraction of habitat keywords matched (capped at 1.0)
        ratio = min(len(matched) / max(len(_TAG_HABITATS[h]) * 0.15, 1), 1.0)
        pcts[h] = round(ratio * _TAG_MATCH_PCT, 2)
    return pcts


def main(dry_run: bool) -> None:
    r2 = R2Client()
    _TMP.mkdir(exist_ok=True)

    # ── Load existing habitat (playlist-title signal) ──────────────────────────
    print("Downloading artist_habitat.parquet …")
    hab_path = _TMP / "artist_habitat_enrich.parquet"
    r2.download("computed/artist_habitat.parquet", str(hab_path))
    hab = pd.read_parquet(hab_path)
    print(f"  {len(hab):,} artists (playlist-title signal)")

    # ── Load Last.fm tags ──────────────────────────────────────────────────────
    print("Downloading artist_lastfm.parquet …")
    lfm_path = _TMP / "artist_lastfm_enrich.parquet"
    r2.download("enrichment/artist_lastfm.parquet", str(lfm_path))
    lfm = pd.read_parquet(lfm_path)
    print(f"  {len(lfm):,} artists in Last.fm data")

    # Build tag signal for every Last.fm artist
    print("Computing tag-based habitat signal …")
    lfm_tag_pcts = lfm["tags"].apply(_tags_to_habitat_pcts)
    for h in HABITATS:
        lfm[f"{h}_tag_pct"] = lfm_tag_pcts.apply(lambda d: d[h])

    lfm_tagged = lfm[lfm[[f"{h}_tag_pct" for h in HABITATS]].max(axis=1) > 0]
    print(f"  {len(lfm_tagged):,} artists with non-zero tag signal")
    for h in HABITATS:
        n = (lfm[f"{h}_tag_pct"] > 0).sum()
        print(f"    {h:<12}: {n:,} artists tagged")

    # ── Merge: update existing artists, append new ones ───────────────────────
    print("\nBlending signals …")
    lfm_lookup = lfm.drop_duplicates("artist_name").set_index("artist_name")

    updated = 0
    for idx, row in hab.iterrows():
        name = row["artist_name"]
        if name not in lfm_lookup.index:
            continue
        lfm_row = lfm_lookup.loc[name]
        for h in HABITATS:
            playlist_pct = float(row[f"{h}_pct"])
            tag_pct = float(lfm_row[f"{h}_tag_pct"])
            if tag_pct > 0:
                blended = round(_PLAYLIST_WEIGHT * playlist_pct + _TAG_WEIGHT * tag_pct, 2)
                hab.at[idx, f"{h}_pct"] = blended
        updated += 1

    print(f"  Updated {updated:,} existing artists with blended signal")

    # ── Append Last.fm-only artists (not in current top-10K) ──────────────────
    existing_names = set(hab["artist_name"].str.lower())
    new_rows = []
    for _, lfm_row in lfm.iterrows():
        if lfm_row["artist_name"].lower() in existing_names:
            continue
        tag_pcts = {h: float(lfm_row[f"{h}_tag_pct"]) for h in HABITATS}
        if max(tag_pcts.values()) == 0:
            continue  # No signal — skip
        row = {
            "artist_name":   lfm_row["artist_name"],
            "playlist_count": int(lfm_row.get("listeners", 0)) // 1000,  # proxy for scale
        }
        for h in HABITATS:
            row[h] = 0          # no playlist count data
            row[f"{h}_pct"] = tag_pcts[h]
        new_rows.append(row)

    new_df = pd.DataFrame(new_rows) if new_rows else pd.DataFrame(columns=hab.columns)

    # Ensure column alignment
    for col in hab.columns:
        if col not in new_df.columns:
            new_df[col] = 0 if col in HABITATS else ""

    combined = pd.concat([hab, new_df[hab.columns]], ignore_index=True)
    combined = combined.sort_values("playlist_count", ascending=False).reset_index(drop=True)
    print(f"  Added {len(new_rows):,} Last.fm-only artists")
    print(f"  Final: {len(combined):,} artists total")

    # ── Sample output ──────────────────────────────────────────────────────────
    print("\nSample — top chill_pct artists (min 500 playlists):")
    sample = combined[combined["playlist_count"] >= 500].nlargest(5, "chill_pct")
    print(sample[["artist_name", "playlist_count", "chill_pct", "party_pct", "throwback_pct"]].to_string(index=False))

    print("\nSample — top throwback_pct artists (min 500 playlists):")
    sample2 = combined[combined["playlist_count"] >= 500].nlargest(5, "throwback_pct")
    print(sample2[["artist_name", "playlist_count", "throwback_pct", "chill_pct"]].to_string(index=False))

    if dry_run:
        print("\n[dry-run] skipping upload.")
        return

    # ── Upload ─────────────────────────────────────────────────────────────────
    out = _TMP / "artist_habitat_enriched.parquet"
    combined.to_parquet(out, index=False, compression="zstd")
    size_mb = out.stat().st_size / 1024 ** 2
    print(f"\nUploading {size_mb:.1f} MB → R2:computed/artist_habitat.parquet …")
    r2.upload(str(out), "computed/artist_habitat.parquet", delete_after=True)
    r2.usage_summary()
    print(f"\n✓ artist_habitat enriched: {len(combined):,} artists "
          f"({len(hab):,} playlist-signal + {len(new_rows):,} tag-only)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    main(dry_run=args.dry_run)
