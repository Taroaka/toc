#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"
OUTPUT_HOST_DIR="${IMMICH_EXTERNAL_OUTPUT_DIR:-${ROOT_DIR}/output}"
OUTPUT_CONTAINER_DIR="${IMMICH_EXTERNAL_OUTPUT_MOUNT:-/external/toc-output}"
MOUNT_LINE="      - ${OUTPUT_HOST_DIR}:${OUTPUT_CONTAINER_DIR}:ro"
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

if [ -d "$OUTPUT_HOST_DIR" ] && ! rg -Fq -- "$MOUNT_LINE" "$IMMICH_DIR/docker-compose.yml"; then
  IMMICH_OUTPUT_MOUNT_LINE="$MOUNT_LINE" perl -0pi -e '
    my $mount = $ENV{IMMICH_OUTPUT_MOUNT_LINE};
    s/(      - \/etc\/localtime:\/etc\/localtime:ro\n)/$1$mount\n/
      or die "Failed to insert external library mount\n";
  ' "$IMMICH_DIR/docker-compose.yml"
fi

echo "Immich directory prepared"
echo "  $IMMICH_DIR"
echo "External library host path:"
echo "  $OUTPUT_HOST_DIR"
echo "External library container path:"
echo "  $OUTPUT_CONTAINER_DIR"
echo "Next:"
echo "  cd $IMMICH_DIR && docker compose up -d"
