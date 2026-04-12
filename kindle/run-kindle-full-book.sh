#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./kindle/run-kindle-full-book.sh [options]

What it does:
  - waits for the active Kindle reader tab in the Chrome CDP session
  - exports one page image at a time
  - runs `codex exec --image` once per page
  - writes checkpoint state so the run can be resumed later

Examples:
  ./kindle/run-kindle-full-book.sh
  ./kindle/run-kindle-full-book.sh --resume --run-dir ./kindle/runs/20260412_123456

Notes:
  - Login and opening the target book are still manual.
  - Start Chrome with ./kindle/open-kindle-web-browser.sh before running this command.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

exec python3 "$SCRIPT_DIR/run-kindle-full-book.py" "$@"
