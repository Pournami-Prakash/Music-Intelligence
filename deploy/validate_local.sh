#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
ATLAS_TEST_PORT="${ATLAS_TEST_PORT:-8000}"
BASE_URL="http://127.0.0.1:${ATLAS_TEST_PORT}"
SERVER_PID=""
SERVER_LOG=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$SERVER_LOG" && -f "$SERVER_LOG" ]]; then
    rm -f "$SERVER_LOG"
  fi
}
trap cleanup EXIT

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python environment not found at $PYTHON_BIN." >&2
  echo "Create .venv and install requirements-api.txt plus pytest." >&2
  exit 2
fi

cd "$ROOT_DIR"

if ! curl --fail --silent --show-error "$BASE_URL/health" >/dev/null 2>&1; then
  SERVER_LOG="$(mktemp -t music-atlas-validation.XXXXXX)"
  "$PYTHON_BIN" -m uvicorn src.app.main:app \
    --host 127.0.0.1 \
    --port "$ATLAS_TEST_PORT" \
    >"$SERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  echo "Started validation API (pid $SERVER_PID); waiting for R2 artifacts."
else
  echo "Using existing API at $BASE_URL."
fi

READY_STATE=""
for _ in {1..120}; do
  READY_STATE="$(
    curl --fail --silent "$BASE_URL/ready" 2>/dev/null |
      "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))' 2>/dev/null ||
      true
  )"
  if [[ "$READY_STATE" == "ready" ]]; then
    break
  fi
  if [[ "$READY_STATE" == "degraded" ]]; then
    echo "API warmup is degraded; data-backed validation cannot run." >&2
    if [[ -n "$SERVER_LOG" ]]; then
      tail -n 30 "$SERVER_LOG" >&2
    fi
    exit 3
  fi
  sleep 1
done

if [[ "$READY_STATE" != "ready" ]]; then
  echo "API did not become data-ready within 120 seconds (state=$READY_STATE)." >&2
  if [[ -n "$SERVER_LOG" ]]; then
    tail -n 30 "$SERVER_LOG" >&2
  fi
  exit 3
fi

echo "API ready. Running the complete validation."
env -u ENABLE_LEGACY_HEAVY_ENDPOINTS \
  BASE_URL="$BASE_URL" \
  "$PYTHON_BIN" -m pytest -q src/tests
"$PYTHON_BIN" -m compileall -q src
(
  cd frontend
  npm run lint
  npm run build
)
