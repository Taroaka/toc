#!/usr/bin/env python3
"""Prepare serial stage context for chat/manual work."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StageGroundingError, prepare_stage_context  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve, audit, and return the canonical readset for one stage.")
    parser.add_argument("--stage", required=True, help="Stage name (research, story, script, image_prompt, video_generation).")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    try:
        payload = prepare_stage_context(run_dir, args.stage, flow=args.flow, retries=0, mark_stage_failure=False)
    except StageGroundingError as exc:
        payload = {
            "stage": exc.stage,
            "run_dir": str(run_dir.resolve()),
            "status": exc.status,
            "missing_paths": exc.report.get("missing_paths", []),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
