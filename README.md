---
title: Music Intelligence Atlas API
emoji: 🎵
colorFrom: green
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Music Intelligence Atlas

A cultural map of playlists — artist footprints, song passports, title language,
taste routes, and editorial afterlives. Built on ~1M playlists / 3.6M tracks.

- **Frontend:** React + Vite (deployed on Vercel)
- **Backend:** FastAPI (this repo → deployed as a Hugging Face Docker Space)
- **Data:** Cloudflare R2 (parquet artifacts + FAISS index), read at runtime
- **LLM:** Groq free API (soundtrack-gift), with a keyword fallback

> The YAML block above is Hugging Face Space metadata; it configures the Docker
> Space (port 7860). It's harmless on GitHub.

## Layout
- `src/app/` — FastAPI app + routes (serving layer, reads precomputed R2 data)
- `src/compute/`, `src/ingestion/` — **offline** pipelines (embeddings, ISRC
  enrichment, clustering); not run by the API
- `src/storage/` — R2 + DuckDB clients
- `frontend/` — Vite React app
- `Dockerfile` + `requirements-api.txt` — slim serving image (no torch/transformers)

## Deploy
See [`docs/huggingface-space.md`](docs/huggingface-space.md) for the backend (HF Space)
and Vercel frontend wiring. Compute jobs run locally / via GitHub Actions and
push results to R2; the API only reads.

## Local dev
```bash
# backend
uvicorn src.app.main:app --reload --port 8000
# frontend
cd frontend && npm install && npm run dev
```
Requires a `.env` with `R2_*` keys (see `.env.example`).

## Local validation

Run the production-shaped checks with one command:

```bash
./deploy/validate_local.sh
```

The validator uses `.venv`, starts the API if necessary, waits until its R2
artifacts report ready, then runs all Python tests, Python compilation, frontend
lint, and the frontend production build. If credentials or artifacts are
unavailable, it exits with one readiness error instead of cascading smoke-test
connection failures.

## Serving coverage and fallbacks

The serving layer keeps the canonical R2 dataset intact and uses bounded,
disk-backed fallbacks on small hosts:

- Track autocomplete searches the 599K embedding vocabulary first, then a
  SQLite FTS5 index containing all 2.26M searchable tracks.
- Artist Ubiquity serves rich detail for the top 10K artists and exact rank /
  playlist reach for the full artist table from a slim precomputed lookup.
- Doppelganger and Transition fetch long-tail query vectors from an idx-sorted
  R2 Parquet lookup. Upstash remains the fast 10K candidate index.
- Artist images use the cached 10K artifact, optionally try Spotify when
  credentials exist, and otherwise return explicit placeholder metadata.

After source data or embeddings change, publish the new serving artifacts:

```bash
DUCKDB_MEMORY_LIMIT=1GB python -m src.compute.export_lookup_artifacts \
  --only artist_ubiquity track_search vector_lookup
```

The command writes new derived artifacts and does not alter the canonical
playlist, track, or enrichment tables. The full track index and vector lookup
are intentionally lazy on the API host so popular demo queries do not pay their
download cost.

## Operations

- `GET /health` is the liveness check.
- `GET /ready` reports background warmup state.
- `GET /api/capabilities` describes fast-path and fallback coverage.
- `GET /api/ops` returns process-local, anonymous route/latency/coverage
  counters. Query values, IP addresses, and headers are never retained.

The 512 MB deployment warms its small critical lookups sequentially, allows at
most four in-flight requests, serializes DuckDB work, and returns `503` with a
`Retry-After` header instead of building an unbounded queue.
