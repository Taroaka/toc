#!/usr/bin/env bash

set -euo pipefail

SESSION_TS="$(date +%Y%m%d_%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$SCRIPT_DIR/runs/$SESSION_TS"
PAGES_DIR="$RUN_DIR/pages"
PROMPT_TEMPLATE="$SCRIPT_DIR/codex-kindle-5page-prompt.md"
PROMPT_OUT="$RUN_DIR/codex-prompt.md"
VISION_PROMPT_TEMPLATE="$SCRIPT_DIR/codex-kindle-vision-prompt.md"
VISION_PROMPT_OUT="$RUN_DIR/codex-vision-prompt.md"

usage() {
  cat <<'EOF'
Usage:
  ./kindle/start-kindle-web-session.sh

What it does:
  - creates a run directory under ./kindle/runs/<timestamp>
  - scaffolds transcript/session output files
  - writes prompt files for export and Codex vision transcription

Notes:
  - Login is intentionally left to the user.
  - Use ./kindle/open-kindle-web-browser.sh to start Chrome with remote debugging.
  - The generated prompt tells Codex to call the CDP extractor instead of Playwright screenshots.
  - Codex is optional; you can run the extractor directly from the shell.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "$PAGES_DIR"

cat > "$RUN_DIR/transcript.txt" <<'EOF'
=== Page 1 ===
[[pending]]

=== Page 2 ===
[[pending]]

=== Page 3 ===
[[pending]]

=== Page 4 ===
[[pending]]

=== Page 5 ===
[[pending]]
EOF

cat > "$RUN_DIR/session.md" <<EOF
# Kindle session

- run_dir: \`$RUN_DIR\`
- target: \`https://read.amazon.com\`
- page_target: \`5\`
- login_mode: manual
- transcription_source: cdp-direct-page-image-export; awaiting Codex vision transcription
- status: pending

## Notes

- Waiting for Kindle browser session, CDP page-image export, and Codex vision transcription.
EOF

sed \
  -e "s|__RUN_DIR__|$RUN_DIR|g" \
  -e "s|__PAGES_DIR__|$PAGES_DIR|g" \
  -e "s|__TRANSCRIPT_PATH__|$RUN_DIR/transcript.txt|g" \
  -e "s|__SESSION_PATH__|$RUN_DIR/session.md|g" \
  "$PROMPT_TEMPLATE" > "$PROMPT_OUT"

sed \
  -e "s|__TRANSCRIPT_PATH__|$RUN_DIR/transcript.txt|g" \
  -e "s|__SESSION_PATH__|$RUN_DIR/session.md|g" \
  -e "s|__IMAGE_1__|$PAGES_DIR/0001.png|g" \
  -e "s|__IMAGE_2__|$PAGES_DIR/0002.png|g" \
  -e "s|__IMAGE_3__|$PAGES_DIR/0003.png|g" \
  -e "s|__IMAGE_4__|$PAGES_DIR/0004.png|g" \
  -e "s|__IMAGE_5__|$PAGES_DIR/0005.png|g" \
  "$VISION_PROMPT_TEMPLATE" > "$VISION_PROMPT_OUT"

cat <<EOF
Run directory:
  $RUN_DIR

Prepared files:
  $PROMPT_OUT
  $VISION_PROMPT_OUT
  $RUN_DIR/transcript.txt
  $RUN_DIR/session.md

Recommended next steps:
  1. Run: ./kindle/open-kindle-web-browser.sh
  2. In that Chrome window, complete Kindle login manually and open the target book manually.
  3. Run directly:
     python3 ./kindle/extract-kindle-web-cdp.py --run-dir "$RUN_DIR" --ocr-mode none
  4. Then transcribe with Codex vision:
     ./kindle/transcribe-kindle-pages-with-codex.sh "$RUN_DIR"
  5. Or let Codex run the export stage:
     codex exec -C /Users/kantaro/Downloads/toc - < "$PROMPT_OUT"
EOF
