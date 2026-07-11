# Music Intelligence Atlas — Frontend

React + Vite frontend for the Music Intelligence Atlas API.

## Dev setup

```bash
npm install
npm run dev        # starts on http://localhost:5173
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` when
`VITE_API_BASE_URL` is unset, so the backend needs to be running locally first.

## Production build

```bash
npm run build      # outputs to dist/
```

For the hosted backend, set this in Vercel:

```bash
VITE_API_BASE_URL=https://<space-owner>-<space-name>.hf.space
```

When `VITE_API_BASE_URL` is set, frontend API calls go directly to that backend.
