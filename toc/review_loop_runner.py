"""Execution helpers for ToC evaluator-improvement loops."""

from __future__ import annotations

from pathlib import Path

from toc.harness import append_state_snapshot, now_iso
from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SPECS,
    aggregated_review_relpath,
    aggregator_prompt_relpath,
    critic_prompt_relpath,
    critic_relpath,
    loop_state_updates,
    render_aggregator_prompt,
    render_critic_prompt,
)


def materialize_review_loop_round(*, run_dir: Path, stage: str, round_number: int) -> dict[str, str]:
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
