#!/usr/bin/env bash
set -euo pipefail

PORT="${CM_PORT:-3101}"
TOKEN_PATH="${HOME}/.commandmate/last-auth-token.txt"
LOG_PATH="${HOME}/.commandmate/last-start.log"
CERT_DIR="${HOME}/.commandmate/certs"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
SCHEME="http"

if [ -f "$LOG_PATH" ]; then
  START_LINE="$(LC_ALL=C perl -pe 's/\e\[[0-9;]*m//g' "$LOG_PATH" | awk '/Starting server at /{print; exit}')"
  if printf '%s\n' "$START_LINE" | grep -q 'Starting server at https://'; then
    SCHEME="https"
  fi
fi

echo "CommandMate URLs"
echo "  Local: ${SCHEME}://127.0.0.1:${PORT}/"
if [ -n "$LAN_IP" ]; then
  echo "  LAN HTTP: http://${LAN_IP}:${PORT}/"
  if [ -f "${CERT_DIR}/localhost+2.pem" ] && [ -f "${CERT_DIR}/localhost+2-key.pem" ]; then
    echo "  LAN HTTPS: https://${LAN_IP}:${PORT}/"
  fi
fi

if [ -f "$TOKEN_PATH" ]; then
  echo "Token"
  cat "$TOKEN_PATH"
fi

if [ -f "${CERT_DIR}/localhost+2.pem" ]; then
  echo "Cert"
  echo "  ${CERT_DIR}/localhost+2.pem"
  echo "  ${CERT_DIR}/localhost+2-key.pem"
fi
