import re
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.app.cache import _load_computed, local_parquet, con, _chart_for_track, _chart_for_name

router = APIRouter()

_ERA_MAP = {
    "60s": (1960, 1969), "70s": (1970, 1979), "80s": (1980, 1989),
    "90s": (1990, 1999), "2000s": (2000, 2009), "2010s": (2010, 2019),
    "2020s": (2020, 2029),
}

_MOOD_PAIRS = {
    "sad":    ["gym", "workout", "hype", "party", "banger", "pump", "energy"],
    "happy":  ["sad", "cry", "heartbreak", "miss", "broken", "pain"],
    "gym":    ["sleep", "sad", "cry", "study", "focus", "calm", "ambient"],
    "party":  ["sleep", "study", "focus", "calm", "sad", "cry", "ambient"],
    "study":  ["party", "hype", "banger", "turn up", "dance", "club"],
    "sleep":  ["gym", "workout", "hype", "party", "dance", "energy", "pump"],
    "chill":  ["gym", "hype", "party", "banger", "pump", "energy", "intense"],
}

# Editorial playlists include a lot of non-music content (language courses,
# audiobooks, meditation, comedy, lectures). These dominate "longest run" and
# "most appearances" rankings, so filter them out of the culture-facing views.
_NONMUSIC_PL = re.compile(
    r"learn\b|language|\blesson|for beginners|audiobook|\bpodcast|meditation|"
    r"white noise|\basmr\b|sleep sounds|rain sounds|nature sounds|bedtime|"
    r"sermon|scripture|the great courses|comedy|stand[- ]?up|spoken word", re.I)
_NONMUSIC_ARTIST = re.compile(
    r"publications|\blimited\b|\bltd\b|audiobook|\breadings?\b|the great courses|"
    r"\blectures?\b|monty python|chomsky", re.I)


def _music_only(df: pd.DataFrame) -> pd.DataFrame:
    """Drop non-music rows by artist and (if present) playlist-name signals."""
    mask = pd.Series(True, index=df.index)
    if "artist_name" in df.columns:
        mask &= ~df["artist_name"].fillna("").str.contains(_NONMUSIC_ARTIST)
    if "playlist_name" in df.columns:
        mask &= ~df["playlist_name"].fillna("").str.contains(_NONMUSIC_PL)
    return df[mask]


def _drop_nonmusic_by_playlist(df: pd.DataFrame, playlist_df) -> pd.DataFrame:
    """Filter tracks that live in non-music playlists (needs playlist_id + playlist_df)."""
    if playlist_df is not None and "playlist_id" in df.columns:
        bad = set(playlist_df[playlist_df["name"].fillna("").str.contains(_NONMUSIC_PL)]["playlist_id"].tolist())
        df = df[~df["playlist_id"].isin(bad)]
    if "artist_name" in df.columns:
        df = df[~df["artist_name"].fillna("").str.contains(_NONMUSIC_ARTIST)]
    return df


def _load_removed_tracks():
    """Load editorial_removed.parquet (or build from raw files if not yet computed)."""
    removed = _load_computed("computed/editorial_removed.parquet")
    if removed is None:
        tracks_df   = _load_computed("processed/editorial_playlist_tracks.parquet")
        playlist_df = _load_computed("processed/editorial_playlists.parquet")
        if tracks_df is None or playlist_df is None:
            return None
        df = tracks_df.copy()
        df["date_added"]   = pd.to_datetime(df["date_added"],   errors="coerce")
        df["date_removed"] = pd.to_datetime(df["date_removed"], errors="coerce")
        removed = df[df["date_removed"].notna()].copy()
        removed["days_on"] = (removed["date_removed"] - removed["date_added"]).dt.days.clip(lower=0)
        pl_names = playlist_df[["playlist_id", "name"]].rename(columns={"name": "playlist_name"})
        removed = removed.merge(pl_names, on="playlist_id", how="left")
        return _music_only(removed)

    removed = removed.copy()
    removed["date_added"]   = pd.to_datetime(removed["date_added"],   errors="coerce")
    removed["date_removed"] = pd.to_datetime(removed["date_removed"], errors="coerce")
    return _music_only(removed)


