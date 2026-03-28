#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${HOME}/.commandmate/certs"
CERT_PATH="${CERT_DIR}/localhost+2.pem"
KEY_PATH="${CERT_DIR}/localhost+2-key.pem"
INFO_DIR="${HOME}/.commandmate"
LOG_PATH="${INFO_DIR}/last-start.log"
TOKEN_PATH="${INFO_DIR}/last-auth-token.txt"

if [ ! -f "$CERT_PATH" ] || [ ! -f "$KEY_PATH" ]; then
  echo "LAN HTTPS certificate not found: $CERT_PATH / $KEY_PATH" >&2
  exit 1
fi

mkdir -p "$INFO_DIR"

"$SCRIPT_DIR/commandmate.sh" stop >/dev/null 2>&1 || true

OUTPUT="$("$SCRIPT_DIR/commandmate.sh" start --auth --https --cert "$CERT_PATH" --key "$KEY_PATH" --daemon 2>&1)"
printf '%s\n' "$OUTPUT" | tee "$LOG_PATH"

TOKEN="$(printf '%s\n' "$OUTPUT" | LC_ALL=C perl -pe 's/\e\[[0-9;]*m//g' | awk '/Authentication token/{getline; gsub(/^[[:space:]]+/, "", $0); sub(/^\[INFO\][[:space:]]*/, "", $0); print $0}' | tail -1)"
if [ -n "$TOKEN" ]; then
  printf '%s\n' "$TOKEN" > "$TOKEN_PATH"
fi

printf '\n'
"$SCRIPT_DIR/commandmate-info.sh"
