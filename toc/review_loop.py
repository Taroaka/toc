"""Contracts for authoring-stage evaluator improvement loops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


MAX_REVIEW_LOOP_ROUNDS = 5
REVIEW_LOOP_CRITIC_COUNT = 5


@dataclass(frozen=True)
class ReviewLoopSpec:
    stage: str
    slot_codes: tuple[str, ...]
    title: str
    final_report: str
    source_artifacts: tuple[str, ...]


REVIEW_LOOP_SPECS: dict[str, ReviewLoopSpec] = {
    "research": ReviewLoopSpec(
        stage="research",
        slot_codes=("p130",),
        title="Research Eval/Improve Loop",
        final_report="research_review.md",
        source_artifacts=("research.md",),
    ),
    "story": ReviewLoopSpec(
        stage="story",
        slot_codes=("p230",),
        title="Story Eval/Improve Loop",
        final_report="story_review.md",
        source_artifacts=("research.md", "story.md"),
    ),
    "visual_value": ReviewLoopSpec(
        stage="visual_value",
        slot_codes=("p320",),
        title="Visual Planning Eval/Improve Loop",
        final_report="visual_value_review.md",
        source_artifacts=("research.md", "story.md", "visual_value.md"),
    ),
    "script": ReviewLoopSpec(
        stage="script",
        slot_codes=("p430",),
        title="Script Eval/Improve Loop",
        final_report="script_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "narration": ReviewLoopSpec(
        stage="narration",
        slot_codes=("p520",),
        title="Narration Text Eval/Improve Loop",
        final_report="narration_text_review.md",
        source_artifacts=("script.md", "video_manifest.md"),
    ),
    "asset": ReviewLoopSpec(
        stage="asset",
        slot_codes=("p640",),
        title="Asset Eval/Improve Loop",
        final_report="asset_review.md",
        source_artifacts=("script.md", "asset_plan.md"),
    ),
    "scene_implementation_hard": ReviewLoopSpec(
        stage="scene_implementation_hard",
        slot_codes=("p730",),
        title="Hard Scene Eval/Improve Loop",
        final_report="manifest_review.md",
        source_artifacts=("script.md", "video_manifest.md"),
    ),
    "scene_implementation_judgment": ReviewLoopSpec(
        stage="scene_implementation_judgment",
        slot_codes=("p740",),
        title="Judgment Eval/Improve Loop",
        final_report="image_prompt_judgment_review.md",
        source_artifacts=("script.md", "video_manifest.md", "image_prompt_story_review.md"),
    ),
    "video_generation_motion": ReviewLoopSpec(
        stage="video_generation_motion",
        slot_codes=("p820",),
        title="Motion / Video Eval/Improve Loop",
        final_report="video_generation_request_review.md",
        source_artifacts=("video_manifest.md",),
    ),
    "video_generation_review": ReviewLoopSpec(
        stage="video_generation_review",
        slot_codes=("p850",),
        title="Video Eval/Improve Loop / Exclusions",
        final_report="video_review.md",
        source_artifacts=("video_manifest.md", "video_generation_requests.md"),
    ),
    "qa": ReviewLoopSpec(
        stage="qa",
        slot_codes=("p930",),
        title="QA Eval/Improve Loop",
        final_report="run_report.md",
        source_artifacts=("run_report.md", "eval_report.json", "video.mp4"),
    ),
}


REVIEW_LOOP_SLOT_BY_CODE = {
    slot_code: spec for spec in REVIEW_LOOP_SPECS.values() for slot_code in spec.slot_codes
}


def stage_for_slot(slot_code: str) -> str:
    normalized = slot_code.strip().lower()
    if normalized and normalized[0].isdigit():
        normalized = f"p{normalized}"
    spec = REVIEW_LOOP_SLOT_BY_CODE.get(normalized)
    if spec is None:
        known = ", ".join(sorted(REVIEW_LOOP_SLOT_BY_CODE))
        raise ValueError(f"unknown review-loop slot: {slot_code}; known slots: {known}")
    return spec.stage


def normalize_round(round_number: int) -> int:
    if round_number < 1 or round_number > MAX_REVIEW_LOOP_ROUNDS:
        raise ValueError(f"round_number must be between 1 and {MAX_REVIEW_LOOP_ROUNDS}: {round_number}")
    return round_number


def normalize_critic(critic_number: int) -> int:
    if critic_number < 1 or critic_number > REVIEW_LOOP_CRITIC_COUNT:
        raise ValueError(f"critic_number must be between 1 and {REVIEW_LOOP_CRITIC_COUNT}: {critic_number}")
    return critic_number


def round_rel_dir(stage: str, round_number: int) -> Path:
    normalize_round(round_number)
    return Path("logs") / "eval" / stage / f"round_{round_number:02d}"


def critic_relpath(stage: str, round_number: int, critic_number: int) -> Path:
    normalize_critic(critic_number)
    return round_rel_dir(stage, round_number) / f"critic_{critic_number}.md"


def critic_prompt_relpath(stage: str, round_number: int, critic_number: int) -> Path:
    normalize_critic(critic_number)
    return round_rel_dir(stage, round_number) / "prompts" / f"critic_{critic_number}.prompt.md"


def aggregated_review_relpath(stage: str, round_number: int) -> Path:
    return round_rel_dir(stage, round_number) / "aggregated_review.md"


def aggregator_prompt_relpath(stage: str, round_number: int) -> Path:
    return round_rel_dir(stage, round_number) / "prompts" / "aggregator.prompt.md"


def final_review_relpath(stage: str) -> Path:
    return Path(REVIEW_LOOP_SPECS[stage].final_report)


def loop_state_updates(
    *,
    stage: str,
    status: str,
    current_round: int,
    final_report: str | Path | None = None,
) -> dict[str, str]:
    if stage not in REVIEW_LOOP_SPECS:
        raise ValueError(f"unknown review loop stage: {stage}")
    if current_round < 0 or current_round > MAX_REVIEW_LOOP_ROUNDS:
        raise ValueError(f"current_round must be between 0 and {MAX_REVIEW_LOOP_ROUNDS}: {current_round}")
    if status not in {"pending", "running", "passed", "changes_requested", "failed"}:
        raise ValueError(f"invalid review loop status: {status}")

    report = str(final_report or final_review_relpath(stage))
    return {
        f"eval.{stage}.loop.status": status,
        f"eval.{stage}.loop.current_round": str(current_round),
        f"eval.{stage}.loop.max_rounds": str(MAX_REVIEW_LOOP_ROUNDS),
        f"eval.{stage}.loop.final_report": report,
    }


def render_critic_prompt(*, run_dir: Path, stage: str, round_number: int, critic_number: int) -> str:
    spec = REVIEW_LOOP_SPECS[stage]
    readset_stage = stage
    for prefix in ("scene_implementation", "video_generation"):
        if stage.startswith(prefix):
            readset_stage = prefix
            break
    source_paths = "\n".join(f"- `{(run_dir / rel).resolve()}`" for rel in spec.source_artifacts)
    readset_path = run_dir / "logs" / "grounding" / f"{readset_stage}.readset.json"
    own_report = (run_dir / critic_relpath(stage, round_number, critic_number)).resolve()
    return dedent(
        f"""
        You are critic_{critic_number} in the ToC {spec.title}.

        Review round: {round_number}/{MAX_REVIEW_LOOP_ROUNDS}
        Run dir: `{run_dir.resolve()}`

        Read these source artifacts directly:
        {source_paths}
        - `{readset_path.resolve()}`

        Work independently. Do not read other critic reports and do not edit files.
        Return markdown for `{own_report}` with:
        - status: passed|changes_requested
        - blocking_findings[]
        - recommended_changes[]
        - rejected_suggestions[]
        - generator_patch_brief
        - round_summary
        """
    ).strip()


def render_aggregator_prompt(*, run_dir: Path, stage: str, round_number: int) -> str:
    spec = REVIEW_LOOP_SPECS[stage]
    critic_paths = "\n".join(
        f"- `{(run_dir / critic_relpath(stage, round_number, idx)).resolve()}`"
        for idx in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
    )
    aggregate_path = (run_dir / aggregated_review_relpath(stage, round_number)).resolve()
    final_path = (run_dir / final_review_relpath(stage)).resolve()
    return dedent(
        f"""
        You are the aggregator in the ToC {spec.title}.

        Wait until all {REVIEW_LOOP_CRITIC_COUNT} critic reports exist, then read:
        {critic_paths}

        Do not edit source artifacts. Consolidate duplicate findings, resolve contradictory
        suggestions, and pass only one generator-facing brief back to main.

        Write markdown suitable for `{aggregate_path}` and final summary `{final_path}` with:
        - status: passed|changes_requested
        - blocking_findings[]
        - recommended_changes[]
        - rejected_suggestions[]
        - generator_patch_brief
        - round_summary
        """
    ).strip()


def render_aggregated_review(
    *,
    stage: str,
    round_number: int,
    critic_reports: list[str],
    status: str = "changes_requested",
) -> str:
    normalize_round(round_number)
    if len(critic_reports) != REVIEW_LOOP_CRITIC_COUNT:
        raise ValueError(f"expected {REVIEW_LOOP_CRITIC_COUNT} critic reports, got {len(critic_reports)}")
    if status not in {"passed", "changes_requested"}:
        raise ValueError(f"invalid aggregated review status: {status}")

    spec = REVIEW_LOOP_SPECS[stage]
    sections: list[str] = [
        f"# {spec.title}",
        "",
        f"- status: {status}",
        f"- round: {round_number}/{MAX_REVIEW_LOOP_ROUNDS}",
        f"- critic_count: {REVIEW_LOOP_CRITIC_COUNT}",
        "",
        "## Blocking Findings",
        "",
        "Aggregator must consolidate critic blockers here. Use an empty list only when status is passed.",
        "",
        "## Recommended Changes",
        "",
        "Aggregator must list non-blocking quality improvements here.",
        "",
        "## Rejected Suggestions",
        "",
        "Aggregator must list rejected critic suggestions and why they were not adopted.",
        "",
        "## Generator Patch Brief",
        "",
        "Aggregator must provide the single brief Main/Generator is allowed to implement next.",
        "",
        "## Round Summary",
        "",
        "Aggregator must summarize what changed or why the loop can stop.",
    ]
    for idx, report in enumerate(critic_reports, start=1):
        sections.extend(["", f"## Critic {idx} Input", "", report.strip()])
    return "\n".join(sections).rstrip() + "\n"