@router.get("/api/editorial-graveyard")
def editorial_graveyard(sort: str = "recent", limit: int = 50):
    removed = _load_removed_tracks()
    if removed is None:
        raise HTTPException(503, detail="not_ready")

    if sort == "longest":
        removed = removed.sort_values("days_on", ascending=False)
    else:
        removed = removed.sort_values("date_removed", ascending=False)

    top = removed.head(limit)
    return {
        "tracks": [
            {
                "title":    r["track_name"],
                "artist":   r["artist_name"],
                "playlist": r.get("playlist_name") or "Unknown",
                "days":     int(r["days_on"]) if pd.notna(r["days_on"]) else None,
                "removed":  r["date_removed"].strftime("%Y-%m-%d") if pd.notna(r["date_removed"]) else None,
                "added":    r["date_added"].strftime("%Y-%m-%d")   if pd.notna(r["date_added"])   else None,
            }
            for _, r in top.iterrows()
        ],
        "total_removed": int(len(removed)),
    }


@router.get("/api/forgotten-hits")
def forgotten_hits(min_days: int = 180, limit: int = 50):
    removed = _load_removed_tracks()
    if removed is None:
        raise HTTPException(503, detail="not_ready")

    cutoff   = pd.Timestamp.now() - pd.Timedelta(days=365)
    forgotten = removed[
        (removed["days_on"] >= min_days) &
        (removed["date_removed"] < cutoff)
    ].copy().sort_values("days_on", ascending=False)

    results = []
    for _, r in forgotten.head(limit).iterrows():
        ch = _chart_for_name(r["track_name"], r["artist_name"])
        results.append({
            "title":              r["track_name"],
            "artist":             r["artist_name"],
            "playlist":           r.get("playlist_name") or "Unknown",
            "days_on":            int(r["days_on"]),
            "removed":            r["date_removed"].strftime("%Y-%m-%d"),
            "added":              r["date_added"].strftime("%Y-%m-%d") if pd.notna(r["date_added"]) else None,
            "chart_peak":         int(ch["chart_peak"])       if ch else None,
            "chart_weeks":        int(ch["total_weeks"])      if ch else None,
            "chart_peak_date":    ch["peak_date"]             if ch else None,
            "chart_last_charted": ch["last_charted"]          if ch else None,
            "max_streams_week":   int(ch["max_streams_week"]) if ch else None,
        })
    return {"tracks": results, "total": int(len(forgotten))}


