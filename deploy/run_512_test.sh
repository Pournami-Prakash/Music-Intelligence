#!/usr/bin/env bash
# One-shot Linux 512 MB load test: starts the image detached under a hard 512 MB
# limit, samples RSS in the background, runs the mixed load at concurrency
# 1/2/5/10 + a soak, then prints peak RSS and the OOM verdict. No multi-terminal
# juggling. Assumes `docker build -t atlas-api .` has been run and .env exists.
#
#   bash deploy/run_512_test.sh
set -uo pipefail
cd "$(dirname "$0")/.."

NAME=atlas
BASE=http://localhost:7860
SAMPLES=/tmp/atlas_rss_samples.txt

echo "→ (re)starting container under --memory=512m"
docker rm -f "$NAME" >/dev/null 2>&1 || true
: > "$SAMPLES"
docker run -d --name "$NAME" \
  --memory=512m --memory-swap=512m \
  --env-file .env \
  -e SKIP_STARTUP_WARMUP=1 \
  -p 7860:7860 \
  atlas-api >/dev/null

echo -n "→ waiting for /health "
for _ in $(seq 1 60); do
  if curl -sf "$BASE/health" -o /dev/null 2>&1; then echo " up"; break; fi
  if ! docker inspect "$NAME" >/dev/null 2>&1; then echo " CONTAINER DIED before ready"; docker logs "$NAME" 2>&1 | tail; exit 1; fi
  echo -n "."; sleep 1
done
docker logs "$NAME" 2>&1 | grep -i "LD_PRELOAD" || echo "  (no LD_PRELOAD line — jemalloc may not be active)"

# Background RSS sampler → file (MiB numbers only)
( while docker inspect "$NAME" >/dev/null 2>&1; do
    docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | awk '{gsub(/MiB.*/,"",$1); print $1}'
    sleep 1
  done ) & SAMPLER=$!

peak() { sort -n "$SAMPLES" 2>/dev/null | tail -1; }

echo "→ warm-up (concurrency 1, 80)"
python deploy/loadtest.py --base "$BASE" --concurrency 1 --count 80
echo "   peak so far: $(peak) MiB   alive: $(docker inspect "$NAME" >/dev/null 2>&1 && echo yes || echo NO)"

for C in 1 2 5 10; do
  if ! docker inspect "$NAME" >/dev/null 2>&1; then echo "‼ container died before c$C"; break; fi
  echo "=== concurrency $C ==="
  python deploy/loadtest.py --base "$BASE" --concurrency "$C" --count 300
  echo "   peak so far: $(peak) MiB"
done

if docker inspect "$NAME" >/dev/null 2>&1; then
  echo "=== soak 5 min @ concurrency 5 ==="
  python deploy/loadtest.py --base "$BASE" --concurrency 5 --duration 300
fi

kill "$SAMPLER" 2>/dev/null || true
echo
echo "──────── VERDICT ────────"
echo "peak RSS        : $(peak) MiB / 512 MiB"
echo "OOMKilled       : $(docker inspect "$NAME" --format '{{.State.OOMKilled}}' 2>/dev/null || echo 'container gone')"
echo "exit / status   : $(docker inspect "$NAME" --format '{{.State.Status}} (exit {{.State.ExitCode}})' 2>/dev/null || echo n/a)"
echo "─────────────────────────"
echo "(container left running for inspection; 'docker rm -f atlas' to remove)"
