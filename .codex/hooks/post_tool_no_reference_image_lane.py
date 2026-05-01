#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any


SENTINEL = "NO_REFERENCE_IMAGE_LANE_REQUIRED"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_response = _stringify(payload.get("tool_response"))
    command = _stringify(((payload.get("tool_input") or {}) if isinstance(payload.get("tool_input"), dict) else {}).get("command"))
    if SENTINEL not in tool_response or "generate-assets-from-manifest.py" not in command:
        return 0

    result = {
        "continue": False,
        "decision": "block",
        "reason": (
            "When generating images in this repo, no-reference requests must stay on the no-reference image lane. "
            "This applies whether you are using an API provider or Codex GPT Image 1.5. "
            "Do not retry google_nanobanana_2, gemini_3_1_flash_image, or seadream without references. "
            "Use $toc-no-reference-image-runner for no-reference scene or cut images, "
            "or $toc-p500-bootstrap-image-runner for p500 asset seeds."
        ),
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "When reference_count == 0, keep execution_lane=bootstrap_builtin. "
                "Apply the same no-reference lane rule whether the image path is an API provider or Codex GPT Image 1.5."
            ),
        },
    }
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
