#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HOME}/.toc-runtime"
PID_FILE="${RUNTIME_DIR}/weekend-keepawake.pid"

mkdir -p "$RUNTIME_DIR"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    echo "Weekend keep-awake is already running (PID: $PID)"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

nohup caffeinate -dimsu >/dev/null 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

echo "Weekend keep-awake started"
echo "  PID: $PID"
echo "  PID file: $PID_FILE"
