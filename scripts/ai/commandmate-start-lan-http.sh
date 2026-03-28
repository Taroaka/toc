#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INFO_DIR="${HOME}/.commandmate"
LOG_PATH="${INFO_DIR}/last-start.log"
TOKEN_PATH="${INFO_DIR}/last-auth-token.txt"

mkdir -p "$INFO_DIR"

"$SCRIPT_DIR/commandmate.sh" stop >/dev/null 2>&1 || true

OUTPUT="$("$SCRIPT_DIR/commandmate.sh" start --auth --daemon --allow-http 2>&1)"
printf '%s\n' "$OUTPUT" | tee "$LOG_PATH"

TOKEN="$(printf '%s\n' "$OUTPUT" | LC_ALL=C perl -pe 's/\e\[[0-9;]*m//g' | awk '/Authentication token/{getline; gsub(/^[[:space:]]+/, "", $0); sub(/^\[INFO\][[:space:]]*/, "", $0); print $0}' | tail -1)"
if [ -n "$TOKEN" ]; then
  printf '%s\n' "$TOKEN" > "$TOKEN_PATH"
fi

printf '\n'
"$SCRIPT_DIR/commandmate-info.sh"
