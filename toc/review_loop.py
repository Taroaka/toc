"""Contracts for authoring-stage evaluator improvement loops."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from toc.review_projection import (
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    ReviewProjectionError,
    review_source_fingerprint,
)


MAX_REVIEW_LOOP_ROUNDS = 5
REVIEW_LOOP_CRITIC_COUNT = 5
REVIEW_INPUT_SNAPSHOT_VERSION = "review_input_snapshot_v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
    - Scene-level `importance`, `target_duration_seconds`, and `estimated_duration_seconds` are optional planning annotations;
      their absence alone is non-blocking. When present, use them only as advisory evidence.
    - Do not require a fixed cut count or fixed beat-function ladder. Scene-set size follows
      the upstream story/duration contract and maximal-meaningful review, not beat labels.
    - Propose a new scene or cut only for an uncovered distinct semantic obligation.
      If the content carries the same obligation, thicken or re-split existing cut
      boundaries without increasing the count.
    - Keep canonical scene meaning contracts (`dramatic_question`, `value_shift`,
      `causal_turn`, and adjacent-scene handoff) required. Do not infer a required
      `beat_function` from example labels such as setup, pressure, turn, payoff,
      reaction, or handoff; a required `scene_intent.causal_turn` does not require
      a `beat_function` label named `turn`.
    """
).strip()


SCENE_REVIEW_CRITIC_FOCUS: dict[str, dict[int, tuple[str, str]]] = {
    "scene_set": {
        1: (
            "scene_count_coverage",
            "Verify that the approved story beats are expanded to the maximal meaningful scene count. "
            "Block approval when a non-compressible beat with an uncovered distinct semantic obligation and its own dramatic question, value shift, and causal turn is buried inside another scene. "
            "Check non_compressible_beat_inventory and scene_promotion_rule explicitly.",
        ),
        2: (
            "dramatic_structure_and_reveal_order",
            "Verify that each scene has an independent dramatic question, value shift, causal turn, and unique_scene_responsibility, "
            "and that scene additions or splits do not break reveal order or fall back to generic template language.",
        ),
        3: (
            "duration_density",
            "Verify duration risk against available planning annotations, provider capability, and distinct semantic obligations without deriving a cut-count floor from importance or duration. "
            "Treat importance, target_duration_seconds, and estimated_duration_seconds as optional advisory evidence whose absence alone is non-blocking. "
            "Decide where a distinct scene responsibility warrants splitting and where an existing cut should be thickened.",
        ),
        4: (
            "visual_production",
            "Verify that every proposed scene can hand visible evidence, actor_force_coverage, object_meaning_ladder, visual thesis, "
            "and asset/image/video requirements to p500/p600/p800.",
        ),
        5: (
            "handoff_integrity",
            "Verify concrete_handoff_chain scene-to-scene causality: each scene ending must visibly or audibly generate the next scene's authored starting condition. This required handoff contract does not imply a beat_function label named handoff, pressure, or question.",
        ),
    },
    "scene_detail": {
        1: (
            "scene_detail_structure",
            "Verify this scene's necessity, non-compressible beat, promotion reason, internal logic, independent dramatic question/value shift/causal turn, exact authored event_beat_inventory / scene_event.event_sequence beat IDs (including must_be_seen=false opt-outs), arbitrary nonblank beat_function values, scene_generation prompt separation, and story-specific concrete grounding within the maximal scene set. scene_intent.causal_turn remains required, but does not require a beat_function label named turn. Treat setup, pressure, turn, payoff, threshold, and custom as examples only; a valid one-beat custom scene does not require the other labels.",
        ),
        2: (
            "scene_detail_density",
            "When scene-level importance, target_duration_seconds, or estimated_duration_seconds annotations are present, use them as advisory evidence against provider capability and distinct semantic obligations; their absence alone is non-blocking. Authored emotional weight remains review evidence. Add or split only for an uncovered distinct semantic obligation; a fully covered one-beat scene may remain one cut.",
        ),
        3: (
            "scene_detail_handoff",
            "Verify incoming and outgoing concrete handoff with neighboring scenes, including the final cut's ability to trigger the next scene. This semantic handoff contract does not require a beat_function label named handoff.",
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
    "story_specific_grounding",
    "non_replaceable_elements",
    "concrete_story_function",
    "specificity_budget",
    "canonical_event_coverage",
    "scene_character_state_timeline",
    "scene_film_coverage_plan",
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
        "Verify that the exact authored event_beat_inventory mirrors all ordered scene_event.event_sequence entries with nonblank beat IDs, including must_be_seen=false opt-outs, and that only beats marked must_be_seen != false require cut assignment through cut_contract.source_event_contract. Verify that each arbitrary nonblank beat_function matches its source beat, not top-level legacy refs or a fixed cut_function sequence. A valid one-beat scene must not fail for omitting example labels such as setup, pressure, turn, payoff, threshold, or custom.",
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
        "Verify duration intent against provider capability and distinct semantic obligations, continuity between cuts, final-cut handoff, downstream handoff readiness for p500/p600/p700/p800, and that importance or duplicate story meaning never creates filler cuts. Require an added cut only for an uncovered distinct semantic obligation; for the same obligation, thicken or re-split existing cut boundaries without increasing the count. The handoff contract does not require a beat_function label named handoff.",
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
        source_artifacts=("story.md", "visual_value.md", "script.md", "video_manifest.md"),
    ),
    "production_readiness": ReviewLoopSpec(
        stage="production_readiness",
        slot_codes=("p435",),
        title="Production Readiness Council",
        final_report="production_readiness_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md", "video_manifest.md"),
    ),
    "scene_set": ReviewLoopSpec(
        stage="scene_set",
        slot_codes=("p410b",),
        title="Scene Set Eval/Improve Loop",
        final_report="scene_set_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md", "video_manifest.md"),
    ),
    "scene_detail": ReviewLoopSpec(
        stage="scene_detail",
        slot_codes=("p410c",),
        title="Scene Detail Eval/Improve Loop",
        final_report="scene_detail_review.md",
        source_artifacts=("story.md", "visual_value.md", "script.md", "video_manifest.md"),
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
        source_artifacts=("story.md", "visual_value.md", "script.md", "video_manifest.md"),
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
        # run_report.md is the review output.  Keeping it in source_artifacts
        # made QA overwrite the artifact that critics had just reviewed.
        source_artifacts=("eval_report.json", "video.mp4"),
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


def review_input_snapshot_relpath(stage: str, round_number: int) -> Path:
    return round_rel_dir(stage, round_number) / "review_input_snapshot.json"


def _review_readset_stage(stage: str) -> str:
    if stage in {"scene_set", "scene_detail", "scene_intent", "cut_blueprint", "production_readiness"}:
        return "script"
    for prefix in ("scene_implementation", "video_generation"):
        if stage.startswith(prefix):
            return prefix
    return stage


def _review_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained_review_source(run_dir: Path, raw_relpath: str) -> tuple[Path | None, str | None]:
    relpath = Path(raw_relpath)
    if relpath.is_absolute() or not relpath.parts or ".." in relpath.parts:
        return None, f"unsafe review source path: {raw_relpath}"
    resolved_run_dir = run_dir.resolve()
    candidate = resolved_run_dir / relpath
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_run_dir)
    except (FileNotFoundError, OSError, ValueError):
        return None, f"missing or escaped review source: {raw_relpath}"
    if not resolved.is_file():
        return None, f"review source is not a file: {raw_relpath}"
    return resolved, None


