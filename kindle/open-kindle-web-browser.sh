#!/usr/bin/env bash

set -euo pipefail

PORT="${KINDLE_CDP_PORT:-59708}"
PROFILE_DIR="${KINDLE_PROFILE_DIR:-$HOME/.codex/playwright-profile}"
KINDLE_URL="${1:-https://read.amazon.co.jp/}"

find_chrome() {
  local candidates=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
  )
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

usage() {
  cat <<EOF
Usage:
  ./kindle/open-kindle-web-browser.sh [kindle-url]

What it does:
  - starts Google Chrome with a dedicated user-data-dir
  - enables Chrome remote debugging on port $PORT
  - opens Kindle for Web

Environment variables:
  KINDLE_CDP_PORT
  KINDLE_PROFILE_DIR
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if curl -sf "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  cat <<EOF
Chrome remote debugging is already available on port $PORT.

Open Kindle in the existing browser session:
  $KINDLE_URL
EOF
  exit 0
fi

CHROME_BIN="$(find_chrome || true)"
if [[ -z "$CHROME_BIN" ]]; then
  cat >&2 <<'EOF'
Google Chrome was not found in /Applications.
Install Google Chrome or update open-kindle-web-browser.sh with your browser path.
EOF
  exit 1
fi

mkdir -p "$PROFILE_DIR"

nohup "$CHROME_BIN" \
  "--user-data-dir=$PROFILE_DIR" \
  "--remote-debugging-port=$PORT" \
  "--no-first-run" \
  "--no-default-browser-check" \
  "--disable-sync" \
  "--disable-search-engine-choice-screen" \
  "$KINDLE_URL" >/tmp/kindle-cdp.log 2>&1 &

sleep 2

cat <<EOF
Started Chrome for Kindle for Web.

- port: $PORT
- profile: $PROFILE_DIR
- url: $KINDLE_URL

Next:
  1. Log in manually
  2. Open the target book manually
  3. Run ./kindle/extract-kindle-web-cdp.py --run-dir <kindle/runs/...>
EOF
