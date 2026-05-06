#!/usr/bin/env python3
"""Materialize prompts for one authoring-stage review-loop round."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso
from toc.review_loop import (
    MAX_REVIEW_LOOP_ROUNDS,
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SLOT_BY_CODE,
    REVIEW_LOOP_SPECS,
    aggregator_prompt_relpath,
    aggregated_review_relpath,
    critic_prompt_relpath,
    critic_relpath,
    loop_state_updates,
    render_aggregator_prompt,
    render_critic_prompt,
    stage_for_slot,
)


def write_review_loop_round(*, run_dir: Path, stage: str, round_number: int) -> dict[str, str]:
    resolved_run_dir = run_dir.resolve()
    if stage not in REVIEW_LOOP_SPECS:
        known = ", ".join(sorted(REVIEW_LOOP_SPECS))
        raise ValueError(f"unknown review-loop stage: {stage}; known stages: {known}")

    spec = REVIEW_LOOP_SPECS[stage]
    missing = [rel for rel in spec.source_artifacts if not (resolved_run_dir / rel).exists()]
    if missing:
        raise FileNotFoundError("review-loop source artifacts are missing: " + ", ".join(missing))

    updates = loop_state_updates(stage=stage, status="running", current_round=round_number)
    updates[f"eval.{stage}.loop.round_{round_number:02d}.started_at"] = now_iso()
    updates[f"eval.{stage}.loop.round_{round_number:02d}.aggregated_review"] = str(
        aggregated_review_relpath(stage, round_number)
    )

    for idx in range(1, REVIEW_LOOP_CRITIC_COUNT + 1):
        report_rel = critic_relpath(stage, round_number, idx)
        prompt_rel = critic_prompt_relpath(stage, round_number, idx)
        path = resolved_run_dir / prompt_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            render_critic_prompt(
                run_dir=resolved_run_dir,
                stage=stage,
                round_number=round_number,
                critic_number=idx,
            )
            + "\n",
            encoding="utf-8",
        )
        updates[f"eval.{stage}.loop.round_{round_number:02d}.critic_{idx}"] = str(report_rel)
        updates[f"eval.{stage}.loop.round_{round_number:02d}.critic_{idx}_prompt"] = str(prompt_rel)

    aggregate_prompt_rel = aggregator_prompt_relpath(stage, round_number)
    aggregate_prompt_path = resolved_run_dir / aggregate_prompt_rel
    aggregate_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_prompt_path.write_text(
        render_aggregator_prompt(run_dir=resolved_run_dir, stage=stage, round_number=round_number) + "\n",
        encoding="utf-8",
    )
    updates[f"eval.{stage}.loop.round_{round_number:02d}.aggregator_prompt"] = str(aggregate_prompt_rel)

    append_state_snapshot(resolved_run_dir / "state.txt", updates)
    return updates


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
