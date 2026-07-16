#!/bin/bash
# Precompute the snapshot endpoints → frontend/public/data/*.json.
# These pages are then served statically by Vercel (no backend hit, no big
# parquet loaded server-side). Re-run after a data refresh, then redeploy the
# frontend.
#
# Usage:  API=http://localhost:8000 bash deploy/build_static_data.sh
set -euo pipefail

API="${API:-http://localhost:8000}"
OUT="frontend/public/data"
mkdir -p "$OUT"

fetch() {  # fetch <url-path> <outfile>
  echo "  $2"
  curl -sf --max-time 90 "$API$1" -o "$OUT/$2"
}

# mood-contradiction is a heavy GROUP BY gated off in prod — the backend must run
# with ENABLE_LEGACY_HEAVY_ENDPOINTS=1 and ample memory (e.g. DUCKDB_MEMORY_LIMIT=1GB)
# for this to succeed. The 5 predefined moods are combined into one keyed file.
echo "  mood-contradiction.json"
python3 - "$API" "$OUT" <<'PY'
import json, sys, urllib.request, urllib.error
api, out = sys.argv[1], sys.argv[2]
res = {}
for m in ["sad", "angry", "heartbreak", "anxious", "lonely"]:
    try:
        with urllib.request.urlopen(f"{api}/api/mood-contradiction?mood={m}&limit=12", timeout=90) as r:
            res[m] = json.load(r)
    except urllib.error.HTTPError:
        res[m] = {"mood": m, "contrary_moods": [], "mood_playlists": 0, "contrary_playlists": 0, "tracks": []}
with open(f"{out}/mood-contradiction.json", "w") as f:
    json.dump(res, f, ensure_ascii=False)
PY

fetch "/api/mood-map/clusters"          "mood-map.json"
fetch "/api/genre-weather/regions"      "genre-weather.json"
fetch "/api/playlist-language?limit=80" "playlist-language.json"
fetch "/api/editorial-graveyard"        "editorial-graveyard.json"
fetch "/api/forgotten-hits"             "forgotten-hits.json"
for era in 1960s 1970s 1980s 1990s 2000s 2010s 2020s; do
  fetch "/api/time-capsule?era=$era&limit=20" "time-capsule-$era.json"
done

echo "done → $OUT"
du -sh "$OUT"