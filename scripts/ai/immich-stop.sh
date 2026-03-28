#!/usr/bin/env bash
set -euo pipefail

IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"

if [ ! -f "$IMMICH_DIR/docker-compose.yml" ] || [ ! -f "$IMMICH_DIR/.env" ]; then
  echo "Immich is not initialized: $IMMICH_DIR" >&2
  exit 1
fi

docker compose -f "$IMMICH_DIR/docker-compose.yml" --env-file "$IMMICH_DIR/.env" down
echo "Immich stopped"