def build_review_input_snapshot(*, run_dir: Path, stage: str, round_number: int) -> dict[str, Any]:
    """Capture the exact source revision that one review round is allowed to approve."""

    normalize_round(round_number)
    if stage not in REVIEW_LOOP_SPECS:
        raise ValueError(f"unknown review-loop stage: {stage}")
    resolved_run_dir = run_dir.resolve()
    sources: list[dict[str, Any]] = []
    for raw_relpath in REVIEW_LOOP_SPECS[stage].source_artifacts:
        source_path, issue = _contained_review_source(resolved_run_dir, raw_relpath)
        if issue or source_path is None:
            raise FileNotFoundError(issue or raw_relpath)
        fingerprint = review_source_fingerprint(
            source_path,
            artifact_relpath=Path(raw_relpath).as_posix(),
            review_kind="review_loop",
            stage=stage,
        )
        sources.append(
            {
                "path": Path(raw_relpath).as_posix(),
                "sha256": fingerprint.sha256,
                "size_bytes": fingerprint.size_bytes,
                REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD: fingerprint.policy,
            }
        )

    readset_relpath = Path("logs") / "grounding" / f"{_review_readset_stage(stage)}.readset.json"
    readset: dict[str, Any] | None = None
    readset_candidate = resolved_run_dir / readset_relpath
    if readset_candidate.exists():
        readset_path, issue = _contained_review_source(resolved_run_dir, readset_relpath.as_posix())
        if issue or readset_path is None:
            raise ValueError(issue or readset_relpath.as_posix())
        readset = {
            "path": readset_relpath.as_posix(),
            "sha256": _review_file_sha256(readset_path),
            "size_bytes": readset_path.stat().st_size,
        }

    digest_payload = {
        "schema_version": REVIEW_INPUT_SNAPSHOT_VERSION,
        "stage": stage,
        "round": round_number,
        "source_artifacts": sources,
        "readset": readset,
    }
    input_digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**digest_payload, "input_digest": input_digest, "prompt_sha256s": {}}


