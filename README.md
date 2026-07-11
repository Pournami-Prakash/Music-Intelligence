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
