#!/usr/bin/env python3
"""Materialize prompts for one authoring-stage review-loop round."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.review_loop import (
    MAX_REVIEW_LOOP_ROUNDS,
    REVIEW_LOOP_SLOT_BY_CODE,
    REVIEW_LOOP_SPECS,
    stage_for_slot,
)
from toc.review_loop_runner import materialize_review_loop_round


def write_review_loop_round(*, run_dir: Path, stage: str, round_number: int) -> dict[str, str]:
    return materialize_review_loop_round(run_dir=run_dir, stage=stage, round_number=round_number)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build prompts for one ToC evaluator-improvement loop round.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>")
    parser.add_argument("--stage", choices=sorted(REVIEW_LOOP_SPECS))
    parser.add_argument("--slot", choices=sorted(REVIEW_LOOP_SLOT_BY_CODE))
    parser.add_argument("--round", type=int, default=1, dest="round_number", help=f"Round number, 1-{MAX_REVIEW_LOOP_ROUNDS}")
    args = parser.parse_args()
    if not args.stage and not args.slot:
        parser.error("one of --stage or --slot is required")

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    stage = args.stage or stage_for_slot(args.slot)
    updates = write_review_loop_round(run_dir=run_dir, stage=stage, round_number=args.round_number)
    for key in sorted(updates):
        print(f"{key}={updates[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
