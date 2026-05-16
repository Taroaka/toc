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
    "production_readiness": ReviewLoopSpec(
        stage="production_readiness",
        slot_codes=("p435",),
        title="Production Readiness Council",
        final_report="production_readiness_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "scene_set": ReviewLoopSpec(
        stage="scene_set",
        slot_codes=("p410b",),
        title="Scene Set Eval/Improve Loop",
        final_report="scene_set_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "scene_detail": ReviewLoopSpec(
        stage="scene_detail",
        slot_codes=("p410c",),
        title="Scene Detail Eval/Improve Loop",
        final_report="scene_detail_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "scene_intent": ReviewLoopSpec(
        stage="scene_intent",
        slot_codes=(),
        title="Scene Intent Eval/Improve Loop (Transitional)",
        final_report="scene_intent_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "cut_blueprint": ReviewLoopSpec(
        stage="cut_blueprint",
        slot_codes=(),
        title="Cut Blueprint Eval/Improve Loop",
        final_report="cut_blueprint_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md"),
    ),
    "narration": ReviewLoopSpec(
        stage="narration",
        slot_codes=("p720",),
        title="Narration Text Eval/Improve Loop",
        final_report="narration_text_review.md",
        source_artifacts=("script.md", "video_manifest.md"),
    ),
    "asset": ReviewLoopSpec(
        stage="asset",
        slot_codes=("p540",),
        title="Asset Eval/Improve Loop",
        final_report="asset_review.md",
        source_artifacts=("story.md", "script.md", "video_manifest.md", "asset_plan.md"),
    ),
    "scene_implementation_hard": ReviewLoopSpec(
        stage="scene_implementation_hard",
        slot_codes=("p630",),
        title="Hard Scene Eval/Improve Loop",
        final_report="manifest_review.md",
        source_artifacts=("script.md", "video_manifest.md"),
    ),
    "scene_implementation_judgment": ReviewLoopSpec(
        stage="scene_implementation_judgment",
        slot_codes=("p640",),
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


def review_guidance_for_stage(stage: str) -> str:
    if stage == "asset":
        return dedent(
            """
            Stage-specific review criteria:
            - Treat p520 coverage as the first gate: verify that the story's characters, story-specific items, used locations, setpieces, and reusable stills are represented in asset_plan.md.
            - Check that principal visual subjects needed by later scenes are not missing: protagonist variants, romantic/decision counterpart, antagonist/authority figures, guide/helper figures, recurring props, setpieces, and recurring locations.
            - For character_reference assets, require full-body front / side / back three-view planning. For character variants, verify they derive from the main character reference instead of becoming a new unrelated design.
            - Verify source_script_selectors[] are only usage locations and generation_plan.reference_inputs[] are only actual visual references.
            - Verify no-reference asset seeds stay on execution_lane=bootstrap_builtin and reference-driven or derived assets stay on execution_lane=standard.
            - Check p550 readiness: each planned request must have a materializable canonical output path, reference count/input consistency, generation/review status readiness, and enough metadata for a human to know what will be generated, with which references, and where it will be saved.
            - Check p550 prompt readiness: each planned request must be writable as a concrete visible prompt, not production metadata such as `物語「<topic>」の scene10`, `scene10_cut01`, `この画像は物語「<topic>」の一場面`, or `後続 scene`.
            - If findings remain, return changes_requested with concrete missing assets or contract fixes so main can patch asset_plan.md and run the next review round.
            """
        ).strip()
    if stage == "scene_detail":
        return dedent(
            """
            Stage-specific review criteria:
            - Judge whether the proposed cut count can carry this scene in a final 5-10 minute video.
            - Estimate the scene's needed duration from total scene count, scene importance, reveal weight, and emotional weight.
            - Treat one cut as roughly 4-15 seconds; explicitly flag that a one-cut scene can only carry about 4-15 seconds.
            - Check whether every piece of content that must be shown in this scene is represented by planned cuts.
            - Review the next scene as context. Decide whether the current scene's final cut connects to the next scene.
            - If the final cut does not connect, recommend either adding one more cut or thickening the final cut.
            - Return concrete add/thicken/delete recommendations that main can auto-apply.
            """
        ).strip()
    if stage == "production_readiness":
        return dedent(
            """
            Stage-specific review criteria:
            - This p435 council runs after p430 script review and before p440 human changes / narration sync.
            - Structure Auditor: inspect story structure, scene order, causality, setup/payoff, scene-to-scene flow, and whether the script skeleton breaks before production.
            - Duration Auditor: estimate runtime from scene and cut counts for a 5-10 minute video, using one cut as roughly 4-15 seconds; identify undersized scenes or missing cuts.
            - Quality Auditor: propose quality improvements, new scenes, new cuts, thicker final cuts, clearer visuals, and stronger production handoffs when duration or structure findings reveal weak spots.
            - Orchestrator: chair the discussion, reconcile Structure/Duration/Quality opinions, and return one prioritized recommendation set.
            - The Orchestrator and all auditors are advisory only. They must not edit canonical artifacts or downstream design artifacts.
            - The Design Owner is the only agent allowed to edit downstream design artifacts in this p435 process.
            - Return every requested change as a patch brief for the Design Owner, including exact target artifact, reason, and acceptance condition.
            """
        ).strip()
    return ""


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
    if stage in {"scene_set", "scene_detail", "scene_intent", "cut_blueprint", "production_readiness"}:
        readset_stage = "script"
    for prefix in ("scene_implementation", "video_generation"):
        if stage.startswith(prefix):
            readset_stage = prefix
            break
    source_paths = "\n".join(f"- `{(run_dir / rel).resolve()}`" for rel in spec.source_artifacts)
    readset_path = run_dir / "logs" / "grounding" / f"{readset_stage}.readset.json"
    own_report = (run_dir / critic_relpath(stage, round_number, critic_number)).resolve()
    stage_guidance = review_guidance_for_stage(stage)
    guidance_block = f"\n\n{stage_guidance}" if stage_guidance else ""
    return dedent(
        f"""
        You are critic_{critic_number} in the ToC {spec.title}.

        Review round: {round_number}/{MAX_REVIEW_LOOP_ROUNDS}
        Run dir: `{run_dir.resolve()}`

        Read these source artifacts directly:
        {source_paths}
        - `{readset_path.resolve()}`

        Work independently. Do not read other critic reports and do not edit files.
        {guidance_block}
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
    if stage == "production_readiness":
        handoff = dedent(
            """
            suggestions, and pass only one Design Owner-facing brief back. The
            Orchestrator and auditors are advisory only; do not route edits to
            Main/Generator, and do not imply that anyone except the Design Owner
            may edit downstream design artifacts.
            """
        ).strip()
        brief_label = "design_owner_patch_brief"
    else:
        handoff = dedent(
            """
            suggestions, and pass only one generator-facing brief back to main.
            """
        ).strip()
        brief_label = "generator_patch_brief"
    return dedent(
        f"""
        You are the aggregator in the ToC {spec.title}.

        Wait until all {REVIEW_LOOP_CRITIC_COUNT} critic reports exist, then read:
        {critic_paths}

        Do not edit source artifacts. Consolidate duplicate findings, resolve contradictory
        {handoff}

        Write markdown suitable for `{aggregate_path}` and final summary `{final_path}` with:
        - status: passed|changes_requested
        - blocking_findings[]
        - recommended_changes[]
        - rejected_suggestions[]
        - {brief_label}
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
    patch_brief_heading = "Design Owner Patch Brief" if stage == "production_readiness" else "Generator Patch Brief"
    patch_brief_text = (
        "Aggregator must provide the single brief the Design Owner is allowed to implement next."
        if stage == "production_readiness"
        else "Aggregator must provide the single brief Main/Generator is allowed to implement next."
    )
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
        f"## {patch_brief_heading}",
        "",
        patch_brief_text,
        "",
        "## Round Summary",
        "",
        "Aggregator must summarize what changed or why the loop can stop.",
    ]
    for idx, report in enumerate(critic_reports, start=1):
        sections.extend(["", f"## Critic {idx} Input", "", report.strip()])
    return "\n".join(sections).rstrip() + "\n"
