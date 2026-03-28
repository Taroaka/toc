#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"

if [ ! -f "$IMMICH_DIR/docker-compose.yml" ] || [ ! -f "$IMMICH_DIR/.env" ]; then
  echo "Immich is not initialized. Run: $SCRIPT_DIR/immich-setup.sh" >&2
  exit 1
fi

docker compose -f "$IMMICH_DIR/docker-compose.yml" --env-file "$IMMICH_DIR/.env" up -d
"$SCRIPT_DIR/immich-info.sh"
