#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$REPO_ROOT/skills"

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
DEST_DIR="$CODEX_HOME/skills"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "[ERROR] skills not found at: $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

installed=0
for skill_path in "$SRC_DIR"/*; do
  [[ -d "$skill_path" ]] || continue

  skill_name="$(basename "$skill_path")"
  [[ "$skill_name" == _* ]] && continue
  [[ -f "$skill_path/SKILL.md" ]] || continue

  dest_path="$DEST_DIR/$skill_name"

  rm -rf "$dest_path"
  cp -R "$skill_path" "$dest_path"

  installed=$((installed + 1))
  echo "[OK] Installed: $skill_name -> $dest_path"
done

if [[ "$installed" -eq 0 ]]; then
  echo "[WARN] No skills found in: $SRC_DIR" >&2
fi
