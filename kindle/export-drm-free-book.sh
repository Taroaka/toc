#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_CALIBRE_BIN="/Applications/calibre.app/Contents/MacOS/ebook-convert"

usage() {
  cat <<'EOF'
Usage:
  ./kindle/export-drm-free-book.sh /path/to/book.epub [output.txt]

Notes:
  - This script is only for DRM-free books or files you are allowed to convert.
  - Default output path: ./kindle/output/<input-basename>.txt
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
  exit 1
fi

input_path="$1"

if [[ ! -f "$input_path" ]]; then
  echo "Input file not found: $input_path" >&2
  exit 1
fi

if command -v ebook-convert >/dev/null 2>&1; then
  calibre_bin="$(command -v ebook-convert)"
elif [[ -x "$DEFAULT_CALIBRE_BIN" ]]; then
  calibre_bin="$DEFAULT_CALIBRE_BIN"
else
  cat >&2 <<'EOF'
ebook-convert is not available.

Install Calibre first:
  brew install --cask calibre
EOF
  exit 1
fi

if [[ $# -eq 2 ]]; then
  output_path="$2"
else
  mkdir -p "$SCRIPT_DIR/output"
  input_name="$(basename "$input_path")"
  output_path="$SCRIPT_DIR/output/${input_name%.*}.txt"
fi

mkdir -p "$(dirname "$output_path")"

"$calibre_bin" \
  "$input_path" \
  "$output_path" \
  --txt-output-formatting=plain \
  --txt-output-encoding=utf-8 \
  --newline=unix \
  --max-line-length=0 \
  --pretty-print

echo "Wrote: $output_path"
