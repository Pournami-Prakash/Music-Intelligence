#!/usr/bin/env bash
# One-shot Linux memory load test: starts the image detached under a hard memory
# limit, drives mixed load at concurrency 1/2/5/10 + a soak, then reports the
# cgroup's own authoritative memory figures. Assumes `docker build -t atlas-api .`
# and .env exist.
#
#   MEM=512m bash deploy/run_512_test.sh      # default 512m; set MEM=1g etc.
#
# Correctness notes (why this is trustworthy):
#  * Liveness is checked with .State.Running, NOT container existence — a -d
#    container without --rm still "exists" (exited) after an OOM, so an
#    existence check reports false "alive".
#  * Peak comes from cgroup v2 memory.peak (a monotonic high-water mark), so it
#    cannot miss a transient spike between samples — unlike sampling MemUsage.
#  * OOM is read from memory.events (oom_kill count) + .State.OOMKilled, not
#    inferred from connection resets.
#  * anon vs file (reclaimable page cache) is read from memory.stat.
set -uo pipefail
cd "$(dirname "$0")/.."

NAME=atlas
BASE=http://localhost:7860
MEM="${MEM:-512m}"
STATS=/tmp/atlas_mem_stats.txt          # rolling: peak_bytes current_bytes anon_bytes file_bytes

running() { [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; }

# Read cgroup memory facts from inside the container (Docker Desktop runs a Linux
# VM, so the cgroup isn't on the mac host — exec is the portable way). cgroup v2
# first, v1 fallback. Emits: "<peak> <current> <anon> <file>" in bytes, or nothing.
cg() {
  docker exec "$NAME" sh -c '
    if [ -f /sys/fs/cgroup/memory.peak ]; then
      P=$(cat /sys/fs/cgroup/memory.peak 2>/dev/null)
      C=$(cat /sys/fs/cgroup/memory.current 2>/dev/null)
      A=$(awk "/^anon /{print \$2}" /sys/fs/cgroup/memory.stat 2>/dev/null)
      F=$(awk "/^file /{print \$2}" /sys/fs/cgroup/memory.stat 2>/dev/null)
    else
      P=$(cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes 2>/dev/null)
      C=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null)
      A=$(awk "/^rss /{print \$2}" /sys/fs/cgroup/memory/memory.stat 2>/dev/null)
      F=$(awk "/^cache /{print \$2}" /sys/fs/cgroup/memory/memory.stat 2>/dev/null)
    fi
    echo "${P:-0} ${C:-0} ${A:-0} ${F:-0}"
  ' 2>/dev/null
}

oom_kills() {
  docker exec "$NAME" sh -c 'awk "/^oom_kill /{print \$2}" /sys/fs/cgroup/memory.events 2>/dev/null || echo 0' 2>/dev/null
}

mib() { awk -v b="${1:-0}" 'BEGIN{printf "%.0f", b/1048576}'; }

echo "→ (re)starting container under --memory=$MEM"
docker rm -f "$NAME" >/dev/null 2>&1 || true
: > "$STATS"
docker run -d --name "$NAME" \
  --memory="$MEM" --memory-swap="$MEM" \
  --env-file .env \
  -e SKIP_STARTUP_WARMUP=1 \
  -p 7860:7860 \
  atlas-api >/dev/null

echo -n "→ waiting for /health "
for _ in $(seq 1 60); do
  if curl -sf "$BASE/health" -o /dev/null 2>&1; then echo " up"; break; fi
  if ! running; then echo " CONTAINER NOT RUNNING before ready"; docker logs "$NAME" 2>&1 | tail; exit 1; fi
  echo -n "."; sleep 1
done
docker logs "$NAME" 2>&1 | grep -i "LD_PRELOAD" || echo "  (no LD_PRELOAD line — jemalloc may not be active)"

# Background sampler: append the cgroup line each second while the container runs.
( while running; do cg; sleep 1; done ) >> "$STATS" & SAMPLER=$!

peak_mib()    { awk '{if($1>m)m=$1}END{printf "%.0f", m/1048576}' "$STATS" 2>/dev/null; }
last_anon()   { awk 'END{printf "%.0f", $3/1048576}' "$STATS" 2>/dev/null; }
last_file()   { awk 'END{printf "%.0f", $4/1048576}' "$STATS" 2>/dev/null; }

run_level() {  # concurrency, args...
  if ! running; then echo "‼ container not running before this level — skipping"; return 1; fi
  python deploy/loadtest.py --base "$BASE" "$@"
  echo "   cgroup peak so far: $(peak_mib) MiB   running: $(running && echo yes || echo NO)"
}

echo "→ warm-up (concurrency 1, 80)"
run_level 1 --concurrency 1 --count 80 || true
for C in 1 2 5 10; do
  echo "=== concurrency $C ==="
  run_level "$C" --concurrency "$C" --count 300 || break
done
if running; then
  echo "=== soak 5 min @ concurrency 5 ==="
  run_level 5 --concurrency 5 --duration 300 || true
fi

kill "$SAMPLER" 2>/dev/null || true

# Final authoritative numbers (read live if still running; else last sample + inspect).
OOM_EVENTS="$(running && oom_kills || echo '?')"
echo
echo "──────── VERDICT (MEM=$MEM) ────────"
echo "cgroup memory.peak : $(peak_mib) MiB   (monotonic high-water — no sampling miss)"
echo "anon / file (last) : $(last_anon) MiB real / $(last_file) MiB reclaimable cache"
echo "OOMKilled          : $(docker inspect -f '{{.State.OOMKilled}}' "$NAME" 2>/dev/null || echo '?')"
echo "memory.events oom  : ${OOM_EVENTS:-?}"
echo "state              : $(docker inspect -f '{{.State.Status}} (exit {{.State.ExitCode}})' "$NAME" 2>/dev/null || echo n/a)"
echo "─────────────────────────────────────"
echo "PASS requires: OOMKilled=false, oom=0, and peak with real headroom under the limit."
echo "(container left for inspection; 'docker rm -f $NAME' to remove)"
