#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMMICH_DIR="${IMMICH_DIR:-$HOME/immich}"
OUTPUT_HOST_DIR="${IMMICH_EXTERNAL_OUTPUT_DIR:-${ROOT_DIR}/output}"
OUTPUT_CONTAINER_DIR="${IMMICH_EXTERNAL_OUTPUT_MOUNT:-/external/toc-output}"
MOUNT_LINE="      - ${OUTPUT_HOST_DIR}:${OUTPUT_CONTAINER_DIR}:ro"

if [ ! -f "$IMMICH_DIR/docker-compose.yml" ] || [ ! -f "$IMMICH_DIR/.env" ]; then
  echo "Immich is not initialized: $IMMICH_DIR" >&2
  echo "Run: $ROOT_DIR/scripts/ai/immich-setup.sh" >&2
  exit 1
fi

if [ ! -d "$OUTPUT_HOST_DIR" ]; then
  echo "Output directory does not exist: $OUTPUT_HOST_DIR" >&2
  exit 1
fi

if ! rg -Fq -- "$MOUNT_LINE" "$IMMICH_DIR/docker-compose.yml"; then
  IMMICH_OUTPUT_MOUNT_LINE="$MOUNT_LINE" perl -0pi -e '
    my $mount = $ENV{IMMICH_OUTPUT_MOUNT_LINE};
    s/(      - \/etc\/localtime:\/etc\/localtime:ro\n)/$1$mount\n/
      or die "Failed to insert external library mount\n";
  ' "$IMMICH_DIR/docker-compose.yml"
  echo "Added external library mount to $IMMICH_DIR/docker-compose.yml"
else
  echo "External library mount already exists"
fi

docker compose -f "$IMMICH_DIR/docker-compose.yml" --env-file "$IMMICH_DIR/.env" up -d

echo "External library host path:"
echo "  $OUTPUT_HOST_DIR"
echo "External library container path:"
echo "  $OUTPUT_CONTAINER_DIR"
echo "Next in Immich UI:"
echo "  Administration -> External Libraries -> Create Library"
echo "  Folder path: $OUTPUT_CONTAINER_DIR"
echo "  Then run: Scan New Library Files"
