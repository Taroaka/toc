#!/usr/bin/env bash
set -euo pipefail

BREW_BIN="/opt/homebrew/bin"

if [ ! -x "$BREW_BIN/node" ] || [ ! -x "$BREW_BIN/commandmate" ]; then
  echo "Homebrew node/commandmate not found under $BREW_BIN" >&2
  exit 1
fi

export PATH="$BREW_BIN:$PATH"

exec "$BREW_BIN/commandmate" "$@"
