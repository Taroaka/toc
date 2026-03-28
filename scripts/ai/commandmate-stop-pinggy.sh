#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="commandmate-pinggy"

if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Pinggy tunnel is not running"
  exit 0
fi

tmux kill-session -t "$SESSION_NAME"
echo "Pinggy tunnel stopped"
