"""
Artist co-occurrence graph, queried on demand from the local artist_edges
parquet via DuckDB.

The full edge list (~7.5 M undirected edges) is ~2.5 GB as a resident pandas
DataFrame and even larger once expanded into a dict-of-dicts adjacency — far too
much for a small serving box. Instead we download the 56 MB parquet to local
disk once (local_parquet) and let DuckDB stream + filter it per request. Only the
neighbours we actually ask for are ever materialised, so memory stays flat while
graph traversals (six-degrees BFS, blends, collisions) remain fast on local disk.

Edges are undirected: an edge (a, b, w) means a neighbour query on either a or b
should surface the other with weight w.
"""
from typing import Optional

import pandas as pd

from src.app.cache import local_parquet, con

_KEY = "computed/artist_edges.parquet"
_reg_seq = 0


def _path() -> Optional[str]:
    p = local_parquet(_KEY)
    return p.as_posix() if p is not None else None


def resolve_artist(name: str) -> Optional[str]:
    """Return the canonical artist name as it appears in the edge list.

    Exact (case-insensitive) match first, then a substring fallback — mirroring
    the old _artist_name_map behaviour so callers resolve the same names.
    """
    path = _path()
    if path is None:
        return None
    n = name.lower()
    exact = con.execute(f"""
        SELECT name FROM (
            SELECT artist_a_name AS name FROM read_parquet('{path}') WHERE lower(artist_a_name) = ?
            UNION
            SELECT artist_b_name AS name FROM read_parquet('{path}') WHERE lower(artist_b_name) = ?
        ) LIMIT 1
    """, [n, n]).fetchone()
    if exact:
        return exact[0]
    like = f"%{n}%"
    fuzzy = con.execute(f"""
        SELECT name FROM (
            SELECT artist_a_name AS name FROM read_parquet('{path}') WHERE lower(artist_a_name) LIKE ?
            UNION
            SELECT artist_b_name AS name FROM read_parquet('{path}') WHERE lower(artist_b_name) LIKE ?
        ) LIMIT 1
    """, [like, like]).fetchone()
    return fuzzy[0] if fuzzy else None


def artist_neighbors(name: str) -> dict[str, int]:
    """{neighbour_name: shared_playlists} for one (canonical) artist."""
    path = _path()
    if path is None:
        return {}
    rows = con.execute(f"""
        SELECT artist_b_name AS nb, shared_playlists AS w
          FROM read_parquet('{path}') WHERE artist_a_name = ?
        UNION ALL
        SELECT artist_a_name AS nb, shared_playlists AS w
          FROM read_parquet('{path}') WHERE artist_b_name = ?
    """, [name, name]).fetchall()
    return {nb: int(w) for nb, w in rows}


def edge_weight(a: str, b: str) -> int:
    """shared_playlists between two canonical artists (0 if not adjacent)."""
    path = _path()
    if path is None:
        return 0
    r = con.execute(f"""
        SELECT max(shared_playlists) FROM read_parquet('{path}')
        WHERE (artist_a_name = ? AND artist_b_name = ?)
           OR (artist_a_name = ? AND artist_b_name = ?)
    """, [a, b, b, a]).fetchone()
    return int(r[0]) if r and r[0] is not None else 0


def neighbors_of_many(names: set[str], fan: Optional[int] = None) -> dict[str, list[tuple[str, int]]]:
    """For each name, its neighbours as (name, weight) sorted by weight desc.

    One DuckDB pass over the edge list against the frontier set — used to expand
    a whole BFS level at once instead of a query per node.
    """
    path = _path()
    if path is None or not names:
        return {}
    global _reg_seq
    _reg_seq += 1
    rel = f"_frontier_{_reg_seq}"
    frontier_df = pd.DataFrame({"n": list(names)})
    con.register(rel, frontier_df)
    try:
        rows = con.execute(f"""
            SELECT artist_a_name AS src, artist_b_name AS nb, shared_playlists AS w
              FROM read_parquet('{path}') WHERE artist_a_name IN (SELECT n FROM {rel})
            UNION ALL
            SELECT artist_b_name AS src, artist_a_name AS nb, shared_playlists AS w
              FROM read_parquet('{path}') WHERE artist_b_name IN (SELECT n FROM {rel})
        """).fetchall()
    finally:
        con.unregister(rel)

    out: dict[str, list[tuple[str, int]]] = {}
    for src, nb, w in rows:
        out.setdefault(src, []).append((nb, int(w)))
    for src in out:
        out[src].sort(key=lambda x: -x[1])
        if fan is not None:
            out[src] = out[src][:fan]
    return out