def write_review_input_snapshot(
    *,
    run_dir: Path,
    stage: str,
    round_number: int,
    snapshot: dict[str, Any],
    prompt_relpaths: tuple[Path, ...] = (),
) -> Path:
    prompt_sha256s: dict[str, str] = {}
    for relpath in prompt_relpaths:
        prompt_path, issue = _contained_review_source(run_dir, relpath.as_posix())
        if issue or prompt_path is None:
            raise FileNotFoundError(issue or relpath.as_posix())
        prompt_sha256s[relpath.as_posix()] = _review_file_sha256(prompt_path)
    payload = dict(snapshot)
    payload["prompt_sha256s"] = prompt_sha256s
    path = run_dir.resolve() / review_input_snapshot_relpath(stage, round_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def review_input_snapshot_issues(*, run_dir: Path, stage: str, round_number: int) -> list[str]:
    """Return currentness/provenance errors for a materialized review round."""

    relpath = review_input_snapshot_relpath(stage, round_number)
    path = run_dir.resolve() / relpath
    if not path.exists():
        return [f"missing review input snapshot: {relpath.as_posix()}"]
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"invalid review input snapshot: {exc}"]
    issues: list[str] = []
    if snapshot.get("schema_version") != REVIEW_INPUT_SNAPSHOT_VERSION:
        issues.append("review input snapshot schema_version mismatch")
    if snapshot.get("stage") != stage or snapshot.get("round") != round_number:
        issues.append("review input snapshot stage/round mismatch")

    raw_sources = snapshot.get("source_artifacts")
    expected_paths = list(REVIEW_LOOP_SPECS[stage].source_artifacts)
    actual_paths = [str(item.get("path") or "") for item in raw_sources if isinstance(item, dict)] if isinstance(raw_sources, list) else []
    if actual_paths != expected_paths:
        issues.append(f"review input source inventory mismatch: expected={expected_paths}, got={actual_paths}")
    if isinstance(raw_sources, list):
        for item in raw_sources:
            if not isinstance(item, dict):
                issues.append("review input source entry must be an object")
                continue
            raw_relpath = str(item.get("path") or "")
            source_path, issue = _contained_review_source(run_dir, raw_relpath)
            if issue or source_path is None:
                issues.append(issue or f"invalid review source: {raw_relpath}")
                continue
            expected_hash = str(item.get("sha256") or "")
            if not _SHA256_RE.fullmatch(expected_hash):
                issues.append(f"invalid review source sha256: {raw_relpath}")
            else:
                raw_policy = item.get(
                    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
                )
                try:
                    fingerprint = review_source_fingerprint(
                        source_path,
                        artifact_relpath=Path(raw_relpath).as_posix(),
                        review_kind="review_loop",
                        stage=stage,
                    )
                except ReviewProjectionError as exc:
                    issues.append(
                        f"invalid review source projection: {raw_relpath}: {exc}"
                    )
                else:
                    if raw_policy is None:
                        # v1 snapshots created before fingerprint policies
                        # were explicit used exact source bytes. Accept them
                        # only while those exact bytes are still current.
                        current_hash = _review_file_sha256(source_path)
                    elif raw_policy != fingerprint.policy:
                        issues.append(
                            "review source fingerprint policy mismatch: "
                            f"{raw_relpath}"
                        )
                        continue
                    else:
                        current_hash = fingerprint.sha256
                    if current_hash != expected_hash:
                        issues.append(
                            f"stale review source sha256: {raw_relpath}"
                        )

    raw_readset = snapshot.get("readset")
    if raw_readset is not None:
        if not isinstance(raw_readset, dict):
            issues.append("review input readset must be an object or null")
        else:
            raw_relpath = str(raw_readset.get("path") or "")
            readset_path, issue = _contained_review_source(run_dir, raw_relpath)
            expected_hash = str(raw_readset.get("sha256") or "")
            if issue or readset_path is None:
                issues.append(issue or "invalid review input readset")
            elif not _SHA256_RE.fullmatch(expected_hash) or _review_file_sha256(readset_path) != expected_hash:
                issues.append(f"stale review readset sha256: {raw_relpath}")

    digest_payload = {
        "schema_version": snapshot.get("schema_version"),
        "stage": snapshot.get("stage"),
        "round": snapshot.get("round"),
        "source_artifacts": snapshot.get("source_artifacts"),
        "readset": snapshot.get("readset"),
    }
    expected_digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if snapshot.get("input_digest") != expected_digest:
        issues.append("review input digest mismatch")
    prompt_sha256s = snapshot.get("prompt_sha256s")
    if not isinstance(prompt_sha256s, dict):
        issues.append("review input prompt_sha256s must be an object")
    else:
        expected_prompt_paths = [
            critic_prompt_relpath(stage, round_number, index).as_posix()
            for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
        ] + [aggregator_prompt_relpath(stage, round_number).as_posix()]
        if list(prompt_sha256s) != expected_prompt_paths:
            issues.append(
                "review prompt inventory mismatch: "
                f"expected={expected_prompt_paths}, got={list(prompt_sha256s)}"
            )
        for raw_relpath, expected_hash in prompt_sha256s.items():
            prompt_path, issue = _contained_review_source(run_dir, str(raw_relpath))
            if issue or prompt_path is None:
                issues.append(issue or f"invalid review prompt: {raw_relpath}")
            elif not _SHA256_RE.fullmatch(str(expected_hash)) or _review_file_sha256(prompt_path) != expected_hash:
                issues.append(f"stale review prompt sha256: {raw_relpath}")
    return issues


