#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INFO_DIR="${HOME}/.commandmate"
LOG_PATH="${INFO_DIR}/last-start.log"
TOKEN_PATH="${INFO_DIR}/last-auth-token.txt"

mkdir -p "$INFO_DIR"

"$SCRIPT_DIR/commandmate.sh" stop >/dev/null 2>&1 || true

rm -f "$TOKEN_PATH"

OUTPUT="$("$SCRIPT_DIR/commandmate.sh" start --daemon --allow-http 2>&1)"
printf '%s\n' "$OUTPUT" | tee "$LOG_PATH"

printf '\n'
"$SCRIPT_DIR/commandmate-info.sh"
