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

rm -f "$TOKEN_PATH"

OUTPUT="$("$SCRIPT_DIR/commandmate.sh" start --https --cert "$CERT_PATH" --key "$KEY_PATH" --daemon 2>&1)"
printf '%s\n' "$OUTPUT" | tee "$LOG_PATH"

printf '\n'
"$SCRIPT_DIR/commandmate-info.sh"
