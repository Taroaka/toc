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
    - Apply semantic QA at every stage. A file that exists and matches schema can
      still fail if its meaning is wrong: wrong subject, wrong location, wrong
      object, wrong timeline, broken reveal order, or references assigned only
      to satisfy counts. Reviewers must judge whether the artifact is a
      meaningful downstream translation of its source artifacts.
    """
).strip()


SCENE_REVIEW_CRITIC_FOCUS: dict[str, dict[int, tuple[str, str]]] = {
    "scene_set": {
        1: (
            "scene_count_coverage",
            "Verify that the approved story beats are expanded to the maximal meaningful scene count. "
            "Block approval if a non-compressible beat with its own dramatic question, value shift, and causal turn is buried inside another scene. "
            "Check non_compressible_beat_inventory and scene_promotion_rule explicitly.",
        ),
        2: (
            "dramatic_structure_and_reveal_order",
            "Verify that each scene has an independent dramatic question, value shift, causal turn, and unique_scene_responsibility, "
            "and that scene additions or splits do not break reveal order or fall back to generic template language.",
        ),
        3: (
            "duration_density",
            "Verify whether scene count, target duration, importance, and planned cut density are sufficient for the target video length. "
            "Decide where scene splitting is better than cut thickening.",
        ),
        4: (
            "visual_production",
            "Verify that every proposed scene can hand visible evidence, actor_force_coverage, object_meaning_ladder, visual thesis, "
            "and asset/image/video requirements to p500/p600/p800.",
        ),
        5: (
            "handoff_integrity",
            "Verify concrete_handoff_chain scene-to-scene causality: each scene ending must visibly or audibly generate the next scene's starting pressure or question.",
        ),
    },
    "scene_detail": {
        1: (
            "scene_detail_structure",
            "Verify this scene's necessity, non-compressible beat, promotion reason, internal logic, independent dramatic question/value shift/causal turn, scene_event setup/pressure/turn/payoff sequence, scene_generation prompt separation, and story-specific concrete grounding within the maximal scene set.",
        ),
        2: (
            "scene_detail_density",
            "Verify this scene's cut count, target duration, emotional weight, and whether to add cuts or split the scene.",
        ),
        3: (
            "scene_detail_handoff",
            "Verify incoming and outgoing concrete handoff with neighboring scenes, including the final cut's ability to trigger the next scene.",
        ),
        4: (
            "scene_detail_reveal_order",
            "Verify that scene_event reveal constraints neither reveal future information too early nor omit information the audience needs here.",
        ),
        5: (
            "scene_detail_visual_production",
            "Verify that this scene's visible evidence, visual thesis, asset story functions, and p500/p600/p800 handoff are concrete enough for production without decorative detail.",
        ),
    },
}

SCENE_SPECIFICITY_GATE_MARKERS: tuple[str, ...] = (
    "## Scene Specificity Gate",
    "non_compressible_beat_inventory",
    "scene_promotion_rule",
    "unique_scene_responsibility",
    "actor_force_coverage",
    "object_meaning_ladder",
    "concrete_handoff_chain",
    "anti_template_language",
)

SCENE_COUNT_GATE_MARKERS: tuple[str, ...] = (
    "## Scene Count Gate",
    "maximal_meaningful_stop_condition",
    "next_scene_candidate",
    "cut_thickening_reason",
    "critic_1_scene_count_coverage_resolution",
)

SCENE_SET_REVEAL_ORDER_GATE_MARKERS: tuple[str, ...] = (
    "## Reveal Order Gate",
    "reveal_order_preserved",
    "withheld_information_preserved",
    "early_reveal_risk_resolved",
)

SCENE_SET_HANDOFF_CHAIN_GATE_MARKERS: tuple[str, ...] = (
    "## Handoff Chain Gate",
    "handoff_chain_coverage",
    "incoming_outgoing_anchor_ids",
    "terminal_resolution_checked",
)

SCENE_SET_GATE_MARKERS: tuple[str, ...] = (
    SCENE_COUNT_GATE_MARKERS
    + SCENE_SPECIFICITY_GATE_MARKERS
    + SCENE_SET_REVEAL_ORDER_GATE_MARKERS
    + SCENE_SET_HANDOFF_CHAIN_GATE_MARKERS
)

SCENE_DETAIL_GATE_MARKERS: tuple[str, ...] = (
    "## Scene Detail Gate",
    "scene_necessity",
    "internal_pressure",
    "value_shift_visibility",
    "causal_turn_visibility",
    "scene_event_sequence",
    "scene_generation_prompt_separation",
    "scene_generation_debug_source",
    "scene_generation_contract",
    "turning_event_alignment",
    "end_situation_alignment",
    "neighbor_handoff",
)

CUT_BLUEPRINT_CRITIC_FOCUS: dict[int, tuple[str, str]] = {
    1: (
        "cut_intent_isolation",
        "Verify that each cut carries exactly one viewer-facing intent and does not combine location move, reveal, emotional reversal, explanation, reaction, and next-scene handoff in one cut.",
    ),
    2: (
        "scene_event_coverage",
        "Verify that cuts cover scene_event.event_sequence by visual necessity through cut_contract.source_event_contract, not top-level legacy refs or a fixed cut_function sequence.",
    ),
    3: (
        "first_frame_motion_readiness",
        "Verify that first_frame_contract aligns with source_event_contract, remains a startable p600 still input, and motion_contract remains p800-only without crossing event beat boundaries.",
    ),
    4: (
        "multimodal_event_boundary_coverage",
        "Verify that viewer/cinematic/continuity/narration/downstream fields are concrete and all p600/p700/p800 handoffs use the derived event_context_for_cut from source_event_contract.",
    ),
    5: (
        "duration_density_and_handoff",
        "Verify cut count, duration intent, importance-based density, continuity between cuts, final-cut handoff, downstream handoff readiness for p500/p600/p700/p800, and that duplicate story meaning thickens prompts instead of adding redundant cuts.",
    ),
}

CUT_BLUEPRINT_GATE_MARKERS: tuple[str, ...] = (
    "## Cut Blueprint Gate",
    "cut_intent_isolation",
    "scene_event_coverage",
    "event_beat_reference_integrity",
    "first_frame_motion_readiness",
    "event_first_frame_alignment",
    "multimodal_event_boundary_coverage",
    "source_event_preservation",
    "no_unapproved_event_invention",
    "event_motion_boundary",
    "event_narration_boundary",
    "event_context_for_cut_ready",
    "causal_proof_coverage",
    "role_coverage",
    "audience_knowledge_delta_coverage",
    "anti_redundancy_gate",
    "duration_density_and_handoff",
    "coverage_plan_complete",
    "continuity_contract_complete",
    "character_emotion_continuity_complete",
    "film_grammar_contract_complete",
    "action_reaction_and_eyeline_complete",
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
        slot_codes=("p420",),
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
            - Before scene count approval, require the seven scene specificity layers: non_compressible_beat_inventory, scene_promotion_rule, unique_scene_responsibility, actor_force_coverage, object_meaning_ladder, concrete_handoff_chain, and anti_template_language.
            - Reject generic placeholders such as `主人公は前進できるか`, `次へ進む理由が生まれる`, `光が次の場面へ運ぶ`, `価値変化の兆し`, `場所の圧力`, and `主人公の姿勢と視線`.
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
            - Semantic QA: verify that asset_id, asset_type, story_purpose, visual_spec, request prompt, and generated output category all describe the same thing. Character assets must be people, object assets must be the intended object, and location assets must be places rather than character portraits.
            - Semantic QA: verify that source_script_selectors[] list the cuts where the asset is meaningfully used. Do not approve round-robin location assignment or always-on object references that place a story-specific item into unrelated scenes.
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
            - Verify the seven scene specificity layers for this concrete scene: non-compressible beat, promotion reason, unique responsibility, actor forces, object/setpiece meaning stage, concrete handoff, and anti-template language.
            - Cut thickening is preferred only when the added material supports the same scene question/value shift/causal turn.
            - Judge whether the proposed cut count can carry this scene in a final 5-10 minute video.
            - Estimate the scene's needed duration from total scene count, scene importance, reveal weight, and emotional weight.
            - Treat one cut as roughly 4-15 seconds; explicitly flag that a one-cut scene can only carry about 4-15 seconds.
            - Check whether every piece of content that must be shown in this scene is represented by planned cuts.
            - Semantic QA: verify that the scene's location, time, subject state, object visibility, and reveal order match the story/script meaning rather than merely using valid ids.
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
            - Semantic QA: every cut must preserve the scene meaning it claims to carry. Block cuts whose visual beat, asset dependency hint, narration role, or first-frame contract points to a different place, time, subject, or story object than the target beat.
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
        if stage == "scene_set":
            stage_guidance = dedent(
                f"""
                Stage-specific aggregation rule:
                {roles}
                For p410b scene-set review, do not pass until the `maximal_meaningful`
                scene count stop condition is explicit: name the next plausible scene
                candidate, and explain why it should be rejected in favor of cut
                thickening. If critic_1 has an unresolved scene_count_coverage blocker,
                the aggregate status must be changes_requested.
                Also require the `Scene Specificity Gate`: non_compressible_beat_inventory,
                scene_promotion_rule, unique_scene_responsibility, actor_force_coverage,
                object_meaning_ladder, concrete_handoff_chain, and anti_template_language.
                Also require `Reveal Order Gate` and `Handoff Chain Gate`, because a
                larger scene set only improves quality when reveal order and scene-to-scene
                causality remain intact. These are blocking gate items, not optional
                reviewer advice.
                """
            ).strip()
        elif stage == "scene_detail":
            stage_guidance = dedent(
                f"""
                Stage-specific aggregation rule:
                {roles}
                For p410c scene-detail review, do not repeat the scene count gate.
                This review must pass a `Scene Detail Gate` for each concrete scene:
                scene_necessity, internal_pressure, value_shift_visibility,
                causal_turn_visibility, scene_event_sequence, story_specific_grounding,
                non_replaceable_elements, concrete_story_function, specificity_budget,
                canonical_event_coverage, scene_generation_prompt_separation,
                scene_generation_debug_source, scene_generation_contract, turning_event_alignment,
                end_situation_alignment, and neighbor_handoff. The scene_event checks
                must verify that turning_event semantically matches scene_intent.causal_turn
                and end_situation semantically matches scene_intent.value_shift.to.
                The scene_generation checks must treat scene_generation.scene_prompt_payload.prompt
                as the canonical scene authoring prompt and fail if it mixes downstream
                image/video/audio execution fields, fixed cut counts, or image directing terms.
                scene_debug_prompt_source must explain source beats, adaptation choices, and
                forbidden changes without being sent to the generation agent.
                Do not reject useful abstract dramatic language by itself; reject only when
                abstract_function is not paired with source-grounded concrete_event /
                story_grounding. Decorative concrete detail without story_function is a blocker.
                Treat these as blocking gate items, not optional reviewer advice.
                """
            ).strip()
        elif stage == "cut_blueprint":
            stage_guidance = dedent(
                f"""
                Stage-specific aggregation rule:
                {roles}
                For p420 cut review, do not pass until the cut blueprint gate is explicit:
                each cut has one intent, every cut references scene_event beat ids,
                cuts cover setup/pressure/turn/payoff through cut_contract.source_event_contract,
                no cut invents unapproved events, story_event_obligations are legacy projection only,
                audience_knowledge_delta and causal_proof are concrete, required roles are not
                collapsed into protagonist-only imagery, anti-redundancy is checked, first_frame_contract
                and motion_contract are separated, viewer/cinematic/continuity/narration/downstream
                fields are concrete, triangulation review is ready, and cut density/handoff are sufficient.
                If critic_1 has an unresolved
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
        - scene_count_gate: for scene_set include maximal_meaningful_stop_condition, next_scene_candidate, cut_thickening_reason, and critic_1_scene_count_coverage_resolution
        - scene_specificity_gate: for scene_set include non_compressible_beat_inventory, scene_promotion_rule, unique_scene_responsibility, actor_force_coverage, object_meaning_ladder, concrete_handoff_chain, and anti_template_language
        - reveal_order_gate: for scene_set include reveal_order_preserved, withheld_information_preserved, and early_reveal_risk_resolved
        - handoff_chain_gate: for scene_set include handoff_chain_coverage, incoming_outgoing_anchor_ids, and terminal_resolution_checked
        - scene_detail_gate: for scene_detail include scene_necessity, internal_pressure, value_shift_visibility, causal_turn_visibility, scene_event_sequence, scene_generation_prompt_separation, scene_generation_debug_source, scene_generation_contract, scene_character_state_timeline, scene_film_coverage_plan, turning_event_alignment, end_situation_alignment, and neighbor_handoff
        - cut_blueprint_gate: for p420 cut_blueprint include cut_intent_isolation, scene_event_coverage, event_beat_reference_integrity, first_frame_motion_readiness, event_first_frame_alignment, multimodal_event_boundary_coverage, source_event_preservation, no_unapproved_event_invention, event_motion_boundary, event_narration_boundary, event_context_for_cut_ready, causal_proof_coverage, role_coverage, audience_knowledge_delta_coverage, anti_redundancy_gate, duration_density_and_handoff, coverage_plan_complete, continuity_contract_complete, character_emotion_continuity_complete, film_grammar_contract_complete, action_reaction_and_eyeline_complete, narration_contract_complete, downstream_handoff_complete, and triangulation_review_ready
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
    if stage == "scene_set":
        sections.extend(
            [
                "## Scene Count Gate",
                "",
                "- maximal_meaningful_stop_condition: satisfied",
                "- next_scene_candidate: candidate_rejected_after_review",
                "- cut_thickening_reason: scene count is expanded until adding cuts is better than splitting scenes",
                "- critic_1_scene_count_coverage_resolution: passed",
                "",
                "## Scene Specificity Gate",
                "",
                "- non_compressible_beat_inventory: story events that cannot be compressed are inventoried before scene approval",
                "- scene_promotion_rule: each promoted scene must own an irreversible story event rather than atmosphere only",
                "- unique_scene_responsibility: each scene has a distinct dramatic question, value shift, causal turn, and audience knowledge delta",
                "- actor_force_coverage: protagonist, opponent, helper, witness, and community roles are covered when the story event requires them",
                "- object_meaning_ladder: artifacts are introduced, withheld, transformed, lost, or proven according to their story function",
                "- concrete_handoff_chain: each scene ending leaves physical evidence or a visible cause for the next scene",
                "- anti_template_language: generic light/direction/pressure language is rejected unless tied to concrete causal proof",
                "",
                "## Reveal Order Gate",
                "",
                "- reveal_order_preserved: scene additions and splits preserve the approved reveal order",
                "- withheld_information_preserved: future-only information remains withheld until its approved scene",
                "- early_reveal_risk_resolved: no new scene leaks payoff evidence early",
                "",
                "## Handoff Chain Gate",
                "",
                "- handoff_chain_coverage: every scene ending leaves a visible or audible cause for the next scene",
                "- incoming_outgoing_anchor_ids: each handoff uses concrete anchor ids or a terminal marker",
                "- terminal_resolution_checked: final scene resolves through terminal_resolution instead of a fake next scene",
                "",
            ]
        )
    if stage == "scene_detail":
        sections.extend(
            [
                "## Scene Detail Gate",
                "",
                "- scene_necessity: each scene owns a non-compressible beat within the approved scene set",
                "- internal_pressure: each scene has visible pressure that escalates before the turn",
                "- value_shift_visibility: value_shift.from/to is proven by visible evidence",
                "- causal_turn_visibility: the irreversible turn is visible or audibly grounded",
                "- scene_event_sequence: scene_event has setup, pressure, turn, and payoff as concrete story events",
                "- scene_generation_prompt_separation: scene_generation.scene_prompt_payload.prompt is the canonical scene authoring prompt and does not include downstream execution fields, image directing terms, or fixed cut counts",
                "- scene_generation_debug_source: scene_debug_prompt_source explains source beats, adaptation choices, excluded payload details, and forbidden changes without being sent to the agent",
                "- scene_generation_contract: scene_generation_contract requires scene_intent, scene_event, scene_character_state_timeline, scene_film_coverage_plan, scene_cut_coverage_plan, and forbidden_event_changes",
                "- story_specific_grounding: each event beat has abstract_function plus concrete_event and story_grounding derived from source story, user input, canonical reference, or asset bible",
                "- non_replaceable_elements: each beat declares the character/object/location/relationship/rule/event elements that make it non-replaceable",
                "- concrete_story_function: concrete details and asset usage have story_function; decorative detail without story function fails",
                "- specificity_budget: concrete detail stays within the declared specificity budget",
                "- canonical_event_coverage: required source/canonical/user-input events are assigned to scene ids and scene_event beat ids",
                "- scene_character_state_timeline: each major character has start/mid/end states with face/gaze/posture/hands/feet/distance visible proof tied to scene_event beats",
                "- scene_film_coverage_plan: shot_mix, action_reaction_pair, missing_coverage, and reaction/insert/eyeline/silence required_when rules are present",
                "- turning_event_alignment: turning_event semantically matches scene_intent.causal_turn",
                "- end_situation_alignment: end_situation semantically matches scene_intent.value_shift.to",
                "- neighbor_handoff: incoming and outgoing handoffs connect to adjacent scenes",
                "",
            ]
        )
    if stage == "cut_blueprint":
        sections.extend(
            [
                "## Cut Blueprint Gate",
                "",
                "- cut_intent_isolation: each cut has one viewer-facing intent",
                "- scene_event_coverage: scene_event beats are assigned from visual necessity through source_event_contract",
                "- event_beat_reference_integrity: primary_event_beat_id, source_event_beat_ids, event_beat_function, and event_time_position match scene_event",
                "- first_frame_motion_readiness: first_frame_contract is static p600 evidence and motion_contract remains p800-only",
                "- event_first_frame_alignment: first_frame_contract.source_event_beat_id and event_fact_visible_in_still match the primary event beat",
                "- multimodal_event_boundary_coverage: viewer/cinematic/continuity/narration/downstream fields are concrete and p600/p700/p800 event boundaries are respected",
                "- source_event_preservation: source_event_contract preserves event facts and reveal boundaries",
                "- no_unapproved_event_invention: cuts preserve event_facts_to_preserve and do not invent event_facts_not_to_invent",
                "- event_motion_boundary: motion starts from the first frame and does not advance to forbidden event beat ids",
                "- event_narration_boundary: narration stays within event and reveal boundaries",
                "- event_context_for_cut_ready: event_context_for_cut is a non-editable derived projection from source_event_contract",
                "- causal_proof_coverage: each cut states how cause and result are visible in the frame",
                "- role_coverage: protagonist, opponent, helper, witness, and community roles are covered when the scene event requires them",
                "- audience_knowledge_delta_coverage: each cut states what the audience newly understands",
                "- anti_redundancy_gate: repeated story meaning is handled by prompt reinforcement instead of duplicate cuts",
                "- duration_density_and_handoff: cut count, duration density, and final handoff are sufficient",
                "- coverage_plan_complete: scene_cut_coverage_plan maps obligations to cuts",
                "- continuity_contract_complete: continuity states and carry-forward items are concrete",
                "- character_emotion_continuity_complete: cut_character_emotion_transition has transition_mode, trigger beat ref, visible behavior, and no final-emotion jump",
                "- film_grammar_contract_complete: cut_film_grammar_contract separates required_modules and conditional_modules and keeps audience_emotion_target separate from character emotion",
                "- action_reaction_and_eyeline_complete: turn/reveal/payoff cuts include reaction contracts, edit motivation, eyeline/attention continuity, and motivated screen direction",
                "- narration_contract_complete: narration role or silence reason is concrete",
                "- downstream_handoff_complete: p500/p600/p700/p800 requirements are present",
                "- triangulation_review_ready: cut contract can be checked across image, narration, motion, and scene composite review",
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
