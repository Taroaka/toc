"""Contracts for authoring-stage evaluator improvement loops."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


MAX_REVIEW_LOOP_ROUNDS = 5
REVIEW_LOOP_CRITIC_COUNT = 5


REVIEW_CAUSAL_ANALYSIS_GUIDANCE = dedent(
    """
    Review artifact quality rule:
    - Do not stop at surface symptoms such as "missing", "weak", "unclear", or
      "not enough detail". Explain the essential failure cause.
    - Every blocking finding must identify root_cause: the artifact design,
      dependency, state mismatch, missing contract, or prompt/manifest structure
      that caused the failure.
    - When the fix is clear, include fix_direction with the target file/section,
      the concrete change, and the acceptance condition for the next review.
    - If the fix is not yet clear, say what evidence must be gathered next
      instead of inventing a patch.
    - Prefer causal chains over restating failed checks: "because X is absent,
      Y cannot be generated/reviewed safely, causing Z downstream".
    """
).strip()


SCENE_REVIEW_CRITIC_FOCUS: dict[str, dict[int, tuple[str, str]]] = {
    "scene_set": {
        1: (
            "scene_count_coverage",
            "Verify that the approved story beats are expanded to the maximal meaningful scene count. "
            "Block approval if a beat with its own dramatic question, value shift, and causal turn is buried inside another scene.",
        ),
        2: (
            "dramatic_structure_and_reveal_order",
            "Verify that each scene has an independent dramatic question, value shift, and causal turn, and that scene additions or splits do not break reveal order.",
        ),
        3: (
            "duration_density",
            "Verify whether scene count, target duration, importance, and planned cut density are sufficient for the target video length. "
            "Decide where scene splitting is better than cut thickening.",
        ),
        4: (
            "visual_production",
            "Verify that every proposed scene can hand visible evidence, visual thesis, and asset/image/video requirements to p500/p600/p800.",
        ),
        5: (
            "handoff_integrity",
            "Verify scene-to-scene causality and handoff: each scene ending must generate the next scene's starting pressure or question.",
        ),
    },
    "scene_detail": {
        1: (
            "scene_detail_structure",
            "Verify this scene's necessity, internal logic, and independent dramatic question/value shift/causal turn within the maximal scene set.",
        ),
        2: (
            "scene_detail_density",
            "Verify this scene's cut count, target duration, emotional weight, and whether to add cuts or split the scene.",
        ),
        3: (
            "scene_detail_handoff",
            "Verify incoming and outgoing handoff with neighboring scenes, including the final cut's ability to trigger the next scene.",
        ),
        4: (
            "scene_detail_reveal_order",
            "Verify that this scene neither reveals future information too early nor omits information the audience needs here.",
        ),
        5: (
            "scene_detail_visual_production",
            "Verify that this scene's visible evidence, visual thesis, and p500/p600/p800 handoff are concrete enough for production.",
        ),
    },
}

CUT_BLUEPRINT_CRITIC_FOCUS: dict[int, tuple[str, str]] = {
    1: (
        "cut_intent_isolation",
        "Verify that each cut carries exactly one viewer-facing intent and does not combine location move, reveal, emotional reversal, explanation, reaction, and next-scene handoff in one cut.",
    ),
    2: (
        "beat_ladder_coverage",
        "Verify that cut_function roles cover the scene spine and that scene obligations are assigned: dramatic question, value_shift.visible_evidence, causal_turn, reveal constraints, reaction, and handoff.",
    ),
    3: (
        "first_frame_motion_readiness",
        "Verify that first_frame_contract is a startable p600 still input, action_completion_state is not an unintended aftermath, and motion_contract remains a p800-only input instead of leaking into image prompt authoring.",
    ),
    4: (
        "multimodal_contract_coverage",
        "Verify that cut_contract.viewer/cinematic/continuity/narration/downstream fields are concrete and that image, motion, and narration can satisfy the same target_beat without narration-only explanation.",
    ),
    5: (
        "duration_density_and_handoff",
        "Verify cut count, duration intent, importance-based density, continuity between cuts, final-cut handoff, and downstream handoff readiness for p500/p600/p700/p800.",
    ),
}

CUT_BLUEPRINT_GATE_MARKERS: tuple[str, ...] = (
    "## Cut Blueprint Gate",
    "cut_intent_isolation",
    "beat_ladder_coverage",
    "first_frame_motion_readiness",
    "multimodal_contract_coverage",
    "duration_density_and_handoff",
    "coverage_plan_complete",
    "continuity_contract_complete",
    "narration_contract_complete",
    "downstream_handoff_complete",
    "triangulation_review_ready",
)

REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE: dict[str, dict[int, tuple[str, str]]] = {
    **SCENE_REVIEW_CRITIC_FOCUS,
    "cut_blueprint": CUT_BLUEPRINT_CRITIC_FOCUS,
}


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
        source_artifacts=("story.md", "script.md", "video_manifest.md", "asset_inventory.md", "asset_plan.md"),
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
    if stage == "scene_set":
        return dedent(
            """
            Stage-specific review criteria:
            - Apply `maximal_meaningful` scene count strategy: do not approve a compressed scene set while an approved story beat can stand as its own production scene.
            - A beat deserves its own scene when it has an independent dramatic_question, value_shift, causal_turn, and visible evidence.
            - The stop condition is not a fixed scene count. Pass only when the next plausible scene would repeat an existing question/value shift/causal turn and cut thickening would improve quality more than another scene.
            - Always name the next scene candidate that could be added. If you reject it, explain why it belongs inside existing scene cuts instead.
            - Check story coverage, scene order, reveal order, target duration, visual production handoff, and scene-to-scene causality.
            """
        ).strip()
    if stage == "asset":
        return dedent(
            """
            Stage-specific review criteria:
            - Treat p520 coverage as the first gate: verify that the story's characters, story-specific items, used locations, setpieces, and reusable stills are represented in asset_inventory.md, then carried into p530 asset_plan.md.
            - Check that principal visual subjects needed by later scenes are not missing: protagonist variants, romantic/decision counterpart, antagonist/authority figures, guide/helper figures, recurring props, setpieces, and recurring locations.
            - For character_reference assets, require full-body front / side / back three-view planning. For character variants, verify they derive from the main character reference instead of becoming a new unrelated design.
            - Hard review: verify source_script_selectors[] are only usage locations, generation_plan.reference_inputs[] are only actual visual references, output paths are canonical, review/status fields are present, all image requests use tool=codex_builtin_image, and no-reference asset seeds stay on execution_lane=bootstrap_builtin while reference-driven or derived assets stay on execution_lane=standard.
            - Hard review: check p550 readiness for each planned request: materializable canonical output path, reference count/input consistency, generation/review status readiness, and enough metadata for a human to know what will be generated, with which references, and where it will be saved.
            - Judgment review: check whether the planned visual identities are concrete enough to preserve continuity across later scenes, whether variants remain recognizably derived from their base asset, and whether fixed details / must_avoid constraints are useful for p600 prompt authors.
            - Judgment review: check p550 prompt readiness: each planned request must be writable as a concrete visible prompt, not production metadata such as `物語「<topic>」の scene10`, `scene10_cut01`, `この画像は物語「<topic>」の一場面`, or `後続 scene`.
            - If findings remain, return changes_requested with concrete missing assets or contract fixes so main can patch asset_plan.md and run the next review round.
            """
        ).strip()
    if stage == "scene_detail":
        return dedent(
            """
            Stage-specific review criteria:
            - Keep `maximal_meaningful` in force at the per-scene level: decide whether this scene should remain one scene, be split into multiple scenes, or be thickened with more cuts.
            - A split is required when a sub-beat has its own dramatic_question, value_shift, causal_turn, and visible evidence.
            - Cut thickening is preferred only when the added material supports the same scene question/value shift/causal turn.
            - Judge whether the proposed cut count can carry this scene in a final 5-10 minute video.
            - Estimate the scene's needed duration from total scene count, scene importance, reveal weight, and emotional weight.
            - Treat one cut as roughly 4-15 seconds; explicitly flag that a one-cut scene can only carry about 4-15 seconds.
            - Check whether every piece of content that must be shown in this scene is represented by planned cuts.
            - Review the next scene as context. Decide whether the current scene's final cut connects to the next scene.
            - If the final cut does not connect, recommend either adding one more cut or thickening the final cut.
            - Return concrete add/thicken/delete recommendations that main can auto-apply.
            """
        ).strip()
    if stage == "cut_blueprint":
        return dedent(
            """
            Stage-specific review criteria:
            - Apply the cut density contract after p410 scenes are approved: every production scene must have enough cuts to make its scene_spine visible.
            - One cut must carry one intent only (one viewer-facing intent). If a cut contains location change, reveal, emotional reversal, explanation, reaction, and next-scene handoff together, return changes_requested.
            - Important beats such as transformation, discovery, confrontation, emotional reversal, and proof reveal must be split into setup / pressure or threshold / turn or payoff / reaction / handoff as appropriate.
            - Require a coverage plan that maps scene obligations to cuts: dramatic_question, value_shift.visible_evidence, causal_turn, reveal constraints, audience information, and handoff_to_next_scene.
            - first_frame_contract must describe a startable still just before motion begins; it must not be a completed action or production metadata.
            - motion_contract is p800-only. p600 image prompt authoring must not read it or summarize future motion into the still prompt.
            - p420 must still ensure motion_contract can start from first_frame_contract without inventing a new story event, but that compatibility check belongs to cut/video planning, not image prompt authoring.
            - viewer_contract, cinematic_contract, continuity_contract, narration_contract, downstream_handoff, and triangulation_review must be concrete enough for p600 image, p700 narration, and p800 motion to verify.
            - The final cut of each scene must hand off to the next scene or terminal resolution through visible action, object, gaze, sound, or causal pressure.
            """
        ).strip()
    if stage == "production_readiness":
        return dedent(
            """
            Stage-specific review criteria:
            - This p435 council runs after p430 script review and before p440 human changes / narration sync.
            - Structure Auditor: inspect story structure, scene order, causality, setup/payoff, scene-to-scene flow, and whether the script skeleton breaks before production.
            - Duration Auditor: estimate runtime from scene and cut counts for a 5-10 minute video, using one cut as roughly 4-15 seconds; identify undersized scenes or missing cuts.
            - Duration Auditor must compare `video_manifest.md.video_metadata.target_duration_seconds` with the sum of production cut durations. Do not defer this judgment to p700.
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
    focus = REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE.get(stage, {}).get(critic_number)
    focus_name = ""
    if focus is not None:
        focus_name, focus_guidance = focus
        stage_guidance = "\n\n".join(
            part
            for part in (
                stage_guidance,
                dedent(
                    f"""
                    Critic focus for this prompt:
                    - role: {focus_name}
                    - responsibility: {focus_guidance}
                    - You may mention findings outside this focus, but prioritize this role and make its pass/fail judgment explicit.
                    """
                ).strip(),
            )
            if part
        )
    focus_output_line = f"- critic_focus: {focus_name}\n        " if focus_name else ""
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
        {REVIEW_CAUSAL_ANALYSIS_GUIDANCE}
        {guidance_block}
        Return markdown for `{own_report}` with:
        {focus_output_line}- status: passed|changes_requested
        - blocking_findings[]: each item must include id, severity, evidence, root_cause, downstream_impact, fix_direction, acceptance_condition
        - recommended_changes[]: each item must include cause, fix_direction, acceptance_condition
        - rejected_suggestions[]
        - generator_patch_brief: target files/sections, concrete edits, reason, acceptance condition
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
    stage_guidance = ""
    if stage in REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE:
        roles = "\n".join(
            f"- critic_{idx}: {name}"
            for idx, (name, _) in sorted(REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE[stage].items())
        )
        if stage in SCENE_REVIEW_CRITIC_FOCUS:
            stage_guidance = dedent(
                f"""
                Stage-specific aggregation rule:
                {roles}
                For p410 scene review, do not pass until the `maximal_meaningful`
                scene count stop condition is explicit: name the next plausible scene
                candidate, and explain why it should be rejected in favor of cut
                thickening. If critic_1 has an unresolved scene_count_coverage blocker,
                the aggregate status must be changes_requested.
                """
            ).strip()
        elif stage == "cut_blueprint":
            stage_guidance = dedent(
                f"""
                Stage-specific aggregation rule:
                {roles}
                For p420 cut review, do not pass until the cut blueprint gate is explicit:
                each cut has one intent, the beat ladder covers the scene spine, coverage_plan maps
                scene obligations to cuts, first_frame_contract and motion_contract are startable,
                viewer/cinematic/continuity/narration/downstream fields are concrete, triangulation
                review is ready, and cut density/handoff are sufficient. If critic_1 has an unresolved
                cut_intent_isolation blocker, the aggregate status must be changes_requested.
                """
            ).strip()
    guidance_block = f"\n\n{stage_guidance}" if stage_guidance else ""
    return dedent(
        f"""
        You are the aggregator in the ToC {spec.title}.

        Wait until all {REVIEW_LOOP_CRITIC_COUNT} critic reports exist, then read:
        {critic_paths}

        Do not edit source artifacts. Consolidate duplicate findings, resolve contradictory
        {handoff}
        Apply the same causal-analysis rule as the critics: every adopted blocker
        must name the essential cause, not only the failed check, and every clear
        fix must include a concrete fix plan and acceptance condition.
        {guidance_block}

        Write markdown suitable for `{aggregate_path}` and final summary `{final_path}` with:
        - status: passed|changes_requested
        - scene_count_gate: for p410 stages include maximal_meaningful_stop_condition, next_scene_candidate, cut_thickening_reason, and critic_1_scene_count_coverage_resolution
        - cut_blueprint_gate: for p420 cut_blueprint include cut_intent_isolation, beat_ladder_coverage, first_frame_motion_readiness, multimodal_contract_coverage, duration_density_and_handoff, coverage_plan_complete, continuity_contract_complete, narration_contract_complete, downstream_handoff_complete, and triangulation_review_ready
        - blocking_findings[]: each item must include id, severity, evidence, root_cause, downstream_impact, adopted_fix_plan, acceptance_condition
        - recommended_changes[]: each item must include cause, fix_plan, acceptance_condition
        - rejected_suggestions[]
        - {brief_label}: target files/sections, concrete edits, reason/root cause, acceptance condition
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
        "Aggregator must consolidate critic blockers here. Each adopted blocker must include evidence, root cause, downstream impact, fix plan, and acceptance condition. Use an empty list only when status is passed.",
        "",
        "## Recommended Changes",
        "",
        "Aggregator must list non-blocking quality improvements here, including cause, fix direction, and acceptance condition when the fix is clear.",
        "",
        "## Rejected Suggestions",
        "",
        "Aggregator must list rejected critic suggestions and why they were not adopted.",
        "",
    ]
    if stage in SCENE_REVIEW_CRITIC_FOCUS:
        sections.extend(
            [
                "## Scene Count Gate",
                "",
                "- maximal_meaningful_stop_condition: TODO",
                "- next_scene_candidate: TODO",
                "- cut_thickening_reason: TODO",
                "- critic_1_scene_count_coverage_resolution: TODO",
                "",
            ]
        )
    if stage == "cut_blueprint":
        sections.extend(
            [
                "## Cut Blueprint Gate",
                "",
                "- cut_intent_isolation: TODO",
                "- beat_ladder_coverage: TODO",
                "- first_frame_motion_readiness: TODO",
                "- multimodal_contract_coverage: TODO",
                "- duration_density_and_handoff: TODO",
                "- coverage_plan_complete: TODO",
                "- continuity_contract_complete: TODO",
                "- narration_contract_complete: TODO",
                "- downstream_handoff_complete: TODO",
                "- triangulation_review_ready: TODO",
                "",
            ]
        )
    sections.extend(
        [
            f"## {patch_brief_heading}",
            "",
            f"{patch_brief_text} Include target files/sections, concrete edits, root cause being fixed, and acceptance condition.",
            "",
            "## Round Summary",
            "",
            "Aggregator must summarize the essential causes found in this round, which fixes are clear, and why the loop can stop or must continue.",
        ]
    )
    for idx, report in enumerate(critic_reports, start=1):
        sections.extend(["", f"## Critic {idx} Input", "", report.strip()])
    return "\n".join(sections).rstrip() + "\n"
