#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${HOME}/.commandmate"
URL_PATH="${STATE_DIR}/pinggy-urls.txt"
LOG_PATH="${STATE_DIR}/pinggy.log"
TOKEN_PATH="${STATE_DIR}/last-auth-token.txt"
SESSION_NAME="commandmate-pinggy"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Pinggy"
  echo "  running via tmux session: ${SESSION_NAME}"
  tmux capture-pane -t "$SESSION_NAME" -p >"$LOG_PATH" 2>/dev/null || true
else
  echo "Pinggy"
  echo "  stopped"
fi

if [ -f "$URL_PATH" ]; then
  echo "URLs"
  grep 'free.pinggy.link' "$URL_PATH" | while IFS= read -r url; do
    echo "$url"
    echo "${url}/login"
  done
fi

if [ -f "$TOKEN_PATH" ]; then
  echo "Token"
  cat "$TOKEN_PATH"
fi

if [ -f "$LOG_PATH" ]; then
  echo "Log"
  echo "  $LOG_PATH"
fi
