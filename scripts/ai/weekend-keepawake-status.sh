#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${HOME}/.toc-runtime"
PID_FILE="${RUNTIME_DIR}/weekend-keepawake.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Weekend keep-awake: stopped"
  exit 0
fi

PID="$(cat "$PID_FILE" 2>/dev/null || true)"

if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
  echo "Weekend keep-awake: running"
  echo "  PID: $PID"
  echo "  PID file: $PID_FILE"
else
  echo "Weekend keep-awake: stale pid file"
  echo "  PID file: $PID_FILE"
  exit 1
fi