def review_input_digest(*, run_dir: Path, stage: str, round_number: int) -> str:
    path = run_dir.resolve() / review_input_snapshot_relpath(stage, round_number)
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("input_digest")
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"cannot load review input digest: {exc}") from exc
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError("review input snapshot has invalid input_digest")
    return value


def review_guidance_for_stage(stage: str) -> str:
    if stage == "scene_set":
        return dedent(
            """
            Stage-specific review criteria:
            - Apply `maximal_meaningful` scene count strategy: do not approve a compressed scene set while an approved story beat can stand as its own production scene.
            - A beat deserves its own scene only when it introduces an uncovered distinct semantic obligation with its own dramatic_question, value_shift, causal_turn, and visible evidence.
            - Before scene count approval, require the seven scene specificity layers: non_compressible_beat_inventory, scene_promotion_rule, unique_scene_responsibility, actor_force_coverage, object_meaning_ladder, concrete_handoff_chain, and anti_template_language.
            - Reject generic placeholders such as `主人公は前進できるか`, `次へ進む理由が生まれる`, `光が次の場面へ運ぶ`, `価値変化の兆し`, `場所の圧力`, and `主人公の姿勢と視線`.
            - The stop condition is not a fixed scene count. Pass only when the next plausible scene would repeat an existing authored semantic obligation and cut thickening would improve quality more than another scene.
            - Always name the next scene candidate that could be added. If you reject it, explain why it belongs inside existing scene cuts instead.
            - Each scene ending must visibly or audibly generate the next scene's authored starting condition. This handoff requirement does not require a beat_function label named pressure, question, turn, payoff, reaction, or handoff.
            - Check story coverage, scene order, reveal order, visual production handoff, and scene-to-scene causality. Consider scene-level target_duration_seconds only when supplied; it is advisory and its absence alone is non-blocking.
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
            - Add or split a scene only when a sub-beat introduces an uncovered distinct semantic obligation. If it carries the same scene responsibility, thicken or re-split existing cut boundaries without increasing the count.
            - Verify the seven scene specificity layers for this concrete scene: non-compressible beat, promotion reason, unique responsibility, actor forces, object/setpiece meaning stage, concrete handoff, and anti-template language.
            - Cut thickening is preferred when the added material supports the same scene question/value shift/causal turn rather than introducing a distinct semantic obligation.
            - Judge whether the proposed cut count can carry this scene in a final 5-10 minute video.
            - `importance`, `target_duration_seconds`, and `estimated_duration_seconds` are optional planning annotations; their absence alone is non-blocking. When present, use them only as advisory evidence alongside authored reveal/emotional weight.
            - Evaluate cut duration against the selected provider/model/input-mode capability and semantic density. Do not derive a cut-count floor from a fixed seconds-per-cut estimate.
            - Require event_beat_inventory to be the exact ordered mirror of every authored scene_event.event_sequence entry with a nonblank ID, including must_be_seen=false opt-outs. Only entries with must_be_seen != false require cut assignment, and each arbitrary nonblank beat_function must match its source.
            - Check whether every canonical scene meaning contract and authored semantic obligation that must be shown is represented by planned cuts. scene_intent.causal_turn remains required, but it does not require a beat_function label named turn; likewise do not infer setup, pressure, payoff, reaction, or handoff function labels.
            - A valid one-beat scene may remain one cut when its must_be_seen != false beat plus distinct visual obligations are fully covered; importance alone does not require filler cuts.
            - Semantic QA: verify that the scene's location, time, subject state, object visibility, and reveal order match the story/script meaning rather than merely using valid ids.
            - Review the next scene as context. Decide whether the current scene's final cut connects to the next scene through the canonical handoff contract.
            - If the outgoing handoff is uncovered, add a cut only when it is an authored, uncovered distinct semantic obligation; otherwise thicken the existing final cut without increasing the count.
            - Return concrete add/thicken/delete recommendations that main can auto-apply.
            """
        ).strip()
    if stage == "cut_blueprint":
        return dedent(
            """
            Stage-specific review criteria:
            - Apply the cut density contract after p410 scenes are approved: every production scene must have enough cuts to make its scene_spine visible.
            - One cut must carry one intent only (one viewer-facing intent). If a cut contains location change, reveal, emotional reversal, explanation, reaction, and next-scene handoff together, return changes_requested.
            - The exact authored event_beat_inventory must be the ordered mirror of every authored scene_event.event_sequence entry with a nonblank ID, including must_be_seen=false opt-outs. Only entries with must_be_seen != false require cut assignment. Preserve each arbitrary nonblank beat_function from its source beat.
            - Split important beats such as transformation, discovery, confrontation, emotional reversal, and proof reveal only when they introduce uncovered distinct visual obligations; distinct visual obligations require separate cuts. For the same obligation, thicken or re-split existing cut boundaries without increasing the count. setup, pressure, turn, payoff, threshold, custom, reaction, and handoff are example labels, not a required ladder; a valid one-beat scene may keep one custom function.
            - Add a cut only for an uncovered distinct semantic obligation; a new label, optional duration annotation, or importance value is not sufficient by itself.
            - Require a coverage plan that maps canonical scene obligations to cuts: dramatic_question, value_shift.visible_evidence, causal_turn, reveal constraints, audience information, reaction when required by the event, and handoff_to_next_scene. This does not require fixed beat_function labels.
            - Semantic QA: every cut must preserve the scene meaning it claims to carry. Block cuts whose visual beat, asset dependency hint, narration role, or first-frame contract points to a different place, time, subject, or story object than the target beat.
            - first_frame_contract must describe a startable still just before motion begins; it must not be a completed action or production metadata.
            - motion_contract is p800-only. p600 image prompt authoring must not read it or summarize future motion into the still prompt.
            - p420 must still ensure motion_contract can start from first_frame_contract without inventing a new story event, but that compatibility check belongs to cut/video planning, not image prompt authoring.
            - viewer_contract, cinematic_contract, continuity_contract, narration_contract, downstream_handoff, and triangulation_review must be concrete enough for p600 image, p700 narration, and p800 motion to verify.
            - The final cut of each scene must carry the canonical handoff to the next scene or terminal resolution through visible action, object, gaze, sound, or causal pressure; this does not require a beat_function label named handoff.
            """
        ).strip()
    if stage == "production_readiness":
        return dedent(
            """
            Stage-specific review criteria:
            - This p435 council runs after p430 script review and before p440 human changes / narration sync.
            - Structure Auditor: inspect story structure, scene order, causality, setup/payoff, scene-to-scene flow, and whether the script skeleton breaks before production. Do not interpret setup/payoff here as required beat_function labels.
            - Duration Auditor: estimate runtime from scene/cut plans and selected provider/model/input-mode capability for a 5-10 minute video; identify duration risk without deriving a cut-count floor from a fixed seconds-per-cut estimate. Scene-level `importance`, `target_duration_seconds`, and `estimated_duration_seconds` are optional planning annotations whose absence alone is non-blocking.
            - Duration Auditor must compare required `video_manifest.md.video_metadata.target_duration_seconds` with the sum of production cut durations. Do not defer this judgment to p700. This global runtime contract is distinct from optional scene-level duration annotations.
            - Quality Auditor: propose a new scene or cut only when it introduces an uncovered distinct semantic obligation, including an authored event beat that creates such an obligation. For the same obligation, thicken or re-split existing cut boundaries instead of increasing the count; otherwise prefer duration allocation, clearer visuals, and stronger production handoffs.
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
    if status == "passed" and current_round < 1:
        raise ValueError("passed review loop requires at least one completed round")

    canonical_report = final_review_relpath(stage)
    report_path = Path(final_report) if final_report is not None else canonical_report
    if report_path.is_absolute() or ".." in report_path.parts or report_path != canonical_report:
        raise ValueError(f"final_report must be the canonical run-relative path: {canonical_report}")
    report = report_path.as_posix()
    return {
        f"eval.{stage}.loop.status": status,
        f"eval.{stage}.loop.current_round": str(current_round),
        f"eval.{stage}.loop.max_rounds": str(MAX_REVIEW_LOOP_ROUNDS),
        f"eval.{stage}.loop.final_report": report,
    }


def render_critic_prompt(
    *,
    run_dir: Path,
    stage: str,
    round_number: int,
    critic_number: int,
    input_digest: str | None = None,
) -> str:
    spec = REVIEW_LOOP_SPECS[stage]
    readset_stage = _review_readset_stage(stage)
    digest = input_digest or build_review_input_snapshot(
        run_dir=run_dir, stage=stage, round_number=round_number
    )["input_digest"]
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ValueError("input_digest must be a SHA-256 hex digest")
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
        Review input digest: `{digest}`

        Read these source artifacts directly:
        {source_paths}
        - `{readset_path.resolve()}`

        Work independently. Do not read other critic reports and do not edit files.
        {REVIEW_CAUSAL_ANALYSIS_GUIDANCE}
        {guidance_block}
        Return markdown for `{own_report}` with:
        - critic_id: critic_{critic_number}
        - review_input_digest: {digest}
        {focus_output_line}- status: passed|changes_requested
        - blocking_findings[]: each item must include id, severity, evidence, root_cause, downstream_impact, fix_direction, acceptance_condition
        - recommended_changes[]: each item must include cause, fix_direction, acceptance_condition
        - rejected_suggestions[]
        - generator_patch_brief: target files/sections, concrete edits, reason, acceptance condition
        - round_summary
        """
    ).strip()


