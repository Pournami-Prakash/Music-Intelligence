"""
Spotify Web API client — Client Credentials flow (no user auth required).

Handles token acquisition and automatic refresh. Exposes helpers for:
  - Audio features (energy, valence, tempo, danceability, etc.)
  - Track/artist search
  - Public playlist fetching
  - Artist metadata (images, genres, popularity)

Usage:
    from src.storage.spotify import SpotifyClient
    sp = SpotifyClient()
    features = sp.audio_features(["spotify:track:...", ...])
    playlist = sp.playlist_tracks("37i9dQZF1DXcBWIGoYBM5M")
"""

import os
import time
import base64
import requests
from typing import Optional


class SpotifyClient:
    _TOKEN_URL = "https://accounts.spotify.com/api/token"
    _API_BASE  = "https://api.spotify.com/v1"

    def __init__(self):
        # Optional: Spotify creds enable LIVE artist images. Without them the API
        # still runs (artist-image falls back to the cached artist_images table),
        # so read leniently instead of crashing the whole app at import time.
        self._client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
        self._client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self._token: Optional[str] = None
        self._token_expiry: float  = 0.0

    def available(self) -> bool:
        return bool(self._client_id and self._client_secret)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        creds = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = requests.post(
            self._TOKEN_URL,
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data["expires_in"]
        return self._token

    def _get(self, path: str, params: dict = None, _retry: int = 0) -> dict:
        token = self._ensure_token()
        resp = requests.get(
            f"{self._API_BASE}/{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=15,
        )
        if resp.status_code == 429 and _retry < 3:
            # Cap wait at 30s — if Spotify wants longer, bail after retries
            wait = min(int(resp.headers.get("Retry-After", 2 ** (_retry + 1))), 30)
            time.sleep(wait)
            return self._get(path, params, _retry + 1)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Audio features
    # ------------------------------------------------------------------

    def audio_features(self, track_uris: list[str]) -> list[dict]:
        """
        Fetch audio features for up to 100 tracks per call.
        Input: list of track URIs or IDs.
        Returns: list of feature dicts (same order, None for missing).
        """
        ids = [u.split(":")[-1] for u in track_uris]
        results = []
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            data = self._get("audio-features", {"ids": ",".join(chunk)})
            results.extend(data.get("audio_features") or [None] * len(chunk))
        return results

    def audio_features_for_id(self, track_id: str) -> Optional[dict]:
        """Single track audio features."""
        data = self._get(f"audio-features/{track_id}")
        return data if data.get("id") else None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_track(self, query: str, limit: int = 5) -> list[dict]:
        data = self._get("search", {"q": query, "type": "track", "limit": min(limit, 10)})
        return data.get("tracks", {}).get("items", [])

    def search_artist(self, query: str, limit: int = 5) -> list[dict]:
        if not self.available():
            return []  # no creds → no live search; callers fall back to cached data
        data = self._get("search", {"q": query, "type": "artist", "limit": min(limit, 10)})
        return data.get("artists", {}).get("items", [])

    # ------------------------------------------------------------------
    # Artist metadata
    # ------------------------------------------------------------------

    def artist(self, artist_id: str) -> dict:
        return self._get(f"artists/{artist_id.split(':')[-1]}")

    # ------------------------------------------------------------------
    # Tracks
    # ------------------------------------------------------------------

    def track(self, track_id: str) -> dict:
        return self._get(f"tracks/{track_id.split(':')[-1]}")

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def playlist_info(self, playlist_id: str) -> dict:
        return self._get(f"playlists/{playlist_id}",
                         {"fields": "id,name,description,public,owner,followers,tracks.total"})

    def playlist_tracks(self, playlist_id: str, limit: int = 100) -> list[dict]:
        """
        Fetch all tracks from a public playlist.
        Returns list of simplified track dicts.
        """
        tracks = []
        offset = 0
        while True:
            data = self._get(
                f"playlists/{playlist_id}/tracks",
                {"limit": min(limit, 100), "offset": offset,
                 "fields": "items(track(id,uri,name,artists,album,duration_ms,popularity)),next"}
            )
            items = data.get("items") or []
            for item in items:
                t = item.get("track")
                if not t or not t.get("id"):
                    continue
                tracks.append({
                    "id":          t["id"],
                    "uri":         t["uri"],
                    "name":        t["name"],
                    "artist":      t["artists"][0]["name"] if t.get("artists") else None,
                    "artist_id":   t["artists"][0]["id"]   if t.get("artists") else None,
                    "album":       t.get("album", {}).get("name"),
                    "duration_ms": t.get("duration_ms"),
                    "popularity":  t.get("popularity"),
                })
            if not data.get("next") or len(tracks) >= limit:
                break
            offset += 100
        return tracks

    # ------------------------------------------------------------------
    # ISRC lookup  — useful for YaMBDa bridge (Phase 3)
    # ------------------------------------------------------------------

    def isrc_for_track(self, track_name: str, artist_name: str) -> Optional[str]:
        """Search for a track and return its ISRC if found."""
        query = f"track:{track_name} artist:{artist_name}"
        results = self.search_track(query, limit=1)
        if not results:
            return None
        ext = results[0].get("external_ids") or {}
        return ext.get("isrc")
