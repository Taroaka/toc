#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="${1:-}"
VISION_DIR=""
WORKDIR="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./kindle/transcribe-kindle-pages-with-codex.sh /absolute/path/to/kindle/runs/<timestamp>

What it does:
  - verifies page images already exist in the run directory
  - runs `codex exec --image ...` once per page
  - stores raw per-page Codex outputs under run_dir/vision/
  - rewrites transcript.txt and updates session.md from those page-level results

Notes:
  - This path uses your Codex subscription login, not the OpenAI API.
  - Run the CDP extractor first so that pages/0001.png ... exist.
EOF
}

if [[ -z "$RUN_DIR" || "$RUN_DIR" == "-h" || "$RUN_DIR" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  cat >&2 <<'EOF'
codex is not installed.

Install it with one of:
  npm install -g @openai/codex
  brew install --cask codex
EOF
  exit 1
fi

RUN_DIR="$(cd "$RUN_DIR" && pwd)"
TRANSCRIPT_PATH="$RUN_DIR/transcript.txt"
SESSION_PATH="$RUN_DIR/session.md"
PAGES_DIR="$RUN_DIR/pages"
VISION_DIR="$RUN_DIR/vision"

if [[ ! -d "$PAGES_DIR" ]]; then
  echo "pages directory not found: $PAGES_DIR" >&2
  exit 1
fi

images=()
for index in 1 2 3 4 5; do
  image_path="$(printf '%s/%04d.png' "$PAGES_DIR" "$index")"
  if [[ ! -f "$image_path" ]]; then
    echo "missing page image: $image_path" >&2
    exit 1
  fi
  images+=("$image_path")
done

mkdir -p "$VISION_DIR"

page_prompt() {
  cat <<'EOF'
Read the attached Kindle page image directly with vision.

Rules:
- Reply with only the transcription text for this single page.
- No preamble, no bullets, no markdown fences.
- If the page is vertical Japanese, transcribe in natural reading order.
- Keep line breaks only when they help readability.
- If the page is readable only in part, start the reply with `[[partial vision transcription]]` on its own line.
- If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
EOF
}

printf 'Running per-page Codex vision transcription for:\n  %s\n' "$RUN_DIR"

for image_path in "${images[@]}"; do
  page_name="$(basename "$image_path" .png)"
  output_path="$VISION_DIR/$page_name.txt"
  log_path="$VISION_DIR/$page_name.log"
  printf '  - transcribing %s\n' "$page_name"
  if ! page_prompt | codex exec \
    -C "$WORKDIR" \
    -c 'model_reasoning_effort="medium"' \
    --image "$image_path" \
    -o "$output_path" \
    - >"$log_path" 2>&1; then
    echo "codex vision transcription failed for $page_name. See $log_path" >&2
    exit 1
  fi
done

python3 - <<'PY' "$RUN_DIR" "$TRANSCRIPT_PATH" "$SESSION_PATH"
import pathlib
import re
import sys

run_dir = pathlib.Path(sys.argv[1])
transcript_path = pathlib.Path(sys.argv[2])
session_path = pathlib.Path(sys.argv[3])
vision_dir = run_dir / "vision"

blocks = []
partial = False
failed = False
for index in range(1, 6):
    page_name = f"{index:04d}"
    page_text = (vision_dir / f"{page_name}.txt").read_text(encoding="utf-8").strip()
    if not page_text:
        page_text = "[[vision transcription failed]]"
    if page_text.startswith("[[partial vision transcription]]"):
        partial = True
    if page_text.startswith("[[vision transcription failed]]"):
        partial = True
        failed = True
    blocks.append(f"=== Page {index} ===\n{page_text}")

transcript_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

session_text = session_path.read_text(encoding="utf-8")
session_text = re.sub(
    r"^- transcription_source: .*$",
    "- transcription_source: codex vision from local images (per-page codex exec --image)",
    session_text,
    flags=re.MULTILINE,
)
status = "partial" if partial else "completed"
session_text = re.sub(r"^- status: .*$", f"- status: {status}", session_text, flags=re.MULTILINE)
note_lines = [
    "- Vision transcription completed via per-page `codex exec --image` runs.",
]
if failed:
    note_lines.append("- At least one page remained a vision transcription failure.")
elif partial:
    note_lines.append("- At least one page was marked as a partial vision transcription.")
else:
    note_lines.append("- All 5 pages received a direct Codex vision transcription.")

if "## Notes" in session_text:
    session_text = session_text.rstrip() + "\n" + "\n".join(note_lines) + "\n"
else:
    session_text = session_text.rstrip() + "\n\n## Notes\n\n" + "\n".join(note_lines) + "\n"

session_path.write_text(session_text, encoding="utf-8")
PY

printf 'Completed per-page Codex vision transcription.\n'
