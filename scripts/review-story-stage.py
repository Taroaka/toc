#!/usr/bin/env python3
"""Run evaluator review for the story stage and write a report/state summary."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.stage_review_cli import run_stage_review_cli


def main() -> int:
    return run_stage_review_cli(
        stage="story",
        description="Review story stage outputs.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