def render_aggregator_prompt(
    *, run_dir: Path, stage: str, round_number: int, input_digest: str | None = None
) -> str:
    spec = REVIEW_LOOP_SPECS[stage]
    digest = input_digest or build_review_input_snapshot(
        run_dir=run_dir, stage=stage, round_number=round_number
    )["input_digest"]
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise ValueError("input_digest must be a SHA-256 hex digest")
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
                causality remain intact. These canonical meaning contracts are blocking,
                but they do not require beat_function labels named pressure, turn, or handoff.
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
                must verify the exact ordered mirror of all authored scene_event entries,
                including must_be_seen=false opt-outs, while requiring cut assignment only
                for must_be_seen != false entries. Every arbitrary nonblank beat_function
                must exactly match its corresponding authored source beat. scene_intent.causal_turn
                remains required, but does not require a beat_function label named turn; likewise
                do not infer setup, pressure, payoff, reaction, or handoff labels. turning_event must
                semantically match scene_intent.causal_turn and end_situation must semantically match
                scene_intent.value_shift.to.
                The scene_generation checks must treat scene_generation.scene_prompt_payload.prompt
                as the canonical scene authoring prompt and fail if it mixes downstream
                image/video/audio execution fields, fixed cut counts, or image directing terms.
                scene_debug_prompt_source must explain source beats, adaptation choices, and
                forbidden changes without being sent to the generation agent.
                Do not reject useful abstract dramatic language by itself; reject only when
                an arbitrary nonblank beat_function is not paired with source-grounded concrete_event /
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
                the exact authored event_beat_inventory mirrors all ordered scene_event.event_sequence entries
                with nonblank beat ids, including must_be_seen=false opt-outs,
                only beats marked must_be_seen != false require assignment through cut_contract.source_event_contract, every arbitrary nonblank
                beat_function matches its source beat, and a valid one-beat scene is not rejected for
                omitting example labels such as setup, pressure, turn, payoff, threshold, or custom,
                no cut invents unapproved events, story_event_obligations are legacy projection only,
                audience_knowledge_delta and causal_proof are concrete, required roles are not
                collapsed into protagonist-only imagery, anti-redundancy is checked, first_frame_contract
                and motion_contract are separated, viewer/cinematic/continuity/narration/downstream
                fields are concrete, triangulation review is ready, and cut density/handoff are sufficient.
                These canonical obligations do not require fixed beat_function labels such as
                pressure, turn, payoff, reaction, or handoff.
                Add a cut only for an uncovered distinct semantic obligation; otherwise thicken or re-split
                existing cut boundaries without increasing the count.
                If critic_1 has an unresolved
                cut_intent_isolation blocker, the aggregate status must be changes_requested.
                """
            ).strip()
    guidance_block = f"\n\n{stage_guidance}" if stage_guidance else ""
    return dedent(
        f"""
        You are the aggregator in the ToC {spec.title}.

        Review input digest: `{digest}`

        Wait until all {REVIEW_LOOP_CRITIC_COUNT} critic reports exist, then read:
        {critic_paths}

        Do not edit source artifacts. Consolidate duplicate findings, resolve contradictory
        {handoff}
        Apply the same causal-analysis rule as the critics: every adopted blocker
        must name the essential cause, not only the failed check, and every clear
        fix must include a concrete fix plan and acceptance condition.
        {REVIEW_CAUSAL_ANALYSIS_GUIDANCE}
        {guidance_block}

        Write markdown suitable for `{aggregate_path}` and final summary `{final_path}` with:
        - review_input_digest: {digest}
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


