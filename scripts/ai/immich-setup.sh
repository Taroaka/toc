#!/usr/bin/env bash
set -euo pipefail

IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"
COMPOSE_URL="https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml"
ENV_URL="https://github.com/immich-app/immich/releases/latest/download/example.env"

mkdir -p "$IMMICH_DIR"

if [ ! -f "$IMMICH_DIR/docker-compose.yml" ]; then
  curl -L -o "$IMMICH_DIR/docker-compose.yml" "$COMPOSE_URL"
fi

if [ ! -f "$IMMICH_DIR/.env" ]; then
  curl -L -o "$IMMICH_DIR/.env" "$ENV_URL"
fi

if rg -q '^UPLOAD_LOCATION=' "$IMMICH_DIR/.env"; then
  perl -0pi -e 's/^UPLOAD_LOCATION=.*/UPLOAD_LOCATION=.\/library/m' "$IMMICH_DIR/.env"
else
  printf '\nUPLOAD_LOCATION=./library\n' >> "$IMMICH_DIR/.env"
fi

mkdir -p "$IMMICH_DIR/library"

echo "Immich directory prepared"
echo "  $IMMICH_DIR"
echo "Next:"
echo "  cd $IMMICH_DIR && docker compose up -d"
