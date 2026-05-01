#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any


ADDITIONAL_CONTEXT = """Codex App repo-local guidance:
- The user authorizes appropriate subagent use for complex, parallelizable, or review-heavy work in this repository, unless the current prompt explicitly asks not to use subagents.
- Before delegating, identify the immediate critical-path task and keep that local; delegate only bounded sidecar work that can progress in parallel.
- If an available skill clearly matches the user's request or the touched repo area, invoke that skill for the turn and follow its SKILL.md instructions.
- For ToC production work, prefer the repo's existing stage skills, workflows, scripts, and docs over ad hoc procedures."""


def _load_stdin() -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    _load_stdin()
    result = {
        "continue": True,
        "suppressOutput": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ADDITIONAL_CONTEXT,
        },
    }
    json.dump(result, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