@router.get("/api/time-capsule")
def time_capsule(era: str = "2010s", limit: int = 20):
    tracks_df   = _load_computed("processed/editorial_playlist_tracks.parquet")
    playlist_df = _load_computed("processed/editorial_playlists.parquet")
    if tracks_df is None:
        raise HTTPException(503, detail="not_ready")

    era_clean = era.strip().lower()
    y_min: Optional[int] = None
    y_max: Optional[int] = None

    if era_clean in _ERA_MAP:
        y_min, y_max = _ERA_MAP[era_clean]
    elif re.fullmatch(r"\d{4}", era_clean):
        y = int(era_clean)
        y_min, y_max = y, y
    else:
        if playlist_df is not None:
            pl_match = playlist_df[playlist_df["name"].str.lower().str.contains(era_clean, na=False)]
            if not pl_match.empty:
                matched_ids = set(pl_match["playlist_id"].tolist())
                df = tracks_df.copy()
                df["date_added"] = pd.to_datetime(df["date_added"], errors="coerce")
                df = df[df["date_added"].notna() & df["playlist_id"].isin(matched_ids)]
                df = _drop_nonmusic_by_playlist(df, playlist_df)
                return _time_capsule_response(era, df, y_min, y_max, "editorial")
        raise HTTPException(400, detail=f"era_not_recognised: {era}")

    df = tracks_df.copy()
    df["date_added"] = pd.to_datetime(df["date_added"], errors="coerce")
    df = df[df["date_added"].notna()]
    if y_min is not None:
        df = df[(df["date_added"].dt.year >= y_min) & (df["date_added"].dt.year <= y_max)]
    df = _drop_nonmusic_by_playlist(df, playlist_df)

    if not df.empty:
        return _time_capsule_response(era, df, y_min, y_max, "editorial")

    era_df = _load_computed("computed/era_tracks.parquet")
    if era_df is None:
        raise HTTPException(503, detail="era_tracks_not_ready")

    sub = era_df[era_df["release_year"].notna()].copy()
    sub["release_year"] = sub["release_year"].astype(int)
    sub = sub[sub["release_year"] >= 1940]
    sub = _music_only(sub)
    if y_min is not None:
        sub = sub[(sub["release_year"] >= y_min) & (sub["release_year"] <= y_max)]

    if sub.empty:
        raise HTTPException(404, detail="no_tracks_found_for_era")

    sub        = sub.sort_values("playlist_count", ascending=False)
    top_tracks = sub.head(limit)
    top_artists = (
        sub.groupby("artist_name")["playlist_count"]
        .agg(track_appearances="sum", unique_tracks="count")
        .reset_index()
        .sort_values("track_appearances", ascending=False)
        .head(10)
    )
    year_dist = (
        sub.groupby("release_year").size()
        .reset_index(name="count")
        .rename(columns={"release_year": "year"})
        .sort_values("year")
    )

    return {
        "era":         era,
        "track_count": int(len(sub)),
        "data_source": "release_year",
        "date_range":  {"min": str(int(sub["release_year"].min())), "max": str(int(sub["release_year"].max()))},
        "top_tracks": [
            {"title": r["track_name"], "artist": r["artist_name"], "appearances": int(r["playlist_count"])}
            for _, r in top_tracks.iterrows()
        ],
        "top_artists": [
            {"name": r["artist_name"], "track_appearances": int(r["track_appearances"]), "unique_tracks": int(r["unique_tracks"])}
            for _, r in top_artists.iterrows()
        ],
        "year_distribution": [
            {"year": int(r["year"]), "count": int(r["count"])}
            for _, r in year_dist.iterrows()
        ],
        "chart_number_ones": _era_chart_ones(y_min, y_max),
    }


def _era_chart_ones(y_min: Optional[int], y_max: Optional[int]) -> list:
    ch_df = _load_computed("enrichment/chart_history.parquet")
    if ch_df is None or y_min is None:
        return []
    ch_df = ch_df.copy()
    ch_df["peak_year"] = pd.to_datetime(ch_df["peak_date"], errors="coerce").dt.year
    era_ch = ch_df[
        (ch_df["chart_peak"] == 1) &
        (ch_df["peak_year"] >= y_min) &
        (ch_df["peak_year"] <= y_max)
    ].sort_values("max_streams_week", ascending=False)
    return [
        {
            "title":            r["track_name"],
            "artist":           r["artist_name"],
            "peak_date":        r["peak_date"],
            "total_weeks":      int(r["total_weeks"]),
            "max_streams_week": int(r["max_streams_week"]),
        }
        for _, r in era_ch.head(10).iterrows()
    ]


def _time_capsule_response(era: str, df: pd.DataFrame,
                            y_min: Optional[int], y_max: Optional[int],
                            source: str) -> dict:
    top_tracks = (
        df.groupby(["track_name", "artist_name"])
        .size().reset_index(name="appearances")
        .sort_values("appearances", ascending=False)
        .head(20)
    )
    top_artists = (
        df.groupby("artist_name")
        .agg(track_appearances=("track_name", "count"), unique_tracks=("track_name", "nunique"))
        .reset_index()
        .sort_values("track_appearances", ascending=False)
        .head(10)
    )
    year_counts = (
        df.groupby(df["date_added"].dt.year).size()
        .reset_index(name="count")
        .rename(columns={"date_added": "year"})
    )
    return {
        "era":         era,
        "track_count": int(len(df)),
        "data_source": source,
        "date_range":  {"min": str(df["date_added"].min().date()), "max": str(df["date_added"].max().date())},
        "top_tracks": [
            {"title": r["track_name"], "artist": r["artist_name"], "appearances": int(r["appearances"])}
            for _, r in top_tracks.iterrows()
        ],
        "top_artists": [
            {"name": r["artist_name"], "track_appearances": int(r["track_appearances"]), "unique_tracks": int(r["unique_tracks"])}
            for _, r in top_artists.iterrows()
        ],
        "year_distribution": [
            {"year": int(r["year"]), "count": int(r["count"])}
            for _, r in year_counts.iterrows()
        ],
        "chart_number_ones": _era_chart_ones(y_min, y_max),
    }


