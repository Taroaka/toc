#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_SYNC_PATH="${ROOT_DIR}/output"
SYNC_PATH="${IMMICH_SYNC_PATH:-$DEFAULT_SYNC_PATH}"
IMMICH_URL="${IMMICH_URL:-}"
IMMICH_API_KEY="${IMMICH_API_KEY:-}"
IMMICH_ALBUM="${IMMICH_ALBUM:-ToC Output}"

if ! command -v immich >/dev/null 2>&1; then
  echo "immich CLI is not installed. Run: npm install -g @immich/cli" >&2
  exit 1
fi

if [ -z "$IMMICH_URL" ]; then
  echo "IMMICH_URL is required, e.g. http://localhost:2283" >&2
  exit 1
fi

if [ -z "$IMMICH_API_KEY" ]; then
  echo "IMMICH_API_KEY is required" >&2
  exit 1
fi

if [ ! -d "$SYNC_PATH" ]; then
  echo "Sync path does not exist: $SYNC_PATH" >&2
  exit 1
fi

echo "Immich URL: $IMMICH_URL"
echo "Sync path: $SYNC_PATH"
echo "Album: $IMMICH_ALBUM"

mapfile -t media_files < <(
  rg --files "$SYNC_PATH" \
    -g '*.png' \
    -g '*.jpg' \
    -g '*.jpeg' \
    -g '*.webp' \
    -g '*.gif' \
    -g '*.mp4' \
    -g '*.mov' \
    -g '*.m4v' \
    -g '*.webm' \
    -g '*.mkv'
)

if [ "${#media_files[@]}" -eq 0 ]; then
  echo "No media files found under $SYNC_PATH"
  exit 0
fi

IMMICH_INSTANCE_URL="$IMMICH_URL" \
IMMICH_API_KEY="$IMMICH_API_KEY" \
immich upload \
  --album "$IMMICH_ALBUM" \
  --recursive \
  "${media_files[@]}"
