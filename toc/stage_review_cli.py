"""Shared command-line runner for canonical stage evaluator reviews."""

from __future__ import annotations

import argparse
from pathlib import Path

from toc.stage_evaluator import (
    append_stage_review_state,
    evaluate_stage,
    render_stage_review,
)

REVIEW_FLOW_CHOICES = ("toc-run", "scene-series", "immersive")
REVIEW_PROFILE_CHOICES = ("fast", "standard")


def run_stage_review_cli(*, stage: str, description: str) -> int:
    """Run one stage review while preserving the legacy CLI contract."""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>")
    parser.add_argument(
        "--profile",
        choices=REVIEW_PROFILE_CHOICES,
        default="standard",
    )
    parser.add_argument(
        "--flow",
        choices=REVIEW_FLOW_CHOICES,
        default=None,
    )
    parser.add_argument(
        "--out",
        default=None,
        help=f"Output markdown path (default: <run-dir>/{stage}_review.md)",
    )
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_path = Path(args.out) if args.out else run_dir / f"{stage}_review.md"
    result, updates, flow = evaluate_stage(
        run_dir,
        stage=stage,
        profile=args.profile,
        flow=args.flow,
    )
    out_path.write_text(
        render_stage_review(
            run_dir=run_dir,
            stage_result=result,
            stage=stage,
            flow=flow,
            profile=args.profile,
        ),
        encoding="utf-8",
    )
    append_stage_review_state(
        run_dir=run_dir,
        stage=stage,
        stage_result=result,
        updates=updates,
        report_path=out_path,
    )
    print(out_path)
    return 1 if (args.fail_on_findings and not result["passed"]) else 0
