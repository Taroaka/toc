#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HOME}/.toc-runtime"
PID_FILE="${RUNTIME_DIR}/weekend-keepawake.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Weekend keep-awake is not running"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped weekend keep-awake (PID: $PID)"
else
  echo "Weekend keep-awake PID was stale"
fi

rm -f "$PID_FILE"
