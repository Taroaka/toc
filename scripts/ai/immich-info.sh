#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"
IMMICH_PORT="${IMMICH_PORT:-2283}"
OUTPUT_HOST_DIR="${IMMICH_EXTERNAL_OUTPUT_DIR:-${ROOT_DIR}/output}"
OUTPUT_CONTAINER_DIR="${IMMICH_EXTERNAL_OUTPUT_MOUNT:-/external/toc-output}"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
TS_STATUS_JSON="$(tailscale status --json 2>/dev/null || true)"
TS_IP="$(printf '%s' "$TS_STATUS_JSON" | jq -r '.Self.TailscaleIPs[0] // empty' 2>/dev/null || true)"
TS_DNS="$(printf '%s' "$TS_STATUS_JSON" | jq -r '.Self.DNSName // empty' 2>/dev/null || true)"

echo "Immich"
echo "  Dir: $IMMICH_DIR"
echo "  Local: http://127.0.0.1:${IMMICH_PORT}"
if [ -n "$LAN_IP" ]; then
  echo "  LAN: http://${LAN_IP}:${IMMICH_PORT}"
fi
if [ -n "$TS_IP" ]; then
  echo "  Tailscale IP: http://${TS_IP}:${IMMICH_PORT}"
fi
if [ -n "$TS_DNS" ]; then
  echo "  Tailscale DNS: http://${TS_DNS%?}:${IMMICH_PORT}"
fi
echo "  Sync source: ${ROOT_DIR}/output"
echo "  External library host path: ${OUTPUT_HOST_DIR}"
echo "  External library container path: ${OUTPUT_CONTAINER_DIR}"

if [ -f "$IMMICH_DIR/docker-compose.yml" ]; then
  echo "  Compose: ready"
else
  echo "  Compose: missing"
fi

if [ -f "$IMMICH_DIR/.env" ]; then
  echo "  Env: ready"
else
  echo "  Env: missing"
fi

if docker compose -f "$IMMICH_DIR/docker-compose.yml" --env-file "$IMMICH_DIR/.env" ps >/dev/null 2>&1; then
  STATUS="$(docker compose -f "$IMMICH_DIR/docker-compose.yml" --env-file "$IMMICH_DIR/.env" ps --status running --services 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [ -n "$STATUS" ]; then
    echo "  Running services: $STATUS"
  else
    echo "  Running services: none"
  fi
fi
