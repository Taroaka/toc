#!/usr/bin/env python3
"""Resolve and record required grounding inputs for a ToC stage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StageGroundingError, run_stage_grounding


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve required files before starting a ToC stage.")
    parser.add_argument("--stage", required=True, help="Stage name (research, story, script, narration, asset, scene_implementation, video_generation).")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    try:
        report = run_stage_grounding(run_dir, args.stage, flow=args.flow, retries=0, mark_stage_failure=False)
    except StageGroundingError as exc:
        report = exc.report
    print(run_dir / "logs" / "grounding" / f"{args.stage}.json")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
