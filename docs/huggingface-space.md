# Hugging Face Space — backend deployment

Zero-dollar deployment target for the stateless API. Free **CPU Basic** Space
(2 vCPU, 16 GB RAM, 50 GB ephemeral disk) — comfortably more than the app needs.

```text
Vercel frontend ──▶ Hugging Face Docker Space ──▶ Cloudflare R2 (parquets)
                              │
                              ├─▶ Upstash Vector (doppelganger / transition / search)
                              └─▶ Groq free API (/api/soundtrack-gift)
```

The Space serves only precomputed R2 artifacts (read-only, stateless). It
downloads the lookup parquets from R2 to local disk on first use — never run
compute jobs on the Space.

## 1. Create the Space

1. New Space → SDK **Docker** → **CPU Basic** (free) → public.
2. It builds the root `Dockerfile` (already HF-ready: `README.md` frontmatter
   sets `sdk: docker`, `app_port: 7860`; the app listens on `7860`).
3. Push this repo to the Space's git remote:

   ```bash
   git remote add space https://huggingface.co/spaces/<owner>/<space-name>
   git push space main
   # if the Space was created with an initial commit:
   #   git push space main --force
   ```

   Auth uses an HF access token (Settings → Access Tokens, write scope) as the
   git password, or `huggingface-cli login`.

`.dockerignore` keeps `.env`, `data/`, venvs, logs, and frontend build artifacts
out of the build context. The image installs `requirements-api.txt` (runtime
only); `requirements.txt` is for local compute jobs.

## 2. Space secrets (Settings → Variables and secrets)

**Required** — data + core features:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
UPSTASH_VECTOR_REST_URL
UPSTASH_VECTOR_REST_TOKEN
GROQ_API_KEY
```

**Recommended:**

```text
FRONTEND_URL=https://<your-vercel-app>.vercel.app     # CORS allow-origin
```

**Optional** (features degrade gracefully without them):

```text
R2_ENDPOINT=...                     # only if not the default *.r2.cloudflarestorage.com
SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET   # live artist images; else cached artist_images.parquet
GROQ_MODEL=llama-3.1-8b-instant
```

**Tuning** — the `DUCKDB_*` defaults are deliberately tight for a 512 MB box.
On the 16 GB Space you can relax them for faster queries (optional):

```text
DUCKDB_MEMORY_LIMIT=512MB   # default 96MB; higher = faster, less spilling
DUCKDB_THREADS=2            # default 1
# SKIP_STARTUP_WARMUP unset → pre-load small artifacts on boot (faster first hit)
```

The concurrency semaphore, result cache, jemalloc, and graceful degradation stay
on — they cost nothing and still help under bursts.

## 3–6. Deploy order

3. **Backend:** push → wait for the Space to build → smoke-test the public URL:

   ```bash
   BASE_URL=https://<owner>-<space-name>.hf.space \
     python -m pytest src/tests/test_smoke.py src/tests/test_rcache.py -q
   ```

4. **Moderate traffic check** (NOT the 512 MB torture test — the Space has 16 GB):

   ```bash
   python deploy/loadtest.py --base https://<owner>-<space-name>.hf.space --concurrency 3 --count 150
   ```

5. **Frontend:** set the Vercel env var and redeploy, then browser-check end to end:

   ```text
   VITE_API_BASE_URL=https://<owner>-<space-name>.hf.space
   ```

   Then set the Space's `FRONTEND_URL` to the Vercel URL (CORS) and restart it.

6. **Wake-from-sleep:** free Spaces sleep after ~48 h idle. The first request
   after sleeping cold-starts and re-downloads parquets from R2 (a few seconds).
   Hit the Space once before a demo to warm it. Ephemeral disk is fine — the
   parquets restore from R2 automatically.

## Known limitation

Upstash Vector holds the top ~10K most-popular tracks (free-tier write cap), so
doppelganger / transition / search return empty for the obscure long tail. This
is a product limitation, not a bug — see project memory.
