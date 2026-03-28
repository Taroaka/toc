#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.commandmate"
LOG_PATH="${STATE_DIR}/pinggy.log"
URL_PATH="${STATE_DIR}/pinggy-urls.txt"
SESSION_NAME="commandmate-pinggy"

mkdir -p "$STATE_DIR"

"$SCRIPT_DIR/commandmate-start-lan-http.sh" >/dev/null

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Pinggy tunnel already running"
  "$SCRIPT_DIR/commandmate-pinggy-info.sh"
  exit 0
fi

rm -f "$LOG_PATH" "$URL_PATH"

tmux new-session -d -s "$SESSION_NAME" \
  "ssh -tt -p 443 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R0:localhost:3101 a.pinggy.io"

for _ in $(seq 1 20); do
  tmux capture-pane -t "$SESSION_NAME" -p >"$LOG_PATH" 2>/dev/null || true
  if grep -Eo 'https?://[^[:space:]]+' "$LOG_PATH" | grep 'free.pinggy.link' >"$URL_PATH" 2>/dev/null; then
    break
  fi
  sleep 1
done

echo "Pinggy tunnel started"
"$SCRIPT_DIR/commandmate-pinggy-info.sh"