@router.get("/api/mood-contradiction")
def mood_contradiction(mood: str = "sad", limit: int = 20):
    playlist_df = _load_computed("processed/editorial_playlists.parquet")  # small (~5 MB)
    ept_path    = local_parquet("processed/editorial_playlist_tracks.parquet")
    if playlist_df is None or ept_path is None:
        raise HTTPException(503, detail="not_ready")

    mood_clean = mood.strip().lower()
    contrary_keywords = _MOOD_PAIRS.get(mood_clean)
    if contrary_keywords is None:
        contrary_keywords = ["party", "hype", "gym"] if "sad" in mood_clean else ["sad", "cry", "heartbreak"]

    pl = playlist_df.copy()
    pl["name_lower"] = pl["name"].str.lower().fillna("")
    pl["is_mood"]     = pl["name_lower"].str.contains(mood_clean, regex=False, na=False)
    pl["is_contrary"] = pl["name_lower"].str.contains("|".join(contrary_keywords), regex=True, na=False)

    mood_ids     = set(pl[pl["is_mood"]]["playlist_id"].tolist())
    contrary_ids = set(pl[pl["is_contrary"]]["playlist_id"].tolist())

    if not mood_ids:
        raise HTTPException(404, detail=f"no_playlists_found_for_mood: {mood}")

    # Count appearances in mood vs contrary playlists in one DuckDB pass over the
    # local editorial-track parquet — only the small ranked result is materialised.
    mrel = f"mood_pids_{id(mood_ids)}"
    crel = f"contrary_pids_{id(contrary_ids)}"
    con.register(mrel, pd.DataFrame({"pid": list(mood_ids)}))
    con.register(crel, pd.DataFrame({"pid": list(contrary_ids)}))
    try:
        merged = con.execute(f"""
            WITH e AS (
                SELECT track_name, artist_name, playlist_id
                FROM read_parquet('{ept_path.as_posix()}')
                WHERE playlist_id IN (SELECT pid FROM {mrel})
                   OR playlist_id IN (SELECT pid FROM {crel})
            )
            SELECT track_name, artist_name,
                sum(CASE WHEN playlist_id IN (SELECT pid FROM {mrel}) THEN 1 ELSE 0 END) AS mood_appearances,
                sum(CASE WHEN playlist_id IN (SELECT pid FROM {crel}) THEN 1 ELSE 0 END) AS contrary_appearances
            FROM e
            GROUP BY track_name, artist_name
            HAVING mood_appearances > 0 AND contrary_appearances > 0
            ORDER BY contrary_appearances DESC
            LIMIT {int(limit)}
        """).df()
    finally:
        con.unregister(mrel)
        con.unregister(crel)

    merged["contradiction_score"] = (
        merged["contrary_appearances"] / merged["mood_appearances"].clip(lower=1)
    ).round(3)

    return {
        "mood":               mood_clean,
        "contrary_moods":     contrary_keywords[:4],
        "mood_playlists":     len(mood_ids),
        "contrary_playlists": len(contrary_ids),
        "tracks": [
            {
                "title":               r["track_name"],
                "artist":              r["artist_name"],
                "mood_appearances":     int(r["mood_appearances"]),
                "contrary_appearances": int(r["contrary_appearances"]),
                "contradiction_score":  float(r["contradiction_score"]),
            }
            for _, r in merged.iterrows()
        ],
    }
