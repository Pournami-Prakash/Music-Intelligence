# Hugging Face Space Backend

This is the zero-dollar deployment target for the stateless API:

```text
Vercel frontend -> Hugging Face Docker Space -> Cloudflare R2
                                      |
                                      +-> Groq free API for /api/soundtrack-gift
```

The Space should only serve precomputed R2 artifacts. Do not run compute jobs on
the Space.

## Create The Space

1. Create a new Hugging Face Space.
2. Select `Docker` as the SDK.
3. Push this repo. Hugging Face will build the root `Dockerfile`.
4. The app listens on port `7860`.

The root `.dockerignore` excludes local secrets, virtualenvs, local data, logs,
and frontend build artifacts from the Docker build context.

The Docker image installs `requirements-api.txt`, a runtime-only dependency set.
Use `requirements.txt` for local compute/enrichment jobs.

## Space Secrets

Set these as Hugging Face Space secrets:

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_ENDPOINT
FRONTEND_URL
GROQ_API_KEY
```

Optional variables:

```text
GROQ_MODEL=llama-3.1-8b-instant
SKIP_STARTUP_WARMUP=1
```

`SKIP_STARTUP_WARMUP=1` is recommended on free Spaces so cold starts do not
eagerly load FAISS and several parquet artifacts. Endpoints still load data on
demand through the normal cache path.

## Vercel Frontend

Set this Vercel environment variable to the Space URL:

```text
VITE_API_BASE_URL=https://<space-owner>-<space-name>.hf.space
```

Local development can leave `VITE_API_BASE_URL` unset; Vite will continue to
proxy `/api/*` to `http://localhost:8000`.

## Compute

Run compute locally or in GitHub Actions cron, then upload outputs to R2. The
hosted API should remain read-only and stateless.
