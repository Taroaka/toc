#!/usr/bin/env python3
"""Run evaluator review for scene/cut manifest outputs and write a report/state summary."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.stage_evaluator import append_stage_review_state, evaluate_stage, render_stage_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Review manifest(scene/cut) stage outputs.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>")
    parser.add_argument("--profile", choices=["fast", "standard"], default="standard")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    parser.add_argument("--out", default=None, help="Output markdown path (default: <run-dir>/manifest_review.md)")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_path = Path(args.out) if args.out else run_dir / "manifest_review.md"
    result, updates, flow = evaluate_stage(run_dir, stage="manifest", profile=args.profile, flow=args.flow)
    out_path.write_text(render_stage_review(run_dir=run_dir, stage_result=result, stage="manifest", flow=flow, profile=args.profile), encoding="utf-8")
    append_stage_review_state(run_dir=run_dir, stage="manifest", stage_result=result, updates=updates, report_path=out_path)
    print(out_path)
    return 1 if (args.fail_on_findings and not result["passed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
