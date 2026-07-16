from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, duck_slot
from src.app.rcache import ttl_cache
from src.app.helpers import _to_list, _extract_playlist_id
from src.app.models import GroupBlendBody, ForensicsBody
from src.app.graph import (
    resolve_artist, artist_neighbors, edge_weight, neighbors_of_many,
)

router = APIRouter()


@router.get("/api/six-degrees")
@ttl_cache()
def six_degrees(from_artist: str = "Drake", to_artist: str = "Radiohead", max_depth: int = 6):
    canon_from = resolve_artist(from_artist)
    if canon_from is None:
        raise HTTPException(404, detail=f"artist_not_found: {from_artist}")
    canon_to = resolve_artist(to_artist)
    if canon_to is None:
        raise HTTPException(404, detail=f"artist_not_found: {to_artist}")

    if canon_from == canon_to:
        return {"from": canon_from, "to": canon_to, "hops": 0,
                "path": [{"name": canon_from, "shared": None}]}

    FAN = 100
    fwd = {canon_from: [canon_from]}
    bwd = {canon_to:   [canon_to]}
    expanded: set[str] = set()

    for _ in range((max_depth + 1) // 2 + 1):
        frontier = fwd if len(fwd) <= len(bwd) else bwd

        # Expand a whole BFS level in one DuckDB pass over the edge list.
        to_expand = {
            node for node, path in frontier.items()
            if node not in expanded and len(path) - 1 < max_depth // 2 + 1
        }
        if not to_expand:
            break
        nbrs = neighbors_of_many(to_expand, fan=FAN)
        expanded |= to_expand

        next_frontier = {}
        for node in to_expand:
            path = frontier[node]
            for nb, _w in nbrs.get(node, []):
                if nb not in frontier and nb not in next_frontier:
                    next_frontier[nb] = path + [nb]

        frontier.update(next_frontier)

        meet = set(fwd) & set(bwd)
        if meet:
            mid      = min(meet, key=lambda n: len(fwd[n]) + len(bwd[n]))
            path_fwd = fwd[mid]
            path_bwd = list(reversed(bwd[mid]))
            full     = path_fwd + path_bwd[1:]
            result   = []
            for i, name in enumerate(full):
                shared = None if i == 0 else edge_weight(full[i - 1], name)
                result.append({"name": name, "shared": shared})
            return {"from": canon_from, "to": canon_to, "hops": len(full) - 1, "path": result}

    raise HTTPException(404, detail="no_path_found")


@router.post("/api/group-blend")
def group_blend(body: GroupBlendBody):
    input_artists = body.artists[:6]
    if not input_artists:
        raise HTTPException(400, detail="provide at least one artist in 'artists' list")

    stats_df = _load_computed("computed/artist_stats.parquet")
    if stats_df is None:
        raise HTTPException(503, detail="not_ready")

    resolved = []
    for name in input_artists:
        row = stats_df[stats_df["artist_name"].str.lower() == name.lower()]
        if row.empty:
            row = stats_df[stats_df["artist_name"].str.lower().str.contains(name.lower(), na=False)]
        if not row.empty:
            resolved.append(row.iloc[0]["artist_name"])

    if not resolved:
        raise HTTPException(404, detail="none_of_the_artists_found")

    def neighbors(artist_name: str) -> dict[str, int]:
        canonical = resolve_artist(artist_name) or artist_name
        return artist_neighbors(canonical)

    neighbor_maps = [neighbors(a) for a in resolved]

    common = set(neighbor_maps[0].keys())
    for nm in neighbor_maps[1:]:
        common &= set(nm.keys())
    common -= set(resolved)

    if not common:
        all_neighbors: dict[str, list[int]] = {}
        for nm in neighbor_maps:
            for artist, shared in nm.items():
                if artist not in resolved:
                    all_neighbors.setdefault(artist, []).append(shared)
        threshold = max(1, len(resolved) // 2)
        common = {a for a, counts in all_neighbors.items() if len(counts) >= threshold}

    def harmonic_mean(values: list[float]) -> float:
        if not values or any(v == 0 for v in values):
            return 0.0
        return len(values) / sum(1.0 / v for v in values)

    scored = []
    for candidate in common:
        scores = [nm.get(candidate, 0) for nm in neighbor_maps]
        h  = harmonic_mean(scores)
        cr = stats_df[stats_df["artist_name"] == candidate]
        pc = int(cr.iloc[0]["playlist_count"]) if not cr.empty else 0
        scored.append({"name": candidate, "blend_score": h, "playlist_count": pc})

    scored.sort(key=lambda x: -x["blend_score"])
    top_artists = scored[:10]

    tracks = []
    for entry in top_artists:
        sr = stats_df[stats_df["artist_name"] == entry["name"]]
        if sr.empty:
            continue
        raw = sr.iloc[0]["top_tracks"]
        try:
            artist_tracks = list(raw) if raw is not None else []
        except TypeError:
            artist_tracks = []
        for t in artist_tracks[:2]:
            tracks.append({
                "title":       t,
                "artist":      entry["name"],
                "blend_score": round(entry["blend_score"] / max(scored[0]["blend_score"], 1), 3),
            })
        if len(tracks) >= 12:
            break

    total_neighbors = len(set().union(*[nm.keys() for nm in neighbor_maps]))
    compatibility   = round(len(common) / max(total_neighbors, 1) * 100, 1)

    return {
        "input_artists":     resolved,
        "compatibility_pct": compatibility,
        "blend_artists": [
            {"name": a["name"], "playlist_count": a["playlist_count"],
             "blend_score": round(a["blend_score"] / max(scored[0]["blend_score"], 1), 3)}
            for a in top_artists
        ],
        "tracks":              [{"rank": i + 1, **t} for i, t in enumerate(tracks)],
        "common_ground_count": len(common),
    }


@router.get("/api/overlap-arena")
@ttl_cache()
def overlap_arena(a: str = "Drake", b: str = "Taylor Swift"):
    stats_df = _load_computed("computed/artist_stats.parquet")
    if stats_df is None:
        raise HTTPException(503, detail="not_ready")

    def get_stats(name: str):
        row = stats_df[stats_df["artist_name"].str.lower() == name.lower()]
        if row.empty:
            row = stats_df[stats_df["artist_name"].str.lower().str.contains(name.lower(), na=False)]
        return row.iloc[0] if not row.empty else None

    sa, sb = get_stats(a), get_stats(b)
    if sa is None:
        raise HTTPException(404, detail=f"artist_not_found: {a}")
    if sb is None:
        raise HTTPException(404, detail=f"artist_not_found: {b}")

    name_a, name_b = sa["artist_name"], sb["artist_name"]
    shared         = edge_weight(name_a, name_b)
    a_total        = int(sa["playlist_count"])
    b_total        = int(sb["playlist_count"])
    overlap_pct    = round(shared / max(min(a_total, b_total), 1) * 100, 2)

    return {
        "a": {
            "name":           name_a,
            "playlist_count": a_total,
            "pct":            float(sa["playlist_pct"]),
            "rank":           int(sa["rank"]),
            "top_tracks":     _to_list(sa.get("top_tracks"))[:3],
        },
        "b": {
            "name":           name_b,
            "playlist_count": b_total,
            "pct":            float(sb["playlist_pct"]),
            "rank":           int(sb["rank"]),
            "top_tracks":     _to_list(sb.get("top_tracks"))[:3],
        },
        "shared_playlists": shared,
        "overlap_pct":      overlap_pct,
        "verdict":          "highly_entangled"      if overlap_pct >= 30 else
                            "frequent_companions"   if overlap_pct >= 15 else
                            "occasional_neighbors"  if overlap_pct >= 5  else
                            "parallel_universes",
    }


@router.get("/api/collision")
@ttl_cache()
def collision(a: str = "Taylor Swift", b: str = "Kendrick Lamar"):
    stats_df = _load_computed("computed/artist_stats.parquet")
    if stats_df is None:
        raise HTTPException(503, detail="not_ready")

    def get_stats(name: str):
        row = stats_df[stats_df["artist_name"].str.lower() == name.lower()]
        if row.empty:
            row = stats_df[stats_df["artist_name"].str.lower().str.contains(name.lower(), na=False)]
        return row.iloc[0] if not row.empty else None

    sa, sb = get_stats(a), get_stats(b)
    if sa is None:
        raise HTTPException(404, detail=f"artist_not_found: {a}")
    if sb is None:
        raise HTTPException(404, detail=f"artist_not_found: {b}")

    name_a, name_b = sa["artist_name"], sb["artist_name"]
    shared         = edge_weight(name_a, name_b)

    neighbors_a  = set(artist_neighbors(name_a).keys())
    neighbors_b  = set(artist_neighbors(name_b).keys())
    bridge_names = (neighbors_a & neighbors_b) - {name_a, name_b}

    bridges = []
    for bname in list(bridge_names)[:100]:
        br = stats_df[stats_df["artist_name"] == bname]
        if not br.empty:
            bridges.append({"name": bname, "playlist_count": int(br.iloc[0]["playlist_count"])})
    bridges.sort(key=lambda x: -x["playlist_count"])

    return {
        "a": {"name": name_a, "playlist_count": int(sa["playlist_count"]), "rank": int(sa["rank"])},
        "b": {"name": name_b, "playlist_count": int(sb["playlist_count"]), "rank": int(sb["rank"])},
        "shared_playlists": shared,
        "bridge_artists":   bridges[:8],
        "bridge_count":     len(bridge_names),
        "verdict": (
            "direct_collision"   if shared >= 10_000 else
            "frequent_proximity" if shared >= 2_000  else
            "occasional_contact" if shared >= 500    else
            "parallel_orbits"
        ),
    }


@router.post("/api/forensics")
def forensics(body: ForensicsBody):
    url    = body.playlist_url
    tracks = body.tracks

    ep_df = _load_computed("processed/editorial_playlists.parquet")  # small (~5 MB)
    if ep_df is None:
        raise HTTPException(503, detail="not_ready")

    playlist_id = _extract_playlist_id(url)

    if playlist_id:
        ep_row = ep_df[ep_df["playlist_id"] == playlist_id]
        if not ep_row.empty:
            ep = ep_row.iloc[0]
            return {
                "playlist_url":   url,
                "playlist_name":  ep["name"],
                "organic_pct":    0,
                "editorial_pct":  100,
                "verdict":        "editorial",
                "verdict_detail": (
                    f"This is a known Spotify editorial playlist ({ep['name']}). "
                    f"It contains {int(ep['num_tracks'])} tracks and was first scraped "
                    f"on {ep['date_first_scraped']}. Editorial playlists are curated by "
                    f"Spotify's in-house team — zero organic signal."
                ),
                "signals": [
                    {"label": "Known editorial playlist", "value": True},
                    {"label": "Tracks",     "value": int(ep["num_tracks"])},
                    {"label": "First seen", "value": str(ep["date_first_scraped"])},
                ],
            }

    ept_path = local_parquet("processed/editorial_tracks_slim.parquet") if tracks else None
    if tracks and ept_path is not None:
        # Substring-match every submitted "Artist - Title" against the editorial
        # track list in a single DuckDB pass (the parquet is streamed from local
        # disk, never loaded whole into pandas).
        q_rows = []
        for i, t in enumerate(tracks):
            parts = t.split(" - ", 1)
            if len(parts) == 2:
                artist_q, track_q = parts[0].strip().lower(), parts[1].strip().lower()
            else:
                artist_q, track_q = "", t.strip().lower()
            q_rows.append({"id": i, "aq": artist_q, "tq": track_q})

        with duck_slot() as cur:  # cursor-local registration + bounded concurrency
            cur.register("forensic_q", pd.DataFrame(q_rows))
            hit = cur.execute(f"""
                SELECT count(DISTINCT q.id) AS hits
                FROM forensic_q q
                JOIN read_parquet('{ept_path.as_posix()}') e
                  ON strpos(lower(e.track_name), q.tq) > 0
                 AND (q.aq = '' OR strpos(lower(e.artist_name), q.aq) > 0)
            """).fetchone()
        editorial_hits = int(hit[0]) if hit and hit[0] is not None else 0

        editorial_pct = round(editorial_hits / len(tracks) * 100) if tracks else 0
        organic_pct   = 100 - editorial_pct
        verdict = (
            "heavy_editorial"   if editorial_pct >= 70 else
            "editorial_leaning" if editorial_pct >= 40 else
            "mixed"             if editorial_pct >= 20 else
            "organic"
        )
        return {
            "playlist_url":   url,
            "playlist_name":  None,
            "organic_pct":    organic_pct,
            "editorial_pct":  editorial_pct,
            "verdict":        verdict,
            "verdict_detail": (
                f"{editorial_hits} of {len(tracks)} tracks appear in Spotify editorial playlists "
                f"({editorial_pct}% editorial density)."
            ),
            "signals": [
                {"label": "Tracks analysed",  "value": len(tracks)},
                {"label": "Editorial hits",   "value": editorial_hits},
                {"label": "Editorial density","value": f"{editorial_pct}%"},
            ],
        }

    return {
        "playlist_url":   url,
        "playlist_name":  None,
        "organic_pct":    None,
        "editorial_pct":  None,
        "verdict":        "unknown",
        "verdict_detail": (
            "Playlist not found in our editorial database. "
            "Pass a 'tracks' list (['Artist - Title', ...]) alongside the URL "
            "for editorial density analysis."
        ),
        "signals": [],
    }