def _review_report_scalar(report: str, key: str) -> str:
    match = re.search(rf"(?mi)^-?\s*{re.escape(key)}\s*:\s*`?([^`\n]+?)`?\s*$", report)
    return match.group(1).strip() if match else ""


def review_critic_report_issues(
    *, critic_reports: list[str], expected_input_digest: str | None = None
) -> tuple[list[str], str, list[str]]:
    """Validate critic identity, source revision, and status before aggregation."""

    issues: list[str] = []
    identities: list[str] = []
    digests: list[str] = []
    statuses: list[str] = []
    for index, report in enumerate(critic_reports, start=1):
        critic_id = _review_report_scalar(report, "critic_id")
        digest = _review_report_scalar(report, "review_input_digest")
        status = _review_report_scalar(report, "status").lower().replace(" ", "_")
        identities.append(critic_id)
        digests.append(digest)
        statuses.append(status)
        expected_id = f"critic_{index}"
        if critic_id != expected_id:
            issues.append(f"critic report {index} identity mismatch: expected={expected_id}, got={critic_id or '(missing)'}")
        if not _SHA256_RE.fullmatch(digest):
            issues.append(f"critic report {index} has invalid review_input_digest")
        if status not in {"passed", "changes_requested"}:
            issues.append(f"critic report {index} has invalid status: {status or '(missing)'}")
    if len(set(identities)) != len(identities):
        issues.append("critic report identities must be unique")
    valid_digests = [value for value in digests if _SHA256_RE.fullmatch(value)]
    resolved_digest = valid_digests[0] if valid_digests else ""
    if valid_digests and any(value != resolved_digest for value in valid_digests):
        issues.append("critic reports do not share one review_input_digest")
    if expected_input_digest is not None:
        if not _SHA256_RE.fullmatch(expected_input_digest):
            issues.append("expected_input_digest is invalid")
        elif any(value != expected_input_digest for value in digests):
            issues.append("critic report digest does not match the materialized review input")
        resolved_digest = expected_input_digest
    derived_status = "passed" if statuses and all(value == "passed" for value in statuses) else "changes_requested"
    return issues, derived_status, statuses


