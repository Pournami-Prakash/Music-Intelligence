from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, duck_slot, local_parquet, sp
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
            return {
                "from": canon_from,
                "to": canon_to,
                "hops": len(full) - 1,
                "path": result,
                "method": "Bidirectional BFS within each node's 100 strongest neighbors",
                "evidence": {
                    "metric": "Fewest hops found in the bounded co-occurrence graph",
                    "population": "Top-100 neighbor edges per expanded artist",
                    "source": "Artist playlist co-occurrence graph",
                    "limitations": ["The path is not guaranteed globally shortest in the full graph"],
                },
            }

    raise HTTPException(404, detail="no_path_found")


@router.post("/api/group-blend")
def group_blend(body: GroupBlendBody):
    return _group_blend_cached(tuple(body.artists[:6]))


@ttl_cache(maxsize=128, ttl=1800)
def _group_blend_cached(input_artist_tuple: tuple[str, ...]):
    input_artists = list(input_artist_tuple)
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

    # Read every requested neighborhood in one DuckDB pass instead of scanning
    # the edge parquet once per artist.
    batched = neighbors_of_many(set(resolved))
    neighbor_maps = [
        {neighbor: weight for neighbor, weight in batched.get(artist, [])}
        for artist in resolved
    ]

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
    shared_neighborhood_pct = round(len(common) / max(total_neighbors, 1) * 100, 1)

    return {
        "input_artists":     resolved,
        "compatibility_pct": shared_neighborhood_pct,
        "shared_neighborhood_pct": shared_neighborhood_pct,
        "blend_artists": [
            {"name": a["name"], "playlist_count": a["playlist_count"],
             "blend_score": round(a["blend_score"] / max(scored[0]["blend_score"], 1), 3)}
            for a in top_artists
        ],
        "tracks":              [{"rank": i + 1, **t} for i, t in enumerate(tracks)],
        "common_ground_count": len(common),
        "evidence": {
            "metric": "Shared candidate neighbors divided by the union of input neighborhoods",
            "population": f"{len(resolved)} resolved input artists",
            "source": "Artist playlist co-occurrence graph",
            "limitations": ["This is graph coverage, not interpersonal compatibility"],
        },
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
        "evidence": {
            "metric": "Shared playlists divided by the smaller artist footprint",
            "population": "Playlists containing either input artist",
            "source": "Artist playlist co-occurrence graph",
            "limitations": ["Playlist placement is not audience overlap"],
        },
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

    # Score the complete intersection. The old code converted the set to a list
    # and inspected an arbitrary first 100 names, so results varied by process
    # and could omit the strongest bridge.
    stats_lookup = stats_df.set_index("artist_name")["playlist_count"].to_dict()
    neighbors_a_map = artist_neighbors(name_a)
    neighbors_b_map = artist_neighbors(name_b)
    bridges = []
    for bname in bridge_names:
        shared_a = int(neighbors_a_map.get(bname, 0))
        shared_b = int(neighbors_b_map.get(bname, 0))
        if not shared_a or not shared_b:
            continue
        # Harmonic mean rewards bridges that are strong on both sides instead of
        # being dominated by a single very popular connection.
        bridge_score = 2 * shared_a * shared_b / (shared_a + shared_b)
        bridges.append({
            "name": bname,
            "playlist_count": int(stats_lookup.get(bname, 0)),
            "shared_with_a": shared_a,
            "shared_with_b": shared_b,
            "bridge_score": round(bridge_score, 1),
        })
    bridges.sort(key=lambda x: (-x["bridge_score"], -x["playlist_count"], x["name"]))

    return {
        "a": {"name": name_a, "playlist_count": int(sa["playlist_count"]), "rank": int(sa["rank"])},
        "b": {"name": name_b, "playlist_count": int(sb["playlist_count"]), "rank": int(sb["rank"])},
        "shared_playlists": shared,
        "bridge_artists":   bridges[:8],
        "bridge_count":     len(bridge_names),
        "method":            "complete_common-neighbor intersection ranked by harmonic mean of both shared-playlist edges",
        "evidence": {
            "metric": "Shared playlists with both input artists",
            "population": "Complete co-occurrence neighborhoods for the two artists",
            "source": "Artist playlist co-occurrence graph",
            "limitations": ["Playlist co-placement is not listener or audience overlap"],
        },
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
    playlist_name = None
    import_mode = None

    if playlist_id:
        ep_row = ep_df[ep_df["playlist_id"] == playlist_id]
        if not ep_row.empty:
            ep = ep_row.iloc[0]
            return {
                "playlist_url":   url,
                "playlist_name":  ep["name"],
                "organic_pct":    0,
                "outside_reference_pct": 0,
                "editorial_pct":  100,
                "verdict":        "known_editorial_playlist",
                "verdict_detail": (
                    f"This is a known Spotify editorial playlist ({ep['name']}). "
                    f"It contains {int(ep['num_tracks'])} tracks and was first scraped "
                    f"on {ep['date_first_scraped']}. Editorial playlists are curated by "
                    f"Spotify's in-house team."
                ),
                "signals": [
                    {"label": "Known editorial playlist", "value": True},
                    {"label": "Tracks",     "value": int(ep["num_tracks"])},
                    {"label": "First seen", "value": str(ep["date_first_scraped"])},
                ],
            }

        if not tracks:
            import_mode = "spotify_api"
            try:
                info = sp.playlist_info(playlist_id)
                imported = sp.playlist_tracks(playlist_id, limit=500)
            except Exception:
                try:
                    info, imported = sp.playlist_embed(playlist_id)
                    import_mode = "public_embed_preview"
                except Exception:
                    raise HTTPException(400, detail="playlist_import_failed")
            if not imported:
                raise HTTPException(404, detail="playlist_empty")
            playlist_name = info.get("name")
            tracks = [
                f"{track['artist']} - {track['name']}"
                for track in imported
                if track.get("artist") and track.get("name")
            ]
    elif not tracks:
        raise HTTPException(400, detail="invalid_playlist_url")

    if tracks:
        editorial_path = local_parquet("processed/editorial_tracks_slim.parquet")
        if editorial_path is None:
            raise HTTPException(503, detail="not_ready")
        # Substring-match every submitted "Artist - Title" against the editorial
        # track list in one local DuckDB pass. The 50 MB parquet is downloaded
        # once and remains disk-backed, avoiding both repeated R2 scans and a
        # large resident pandas DataFrame.
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
                JOIN read_parquet('{editorial_path.as_posix()}') e
                  ON strpos(lower(e.track_name), q.tq) > 0
                 AND (q.aq = '' OR strpos(lower(e.artist_name), q.aq) > 0)
            """).fetchone()
        editorial_hits = int(hit[0]) if hit and hit[0] is not None else 0

        editorial_pct = round(editorial_hits / len(tracks) * 100) if tracks else 0
        outside_reference_pct = 100 - editorial_pct
        verdict = (
            "high_reference_overlap"   if editorial_pct >= 70 else
            "moderate_reference_overlap" if editorial_pct >= 40 else
            "some_reference_overlap"     if editorial_pct >= 20 else
            "low_reference_overlap"
        )
        return {
            "playlist_url":   url,
            "playlist_name":  playlist_name,
            "organic_pct":    outside_reference_pct,
            "outside_reference_pct": outside_reference_pct,
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
                *([{"label": "Import coverage", "value": f"Public preview ({len(tracks)} tracks)"}]
                  if playlist_id and import_mode == "public_embed_preview" else []),
            ],
            "evidence": {
                "metric": "Share of imported tracks also observed in the Spotify editorial reference set",
                "population": f"{len(tracks)} imported playlist tracks",
                "source": "Public Spotify playlist import and archived editorial track set",
                "limitations": [
                    "Tracks outside the reference set are not proven to be organically selected",
                    "Public embed imports may expose only a preview",
                ],
            },
        }

    raise HTTPException(404, detail="playlist_empty")
