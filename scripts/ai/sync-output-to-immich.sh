#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_SYNC_PATH="${ROOT_DIR}/output"
SYNC_PATH="${IMMICH_SYNC_PATH:-$DEFAULT_SYNC_PATH}"
IMMICH_URL="${IMMICH_URL:-}"
IMMICH_API_KEY="${IMMICH_API_KEY:-}"
IMMICH_ALBUM="${IMMICH_ALBUM:-ToC Output}"
IMMICH_CLI_PATH="${IMMICH_CLI_PATH:-$(command -v immich 2>/dev/null || true)}"

# Immich CLI 2.6.x requires Node 20+, while this machine defaults to nvm Node 18.
# Prepending Homebrew keeps the existing global `immich` install but runs it with a newer Node.
if [ -x "/opt/homebrew/bin/node" ]; then
  export PATH="/opt/homebrew/bin:$PATH"
fi

if [ -z "$IMMICH_CLI_PATH" ] || [ ! -x "$IMMICH_CLI_PATH" ]; then
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

IMMICH_URL="${IMMICH_URL%/}"
if [[ "$IMMICH_URL" != */api ]]; then
  IMMICH_API_URL="${IMMICH_URL}/api"
else
  IMMICH_API_URL="$IMMICH_URL"
fi

echo "Immich URL: $IMMICH_URL"
echo "Immich API URL: $IMMICH_API_URL"
echo "Sync path: $SYNC_PATH"
echo "Album: $IMMICH_ALBUM"

media_files=()
while IFS= read -r file; do
  media_files+=("$file")
done < <(
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

IMMICH_INSTANCE_URL="$IMMICH_API_URL" \
IMMICH_API_KEY="$IMMICH_API_KEY" \
"$IMMICH_CLI_PATH" upload \
  --album "$IMMICH_ALBUM" \
  --recursive \
  "${media_files[@]}"