def render_aggregated_review(
    *,
    stage: str,
    round_number: int,
    critic_reports: list[str],
    status: str | None = None,
    expected_input_digest: str | None = None,
) -> str:
    normalize_round(round_number)
    if len(critic_reports) != REVIEW_LOOP_CRITIC_COUNT:
        raise ValueError(f"expected {REVIEW_LOOP_CRITIC_COUNT} critic reports, got {len(critic_reports)}")
    report_issues, derived_status, _critic_statuses = review_critic_report_issues(
        critic_reports=critic_reports,
        expected_input_digest=expected_input_digest,
    )
    if report_issues:
        raise ValueError("invalid critic reports: " + "; ".join(report_issues))
    if status is None:
        status = derived_status
    if status not in {"passed", "changes_requested"}:
        raise ValueError(f"invalid aggregated review status: {status}")
    if status == "passed" and derived_status != "passed":
        raise ValueError("aggregated review cannot pass while any critic requests changes")
    resolved_digest = expected_input_digest or _review_report_scalar(critic_reports[0], "review_input_digest")

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
        f"- review_input_digest: {resolved_digest}",
        "- critic_report_sha256s:",
        *[
            f"  - critic_{idx}: {hashlib.sha256(report.encode('utf-8')).hexdigest()}"
            for idx, report in enumerate(critic_reports, start=1)
        ],
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
                "- cut_thickening_reason: add a scene only for an uncovered distinct semantic obligation; otherwise thicken or re-split existing cut boundaries without increasing the count",
                "- critic_1_scene_count_coverage_resolution: passed",
                "",
                "## Scene Specificity Gate",
                "",
                "- non_compressible_beat_inventory: story events that cannot be compressed are inventoried before scene approval",
                "- scene_promotion_rule: each promoted scene must own an uncovered distinct semantic obligation and irreversible story event rather than atmosphere only",
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
                "- early_reveal_risk_resolved: no new scene leaks future authored evidence early",
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
                "- internal_pressure: evaluate visible pressure escalation only when the authored scene semantics require it; do not infer required pressure/turn beat_function labels",
                "- value_shift_visibility: value_shift.from/to is proven by visible evidence",
                "- causal_turn_visibility: scene_intent.causal_turn remains required and is visible or audibly grounded without requiring a beat_function label named turn",
                "- scene_event_sequence: scene_event and event_beat_inventory contain the same exact ordered authored nonblank beat IDs, including must_be_seen=false opt-outs; only beats with must_be_seen != false require cut assignment, each arbitrary nonblank beat_function is preserved, and no fixed setup/pressure/turn/payoff/reaction/handoff function labels are inferred",
                "- scene_generation_prompt_separation: scene_generation.scene_prompt_payload.prompt is the canonical scene authoring prompt and does not include downstream execution fields, image directing terms, or fixed cut counts",
                "- scene_generation_debug_source: scene_debug_prompt_source explains source beats, adaptation choices, excluded payload details, and forbidden changes without being sent to the agent",
                "- scene_generation_contract: scene_generation_contract requires scene_intent, scene_event, scene_character_state_timeline, scene_film_coverage_plan, scene_cut_coverage_plan, and forbidden_event_changes",
                "- story_specific_grounding: each event beat has an arbitrary nonblank beat_function plus concrete_event and story_grounding derived from source story, user input, canonical reference, or asset bible",
                "- non_replaceable_elements: each beat declares the character/object/location/relationship/rule/event elements that make it non-replaceable",
                "- concrete_story_function: concrete details and asset usage have story_function; decorative detail without story function fails",
                "- specificity_budget: concrete detail stays within the declared specificity budget",
                "- canonical_event_coverage: required source/canonical/user-input events are assigned to scene ids and scene_event beat ids",
                "- scene_character_state_timeline: each major character has start/mid/end states with face/gaze/posture/hands/feet/distance visible proof tied to scene_event beats",
                "- scene_film_coverage_plan: shot_mix, action_reaction_pair, missing_coverage, and reaction/insert/eyeline/silence required_when rules are present",
                "- turning_event_alignment: turning_event semantically matches scene_intent.causal_turn without requiring a beat_function label named turn",
                "- end_situation_alignment: end_situation semantically matches scene_intent.value_shift.to",
                "- neighbor_handoff: incoming and outgoing handoffs connect to adjacent scenes without requiring a beat_function label named handoff",
                "",
            ]
        )
    if stage == "cut_blueprint":
        sections.extend(
            [
                "## Cut Blueprint Gate",
                "",
                "- cut_intent_isolation: each cut has one viewer-facing intent",
                "- scene_event_coverage: event_beat_inventory mirrors every exact ordered nonblank scene_event beat ID and beat_function, including must_be_seen=false opt-outs, while only beats with must_be_seen != false require assignment from visual necessity through source_event_contract",
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
                "- duration_density_and_handoff: provider-capable duration, distinct semantic-obligation coverage, and final handoff are sufficient without an importance- or duration-derived cut floor; scene-level importance, target_duration_seconds, and estimated_duration_seconds are optional advisory annotations whose absence alone is non-blocking; an added cut requires an uncovered distinct obligation, otherwise thicken or re-split existing cut boundaries without increasing the count",
                "- coverage_plan_complete: scene_cut_coverage_plan maps obligations to cuts",
                "- continuity_contract_complete: continuity states and carry-forward items are concrete",
                "- character_emotion_continuity_complete: cut_character_emotion_transition has transition_mode, trigger beat ref, visible behavior, and no final-emotion jump",
                "- film_grammar_contract_complete: cut_film_grammar_contract separates required_modules and conditional_modules and keeps audience_emotion_target separate from character emotion",
                "- action_reaction_and_eyeline_complete: authored beats whose semantics require a reaction (for example turn, reveal, or payoff) include reaction contracts, edit motivation, eyeline/attention continuity, and motivated screen direction; those function names are not required",
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
    if status == "changes_requested":
        blocking_markers: tuple[str, ...] = ()
        if stage == "scene_set":
            blocking_markers = SCENE_SET_GATE_MARKERS
        elif stage == "scene_detail":
            blocking_markers = SCENE_DETAIL_GATE_MARKERS
        elif stage == "cut_blueprint":
            blocking_markers = CUT_BLUEPRINT_GATE_MARKERS
        marker_names = {value for value in blocking_markers if not value.startswith("##")}
        sections = [
            (
                f"- {line.split(':', 1)[0].removeprefix('- ').strip()}: changes_requested; "
                "re-evaluate after critic blockers are resolved"
            )
            if line.startswith("- ")
            and ":" in line
            and line.split(":", 1)[0].removeprefix("- ").strip() in marker_names
            else line
            for line in sections
        ]
    return "\n".join(sections).rstrip() + "\n"
