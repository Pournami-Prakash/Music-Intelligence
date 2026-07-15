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