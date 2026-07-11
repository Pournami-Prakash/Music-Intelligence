# Music Intelligence Atlas — Frontend

React + Vite frontend for the Music Intelligence Atlas API.

## Dev setup

```bash
npm install
npm run dev        # starts on http://localhost:5173
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.js`),
so the backend needs to be running locally first.

## Production build

```bash
npm run build      # outputs to dist/
```

Deployed on Vercel. The `vercel.json` rewrites `/api/*` to the production API at
`https://api.pournamiprakash.dev`, so no environment variables are needed in the build.
