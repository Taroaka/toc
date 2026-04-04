#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale is not installed" >&2
  exit 1
fi

STATUS_JSON="$(tailscale status --json 2>/dev/null || true)"

echo "Tailscale"
echo "  Version: $(tailscale version | head -1)"

if [ -z "$STATUS_JSON" ]; then
  echo "  State: unavailable"
  echo "  Action: open Tailscale app and sign in"
  exit 0
fi

BACKEND_STATE="$(printf '%s' "$STATUS_JSON" | jq -r '.BackendState // "unknown"' 2>/dev/null || echo unknown)"
TS_IP="$(printf '%s' "$STATUS_JSON" | jq -r '.Self.TailscaleIPs[0] // empty' 2>/dev/null || true)"
TS_DNS="$(printf '%s' "$STATUS_JSON" | jq -r '.Self.DNSName // empty' 2>/dev/null || true)"

echo "  State: $BACKEND_STATE"

if [ -n "$TS_IP" ]; then
  echo "  IP: $TS_IP"
fi

if [ -n "$TS_DNS" ]; then
  echo "  DNS: $TS_DNS"
fi
