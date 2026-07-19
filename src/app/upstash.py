"""
Thin Upstash Vector REST client (uses `requests`, no extra SDK).

Replaces the in-process 393 MB FAISS index: track2vec vectors live in Upstash,
and the API fetches/queries them over HTTP. Vector ids are the string form of
the vocab `idx` (== FAISS position). Metadata per vector: {uri, title, artist}.
"""
import os
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")


def _clean_env(name: str) -> str:
    """Read an env var, stripping whitespace and surrounding quotes.

    Docker's `--env-file` (unlike python-dotenv) keeps quotes as part of the
    value, so `UPSTASH_VECTOR_REST_URL="https://…"` would otherwise yield a URL
    with literal quotes and break the request scheme.
    """
    v = os.environ.get(name, "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


_URL   = _clean_env("UPSTASH_VECTOR_REST_URL").rstrip("/")
_TOKEN = _clean_env("UPSTASH_VECTOR_REST_TOKEN")
_session = requests.Session()


def upstash_ready() -> bool:
    return bool(_URL and _TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"}


def upstash_fetch_vectors(ids: list[str], timeout: int = 20) -> dict[str, np.ndarray]:
    """Fetch vectors by id → {id: np.ndarray(float32)}."""
    if not ids:
        return {}
    r = _session.post(f"{_URL}/fetch",
                      json={"ids": list(ids), "includeVectors": True},
                      headers=_headers(), timeout=timeout)
    r.raise_for_status()
    out: dict[str, np.ndarray] = {}
    for item in (r.json().get("result") or []):
        if item and item.get("vector") is not None:
            out[str(item["id"])] = np.asarray(item["vector"], dtype="float32")
    return out


def upstash_query(vector, top_k: int = 100, timeout: int = 20) -> list[dict]:
    """Nearest-neighbour query → list of {id, score, metadata}."""
    v = vector.tolist() if hasattr(vector, "tolist") else list(vector)
    r = _session.post(f"{_URL}/query",
                      json={"vector": v, "topK": top_k, "includeMetadata": True},
                      headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json().get("result") or []
