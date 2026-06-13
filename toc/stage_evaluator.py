"""Reusable stage evaluator helpers for research/story/script/manifest/video reviews."""

from __future__ import annotations

import shutil
import subprocess
import re
from pathlib import Path
from typing import Any

from toc.grounding import grounding_validation
from toc.harness import append_state_snapshot, load_structured_document, parse_state_file
from toc.immersive_manifest import dotted_id_sort_key, make_scene_cut_selector, normalize_dotted_id
from toc.review_loop import (
    CUT_BLUEPRINT_GATE_MARKERS,
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE,
    SCENE_DETAIL_GATE_MARKERS,
    SCENE_SET_GATE_MARKERS,
)

EVENT_TIME_POSITION_VALUES = {
    "before_trigger",
    "trigger_moment",
    "early_action",
    "mid_action",
    "consequence",
    "reaction_after",
    "handoff_after",
}


STAGE_RUBRIC_WEIGHTS = {
    "research": {
        "source_grounding": 0.25,
        "coverage": 0.20,
        "conflict_readiness": 0.20,
        "structure_readiness": 0.15,
        "story_material_readiness": 0.20,
    },
    "story": {
        "selection_readiness": 0.20,
        "scene_density": 0.30,
        "grounding_boundary": 0.20,
        "affect_readiness": 0.15,
        "handoff_readiness": 0.15,
    },
    "script": {
        "arc_coverage": 0.25,
        "scene_specificity": 0.20,
        "reference_grounding": 0.20,
        "anti_todo": 0.15,
        "production_readiness": 0.20,
    },
    "manifest": {
        "beat_clarity": 0.25,
        "visual_specificity": 0.20,
        "continuity_readiness": 0.20,
        "narration_alignment": 0.15,
        "production_readiness": 0.20,
    },
    "video": {
        "render_integrity": 0.25,
        "asset_completeness": 0.20,
        "review_readiness": 0.15,
        "audio_packaging": 0.20,
        "publish_readiness": 0.20,
    },
}

STAGE_RUBRIC_THRESHOLDS = {
    "research": {
        "source_grounding": 0.60,
        "coverage": 0.60,
        "conflict_readiness": 0.55,
        "structure_readiness": 0.60,
        "story_material_readiness": 0.60,
    },
    "story": {
        "selection_readiness": 0.70,
        "scene_density": 0.85,
        "grounding_boundary": 0.80,
        "affect_readiness": 0.80,
        "handoff_readiness": 0.80,
    },
    "script": {
        "arc_coverage": 0.60,
        "scene_specificity": 0.60,
        "reference_grounding": 0.55,
        "anti_todo": 0.70,
        "production_readiness": 0.60,
    },
    "manifest": {
        "beat_clarity": 0.60,
        "visual_specificity": 0.60,
        "continuity_readiness": 0.60,
        "narration_alignment": 0.55,
        "production_readiness": 0.60,
    },
    "video": {
        "render_integrity": 0.70,
        "asset_completeness": 0.60,
        "review_readiness": 0.60,
        "audio_packaging": 0.55,
        "publish_readiness": 0.60,
    },
}

CINEMATIC_SCENE_MIN_CUTS = 3
CINEMATIC_LOW_IMPORTANCE_MIN_CUTS = 2
CINEMATIC_HIGH_IMPORTANCE_MIN_CUTS = 5
CINEMATIC_CRITICAL_IMPORTANCE_MIN_CUTS = 7
CINEMATIC_SECONDS_PER_CUT_TARGET = 8
GENERIC_SCENE_TEMPLATE_PHRASES: tuple[str, ...] = (
    "主人公は前進できるか",
    "次へ進む理由が生まれる",
    "光が次の場面へ運ぶ",
    "価値変化の兆し",
    "場所の圧力",
    "主人公の姿勢と視線",
    "主人公が変化する",
    "次の展開につながる",
    "感情が動く",
    "状況が悪くなる",
    "何かが起きる",
    "物語が進む",
)
GENERIC_HANDOFF_ONLY_PHRASES: tuple[str, ...] = (
    "次へ",
    "つながる",
    "進む",
    "次の場面",
    "次の展開",
)
UNRESOLVED_GATE_VALUES: set[str] = {
    "todo",
    "tbd",
    "pending",
    "...",
    "changes_requested",
    "failed",
    "missing",
    "unclear",
    "none",
    "null",
    "n/a",
    "なし",
    "不明",
    "未定",
    "不足",
    "",
}
SCENE_COVERAGE_REVIEW_REQUIRED_KEYS: tuple[str, ...] = (
    "audience_information_covered",
    "visualizable_action_covered",
    "value_shift_visible",
    "causal_turn_visible",
    "scene_specificity_gate_passed",
    "next_scene_connection_checked",
)
MOTION_LEAK_TOKENS: tuple[str, ...] = (
    "motion_brief",
    "p800",
    "動画生成",
    "カメラが動く",
    "このあと",
    "end_state",
)
TRIANGULATION_REQUIRED_KEYS: tuple[str, ...] = (
    "same_target_beat",
    "image_supports_motion_start",
    "motion_reaches_declared_end_state",
    "narration_not_captioning_image",
    "reveal_constraints_preserved",
    "continuity_preserved",
    "handoff_visible_or_audible",
)
REQUIRED_SCENE_EVENT_BEAT_FUNCTIONS: tuple[str, ...] = ("setup", "pressure", "turn", "payoff")
FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS: tuple[str, ...] = (
    "cut_id",
    "camera",
    "shot",
    "lens",
    "framing",
    "image_prompt",
    "video_prompt",
    "motion_prompt",
)


def has_todo(text: str) -> bool:
    upper = text.upper()
    return "TODO" in upper or "TBD" in upper


def non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return value is not None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def as_dotted_str(value: Any) -> str | None:
    return normalize_dotted_id(value)


def nested_get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(flatten_text(v) for v in value)
    return ""


def flatten_without_keys(value: Any, *, excluded: set[str]) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_without_keys(v, excluded=excluded) for k, v in value.items() if str(k) not in excluded)
    if isinstance(value, list):
        return "\n".join(flatten_without_keys(v, excluded=excluded) for v in value)
    return ""


def contract_list(contract: dict[str, Any], key: str) -> list[str]:
    value = contract.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _contract_value(contract: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        cur: Any = contract
        ok = True
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and non_empty(cur):
            return cur
    return None


def _contract_string(contract: dict[str, Any], *paths: str) -> str:
    value = _contract_value(contract, *paths)
    return str(value).strip() if value is not None else ""


def _contract_list_paths(contract: dict[str, Any], *paths: str) -> list[str]:
    for path in paths:
        value = _contract_value(contract, path)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return []


def _node_cut_contract(node: dict[str, Any], *, allow_legacy: bool = True) -> dict[str, Any]:
    value = node.get("cut_contract") if isinstance(node, dict) else None
    if isinstance(value, dict) and value:
        return value
    if not allow_legacy:
        return {}
    for key in ("scene_contract", "cut_blueprint"):
        value = node.get(key) if isinstance(node, dict) else None
        if isinstance(value, dict) and value:
            return value
    return {}


def _cut_contract_complete(contract: dict[str, Any]) -> bool:
    if not isinstance(contract, dict) or not contract:
        return False
    source_contract = _cut_source_event_contract(contract)
    return (
        non_empty(_contract_string(contract, "cut_function"))
        and non_empty(_contract_string(source_contract, "primary_event_beat_id"))
        and non_empty(_contract_string(contract, "target_beat", "viewer_contract.target_beat"))
        and non_empty(_contract_string(contract, "visual_beat", "viewer_contract.visual_proof"))
        and non_empty(_contract_string(contract, "first_frame_brief", "first_frame_contract.first_frame_brief"))
        and non_empty(_contract_string(contract, "motion_brief", "motion_contract.motion_brief"))
        and non_empty(_contract_string(contract, "narration_role", "narration_contract.role"))
        and bool(_contract_list_paths(source_contract, "source_event_beat_ids"))
        and bool(_contract_list_paths(contract, "must_show", "viewer_contract.must_show"))
        and bool(_contract_list_paths(contract, "done_when", "viewer_contract.done_when"))
    )


def _cut_source_event_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict) or _contract_string(contract, "schema_version") != "3.0":
        return {}
    nested = as_dict(contract.get("source_event_contract"))
    return nested


def _cut_primary_event_beat_id(contract: dict[str, Any]) -> str:
    return _contract_string(_cut_source_event_contract(contract), "primary_event_beat_id")


def _cut_source_event_beat_ids(contract: dict[str, Any]) -> list[str]:
    return _contract_list_paths(_cut_source_event_contract(contract), "source_event_beat_ids")


def _cut_contract_structure_issues(contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(contract, dict) or not contract:
        return ["cut_contract:missing"]
    source_contract = _cut_source_event_contract(contract)
    if _contract_string(contract, "schema_version") != "3.0":
        issues.append("schema_version:3.0")
    if not source_contract:
        issues.append("source_event_contract")
    required_strings = (
        ("cut_function", "cut_function"),
        ("viewer_contract.target_beat", "target_beat", "viewer_contract.target_beat"),
        ("viewer_contract.screen_question", "screen_question", "viewer_contract.screen_question"),
        ("viewer_contract.dramatic_job", "dramatic_job", "viewer_contract.dramatic_job"),
        ("viewer_contract.audience_knowledge_delta", "audience_knowledge_delta", "viewer_contract.audience_knowledge_delta"),
        ("viewer_contract.causal_proof", "causal_proof", "viewer_contract.causal_proof"),
        ("viewer_contract.anti_redundancy_key", "anti_redundancy_key", "viewer_contract.anti_redundancy_key"),
        ("viewer_contract.visual_proof", "visual_beat", "viewer_contract.visual_proof"),
        ("first_frame_contract.first_frame_brief", "first_frame_brief", "first_frame_contract.first_frame_brief"),
        ("first_frame_contract.source_event_beat_id", "first_frame_contract.source_event_beat_id"),
        ("first_frame_contract.event_time_position", "first_frame_contract.event_time_position"),
        ("first_frame_contract.event_fact_visible_in_still", "first_frame_contract.event_fact_visible_in_still"),
        ("first_frame_contract.action_completion_state", "action_completion_state", "first_frame_contract.action_completion_state"),
        ("first_frame_contract.static_first_frame_rule", "static_first_frame_rule", "first_frame_contract.static_first_frame_rule"),
        ("motion_contract.motion_brief", "motion_brief", "motion_contract.motion_brief"),
        ("motion_contract.source_event_beat_id", "motion_contract.source_event_beat_id"),
        ("motion_contract.end_state", "motion_end_state", "motion_contract.end_state"),
        ("narration_contract.role", "narration_role", "narration_contract.role"),
        ("narration_contract.target_function", "narration_target_function", "narration_contract.target_function"),
    )
    for label, *paths in required_strings:
        if not non_empty(_contract_string(contract, *paths)):
            issues.append(label)

    required_lists = (
        ("viewer_contract.visual_evidence", "visual_evidence", "viewer_contract.visual_evidence"),
        ("viewer_contract.required_roles", "required_roles", "viewer_contract.required_roles"),
        ("viewer_contract.must_show", "must_show", "viewer_contract.must_show"),
        ("viewer_contract.done_when", "done_when", "viewer_contract.done_when"),
        ("motion_contract.must_not_add", "motion_contract.must_not_add"),
        ("narration_contract.source_event_beat_ids", "narration_contract.source_event_beat_ids"),
        ("narration_contract.must_avoid", "narration_contract.must_avoid"),
    )
    allow_empty_list_labels = {
        "motion_contract.must_not_advance_to_event_beat_ids",
        "narration_contract.must_not_advance_to_event_beat_ids",
    }
    for label, *paths in required_lists:
        if label in allow_empty_list_labels:
            if not any(isinstance(nested_get(contract, path.split(".")), list) for path in paths):
                issues.append(label)
        elif not _contract_list_paths(contract, *paths):
            issues.append(label)
    for label in ("primary_event_beat_id", "event_beat_function", "event_time_position", "source_event_summary", "source_visible_action"):
        if not non_empty(source_contract.get(label)):
            issues.append(f"source_event_contract.{label}")
    if not non_empty(source_contract.get("source_visible_reaction")) and not non_empty(source_contract.get("no_reaction_required_reason")):
        issues.append("source_event_contract.source_visible_reaction")
    if not _contract_list_paths(source_contract, "source_event_beat_ids"):
        issues.append("source_event_contract.source_event_beat_ids")
    if _contract_string(source_contract, "event_time_position") not in EVENT_TIME_POSITION_VALUES:
        issues.append("source_event_contract.event_time_position.enum")
    for label in ("source_required_visual_evidence", "event_facts_to_preserve", "event_facts_not_to_invent", "allowed_reveal_info_ids", "forbidden_reveal_info_ids"):
        if label not in source_contract or not isinstance(source_contract.get(label), list):
            issues.append(f"source_event_contract.{label}")

    first_frame = as_dict(contract.get("first_frame_contract"))
    if first_frame.get("imageable") is not True:
        issues.append("first_frame_contract.imageable")
    if first_frame.get("must_be_static_evidence_not_motion") is not True:
        issues.append("first_frame_contract.must_be_static_evidence_not_motion")
    if _contract_string(first_frame, "event_time_position") not in EVENT_TIME_POSITION_VALUES:
        issues.append("first_frame_contract.event_time_position.enum")
    if not isinstance(first_frame.get("visible_start_state"), dict) or not first_frame.get("visible_start_state"):
        issues.append("first_frame_contract.visible_start_state")
    if not isinstance(first_frame.get("motion_start_affordance"), dict) or not first_frame.get("motion_start_affordance"):
        issues.append("first_frame_contract.motion_start_affordance")

    motion_contract = as_dict(contract.get("motion_contract"))
    if motion_contract.get("starts_from_first_frame") is not True:
        issues.append("motion_contract.starts_from_first_frame")
    if "must_not_advance_to_event_beat_ids" not in motion_contract or not isinstance(motion_contract.get("must_not_advance_to_event_beat_ids"), list):
        issues.append("motion_contract.must_not_advance_to_event_beat_ids")
    if not non_empty(motion_contract.get("start_from_visible_state")):
        issues.append("motion_contract.start_from_visible_state")
    if not non_empty(motion_contract.get("end_frame_brief")):
        issues.append("motion_contract.end_frame_brief")

    role = _contract_string(contract, "narration_contract.role", "narration_role").lower()
    if role == "silent" and not non_empty(_contract_string(contract, "narration_contract.silence_reason", "silence_reason")):
        issues.append("narration_contract.silence_reason")
    narration = as_dict(contract.get("narration_contract"))
    for key in ("allowed_info_ids", "forbidden_info_ids", "must_not_advance_to_event_beat_ids"):
        if key not in narration or not isinstance(narration.get(key), list):
            issues.append(f"narration_contract.{key}")
    if narration.get("must_not_explain_visible_action_as_caption") is not True:
        issues.append("narration_contract.must_not_explain_visible_action_as_caption")
    if _contract_string(narration, "narration_event_boundary") not in {"same_event_only", "may_bridge_previous", "may_bridge_next_without_reveal"}:
        issues.append("narration_contract.narration_event_boundary")

    downstream = as_dict(contract.get("downstream_handoff"))
    downstream_required = {
        "p500_asset": ("required_asset_ids", "asset_candidates", "continuity_anchor_needed", "new_asset_needed", "reuse_allowed"),
        "p600_image": ("prompt_requirements", "reference_requirements", "first_frame_must_include", "first_frame_must_avoid"),
        "p700_narration": ("narration_requirements", "role", "must_not_caption_visible_content"),
        "p800_video": ("motion_requirements", "start_state", "last_frame_or_end_state", "must_not_add"),
    }
    for key, required_keys in downstream_required.items():
        section = downstream.get(key)
        if not isinstance(section, dict) or not section:
            issues.append(f"downstream_handoff.{key}")
            continue
        if not all(required_key in section for required_key in required_keys):
            issues.append(f"downstream_handoff.{key}")

    intent_budget = as_dict(contract.get("intent_budget"))
    if not intent_budget:
        issues.append("intent_budget")
    else:
        if not non_empty(intent_budget.get("primary_intent")):
            issues.append("intent_budget.primary_intent")
        assigned = intent_budget.get("assigned_obligation_ids")
        if not isinstance(assigned, list) or not assigned:
            issues.append("intent_budget.assigned_obligation_ids")
        elif len(assigned) > 3 and not non_empty(intent_budget.get("overload_exception_reason")):
            issues.append("cut_overloaded_multiple_beats")
        if str(contract.get("cut_function") or "").strip().lower() == "custom" and not non_empty(intent_budget.get("custom_function_reason")):
            issues.append("cut_function_custom_without_reason")

    rhythm_contract = as_dict(contract.get("rhythm_contract"))
    if not rhythm_contract:
        issues.append("rhythm_contract")
    else:
        for key in ("expected_duration_seconds", "pacing", "comprehension_moment", "cut_out_reason"):
            if not non_empty(rhythm_contract.get(key)):
                issues.append(f"rhythm_contract.{key}")
        duration = rhythm_contract.get("expected_duration_seconds")
        exception = as_dict(rhythm_contract.get("duration_exception"))
        if isinstance(duration, (int, float)) and duration > 12 and not non_empty(exception.get("reason")):
            issues.append("rhythm_contract.duration_exception.reason")

    asset_dependency = as_dict(contract.get("asset_dependency"))
    if not asset_dependency:
        issues.append("asset_dependency")
    else:
        if not isinstance(asset_dependency.get("character_ids_required"), list):
            issues.append("asset_dependency.character_ids_required")
        if not isinstance(asset_dependency.get("location_ids_required"), list):
            issues.append("asset_dependency.location_ids_required")
    return issues


def score_from_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 1.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, message: str, *, kind: str = "deterministic") -> None:
    checks.append({"id": check_id, "passed": passed, "kind": kind, "message": message})


def score_from_checks(checks: list[dict[str, Any]]) -> float:
    if not checks:
        return 0.0
    passed = sum(1 for check in checks if check["passed"])
    return round(passed / len(checks), 4)


def make_stage(
    stage: str,
    artifact: str,
    checks: list[dict[str, Any]],
    *,
    details: dict[str, Any] | None = None,
    rubric_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    score = score_from_checks(checks)
    rubric_scores = rubric_scores or {}
    overall_rubric = round(
        sum(rubric_scores.get(key, 0.0) * STAGE_RUBRIC_WEIGHTS[stage][key] for key in STAGE_RUBRIC_WEIGHTS.get(stage, {})),
        4,
    ) if rubric_scores else score
    return {
        "stage": stage,
        "artifact": artifact,
        "passed": all(check["passed"] for check in checks),
        "score": score,
        "overall_rubric": overall_rubric,
        "rubric_scores": rubric_scores,
        "reason_keys": [check["id"] for check in checks if not check["passed"]],
        "checks": checks,
        "details": details or {},
    }


def _append_grounding_checks(checks: list[dict[str, Any]], *, run_dir: Path, stage: str) -> None:
    validation = grounding_validation(run_dir, stage)
    report = validation.get("report") or {}
    report_path = validation.get("report_path")
    readset_path = validation.get("readset_path")
    audit_path = validation.get("audit_path")
    add_check(
        checks,
        f"{stage}.grounding_report",
        bool(validation.get("report_exists")),
        f"grounding report exists for {stage} (got {report_path or '(missing)'})",
        kind="rubric",
    )
    if validation.get("report_exists"):
        add_check(
            checks,
            f"{stage}.grounding_ready",
            bool(validation.get("report_ready")),
            f"grounding report status is ready (got {report.get('status', '(unset)')})",
            kind="rubric",
        )
    add_check(
        checks,
        f"{stage}.grounding_state",
        validation.get("state_status") == "ready",
        f"state records stage grounding as ready (got {validation.get('state_status') or '(unset)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.readset_report",
        bool(validation.get("readset_exists")),
        f"readset report exists for {stage} (got {readset_path or '(missing)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.audit_report",
        bool(validation.get("audit_exists")),
        f"audit report exists for {stage} (got {audit_path or '(missing)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.readset_state",
        bool(validation.get("state_readset")),
        f"state records readset report for {stage} (got {validation.get('state_readset') or '(unset)'})",
        kind="rubric",
    )
    if validation.get("audit_exists"):
        add_check(
            checks,
            f"{stage}.audit_passed",
            bool(validation.get("audit_passed")),
            f"audit report status is passed (got {(validation.get('audit') or {}).get('status', '(unset)')})",
            kind="rubric",
        )
    add_check(
        checks,
        f"{stage}.audit_state",
        validation.get("state_audit_status") == "passed",
        f"state records stage audit as passed (got {validation.get('state_audit_status') or '(unset)'})",
        kind="rubric",
    )


def detect_flow(run_dir: Path) -> str:
    if (run_dir / "scenes").exists():
        return "scene-series"
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _, data = load_structured_document(manifest_path)
        if nested_get(data, ["video_metadata", "experience"]):
            return "immersive"
    return "toc-run"


def _append_rubric_findings(*, checks: list[dict[str, Any]], stage: str, rubric_scores: dict[str, float]) -> None:
    for key, threshold in STAGE_RUBRIC_THRESHOLDS.get(stage, {}).items():
        passed = rubric_scores.get(key, 0.0) >= threshold
        add_check(checks, f"{stage}.rubric.{key}", passed, f"{key} rubric is >= {threshold:.2f} (got {rubric_scores.get(key, 0.0):.2f})", kind="rubric")


def _research_rubric(
    data: dict[str, Any],
    *,
    sources: list[Any],
    chronological_events: list[Any],
    beat_sheet: list[Any],
    source_passages: list[Any],
    facts: list[Any],
    handoff_to_story: Any,
    conflict_items: list[Any],
    conflict_topics: list[str],
) -> dict[str, float]:
    confidence = nested_get(data, ["metadata", "confidence_score"])
    confidence_score = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    event_count = len(chronological_events) or len(beat_sheet)
    canonical_story = nested_get(data, ["story_materials", "canonical_story_dump"]) or nested_get(
        data, ["story_baseline", "canonical_synopsis", "short_summary"]
    )
    compact_pack_ok = compact_research_pack_ok(
        sources=sources,
        passage_count=len(source_passages),
        canonical_story=canonical_story,
        conflict_items=conflict_items,
        handoff_to_story=handoff_to_story,
    )
    source_grounding = 1.0 if compact_pack_ok else score_from_ratio(len(sources), 12)
    event_coverage = 1.0 if compact_pack_ok else score_from_ratio(event_count, 20)
    fact_coverage = 1.0 if compact_pack_ok else score_from_ratio(len(facts), 30)
    passage_coverage = 1.0 if compact_pack_ok else score_from_ratio(len(source_passages), 10)
    material_readiness = round(
        (
            event_coverage
            + passage_coverage
            + fact_coverage
            + (1.0 if handoff_to_story else 0.0)
        )
        / 4,
        4,
    )
    return {
        "source_grounding": source_grounding,
        "coverage": round((event_coverage + fact_coverage) / 2, 4),
        "conflict_readiness": round((1.0 if conflict_topics else 0.9), 4),
        "structure_readiness": round((1.0 if canonical_story else 0.5) * max(confidence_score, 0.5), 4),
        "story_material_readiness": material_readiness,
    }


STORY_REQUIRED_SCENE_FIELDS = [
    "purpose",
    "conflict",
    "turn",
    "affect",
    "visualizable_action",
    "grounding_note",
]


def compact_research_pack_ok(
    *,
    sources: list[Any],
    passage_count: int,
    canonical_story: Any,
    conflict_items: list[Any],
    handoff_to_story: Any,
) -> bool:
    """Accept focused research when it is grounded enough to avoid count padding."""
    has_canonical = non_empty(canonical_story)
    has_conflict_or_handoff = bool(conflict_items) or non_empty(handoff_to_story)
    has_source_grounding = len(sources) >= 3 or (len(sources) >= 1 and passage_count >= 5)
    return has_canonical and has_source_grounding and passage_count >= 3 and has_conflict_or_handoff


def dense_story_scene_count(scenes: list[Any]) -> int:
    return sum(
        1
        for scene in scenes
        if isinstance(scene, dict)
        and all(non_empty(scene.get(field)) for field in STORY_REQUIRED_SCENE_FIELDS)
        and bool(as_list(scene.get("research_refs")))
    )


def story_scene_coverage_ok(scenes: list[Any]) -> bool:
    return len(scenes) >= 20 or dense_story_scene_count(scenes) >= 8


def _story_scene_field_presence(scenes: list[Any], field: str) -> float:
    if not scenes:
        return 0.0
    return score_from_ratio(sum(1 for scene in scenes if isinstance(scene, dict) and non_empty(scene.get(field))), len(scenes))


def _story_rubric(*, candidates: list[Any], chosen_id: Any, rationale: Any, scenes: list[Any]) -> dict[str, float]:
    if not scenes:
        return {key: 0.0 for key in STAGE_RUBRIC_WEIGHTS["story"]}
    required_field_scores = [_story_scene_field_presence(scenes, field) for field in STORY_REQUIRED_SCENE_FIELDS]
    scene_density = round(sum(required_field_scores) / len(required_field_scores), 4)
    reference_grounding = score_from_ratio(
        sum(1 for scene in scenes if isinstance(scene, dict) and as_list(scene.get("research_refs"))),
        len(scenes),
    )
    grounding_note = _story_scene_field_presence(scenes, "grounding_note")
    affect_readiness = _story_scene_field_presence(scenes, "affect")
    handoff_readiness = round(
        (
            _story_scene_field_presence(scenes, "purpose")
            + _story_scene_field_presence(scenes, "conflict")
            + _story_scene_field_presence(scenes, "turn")
            + _story_scene_field_presence(scenes, "visualizable_action")
        )
        / 4,
        4,
    )
    selection_readiness = round(
        (
            score_from_ratio(len(candidates), 2)
            + (1.0 if len(candidates) <= 4 else 0.5)
            + (1.0 if non_empty(chosen_id) else 0.0)
            + (1.0 if non_empty(rationale) else 0.0)
        )
        / 4,
        4,
    )
    return {
        "selection_readiness": selection_readiness,
        "scene_density": scene_density,
        "grounding_boundary": round((reference_grounding + grounding_note) / 2, 4),
        "affect_readiness": affect_readiness,
        "handoff_readiness": handoff_readiness,
    }


def _scene_selector_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("scene"):
        raw = raw[len("scene") :]
    if "_cut" in raw:
        raw = raw.split("_cut", 1)[0]
    raw = raw.replace("-", ".").replace("_", ".")
    parts = [part for part in raw.split(".") if part]
    normalized_parts: list[str] = []
    for part in parts:
        if part.isdigit():
            normalized_parts.append(str(int(part)))
        else:
            normalized_parts.append(part)
    return ".".join(normalized_parts)


def _story_scene_keys(run_dir: Path) -> set[str]:
    path = run_dir / "story.md"
    if not path.exists():
        return set()
    _, data = load_structured_document(path)
    scenes = as_list(nested_get(data, ["script", "scenes"], [])) or as_list(data.get("scenes"))
    keys = set()
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        key = _scene_selector_key(scene.get("scene_id") or scene.get("scene_selector") or index + 1)
        if key:
            keys.add(key)
    return keys


def _major_scene_coverage_ok(story_keys: set[str], covered_story_keys: set[str], scene_value_count: int) -> bool:
    if scene_value_count <= 0:
        return False
    if not story_keys:
        return True
    if story_keys <= covered_story_keys:
        return True
    minimum_major_coverage = min(len(story_keys), 8)
    return len(covered_story_keys) >= minimum_major_coverage


def _has_template_placeholder(text: str) -> bool:
    return any(marker in text for marker in ("REPLACE_ME", "EXAMPLE_ONLY", "TEMPLATE_ONLY"))


IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
IMAGE_API_PROMPT_FORBIDDEN_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_prompt_contains_no_scene_event_ids", re.compile(r"\bscene\d+_event_[A-Za-z0-9_]+\b|\b_event_[A-Za-z0-9_]+\b", re.I)),
    (
        "api_prompt_contains_no_yaml_field_names",
        re.compile(
            r"first_frame_visual_plan|cut_contract|scene_event|source_event_contract|event_context_for_cut|validation_gates|"
            r"source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief|debug_prompt_source|api_prompt_payload",
            re.I,
        ),
    ),
    ("api_prompt_contains_no_boolean_gate_values", re.compile(r"\b(?:true|false|null|none)\b", re.I)),
    ("api_prompt_contains_no_legacy_additional_description", re.compile(r"追加の具体描写|追加具体描写")),
    ("api_prompt_contains_no_abstract_story_terms", re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")),
    ("api_prompt_contains_no_unresolved_generic_placeholders", re.compile(r"\b(?:TODO|TBD|placeholder|approved_story_evidence|primary_visible_object|primary_visible_zone)\b", re.I)),
)
IMAGE_API_PROMPT_ABSTRACT_TERM_RE = re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")


def _image_api_prompt_payload(image_generation: dict[str, Any]) -> dict[str, Any]:
    payload = image_generation.get("api_prompt_payload")
    return payload if isinstance(payload, dict) else {}


def _image_api_prompt_text(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("prompt") or image_generation.get("prompt") or "")


def _image_api_prompt_policy(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("policy_version") or image_generation.get("prompt_policy_version") or "").strip()


def _image_api_prompt_v1_issues(selector: str, image_generation: dict[str, Any]) -> list[str]:
    if _image_api_prompt_policy(image_generation) != IMAGE_API_PROMPT_POLICY_VERSION:
        return []
    prompt = str(_image_api_prompt_payload(image_generation).get("prompt") or "").strip()
    issues: list[str] = []
    if not prompt:
        issues.append(f"{selector}:api_prompt_missing_for_new_prompt_policy")
        return issues
    for gate_name, pattern in IMAGE_API_PROMPT_FORBIDDEN_GATES:
        if pattern.search(prompt):
            issues.append(f"{selector}:{gate_name}")
    required = {
        "api_prompt_has_shot_role": "shot_role:",
        "api_prompt_has_location_zone": "location_zone:",
        "api_prompt_has_previous_cut_delta": "this_cut_delta:",
        "api_prompt_has_character_blocking": "hand_position:",
    }
    for gate_name, needle in required.items():
        if needle not in prompt:
            issues.append(f"{selector}:{gate_name}")
    if as_list(image_generation.get("object_ids")) and "object_contact_state:" not in prompt:
        issues.append(f"{selector}:api_prompt_has_object_contact_state_if_object_present")
    for required_payload in ("shot_design_contract", "cut_location_frame_plan", "cut_visual_delta", "blocking_and_interaction"):
        if not isinstance(_image_api_prompt_payload(image_generation).get(required_payload), dict):
            issues.append(f"{selector}:{required_payload}_missing")
    return issues


def _scene_shot_mix_plan_v1_issues(scenes: list[Any]) -> list[str]:
    issues: list[str] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        cuts = as_list(scene.get("cuts")) or [scene]
        v1_shots: list[tuple[str, str, str]] = []
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict):
                continue
            image_generation = cut.get("image_generation") if isinstance(cut.get("image_generation"), dict) else {}
            if _image_api_prompt_policy(image_generation) != IMAGE_API_PROMPT_POLICY_VERSION:
                continue
            scene_id = as_dotted_str(scene.get("scene_id")) or str(scene_index)
            cut_id = as_dotted_str(cut.get("cut_id")) or str(cut_index)
            selector = str(cut.get("selector") or make_scene_cut_selector(scene_id, cut_id))
            shot = _image_api_prompt_payload(image_generation).get("shot_design_contract")
            shot = shot if isinstance(shot, dict) else {}
            v1_shots.append((selector, str(shot.get("shot_role") or "").strip(), str(shot.get("shot_scale") or "").strip()))
        if not v1_shots:
            continue
        scene_id = as_dotted_str(scene.get("scene_id")) or str(scene_index)
        if not isinstance(scene.get("scene_shot_mix_plan"), dict):
            issues.append(f"scene{scene_id}:scene_shot_mix_plan_exists")
        scales = [scale for _, _, scale in v1_shots if scale]
        if scales and all(scale == "medium_wide" for scale in scales):
            issues.append(f"scene{scene_id}:scene_shot_mix_not_all_medium_wide")
        for previous, current in zip(v1_shots, v1_shots[1:]):
            if previous[1:] == current[1:] and previous[1]:
                issues.append(f"{current[0]}:no_two_adjacent_cuts_same_shot_role_and_scale")
    return issues


def _asset_bible_candidate_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if not isinstance(value, dict):
        return 0
    count = 0
    for item in value.values():
        count += len(as_list(item))
    return count


def _production_manifest_issues(run_dir: Path) -> list[str]:
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        return []
    _, data = load_structured_document(manifest_path)
    issues: list[str] = []
    for selector, node in _iter_manifest_nodes_with_selectors(data):
        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        prompt = str(image_generation.get("prompt") or "").strip()
        motion_prompt = str(video_generation.get("motion_prompt") or "").strip()
        if prompt:
            issues.append(f"{selector}:image_generation.prompt")
        if motion_prompt:
            issues.append(f"{selector}:video_generation.motion_prompt")
    return issues


def _p300_production_artifact_issues(run_dir: Path) -> list[str]:
    issues: list[str] = []
    for filename in ("asset_generation_requests.md", "image_generation_requests.md", "video_generation_requests.md", "video.mp4"):
        if (run_dir / filename).exists():
            issues.append(filename)
    shorts_dir = run_dir / "shorts"
    if shorts_dir.exists() and any(shorts_dir.rglob("*")):
        issues.append("shorts")
    scene_video_paths = sorted((run_dir / "scenes").glob("scene*/video.mp4"))
    if scene_video_paths:
        issues.extend(str(path.relative_to(run_dir)) for path in scene_video_paths[:20])
    for rel in ("assets/scenes", "assets/videos", "assets/characters", "assets/objects", "assets/locations", "assets/test"):
        path = run_dir / rel
        if path.exists() and any(path.rglob("*")):
            issues.append(rel)
    issues.extend(_production_manifest_issues(run_dir))
    return sorted(set(issues))


def check_visual_value(run_dir: Path, profile: str, *, forbid_production_artifacts: bool = True) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "visual_value.md"
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}

    add_check(checks, "visual_value.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("visual_value", path.name, checks), updates

    text, data = load_structured_document(path)
    add_check(
        checks,
        "visual_value.no_template_placeholders",
        not _has_template_placeholder(text),
        "visual_value.md does not contain REPLACE_ME/EXAMPLE_ONLY template markers",
        kind="rubric",
    )
    if profile == "standard":
        add_check(checks, "visual_value.no_todo", not has_todo(text), "visual_value.md does not contain TODO/TBD markers", kind="rubric")
    _append_grounding_checks(checks, run_dir=run_dir, stage="visual_value")

    scene_values = as_list(data.get("scene_visual_values"))
    scene_value_keys = {
        _scene_selector_key(item.get("scene_selector") or item.get("scene_id"))
        for item in scene_values
        if isinstance(item, dict)
    }
    scene_value_keys.discard("")
    story_keys = _story_scene_keys(run_dir)
    covered_story_keys = story_keys & scene_value_keys
    missing_story_keys = sorted(story_keys - scene_value_keys, key=lambda item: dotted_id_sort_key(item))
    asset_candidate_count = _asset_bible_candidate_count(data.get("asset_bible_candidates"))
    anchor_candidates = as_list(data.get("anchor_cut_candidates"))
    reference_strategy = data.get("reference_strategy")
    regeneration_risks = as_list(data.get("regeneration_risks"))
    handoff = data.get("handoff_to_p400_p500_p600_p700") if isinstance(data.get("handoff_to_p400_p500_p600_p700"), dict) else {}
    if not handoff:
        handoff = data.get("handoff_to_p400_p600_p700") if isinstance(data.get("handoff_to_p400_p600_p700"), dict) else {}
    handoff_keys = {"p400_script", "p500_asset", "p600_scene_implementation", "p700_narration"}
    production_issues = _p300_production_artifact_issues(run_dir) if forbid_production_artifacts else []

    details["scene_visual_value_count"] = len(scene_values)
    details["story_scene_count"] = len(story_keys)
    details["covered_story_scene_count"] = len(covered_story_keys)
    if missing_story_keys:
        details["missing_story_scene_selectors"] = ",".join(f"scene{key}" for key in missing_story_keys[:20])
    if production_issues:
        details["p300_production_artifact_issues"] = ", ".join(production_issues[:20])

    add_check(checks, "visual_value.structured", bool(data), "visual_value.md contains structured YAML output", kind="rubric")
    add_check(checks, "visual_value.global_identity", isinstance(data.get("global_visual_identity"), dict) and bool(data.get("global_visual_identity")), "global_visual_identity is present", kind="rubric")
    coverage_ok = _major_scene_coverage_ok(story_keys, covered_story_keys, len(scene_values))
    add_check(checks, "visual_value.scene_coverage", coverage_ok, "scene_visual_values cover all story scenes or at least the major story scenes", kind="rubric")
    add_check(checks, "visual_value.asset_bible_candidates", asset_candidate_count >= 1, f"asset_bible_candidates are listed (got {asset_candidate_count})", kind="rubric")
    add_check(checks, "visual_value.anchor_cut_candidates", len(anchor_candidates) >= 1, f"anchor_cut_candidates are listed (got {len(anchor_candidates)})", kind="rubric")
    add_check(checks, "visual_value.reference_strategy", isinstance(reference_strategy, dict) and bool(reference_strategy), "reference_strategy is present", kind="rubric")
    add_check(checks, "visual_value.regeneration_risks", len(regeneration_risks) >= 1, f"regeneration_risks are listed (got {len(regeneration_risks)})", kind="rubric")
    add_check(checks, "visual_value.handoff", handoff_keys.issubset(set(handoff)), "handoff includes p400_script, p500_asset, p600_scene_implementation, and p700_narration", kind="rubric")
    add_check(checks, "visual_value.no_p300_production_artifacts", not production_issues, "p300 has no production cut prompts, image/video request files, or generated asset/video artifacts", kind="rubric")

    updates["eval.visual_value.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("visual_value", path.name, checks, details=details), updates


def check_story(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "story.md"
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}

    add_check(checks, "story.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("story", path.name, checks), updates

    text, data = load_structured_document(path)
    if profile == "standard":
        add_check(checks, "story.no_todo", not has_todo(text), "story.md does not contain TODO/TBD markers", kind="rubric")
    _append_grounding_checks(checks, run_dir=run_dir, stage="story")

    selection = nested_get(data, ["selection"], {})
    candidates = as_list(selection.get("candidates")) if isinstance(selection, dict) else []
    chosen_id = selection.get("chosen_candidate_id") if isinstance(selection, dict) else None
    rationale = selection.get("rationale") if isinstance(selection, dict) else None
    scenes = as_list(nested_get(data, ["script", "scenes"], []))
    hybrid_status = nested_get(data, ["hybridization", "approval_status"])

    details["candidate_count"] = len(candidates)
    details["scene_count"] = len(scenes)
    details["chosen_candidate_id"] = chosen_id

    add_check(checks, "story.structured", bool(data), "story.md contains structured YAML output")
    add_check(checks, "story.candidates", 2 <= len(candidates) <= 4, f"selection has 2-4 candidates (got {len(candidates)})", kind="rubric")
    add_check(checks, "story.choice", non_empty(chosen_id), "chosen_candidate_id is set", kind="rubric")
    add_check(checks, "story.rationale", non_empty(rationale), "selection rationale is present", kind="rubric")
    add_check(
        checks,
        "story.scenes",
        story_scene_coverage_ok(scenes),
        f"story has >= 20 scenes or >= 8 dense grounded scenes (got scenes={len(scenes)}, dense_grounded={dense_story_scene_count(scenes)})",
        kind="rubric",
    )

    for field in STORY_REQUIRED_SCENE_FIELDS:
        missing = [
            str(scene.get("scene_id") or index + 1)
            for index, scene in enumerate(scenes)
            if not isinstance(scene, dict) or not non_empty(scene.get(field))
        ]
        if missing:
            details[f"missing_{field}_scene_ids"] = ",".join(missing[:20])
        add_check(
            checks,
            f"story.scene_{field}",
            not missing,
            f"all scripted scenes include {field}",
            kind="rubric",
        )

    research_refs_missing = [
        str(scene.get("scene_id") or index + 1)
        for index, scene in enumerate(scenes)
        if not isinstance(scene, dict) or not as_list(scene.get("research_refs"))
    ]
    if research_refs_missing:
        details["missing_research_refs_scene_ids"] = ",".join(research_refs_missing[:20])
    add_check(checks, "story.research_refs", not research_refs_missing, "scripted scenes keep research_refs", kind="rubric")

    hybrid_ok = hybrid_status in {None, "", "not_needed", "approved", "rejected"}
    add_check(checks, "story.hybrid_gate", hybrid_ok, "hybridization approval is not left pending", kind="rubric")

    rubric_scores = _story_rubric(candidates=candidates, chosen_id=chosen_id, rationale=rationale, scenes=scenes)
    _append_rubric_findings(checks=checks, stage="story", rubric_scores=rubric_scores)

    updates["eval.story.score"] = f"{score_from_checks(checks):.4f}"
    if candidates:
        updates["selection.story.candidate_count"] = str(len(candidates))
    if non_empty(chosen_id):
        updates["selection.story.chosen_id"] = str(chosen_id)
    return make_stage("story", path.name, checks, details=details, rubric_scores=rubric_scores), updates


def _script_rubric(text: str, data: dict[str, Any], *, scenes: list[Any]) -> dict[str, float]:
    phases = {str(scene.get("phase") or "").strip() for scene in scenes if isinstance(scene, dict) and str(scene.get("phase") or "").strip()}
    reference_grounding = 1.0
    if scenes:
        reference_grounding = score_from_ratio(
            sum(1 for scene in scenes if isinstance(scene, dict) and as_list(scene.get("research_refs"))),
            len(scenes),
        )
    meaningful_len = len("".join(text.split()))
    return {
        "arc_coverage": score_from_ratio(len(phases), 3),
        "scene_specificity": score_from_ratio(meaningful_len, 160),
        "reference_grounding": reference_grounding,
        "anti_todo": 0.0 if has_todo(text) else 1.0,
        "production_readiness": 1.0 if meaningful_len >= 80 else 0.4,
    }


def _manifest_rubric(nodes: list[dict[str, Any]], body_text: str) -> dict[str, float]:
    if not nodes:
        return {key: 0.0 for key in STAGE_RUBRIC_WEIGHTS["manifest"]}
    prompt_lengths = []
    ids_with_values = 0
    narration_count = 0
    contract_count = 0
    for node in nodes:
        image_generation = node.get("image_generation") if isinstance(node, dict) and isinstance(node.get("image_generation"), dict) else {}
        audio = node.get("audio") if isinstance(node, dict) and isinstance(node.get("audio"), dict) else {}
        video_generation = node.get("video_generation") if isinstance(node, dict) and isinstance(node.get("video_generation"), dict) else {}
        combined_node_text = "\n".join(
            [
                str(image_generation.get("prompt") or "").strip(),
                str(video_generation.get("motion_prompt") or "").strip(),
                str((((audio or {}).get("narration") or {}) if isinstance((audio or {}).get("narration"), dict) else {}).get("text") or "").strip(),
            ]
        )
        prompt_lengths.append(len(combined_node_text))
        if image_generation.get("character_ids") is not None and image_generation.get("object_ids") is not None:
            ids_with_values += 1
        narration = (audio or {}).get("narration") if isinstance(audio, dict) else {}
        if isinstance(narration, dict):
            narration_text = str(narration.get("text") or "").strip()
            silence_contract = narration.get("silence_contract") if isinstance(narration.get("silence_contract"), dict) else {}
            is_intentional_silence = (
                str(narration.get("tool") or "").strip().lower() == "silent"
                and bool(silence_contract.get("intentional"))
                and bool(silence_contract.get("confirmed_by_human"))
                and non_empty(silence_contract.get("kind"))
                and non_empty(silence_contract.get("reason"))
            )
            if narration_text or is_intentional_silence:
                narration_count += 1
        if _node_cut_contract(node):
            contract_count += 1
        if isinstance(video_generation, dict) and video_generation.get("duration_seconds"):
            pass
    avg_prompt_length = sum(prompt_lengths) / len(prompt_lengths)
    return {
        "beat_clarity": score_from_ratio(contract_count, len(nodes)),
        "visual_specificity": score_from_ratio(avg_prompt_length, 150),
        "continuity_readiness": score_from_ratio(ids_with_values, len(nodes)),
        "narration_alignment": score_from_ratio(narration_count, len(nodes)),
        "production_readiness": 0.0 if has_todo(body_text) else 1.0,
    }


def _video_rubric(run_dir: Path, state: dict[str, str], checks: list[dict[str, Any]]) -> dict[str, float]:
    passed_map = {check["id"]: bool(check["passed"]) for check in checks}
    narration_list = run_dir / "video_narration_list.txt"
    return {
        "render_integrity": 1.0 if passed_map.get("video.file_exists") and passed_map.get("video.render_status") else 0.3,
        "asset_completeness": 1.0 if (run_dir / "video.mp4").exists() else 0.3,
        "review_readiness": 1.0 if state.get("review.video.status", "").strip().lower() in {"pending", "approved", "changes_requested"} else 0.3,
        "audio_packaging": 1.0 if (not narration_list.exists() or passed_map.get("video.narration_list", False)) else 0.4,
        "publish_readiness": score_from_ratio(sum(1 for check in checks if check["passed"]), len(checks)),
    }


def check_research(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "research.md"
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}

    add_check(checks, "research.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("research", path.name, checks), updates

    text, data = load_structured_document(path)
    if profile == "standard":
        add_check(checks, "research.no_todo", not has_todo(text), "research.md does not contain TODO/TBD markers", kind="rubric")
    _append_grounding_checks(checks, run_dir=run_dir, stage="research")

    sources = as_list(data.get("source_inventory") or data.get("sources"))
    story_materials = data.get("story_materials")
    chronological_events = nested_get(data, ["story_materials", "chronological_events"], [])
    source_passages = as_list(data.get("source_passages"))
    primary_sources = as_list(data.get("primary_sources"))
    legacy_passages: list[Any] = []
    for source in primary_sources:
        if isinstance(source, dict):
            legacy_passages.extend(as_list(source.get("key_passages")))
    beat_sheet = nested_get(data, ["story_baseline", "canonical_synopsis", "beat_sheet"], [])
    conflicts = data.get("conflicts")
    conflict_items = as_list(conflicts)
    conflict_topics = [str(item.get("topic") or "").strip() for item in conflict_items if isinstance(item, dict) and str(item.get("topic") or "").strip()]
    facts_value = data.get("facts")
    facts = as_list(facts_value.get("items")) if isinstance(facts_value, dict) else as_list(facts_value)
    handoff_to_story = data.get("handoff_to_story")
    confidence = nested_get(data, ["metadata", "confidence_score"])
    synopsis = nested_get(data, ["story_baseline", "canonical_synopsis", "short_summary"]) or nested_get(
        data, ["story_baseline", "canonical_synopsis", "one_liner"]
    )
    canonical_story_dump = nested_get(data, ["story_materials", "canonical_story_dump"])
    canonical_story = canonical_story_dump or synopsis
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    flattened = flatten_without_keys(data, excluded={"evaluation_contract"})

    details["sources"] = len(sources)
    details["event_count"] = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    details["source_passage_count"] = len(source_passages) or len(legacy_passages)
    details["fact_count"] = len(as_list(facts))

    add_check(checks, "research.structured", bool(data), "research.md contains structured YAML output")
    if not contract:
        add_check(checks, "research.contract_missing", False, "evaluation_contract is missing for research stage.", kind="rubric")
    else:
        target_questions = contract_list(contract, "target_questions")
        must_cover = contract_list(contract, "must_cover")
        must_resolve = contract_list(contract, "must_resolve_conflicts")
        if target_questions and not all(question in flattened for question in target_questions):
            add_check(checks, "research.contract_target_questions_unmet", False, "research does not yet address all target_questions.", kind="rubric")
        if must_cover and not all(term in flattened for term in must_cover):
            add_check(checks, "research.contract_must_cover_unmet", False, "research does not yet cover all required anchors.", kind="rubric")
        if must_resolve and not all(term in "\n".join(conflict_topics) for term in must_resolve):
            add_check(checks, "research.contract_conflict_unmet", False, "research conflicts do not yet cover all required conflict topics.", kind="rubric")
    story_materials_ok = bool(story_materials) or non_empty(synopsis)
    passage_count = len(source_passages) or len(legacy_passages)
    compact_pack_ok = compact_research_pack_ok(
        sources=sources,
        passage_count=passage_count,
        canonical_story=canonical_story,
        conflict_items=conflict_items,
        handoff_to_story=handoff_to_story,
    )
    add_check(
        checks,
        "research.sources",
        len(sources) >= 12 or compact_pack_ok,
        f"sources meet broad target >= 12 or compact grounded pack is present (got sources={len(sources)}, passages={passage_count})",
        kind="rubric",
    )
    add_check(checks, "research.story_materials", story_materials_ok, "story_materials or legacy story baseline is present", kind="rubric")
    add_check(
        checks,
        "research.canonical_story",
        non_empty(canonical_story),
        "canonical story dump or legacy synopsis is present",
        kind="rubric",
    )
    event_count = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    add_check(
        checks,
        "research.chronological_events",
        event_count >= 20 or compact_pack_ok,
        f"chronological coverage meets broad target >= 20 or compact grounded pack is present (got events={event_count}, passages={passage_count})",
        kind="rubric",
    )
    add_check(checks, "research.source_passages", passage_count >= 1, f"source passages are present (got {passage_count})", kind="rubric")
    add_check(
        checks,
        "research.facts",
        len(as_list(facts)) >= 10 or compact_pack_ok,
        f"facts meet broad target >= 10 or compact grounded pack is present (got facts={len(as_list(facts))}, passages={passage_count})",
        kind="rubric",
    )
    add_check(checks, "research.conflicts_field", conflicts is not None, "conflicts field is present", kind="rubric")
    add_check(checks, "research.handoff_to_story", bool(handoff_to_story), "handoff_to_story is present", kind="rubric")

    confidence_ok = isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
    add_check(checks, "research.confidence", confidence_ok, "metadata.confidence_score is between 0.0 and 1.0", kind="rubric")
    rubric_scores = _research_rubric(
        data,
        sources=sources,
        chronological_events=as_list(chronological_events),
        beat_sheet=as_list(beat_sheet),
        source_passages=source_passages or legacy_passages,
        facts=as_list(facts),
        handoff_to_story=handoff_to_story,
        conflict_items=conflict_items,
        conflict_topics=conflict_topics,
    )
    _append_rubric_findings(checks=checks, stage="research", rubric_scores=rubric_scores)
    updates["eval.research.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("research", path.name, checks, details=details, rubric_scores=rubric_scores), updates


def _script_text_quality_checks(checks: list[dict[str, Any]], text: str, data: dict[str, Any], profile: str) -> None:
    meaningful_len = len("".join(text.split()))
    add_check(checks, "script.content_length", meaningful_len >= 80, f"script content length is meaningful (got {meaningful_len} chars)", kind="rubric")
    if profile == "standard":
        add_check(checks, "script.no_todo", not has_todo(text), "script does not contain TODO/TBD markers", kind="rubric")
    generic_hits = [phrase for phrase in GENERIC_SCENE_TEMPLATE_PHRASES if phrase in text]
    add_check(
        checks,
        "script.no_generic_scene_template_phrases",
        not generic_hits,
        "script scene design does not rely on banned generic scene placeholders"
        + (f" (hits: {', '.join(generic_hits)})" if generic_hits else ""),
        kind="rubric",
    )

    scenes = []
    if isinstance(data.get("scenes"), list):
        scenes = as_list(data.get("scenes"))
    elif isinstance(nested_get(data, ["script", "scenes"], []), list):
        scenes = as_list(nested_get(data, ["script", "scenes"], []))
    if scenes:
        add_check(checks, "script.structured_scenes", len(scenes) >= 1, "structured script includes scene list", kind="rubric")


def _scene_has_intent(scene: dict[str, Any]) -> bool:
    return not _scene_intent_issue_map(scene)


def _scene_id_for_issue(scene: dict[str, Any], fallback: str = "?") -> str:
    return as_dotted_str(scene.get("scene_id")) or str(scene.get("scene_id") or fallback)


def _dict_has_any_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(non_empty(v) for v in value.values())
    if isinstance(value, list):
        return bool(value)
    return non_empty(value)


def _contains_generic_scene_language(value: Any) -> bool:
    text = flatten_text(value)
    return any(phrase in text for phrase in GENERIC_SCENE_TEMPLATE_PHRASES)


def _looks_only_generic_handoff(value: Any) -> bool:
    text = "".join(flatten_text(value).split())
    return bool(text) and len(text) <= 18 and any(phrase in text for phrase in GENERIC_HANDOFF_ONLY_PHRASES)


def _has_story_specific_terms(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return sum(1 for item in value if str(item).strip()) >= 2


def _has_actor_force_pressure(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    people_keys = ("protagonist", "opposing", "helping", "observing", "witness", "community", "authority")
    has_people = any(non_empty(value.get(key)) for key in people_keys)
    pressure_keys = ("pressure_method", "pressure", "visible_pressure", "obstacle", "leverage")
    has_pressure = any(non_empty(value.get(key)) for key in pressure_keys)
    return has_people and has_pressure


def _scene_intent_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "dramatic_question": [],
        "value_shift": [],
        "causal_turn": [],
        "visual_thesis": [],
        "story_specificity": [],
        "conflict_engine": [],
        "handoff_chain": [],
        "coverage_review": [],
    }
    intent = scene.get("scene_intent")
    if not isinstance(intent, dict):
        for key in issues:
            issues[key].append(f"scene{scene_id}:scene_intent")
        return {key: values for key, values in issues.items() if values}
    required_keys = {
        "story_purpose",
        "dramatic_question",
        "scene_spine",
        "value_shift",
        "causal_turn",
        "audience_information",
        "withheld_information",
        "reveal_constraints",
        "affect_transition",
        "character_state",
        "visual_thesis",
        "story_specificity",
        "visual_value_source",
        "production_risks",
        "handoff_notes",
    }
    missing_required = sorted(required_keys - set(intent))
    if missing_required:
        issues["story_specificity"].extend(f"scene{scene_id}:scene_intent.{key}" for key in missing_required)
    if not non_empty(intent.get("story_purpose")):
        issues["story_specificity"].append(f"scene{scene_id}:story_purpose")
    if not non_empty(intent.get("affect_transition")):
        issues["story_specificity"].append(f"scene{scene_id}:affect_transition")
    if not isinstance(intent.get("handoff_notes"), dict):
        issues["handoff_chain"].append(f"scene{scene_id}:handoff_notes")

    if not non_empty(intent.get("dramatic_question")):
        issues["dramatic_question"].append(f"scene{scene_id}:dramatic_question")
    if not non_empty(intent.get("scene_spine")):
        issues["dramatic_question"].append(f"scene{scene_id}:scene_spine")
    if not non_empty(intent.get("causal_turn")):
        issues["causal_turn"].append(f"scene{scene_id}:causal_turn")
    if not non_empty(intent.get("visual_thesis")):
        issues["visual_thesis"].append(f"scene{scene_id}:visual_thesis")

    value_shift = intent.get("value_shift")
    if not isinstance(value_shift, dict):
        issues["value_shift"].append(f"scene{scene_id}:value_shift")
    else:
        for key in ("from", "to"):
            if not non_empty(value_shift.get(key)):
                issues["value_shift"].append(f"scene{scene_id}:value_shift.{key}")
        if not as_list(value_shift.get("visible_evidence")):
            issues["value_shift"].append(f"scene{scene_id}:value_shift.visible_evidence")

    character_state = intent.get("character_state")
    if not isinstance(character_state, dict):
        issues["story_specificity"].append(f"scene{scene_id}:character_state")
    else:
        for key in ("start", "end"):
            if not non_empty(character_state.get(key)):
                issues["story_specificity"].append(f"scene{scene_id}:character_state.{key}")
        if not as_list(character_state.get("visible_behavior")):
            issues["story_specificity"].append(f"scene{scene_id}:character_state.visible_behavior")

    specificity = intent.get("story_specificity")
    if not isinstance(specificity, dict):
        issues["story_specificity"].append(f"scene{scene_id}:story_specificity")
    else:
        for key in ("non_compressible_beat", "scene_promotion_reason", "unique_scene_responsibility"):
            if not non_empty(specificity.get(key)):
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.{key}")
        if not _dict_has_any_value(specificity.get("actor_forces")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.actor_forces")
        elif not _has_actor_force_pressure(specificity.get("actor_forces")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.actor_forces.pressure_method")
        if not _dict_has_any_value(specificity.get("meaning_ladder")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.meaning_ladder")
        concrete_handoff = specificity.get("concrete_handoff")
        if not isinstance(concrete_handoff, dict):
            issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff")
        else:
            for key in ("incoming_trigger", "outgoing_anchor", "outgoing_pressure"):
                if not non_empty(concrete_handoff.get(key)):
                    issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff.{key}")
                elif _looks_only_generic_handoff(concrete_handoff.get(key)):
                    issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff.{key}.generic")
        anti_template = specificity.get("anti_template_language")
        if not isinstance(anti_template, dict):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language")
        else:
            if anti_template.get("banned_generic_phrases_absent") is not True:
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language.banned_generic_phrases_absent")
            if not _has_story_specific_terms(anti_template.get("story_specific_terms")):
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language.story_specific_terms")

    conflict_engine = intent.get("scene_conflict_engine")
    if not isinstance(conflict_engine, dict):
        issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine")
    else:
        for key in ("desire", "obstacle", "stakes", "escalation", "no_return_point"):
            if not non_empty(conflict_engine.get(key)):
                issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine.{key}")
        if not as_list(conflict_engine.get("visible_pressure")):
            issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine.visible_pressure")

    knowledge_delta = intent.get("audience_knowledge_delta")
    if not isinstance(knowledge_delta, dict):
        issues["dramatic_question"].append(f"scene{scene_id}:audience_knowledge_delta")
    else:
        for key in ("before_scene", "learned_during_scene", "still_unknown_after_scene", "forbidden_early_reveals"):
            if not as_list(knowledge_delta.get(key)):
                issues["dramatic_question"].append(f"scene{scene_id}:audience_knowledge_delta.{key}")

    handoff_chain = intent.get("handoff_chain")
    if not isinstance(handoff_chain, dict):
        issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain")
    else:
        incoming = handoff_chain.get("incoming")
        outgoing = handoff_chain.get("outgoing")
        if not isinstance(incoming, dict) or not non_empty(incoming.get("anchor_type")) or not non_empty(incoming.get("visible_or_audible_form")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.incoming")
        if not isinstance(outgoing, dict) or not non_empty(outgoing.get("anchor_id")) or not non_empty(outgoing.get("anchor_type")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing")
        if isinstance(outgoing, dict) and not (non_empty(outgoing.get("next_scene_selector")) or str(outgoing.get("anchor_type") or "") == "terminal"):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing.next_scene_selector")
        if isinstance(outgoing, dict) and _looks_only_generic_handoff(outgoing.get("required_next_scene_start_pressure")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing.required_next_scene_start_pressure.generic")

    coverage = scene.get("coverage_review")
    if not isinstance(coverage, dict):
        issues["coverage_review"].append(f"scene{scene_id}:coverage_review")
    else:
        for key in SCENE_COVERAGE_REVIEW_REQUIRED_KEYS:
            if coverage.get(key) is not True:
                issues["coverage_review"].append(f"scene{scene_id}:{key}")

    if _contains_generic_scene_language(intent):
        issues["story_specificity"].append(f"scene{scene_id}:generic_scene_template_phrase")

    return {key: values for key, values in issues.items() if values}


def _iter_mapping_keys_recursive(value: Any, *, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            keys.append(path)
            keys.extend(_iter_mapping_keys_recursive(child, prefix=path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            keys.extend(_iter_mapping_keys_recursive(child, prefix=f"{prefix}[{index}]" if prefix else f"[{index}]"))
    return keys


def _scene_event(scene: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scene.get("scene_event"))


def _scene_event_sequence(scene: dict[str, Any]) -> list[dict[str, Any]]:
    event = _scene_event(scene)
    return [beat for beat in as_list(event.get("event_sequence")) if isinstance(beat, dict)]


def _scene_event_beat_id(beat: dict[str, Any]) -> str:
    return str(beat.get("beat_id") or "").strip()


def _scene_event_beat_function(beat: dict[str, Any]) -> str:
    return str(beat.get("beat_function") or beat.get("function") or "").strip().lower()


def _scene_event_beat_ids(scene: dict[str, Any]) -> list[str]:
    return [_scene_event_beat_id(beat) for beat in _scene_event_sequence(scene) if _scene_event_beat_id(beat)]


def _scene_event_source_story_beat_refs(scene_event: dict[str, Any]) -> list[str]:
    refs = scene_event.get("source_story_beat_ids")
    return [str(item).strip() for item in refs if str(item).strip()] if isinstance(refs, list) else []


def _forbidden_reveal_ids_from_scene_intent(scene: dict[str, Any]) -> set[str]:
    intent = as_dict(scene.get("scene_intent"))
    forbidden: set[str] = set()
    delta = as_dict(intent.get("audience_knowledge_delta"))
    for item in as_list(delta.get("forbidden_early_reveals")):
        if isinstance(item, dict):
            for key in ("info_id", "reveal_id", "id"):
                value = str(item.get(key) or "").strip()
                if value:
                    forbidden.add(value)
        else:
            text = str(item).strip()
            if text and text.isascii() and " " not in text:
                forbidden.add(text)
    for constraint in as_list(intent.get("reveal_constraints")):
        if not isinstance(constraint, dict):
            text = str(constraint).strip()
            if text and text.isascii() and " " not in text:
                forbidden.add(text)
            continue
        for key in ("forbidden_info_ids", "forbidden_reveal_ids"):
            for value in as_list(constraint.get(key)):
                text = str(value).strip()
                if text:
                    forbidden.add(text)
    return forbidden


def _scene_event_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "exists": [],
        "sequence_complete": [],
        "visible_actions_complete": [],
        "no_forbidden_directing_fields": [],
        "beat_ids_unique": [],
        "turning_event_ref_valid": [],
        "end_situation_ref_valid": [],
        "reveal_constraints_respected": [],
    }
    event = _scene_event(scene)
    if not event:
        issues["exists"].append(f"scene{scene_id}:scene_event")
        return {key: values for key, values in issues.items() if values}

    if str(event.get("schema_version") or "").strip() != "scene_event_v1":
        issues["exists"].append(f"scene{scene_id}:scene_event.schema_version")
    for key in ("event_logline", "start_situation", "turning_event", "end_situation"):
        if key not in event or not non_empty(event.get(key)):
            issues["exists"].append(f"scene{scene_id}:scene_event.{key}")
    for key in ("offscreen_context", "forbidden_event_changes"):
        if key not in event or not isinstance(event.get(key), list):
            issues["exists"].append(f"scene{scene_id}:scene_event.{key}")
    if not _scene_event_source_story_beat_refs(event):
        issues["exists"].append(f"scene{scene_id}:scene_event.source_story_beat_ids")

    forbidden_fields = set(FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS)
    forbidden_paths = [
        path
        for path in _iter_mapping_keys_recursive(event)
        if path.rsplit(".", 1)[-1] in forbidden_fields or path.rsplit("[", 1)[-1].rstrip("]") in forbidden_fields
    ]
    if forbidden_paths:
        issues["no_forbidden_directing_fields"].extend(f"scene{scene_id}:scene_event.{path}" for path in forbidden_paths[:8])

    sequence = _scene_event_sequence(scene)
    if not sequence:
        issues["sequence_complete"].append(f"scene{scene_id}:scene_event.event_sequence")
    functions = {_scene_event_beat_function(beat) for beat in sequence}
    for required in REQUIRED_SCENE_EVENT_BEAT_FUNCTIONS:
        if required not in functions:
            issues["sequence_complete"].append(f"scene{scene_id}:scene_event.event_sequence.{required}")

    beat_ids: list[str] = []
    source_story_beat_ids = set(_scene_event_source_story_beat_refs(event))
    for index, beat in enumerate(sequence, start=1):
        beat_id = _scene_event_beat_id(beat)
        if not beat_id:
            issues["beat_ids_unique"].append(f"scene{scene_id}:scene_event.event_sequence[{index}].beat_id")
        else:
            beat_ids.append(beat_id)
        if not _scene_event_beat_function(beat):
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.beat_function")
        source_ids = [str(item).strip() for item in as_list(beat.get("source_story_beat_ids")) if str(item).strip()]
        if not source_ids:
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.source_story_beat_ids")
        elif source_story_beat_ids and any(source_id not in source_story_beat_ids for source_id in source_ids):
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.source_story_beat_ids.ref")
        for key in ("what_happens", "visible_action", "visible_reaction", "immediate_consequence", "emotional_pressure"):
            if not non_empty(beat.get(key)):
                issues["visible_actions_complete"].append(f"scene{scene_id}:{beat_id or index}.{key}")
        if not as_list(beat.get("required_visual_evidence")):
            issues["visible_actions_complete"].append(f"scene{scene_id}:{beat_id or index}.required_visual_evidence")

    duplicate_ids = sorted({beat_id for beat_id in beat_ids if beat_ids.count(beat_id) > 1})
    if duplicate_ids:
        issues["beat_ids_unique"].extend(f"scene{scene_id}:{beat_id}.duplicate" for beat_id in duplicate_ids)

    beat_id_set = set(beat_ids)
    turn_ids = {_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_function(beat) == "turn"}
    turning_event = as_dict(event.get("turning_event"))
    turning_ref = str(turning_event.get("source_event_beat_id") or turning_event.get("event_beat_id") or "").strip()
    if not turning_ref or turning_ref not in beat_id_set:
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.source_event_beat_id")
    elif turn_ids and turning_ref not in turn_ids:
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.source_event_beat_id.not_turn")
    if str(turning_event.get("causal_turn_ref") or "").strip() != "scene_intent.causal_turn":
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.causal_turn_ref")

    end_situation = as_dict(event.get("end_situation"))
    if str(end_situation.get("value_shift_to_ref") or "").strip() != "scene_intent.value_shift.to":
        issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.value_shift_to_ref")
    for key in ("outcome", "character_position", "object_state", "relationship_state", "new_pressure"):
        if not non_empty(end_situation.get(key)):
            issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.{key}")
    visible_refs = [str(item).strip() for item in as_list(end_situation.get("visible_evidence_refs")) if str(item).strip()]
    if visible_refs and any(ref not in beat_id_set for ref in visible_refs):
        issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.visible_evidence_refs")

    forbidden_reveals = _forbidden_reveal_ids_from_scene_intent(scene)
    if forbidden_reveals:
        for beat in sequence:
            beat_id = _scene_event_beat_id(beat) or "?"
            revealed = {str(item).strip() for item in as_list(beat.get("story_information_revealed_ids")) if str(item).strip()}
            if revealed & forbidden_reveals:
                issues["reveal_constraints_respected"].append(f"scene{scene_id}:{beat_id}.forbidden_reveal:{','.join(sorted(revealed & forbidden_reveals))}")

    return {key: values for key, values in issues.items() if values}


def _cut_event_ref_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "refs_valid": [],
        "reference_integrity": [],
        "source_event_preservation": [],
        "first_frame_alignment": [],
        "motion_boundary": [],
        "narration_boundary": [],
        "event_context_ready": [],
        "sequence_covered": [],
        "turn_payoff_have_cuts": [],
    }
    sequence = _scene_event_sequence(scene)
    beat_ids = {_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_id(beat)}
    if not beat_ids:
        issues["refs_valid"].append(f"scene{scene_id}:scene_event.event_sequence")
        return {key: values for key, values in issues.items() if values}

    beat_functions = {_scene_event_beat_id(beat): _scene_event_beat_function(beat) for beat in sequence if _scene_event_beat_id(beat)}
    beat_by_id = {_scene_event_beat_id(beat): beat for beat in sequence if _scene_event_beat_id(beat)}
    sequence_ids = [_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_id(beat)]
    forbidden_event_changes = {str(item).strip() for item in as_list(_scene_event(scene).get("forbidden_event_changes")) if str(item).strip()}
    covered: set[str] = set()
    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict) or str(cut.get("cut_status") or "").strip().lower() == "deleted":
            continue
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "?")
        contract = _node_cut_contract(cut, allow_legacy=False)
        if not contract:
            issues["refs_valid"].append(f"{selector}:cut_contract")
            continue
        source_contract = _cut_source_event_contract(contract)
        if not source_contract:
            issues["refs_valid"].append(f"{selector}:cut_contract.source_event_contract")
            continue
        primary = str(source_contract.get("primary_event_beat_id") or "").strip()
        refs = [str(item).strip() for item in as_list(source_contract.get("source_event_beat_ids")) if str(item).strip()]
        if not primary:
            issues["refs_valid"].append(f"{selector}:source_event_contract.primary_event_beat_id")
        elif primary not in beat_ids:
            issues["refs_valid"].append(f"{selector}:source_event_contract.primary_event_beat_id.ref")
        if not refs:
            issues["refs_valid"].append(f"{selector}:source_event_contract.source_event_beat_ids")
        elif any(ref not in beat_ids for ref in refs):
            issues["refs_valid"].append(f"{selector}:source_event_contract.source_event_beat_ids.ref")
        if primary and refs and primary not in refs:
            issues["reference_integrity"].append(f"{selector}:source_event_contract.primary_event_beat_id.not_in_source_event_beat_ids")
        declared_function = str(source_contract.get("event_beat_function") or "").strip()
        if primary and declared_function != beat_functions.get(primary):
            issues["reference_integrity"].append(f"{selector}:source_event_contract.event_beat_function")
        if str(source_contract.get("event_time_position") or "").strip() not in EVENT_TIME_POSITION_VALUES:
            issues["reference_integrity"].append(f"{selector}:source_event_contract.event_time_position")
        if not non_empty(source_contract.get("source_visible_reaction")) and not non_empty(source_contract.get("no_reaction_required_reason")):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_visible_reaction")
        for key in ("event_facts_to_preserve", "event_facts_not_to_invent", "allowed_reveal_info_ids", "forbidden_reveal_info_ids"):
            if key not in source_contract or not isinstance(source_contract.get(key), list):
                if key in {"event_facts_to_preserve", "event_facts_not_to_invent"}:
                    issues["refs_valid"].append(f"{selector}:source_event_contract.{key}")
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.{key}")
        ref_beats = [beat_by_id[ref] for ref in refs if ref in beat_by_id]
        primary_beat = beat_by_id.get(primary)
        expected_facts = {str(beat.get("what_happens") or "").strip() for beat in ref_beats if str(beat.get("what_happens") or "").strip()}
        declared_preserve = {str(item).strip() for item in as_list(source_contract.get("event_facts_to_preserve")) if str(item).strip()}
        if expected_facts and not expected_facts.issubset(declared_preserve):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.event_facts_to_preserve.mismatch")
        expected_not_invent = forbidden_event_changes
        declared_not_invent = {str(item).strip() for item in as_list(source_contract.get("event_facts_not_to_invent")) if str(item).strip()}
        if expected_not_invent and not expected_not_invent.issubset(declared_not_invent):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.event_facts_not_to_invent.mismatch")
        if primary_beat:
            expected_action = str(primary_beat.get("visible_action") or "").strip()
            if expected_action and str(source_contract.get("source_visible_action") or "").strip() != expected_action:
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_visible_action.mismatch")
            expected_evidence = {str(item).strip() for item in as_list(primary_beat.get("required_visual_evidence")) if str(item).strip()}
            declared_evidence = {str(item).strip() for item in as_list(source_contract.get("source_required_visual_evidence")) if str(item).strip()}
            if expected_evidence and not expected_evidence.issubset(declared_evidence):
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_required_visual_evidence.mismatch")
        first_frame = as_dict(contract.get("first_frame_contract"))
        if str(first_frame.get("source_event_beat_id") or "").strip() != primary:
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.source_event_beat_id")
        if str(first_frame.get("event_time_position") or "").strip() not in EVENT_TIME_POSITION_VALUES:
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.event_time_position")
        if not non_empty(first_frame.get("event_fact_visible_in_still")):
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.event_fact_visible_in_still")
        motion = as_dict(contract.get("motion_contract"))
        if str(motion.get("source_event_beat_id") or "").strip() != primary:
            issues["motion_boundary"].append(f"{selector}:motion_contract.source_event_beat_id")
        if motion.get("starts_from_first_frame") is not True:
            issues["motion_boundary"].append(f"{selector}:motion_contract.starts_from_first_frame")
        if "must_not_advance_to_event_beat_ids" not in motion or not isinstance(motion.get("must_not_advance_to_event_beat_ids"), list):
            issues["motion_boundary"].append(f"{selector}:motion_contract.must_not_advance_to_event_beat_ids")
        expected_blocked = [
            beat_id
            for beat_id in sequence_ids
            if beat_id not in refs and beat_functions.get(beat_id) in {"turn", "payoff"}
        ]
        motion_blocked = {str(item).strip() for item in as_list(motion.get("must_not_advance_to_event_beat_ids")) if str(item).strip()}
        if expected_blocked and not set(expected_blocked).issubset(motion_blocked):
            issues["motion_boundary"].append(f"{selector}:motion_contract.must_not_advance_to_event_beat_ids.incomplete")
        narration = as_dict(contract.get("narration_contract"))
        narration_refs = [str(item).strip() for item in as_list(narration.get("source_event_beat_ids")) if str(item).strip()]
        if not narration_refs or any(ref not in refs for ref in narration_refs):
            issues["narration_boundary"].append(f"{selector}:narration_contract.source_event_beat_ids")
        if narration.get("must_not_explain_visible_action_as_caption") is not True:
            issues["narration_boundary"].append(f"{selector}:narration_contract.must_not_explain_visible_action_as_caption")
        if str(narration.get("narration_event_boundary") or "").strip() not in {"same_event_only", "may_bridge_previous", "may_bridge_next_without_reveal"}:
            issues["narration_boundary"].append(f"{selector}:narration_contract.narration_event_boundary")
        narration_blocked = {str(item).strip() for item in as_list(narration.get("must_not_advance_to_event_beat_ids")) if str(item).strip()}
        if expected_blocked and not set(expected_blocked).issubset(narration_blocked):
            issues["narration_boundary"].append(f"{selector}:narration_contract.must_not_advance_to_event_beat_ids.incomplete")
        event_context = as_dict(contract.get("event_context_for_cut"))
        context_primary = as_dict(event_context.get("primary_event_beat"))
        if not event_context:
            issues["event_context_ready"].append(f"{selector}:event_context_for_cut")
        else:
            derived_from = {str(item).strip() for item in as_list(event_context.get("derived_from")) if str(item).strip()}
            if not {"scene_event.event_sequence[]", "cut_contract.source_event_contract"}.issubset(derived_from):
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.derived_from")
            if event_context.get("editable") is not False:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.editable")
            if str(context_primary.get("beat_id") or "").strip() != primary:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.primary_event_beat.beat_id")
            context_source_ids = {
                str(as_dict(beat).get("beat_id") or "").strip()
                for beat in as_list(event_context.get("source_event_beats"))
                if str(as_dict(beat).get("beat_id") or "").strip()
            }
            if set(refs) != context_source_ids:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.source_event_beats")
            expected_neighbor_ids: set[str] = set()
            for ref in refs:
                if ref not in sequence_ids:
                    continue
                index = sequence_ids.index(ref)
                for neighbor_index in (index - 1, index + 1):
                    if 0 <= neighbor_index < len(sequence_ids):
                        neighbor_id = sequence_ids[neighbor_index]
                        if neighbor_id not in refs:
                            expected_neighbor_ids.add(neighbor_id)
            context_neighbor_ids = {
                str(as_dict(beat).get("beat_id") or "").strip()
                for beat in as_list(event_context.get("neighboring_event_beats"))
                if str(as_dict(beat).get("beat_id") or "").strip()
            }
            if expected_neighbor_ids != context_neighbor_ids:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.neighboring_event_beats")
            context_forbidden = {str(item).strip() for item in as_list(event_context.get("forbidden_event_changes")) if str(item).strip()}
            if forbidden_event_changes and not forbidden_event_changes.issubset(context_forbidden):
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.forbidden_event_changes")
        covered.update(ref for ref in refs if ref in beat_ids)

    required_beats = {beat_id for beat_id, function in beat_functions.items() if function in set(REQUIRED_SCENE_EVENT_BEAT_FUNCTIONS)}
    missing_required = sorted(required_beats - covered)
    if missing_required:
        issues["sequence_covered"].extend(f"scene{scene_id}:{beat_id}.uncovered" for beat_id in missing_required)
    missing_turn_payoff = sorted(beat_id for beat_id in missing_required if beat_functions.get(beat_id) in {"turn", "payoff"})
    if missing_turn_payoff:
        issues["turn_payoff_have_cuts"].extend(f"scene{scene_id}:{beat_id}.uncovered" for beat_id in missing_turn_payoff)

    return {key: values for key, values in issues.items() if values}


def _scene_event_readiness_issues(scenes: list[Any], *, prefix: str = "script") -> list[str]:
    issues: list[str] = []
    for scene in scenes:
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip() == "reference":
            continue
        for issue_key, values in _scene_event_issue_map(scene).items():
            if values:
                issues.append(f"{prefix}.scene_event.{issue_key}")
        for issue_key, values in _cut_event_ref_issue_map(scene).items():
            if values:
                issues.append(f"{prefix}.cut_event.{issue_key}")
    return list(dict.fromkeys(issues))


def _cut_has_blueprint(cut: dict[str, Any]) -> bool:
    contract = _node_cut_contract(cut)
    if contract and _cut_contract_complete(contract):
        return True

    blueprint = cut.get("cut_blueprint")
    if not isinstance(blueprint, dict):
        return False
    required_keys = {
        "cut_role",
        "duration_intent",
        "target_beat",
        "must_show",
        "must_avoid",
        "done_when",
        "visual_beat",
        "narration_role",
        "asset_dependency_hint",
    }
    if not required_keys.issubset(set(blueprint)):
        return False
    return (
        non_empty(blueprint.get("cut_role"))
        and non_empty(blueprint.get("duration_intent"))
        and non_empty(blueprint.get("target_beat"))
        and non_empty(blueprint.get("visual_beat"))
        and non_empty(blueprint.get("narration_role"))
        and as_list(blueprint.get("must_show"))
        and as_list(blueprint.get("done_when"))
        and isinstance(blueprint.get("asset_dependency_hint"), dict)
    )


def _scene_target_duration_seconds(scene: dict[str, Any]) -> float:
    for key in ("target_duration_seconds", "estimated_duration_seconds"):
        value = scene.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    intent = scene.get("scene_intent") if isinstance(scene.get("scene_intent"), dict) else {}
    for key in ("target_duration_seconds", "estimated_duration_seconds"):
        value = intent.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 0.0


def _scene_importance(scene: dict[str, Any]) -> str:
    value = scene.get("importance")
    if not value and isinstance(scene.get("scene_intent"), dict):
        value = scene["scene_intent"].get("importance")
    return str(value or "").strip().lower()


def _scene_cut_coverage_plan(scene: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scene.get("scene_cut_coverage_plan"))


def _coverage_minimum_cut_count(plan: dict[str, Any]) -> int:
    if not isinstance(plan, dict):
        return 2
    direct = as_int(plan.get("minimum_cut_count"))
    if direct and direct > 0:
        return direct
    min_cut_count = as_dict(plan.get("min_cut_count"))
    selected = as_int(min_cut_count.get("selected"))
    if selected and selected > 0:
        return selected
    by_importance = as_int(min_cut_count.get("by_importance")) or 0
    by_duration = as_int(min_cut_count.get("by_duration")) or 0
    by_event_beats = as_int(min_cut_count.get("by_event_beats")) or 0
    return max(by_importance, by_duration, by_event_beats, 2)


def _scene_cut_selector(scene_id: str, cut: dict[str, Any]) -> str:
    selector = str(cut.get("selector") or "").strip()
    if selector:
        return selector
    cut_id = as_dotted_str(cut.get("cut_id"))
    if cut_id is None:
        return ""
    return make_scene_cut_selector(scene_id, cut_id)


def _cinematic_min_cuts_for_scene(scene: dict[str, Any]) -> int:
    importance = _scene_importance(scene)
    if importance == "critical":
        base_min = CINEMATIC_CRITICAL_IMPORTANCE_MIN_CUTS
    elif importance == "high":
        base_min = CINEMATIC_HIGH_IMPORTANCE_MIN_CUTS
    elif importance == "low":
        base_min = CINEMATIC_LOW_IMPORTANCE_MIN_CUTS
    else:
        base_min = CINEMATIC_SCENE_MIN_CUTS

    duration = _scene_target_duration_seconds(scene)
    if duration > 0:
        base_min = max(base_min, int((duration + CINEMATIC_SECONDS_PER_CUT_TARGET - 1) // CINEMATIC_SECONDS_PER_CUT_TARGET))
    return base_min


def _scene_cut_coverage_plan_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    plan = _scene_cut_coverage_plan(scene)
    if not plan:
        return [f"scene{scene_id}:scene_cut_coverage_plan"]

    actual_selectors = {_scene_cut_selector(scene_id, cut) for cut in cuts}
    actual_selectors = {selector for selector in actual_selectors if selector}
    selected_min = _coverage_minimum_cut_count(plan)
    actual_cut_count = len(cuts)
    if actual_cut_count < selected_min:
        issues.append(f"scene{scene_id}:cut_count_below_coverage_plan:{actual_cut_count}<{selected_min}")

    min_cut_count = as_dict(plan.get("min_cut_count"))
    by_importance = as_int(min_cut_count.get("by_importance")) or 0
    by_duration = as_int(min_cut_count.get("by_duration")) or 0
    by_event_beats = as_int(min_cut_count.get("by_event_beats")) or 0
    selected = as_int(min_cut_count.get("selected")) or as_int(plan.get("minimum_cut_count")) or 0
    if selected and selected < max(by_importance, by_duration, by_event_beats):
        issues.append(f"scene{scene_id}:coverage_plan_selected_below_floor")
    strategy = str(plan.get("coverage_strategy") or "").strip()
    if strategy and strategy != "reverse_from_scene_event":
        issues.append(f"scene{scene_id}:coverage_strategy")
    source_schema_version = str(plan.get("source_schema_version") or "").strip()
    if source_schema_version and source_schema_version != "scene_event_v1":
        issues.append(f"scene{scene_id}:source_schema_version")

    obligations = as_list(plan.get("scene_obligations"))
    if not obligations:
        issues.append(f"scene{scene_id}:scene_obligations")
    obligation_ids: set[str] = set()
    scene_obligation_assigned_selectors: set[str] = set()
    for index, obligation in enumerate(obligations, start=1):
        if not isinstance(obligation, dict):
            issues.append(f"scene{scene_id}:scene_obligations[{index}]")
            continue
        obligation_id = str(obligation.get("obligation_id") or "").strip()
        if obligation_id:
            obligation_ids.add(obligation_id)
        assigned = [str(item).strip() for item in as_list(obligation.get("assigned_cut_ids")) if str(item).strip()]
        scene_obligation_assigned_selectors.update(assigned)
        if not assigned:
            issues.append(f"scene{scene_id}:scene_obligations[{obligation_id or index}].assigned_cut_ids")
        for selector in assigned:
            if selector not in actual_selectors:
                issues.append(f"scene{scene_id}:scene_obligations[{obligation_id or index}].unknown_cut:{selector}")

    assignments = as_list(plan.get("cut_assignments"))
    if not assignments:
        issues.append(f"scene{scene_id}:cut_assignments")
    for index, assignment in enumerate(assignments, start=1):
        if not isinstance(assignment, dict):
            issues.append(f"scene{scene_id}:cut_assignments[{index}]")
            continue
        cut_selector_value = str(assignment.get("cut_selector") or "").strip()
        if not cut_selector_value:
            cut_index = as_int(assignment.get("cut_index"))
            if cut_index:
                cut_selector_value = make_scene_cut_selector(scene_id, f"{cut_index:02d}")
        if cut_selector_value not in actual_selectors:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].cut_selector")
        assignment_obligations = [
            str(item).strip()
            for item in as_list(assignment.get("obligation_ids"))
            if str(item).strip()
        ]
        single_obligation = str(assignment.get("obligation_id") or "").strip()
        if single_obligation:
            assignment_obligations.append(single_obligation)
        if obligation_ids and not any(obligation_id in obligation_ids for obligation_id in assignment_obligations) and cut_selector_value not in scene_obligation_assigned_selectors:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].obligation_ids")

    if as_list(plan.get("unassigned_obligations")):
        issues.append(f"scene{scene_id}:unassigned_obligations")
    overloaded = as_list(plan.get("overloaded_cuts"))
    for index, item in enumerate(overloaded, start=1):
        if not isinstance(item, dict) or not non_empty(item.get("overload_exception_reason") or item.get("exception_reason")):
            issues.append(f"scene{scene_id}:overloaded_cuts[{index}]")
    duplicate_risks = as_list(plan.get("duplicate_meaning_risks"))
    for index, item in enumerate(duplicate_risks, start=1):
        if not isinstance(item, dict) or not non_empty(item.get("prompt_reinforcement_reason") or item.get("reinforcement_reason")):
            issues.append(f"scene{scene_id}:duplicate_meaning_risks[{index}]")
    return issues


def _scene_cut_redundancy_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    plan = _scene_cut_coverage_plan(scene)
    allowed_duplicate_keys = {
        str(item.get("anti_redundancy_key") or item.get("meaning_key") or "").strip()
        for item in as_list(plan.get("duplicate_meaning_risks"))
        if isinstance(item, dict) and non_empty(item.get("prompt_reinforcement_reason") or item.get("reinforcement_reason"))
    }
    seen: dict[str, str] = {}
    for cut in cuts:
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "cut")
        contract = _node_cut_contract(cut, allow_legacy=False)
        key = _contract_string(contract, "viewer_contract.anti_redundancy_key", "anti_redundancy_key")
        if not key:
            issues.append(f"{selector}:anti_redundancy_key")
            continue
        if key in seen and key not in allowed_duplicate_keys:
            issues.append(f"{selector}:duplicate_anti_redundancy_key:{key}")
        seen.setdefault(key, selector)
    return issues


def _scene_cut_handoff_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    previous_outgoing: dict[str, Any] | None = None
    previous_selector = ""
    for index, cut in enumerate(cuts):
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or index + 1)
        contract = _node_cut_contract(cut, allow_legacy=False)
        handoff = as_dict(contract.get("cut_handoff"))
        incoming = as_dict(handoff.get("receives_from_previous"))
        outgoing = as_dict(handoff.get("delivers_to_next"))
        if not incoming:
            issues.append(f"{selector}:cut_handoff.receives_from_previous")
        if not outgoing:
            issues.append(f"{selector}:cut_handoff.delivers_to_next")
        if index == 0:
            incoming_type = str(incoming.get("anchor_type") or "").strip().lower()
            if incoming and incoming_type not in {"none", "question", "object", "sound", "gaze", "gesture", "movement", "light", "threat"}:
                issues.append(f"{selector}:cut_handoff.incoming.anchor_type")
        elif previous_outgoing:
            previous_anchor = str(previous_outgoing.get("anchor_id") or "").strip()
            incoming_anchor = str(incoming.get("anchor_id") or "").strip()
            if previous_anchor and previous_anchor != incoming_anchor:
                issues.append(f"{selector}:cut_handoff.anchor_mismatch:{previous_selector}->{selector}")
        if index < len(cuts) - 1:
            if not non_empty(outgoing.get("anchor_id")) or not non_empty(outgoing.get("visible_or_audible_form")):
                issues.append(f"{selector}:cut_handoff.outgoing")
        else:
            outgoing_type = str(outgoing.get("anchor_type") or "").strip().lower()
            if outgoing_type not in {"terminal", "question", "object", "sound", "gaze", "gesture", "movement", "light", "threat"}:
                issues.append(f"{selector}:cut_handoff.final_anchor_type")
        previous_outgoing = outgoing
        previous_selector = selector
    return issues


def _triangulation_review_issues(cut: dict[str, Any], *, selector: str) -> list[str]:
    review = as_dict(cut.get("review")).get("triangulation_review")
    if not isinstance(review, dict):
        image_review = as_dict(as_dict(cut.get("image_generation")).get("review"))
        review = image_review.get("triangulation_review")
    if not isinstance(review, dict):
        return [f"{selector}:triangulation_review"]
    status = str(review.get("status") or "").strip().lower()
    human_waived = str(review.get("waived_by") or "").strip().lower() in {"human", "user"} and non_empty(review.get("waiver_reason"))
    if status in {"waived", "approved"} and human_waived:
        return []
    issues = [f"{selector}:triangulation_review.status" if status and status not in {"passed", "approved"} else ""]
    for key in TRIANGULATION_REQUIRED_KEYS:
        if review.get(key) is not True:
            issues.append(f"{selector}:triangulation_review.{key}")
    return [issue for issue in issues if issue]


def _scene_readiness_issues(scenes: list[Any]) -> list[str]:
    issues: list[str] = []
    concrete_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    for index, scene in enumerate(concrete_scenes):
        scene_id = as_dotted_str(scene.get("scene_id")) or str(index + 1)
        importance = _scene_importance(scene)
        if importance not in {"low", "medium", "high", "critical"}:
            issues.append(f"scene{scene_id}:importance")
        for key in ("target_duration_seconds", "estimated_duration_seconds"):
            value = scene.get(key)
            if not isinstance(value, (int, float)) and isinstance(scene.get("scene_intent"), dict):
                value = scene["scene_intent"].get(key)
            if not isinstance(value, (int, float)) or value <= 0:
                issues.append(f"scene{scene_id}:{key}")
        if index < len(concrete_scenes) - 1:
            if not non_empty(scene.get("handoff_to_next_scene")):
                issues.append(f"scene{scene_id}:handoff_to_next_scene")
        elif not (non_empty(scene.get("terminal_resolution")) or non_empty(scene.get("handoff_to_next_scene"))):
            issues.append(f"scene{scene_id}:terminal_resolution")

        cuts = [
            cut
            for cut in as_list(scene.get("cuts"))
            if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
        ]
        min_cuts = _cinematic_min_cuts_for_scene(scene)
        if len(cuts) < min_cuts:
            issues.append(f"scene{scene_id}:cut_count_below_calculated_floor:{len(cuts)}<{min_cuts}")
        has_new_cut_contract = any(isinstance(cut.get("cut_contract"), dict) and cut.get("cut_contract") for cut in cuts)
        if _scene_cut_coverage_plan(scene) or has_new_cut_contract:
            issues.extend(_scene_cut_coverage_plan_issues(scene, scene_id=scene_id, cuts=cuts))
            issues.extend(_scene_cut_redundancy_issues(scene, scene_id=scene_id, cuts=cuts))
            issues.extend(_scene_cut_handoff_issues(scene, scene_id=scene_id, cuts=cuts))

        coverage = scene.get("coverage_review")
        if not isinstance(coverage, dict):
            issues.append(f"scene{scene_id}:coverage_review")
        else:
            for key in SCENE_COVERAGE_REVIEW_REQUIRED_KEYS:
                if coverage.get(key) is not True:
                    issues.append(f"scene{scene_id}:{key}")
    return issues


def _review_status(data: dict[str, Any], key: str) -> str:
    review = data.get(key)
    if isinstance(review, dict):
        return str(review.get("status") or "").strip().lower()
    nested = nested_get(data, ["script", key], {})
    if isinstance(nested, dict):
        return str(nested.get("status") or "").strip().lower()
    return ""


def _append_p400_scene_cut_checks(checks: list[dict[str, Any]], data: dict[str, Any], scenes: list[Any]) -> None:
    if not scenes:
        return

    scene_set_status = _review_status(data, "scene_set_review")
    scene_detail_status = _review_status(data, "scene_detail_review")
    cut_blueprint_status = _review_status(data, "cut_blueprint_review")
    add_check(
        checks,
        "script.scene_set_review_approved",
        scene_set_status == "approved",
        f"p410 abstract scene-set review is approved before p420 (got {scene_set_status or 'missing'})",
        kind="rubric",
    )
    add_check(
        checks,
        "script.scene_detail_review_approved",
        scene_detail_status == "approved",
        f"p410 concrete per-scene review is approved before p420 (got {scene_detail_status or 'missing'})",
        kind="rubric",
    )
    add_check(
        checks,
        "script.cut_blueprint_review_approved",
        cut_blueprint_status == "approved",
        f"p420 cut blueprint review is approved before p430 (got {cut_blueprint_status or 'missing'})",
        kind="rubric",
    )
    scene_count = len([scene for scene in scenes if isinstance(scene, dict)])
    scenes_with_intent = sum(1 for scene in scenes if isinstance(scene, dict) and _scene_has_intent(scene))
    add_check(
        checks,
        "script.scene_intent_cards",
        scenes_with_intent == scene_count,
        f"all scenes include p410 scene_intent cards ({scenes_with_intent}/{scene_count})",
        kind="rubric",
    )
    scene_contract_issues: dict[str, list[str]] = {
        "dramatic_question": [],
        "value_shift": [],
        "causal_turn": [],
        "visual_thesis": [],
        "story_specificity": [],
        "conflict_engine": [],
        "handoff_chain": [],
        "coverage_review": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for key, values in _scene_intent_issue_map(scene).items():
            scene_contract_issues.setdefault(key, []).extend(values)
    scene_contract_checks = (
        ("script.scene_dramatic_question_complete", "dramatic_question", "all scenes declare dramatic_question, scene_spine, and audience knowledge delta"),
        ("script.scene_value_shift_complete", "value_shift", "all scenes declare value_shift.from/to and visible evidence"),
        ("script.scene_causal_turn_complete", "causal_turn", "all scenes declare an irreversible causal_turn"),
        ("script.scene_visual_thesis_complete", "visual_thesis", "all scenes declare a concrete visual thesis"),
        ("script.scene_story_specificity_complete", "story_specificity", "all scenes declare story_specificity and avoid generic template language"),
        ("script.scene_conflict_engine_complete", "conflict_engine", "all scenes declare desire, obstacle, stakes, escalation, no-return point, and visible pressure"),
        ("script.scene_handoff_chain_complete", "handoff_chain", "all scenes declare concrete incoming/outgoing handoff chains"),
        ("script.scene_coverage_review_complete", "coverage_review", "all scenes mark required coverage_review gates as true"),
    )
    for check_id, issue_key, message in scene_contract_checks:
        issue_values = scene_contract_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )

    scene_event_issues: dict[str, list[str]] = {
        "exists": [],
        "sequence_complete": [],
        "visible_actions_complete": [],
        "no_forbidden_directing_fields": [],
        "beat_ids_unique": [],
        "turning_event_ref_valid": [],
        "end_situation_ref_valid": [],
        "reveal_constraints_respected": [],
    }
    cut_event_issues: dict[str, list[str]] = {
        "refs_valid": [],
        "reference_integrity": [],
        "source_event_preservation": [],
        "first_frame_alignment": [],
        "motion_boundary": [],
        "narration_boundary": [],
        "event_context_ready": [],
        "sequence_covered": [],
        "turn_payoff_have_cuts": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for key, values in _scene_event_issue_map(scene).items():
            scene_event_issues.setdefault(key, []).extend(values)
        for key, values in _cut_event_ref_issue_map(scene).items():
            cut_event_issues.setdefault(key, []).extend(values)
    scene_event_checks = (
        ("script.scene_event_exists", "exists", "all scenes include canonical scene_event with scene_event_v1 fields"),
        ("script.scene_event_sequence_complete", "sequence_complete", "scene_event.event_sequence includes setup, pressure, turn, payoff beats with source story refs"),
        ("script.scene_event_visible_actions_complete", "visible_actions_complete", "each scene_event beat declares what happens, visible action/reaction, consequence, pressure, and visual evidence"),
        ("script.scene_event_no_forbidden_directing_fields", "no_forbidden_directing_fields", "scene_event contains story events only and no directing or prompt fields"),
        ("script.scene_event_beat_ids_unique", "beat_ids_unique", "scene_event beat_id values are present and unique per scene"),
        ("script.scene_event_turning_event_ref_valid", "turning_event_ref_valid", "scene_event.turning_event references the turn beat and scene_intent.causal_turn"),
        ("script.scene_event_end_situation_ref_valid", "end_situation_ref_valid", "scene_event.end_situation references scene_intent.value_shift.to and declared event evidence"),
        ("script.scene_event_reveal_constraints_respected", "reveal_constraints_respected", "scene_event does not fully reveal forbidden reveal IDs"),
    )
    for check_id, issue_key, message in scene_event_checks:
        issue_values = scene_event_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )
    cut_event_checks = (
        ("script.cut_event_beat_refs_valid", "refs_valid", "all cut_contract entries reference valid scene_event beat ids"),
        ("script.event_beat_reference_integrity", "reference_integrity", "cut_contract.source_event_contract matches the primary scene_event beat and enum policy"),
        ("script.source_event_preservation", "source_event_preservation", "cut_contract.source_event_contract preserves source event facts and reveal boundaries"),
        ("script.event_first_frame_alignment", "first_frame_alignment", "first_frame_contract aligns with the primary source event beat"),
        ("script.event_motion_boundary", "motion_boundary", "motion_contract starts from the first frame and does not cross forbidden event beat boundaries"),
        ("script.event_narration_boundary", "narration_boundary", "narration_contract stays within allowed event and reveal boundaries"),
        ("script.event_context_for_cut_ready", "event_context_ready", "event_context_for_cut is a non-editable derived projection matching source_event_contract"),
        ("script.cuts_cover_scene_event_sequence", "sequence_covered", "cuts cover every required scene_event setup/pressure/turn/payoff beat"),
        ("script.turn_and_payoff_event_beats_have_cuts", "turn_payoff_have_cuts", "turn and payoff event beats are assigned to at least one cut"),
    )
    for check_id, issue_key, message in cut_event_checks:
        issue_values = cut_event_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )
    scenes_agent_passed = sum(
        1
        for scene in scenes
        if isinstance(scene, dict)
        and str(((scene.get("agent_review") or {}) if isinstance(scene.get("agent_review"), dict) else {}).get("status") or "").strip().lower() == "passed"
    )
    add_check(
        checks,
        "script.scene_agent_review_passed",
        scenes_agent_passed == scene_count,
        f"all scenes have agent_review.status=passed ({scenes_agent_passed}/{scene_count})",
        kind="rubric",
    )

    renderable_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    scenes_with_cuts = [scene for scene in renderable_scenes if as_list(scene.get("cuts"))]
    add_check(
        checks,
        "script.renderable_scenes_have_cuts",
        len(scenes_with_cuts) == len(renderable_scenes),
        f"all renderable scenes include cuts ({len(scenes_with_cuts)}/{len(renderable_scenes)})",
        kind="rubric",
    )

    cuts: list[dict[str, Any]] = []
    for scene in renderable_scenes:
        cuts.extend([cut for cut in as_list(scene.get("cuts")) if isinstance(cut, dict)])
    if not cuts:
        add_check(checks, "script.cut_blueprints", False, "renderable cuts include p420 cut_blueprint entries (0/0)", kind="rubric")
        return
    cuts_with_blueprint = sum(1 for cut in cuts if _cut_has_blueprint(cut))
    add_check(
        checks,
        "script.cut_blueprints",
        cuts_with_blueprint == len(cuts),
        f"all cuts include p420 cut_blueprint entries ({cuts_with_blueprint}/{len(cuts)})",
        kind="rubric",
    )
    readiness_issues = _scene_readiness_issues(scenes)
    add_check(
        checks,
        "script.scene_readiness_contract",
        not readiness_issues,
        "all scenes declare importance, target/estimated duration, handoff, coverage review, and importance-based cut count"
        + (f" (issues: {', '.join(readiness_issues[:8])})" if readiness_issues else ""),
        kind="rubric",
    )


def check_script_single(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "script.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}

    add_check(checks, "script.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("script", path.name, checks), updates

    text, data = load_structured_document(path)
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    body_text = flatten_without_keys(data, excluded={"evaluation_contract"}) or text
    _script_text_quality_checks(checks, body_text, data, profile)
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    flattened = body_text
    _append_p400_scene_cut_checks(checks, data, scenes)
    if not contract:
        add_check(checks, "script.contract_missing", False, "evaluation_contract is missing for script stage.", kind="rubric")
    else:
        must_cover = contract_list(contract, "must_cover")
        must_avoid = contract_list(contract, "must_avoid")
        target_arc = [part.strip() for part in str(contract.get("target_arc") or "").split(",") if part.strip()]
        phases = {str(scene.get("phase") or "").strip() for scene in scenes if isinstance(scene, dict)}
        if must_cover and not all(term in flattened for term in must_cover):
            add_check(checks, "script.contract_must_cover_unmet", False, "script does not yet cover all required beats or anchors.", kind="rubric")
        if must_avoid and any(term in flattened for term in must_avoid):
            add_check(checks, "script.contract_must_avoid_violated", False, "script still includes a forbidden beat or phrase from the contract.", kind="rubric")
        if target_arc and not all(phase in phases for phase in target_arc):
            add_check(checks, "script.contract_target_arc_unmet", False, "script phases do not yet satisfy target_arc.", kind="rubric")
    rubric_scores = _script_rubric(body_text, data, scenes=scenes)
    _append_rubric_findings(checks=checks, stage="script", rubric_scores=rubric_scores)
    updates["eval.script.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("script", path.name, checks, rubric_scores=rubric_scores), updates


def check_script_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    script_paths = [scene_dir / "script.md" for scene_dir in scene_dirs]

    add_check(checks, "script.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "script.scene_files", all(path.exists() for path in script_paths), "each scene has script.md")
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")

    all_no_todo = True
    scene_event_issues: list[str] = []
    for path in script_paths:
        if not path.exists():
            all_no_todo = False
            continue
        text = path.read_text(encoding="utf-8")
        if profile == "standard" and has_todo(text):
            all_no_todo = False
        _scene_text, data = load_structured_document(path)
        scene_data = data.get("scene") if isinstance(data.get("scene"), dict) else data
        scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
        if not scenes and isinstance(scene_data, dict):
            scenes = [scene_data]
        scene_event_issues.extend(_scene_event_readiness_issues(scenes, prefix="script.scene_series"))
    if profile == "standard":
        add_check(checks, "script.scene_no_todo", all_no_todo, "scene scripts do not contain TODO/TBD markers", kind="rubric")
    add_check(
        checks,
        "script.scene_series_scene_event_contract",
        not scene_event_issues,
        "scene-series scripts satisfy scene_event v1 and cut event beat contracts"
        + (f" (issues: {', '.join(scene_event_issues[:8])})" if scene_event_issues else ""),
        kind="rubric",
    )

    updates = {"eval.script.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("script", "scenes/*/script.md", checks, details={"scene_count": len(scene_dirs)}), updates


def _iter_manifest_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for scene in as_list(manifest.get("scenes")):
        if isinstance(scene, dict) and str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = as_list(scene.get("cuts")) if isinstance(scene, dict) else []
        if cuts:
            nodes.extend([cut for cut in cuts if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"])
        elif isinstance(scene, dict):
            nodes.append(scene)
    return nodes


def _iter_manifest_nodes_with_selectors(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for scene in as_list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue
        cuts = as_list(scene.get("cuts"))
        if cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                if str(cut.get("cut_status") or "").strip().lower() == "deleted":
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if cut_id is None:
                    continue
                items.append((make_scene_cut_selector(scene_id, cut_id), cut))
        else:
            items.append((make_scene_cut_selector(scene_id), scene))
    return items


def _minimum_cut_issues(manifest: dict[str, Any], *, min_cuts_per_scene: int | None = None) -> list[str]:
    issues: list[str] = []
    for index, scene in enumerate(as_list(manifest.get("scenes")), start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene[{index}]:invalid")
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id")) or str(index)
        cuts = [
            cut
            for cut in as_list(scene.get("cuts"))
            if not (isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() == "deleted")
        ]
        scene_min = min_cuts_per_scene if min_cuts_per_scene is not None else _cinematic_min_cuts_for_scene(scene)
        if len(cuts) < scene_min:
            issues.append(f"scene{scene_id}:cut_count_below_calculated_floor:{len(cuts)}<{scene_min}")
        plan = _scene_cut_coverage_plan(scene)
        planned_min = _coverage_minimum_cut_count(plan) if plan else 0
        if planned_min and len(cuts) < planned_min:
            issues.append(f"scene{scene_id}:cut_count_below_coverage_plan:{len(cuts)}<{planned_min}")
        min_cut_count = as_dict(plan.get("min_cut_count")) if plan else {}
        selected = as_int(min_cut_count.get("selected")) or as_int(plan.get("minimum_cut_count")) or 0
        by_importance = as_int(min_cut_count.get("by_importance")) or 0
        by_duration = as_int(min_cut_count.get("by_duration")) or 0
        if selected and selected < max(by_importance, by_duration):
            issues.append(f"scene{scene_id}:coverage_plan_selected_below_floor")
    return issues


P400_READINESS_CHECK_IDS = {
    "p400.skeleton_manifest_phase",
    "p400.target_duration_range",
    "p400.duration_coverage",
    "p400.script_readiness_contract",
    "p400.script_manifest_selector_match",
    "p400.review_report_integrity",
    "p400.review_loop_integrity",
    "manifest.scenes",
    "manifest.nodes",
    "manifest.minimum_scene_cuts",
    "manifest.cut_duration",
    "manifest.asset_ids",
    "manifest.experience",
    "manifest.no_onscreen_text_rule",
    "manifest.contract_missing",
    "manifest.contract_must_show_unmet",
    "manifest.contract_must_avoid_violated",
    "manifest.reveal_constraints_violated",
    "manifest.prompt_leaks_motion_brief",
    "manifest.scene_cut_coverage_plan",
    "manifest.scene_cut_redundancy",
    "manifest.cut_handoff_chain",
    "manifest.scene_composite_review",
    "manifest.triangulation_review",
    "manifest.cut_contract_structure",
}


def _manifest_duration_summary(manifest: dict[str, Any]) -> tuple[float, float, int]:
    target = nested_get(manifest, ["video_metadata", "target_duration_seconds"])
    target_seconds = float(target) if isinstance(target, (int, float)) else 0.0
    actual_seconds = 0.0
    cut_count = 0
    for node in _iter_manifest_nodes(manifest):
        if str(node.get("cut_status") or "").strip().lower() == "deleted":
            continue
        duration = node.get("duration_seconds")
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        if not isinstance(duration, (int, float)):
            duration = video_generation.get("duration_seconds")
        if isinstance(duration, (int, float)):
            actual_seconds += float(duration)
        cut_count += 1
    return target_seconds, actual_seconds, cut_count


def _script_selectors_from_run(run_dir: Path) -> set[str]:
    path = run_dir / "script.md"
    if not path.exists():
        return set()
    _text, data = load_structured_document(path)
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    selectors: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip() == "reference":
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            explicit = str(cut.get("selector") or "").strip()
            if explicit:
                selectors.add(explicit)
                continue
            cut_id = as_dotted_str(cut.get("cut_id"))
            if cut_id is not None:
                selectors.add(make_scene_cut_selector(scene_id, cut_id))
    return selectors


def _script_readiness_issues_from_run(run_dir: Path) -> list[str]:
    path = run_dir / "script.md"
    if not path.exists():
        return ["script.md:missing"]
    _text, data = load_structured_document(path)
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    issues: list[str] = []
    if not scenes:
        issues.append("script.scenes:missing")
    readiness_issues = _scene_readiness_issues(scenes)
    issues.extend(readiness_issues)
    issues.extend(_scene_event_readiness_issues(scenes, prefix="script"))
    if _review_status(data, "cut_blueprint_review") not in {"approved", "passed"}:
        issues.append("script.cut_blueprint_review_approved")
    renderable_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    missing_cuts = [
        as_dotted_str(scene.get("scene_id")) or str(index + 1)
        for index, scene in enumerate(renderable_scenes)
        if not as_list(scene.get("cuts"))
    ]
    if missing_cuts:
        issues.append("script.renderable_scenes_have_cuts")
    missing_blueprints: list[str] = []
    for scene in renderable_scenes:
        scene_id = as_dotted_str(scene.get("scene_id")) or "unknown"
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            if not _cut_has_blueprint(cut):
                cut_id = as_dotted_str(cut.get("cut_id")) or "unknown"
                missing_blueprints.append(f"scene{scene_id}_cut{cut_id}")
    if missing_blueprints:
        issues.append("script.cut_blueprints")
    return issues


def _manifest_selectors(manifest: dict[str, Any]) -> set[str]:
    selectors: set[str] = set()
    for selector, node in _iter_manifest_nodes_with_selectors(manifest):
        if str(node.get("cut_status") or "").strip().lower() == "deleted":
            continue
        explicit = str(node.get("selector") or "").strip()
        selectors.add(explicit or selector)
    return selectors


def _review_report_status(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("status:"):
            return stripped.split(":", 1)[1].strip().strip("`\"'").lower()
        if stripped.lower().startswith("- status:"):
            return stripped.split(":", 1)[1].strip().strip("`\"'").lower()
    return ""


def _review_report_issues(run_dir: Path) -> list[str]:
    required_reports = {
        "scene_set_review.md": ("status",),
        "scene_detail_review.md": ("status",),
        "cut_blueprint_review.md": ("status",),
        "script_review.md": ("status",),
        "production_readiness_review.md": ("Structure", "Duration", "Quality", "Design Owner Patch Brief"),
    }
    issues: list[str] = []
    for filename, markers in required_reports.items():
        path = run_dir / filename
        if not path.exists():
            issues.append(f"{filename}:missing")
            continue
        text = path.read_text(encoding="utf-8")
        if _review_report_status(text) not in {"passed", "approved"}:
            issues.append(f"{filename}:status")
        for marker in markers:
            if marker not in text:
                issues.append(f"{filename}:missing:{marker}")
    readiness_path = run_dir / "production_readiness_review.md"
    if readiness_path.exists():
        text = readiness_path.read_text(encoding="utf-8").lower()
        forbidden = ("p700", "後続", "defer", "later", "実尺 gate")
        if any(token in text for token in forbidden):
            issues.append("production_readiness_review.md:duration_deferred")
    return issues


def _review_loop_integrity_issues(run_dir: Path, stages: tuple[str, ...] = ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness")) -> list[str]:
    issues: list[str] = []

    def marker_value_resolved(text: str, marker: str) -> bool:
        if marker.startswith("##"):
            return True
        for line in text.splitlines():
            if marker not in line:
                continue
            if ":" not in line:
                return True
            value = line.split(":", 1)[1].strip().strip("`").lower()
            return value not in UNRESOLVED_GATE_VALUES and "todo" not in value
        return False

    for stage in stages:
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        if not round_dir.exists():
            issues.append(f"{stage}:round_01_missing")
            continue
        critic_reports = sorted(round_dir.glob("critic_*.md"))
        if len(critic_reports) != REVIEW_LOOP_CRITIC_COUNT:
            issues.append(f"{stage}:critics<{REVIEW_LOOP_CRITIC_COUNT}")
        stage_focus = REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE.get(stage, {})
        for critic_number, (focus_name, _) in stage_focus.items():
            prompt_path = round_dir / "prompts" / f"critic_{critic_number}.prompt.md"
            if not prompt_path.exists():
                issues.append(f"{stage}:critic_{critic_number}_prompt_missing")
            elif focus_name not in prompt_path.read_text(encoding="utf-8"):
                issues.append(f"{stage}:critic_{critic_number}_prompt_missing_focus:{focus_name}")
            report_path = round_dir / f"critic_{critic_number}.md"
            if report_path.exists() and focus_name not in report_path.read_text(encoding="utf-8"):
                issues.append(f"{stage}:critic_{critic_number}_report_missing_focus:{focus_name}")
        aggregate = round_dir / "aggregated_review.md"
        if not aggregate.exists():
            issues.append(f"{stage}:aggregated_review_missing")
            continue
        aggregate_text = aggregate.read_text(encoding="utf-8")
        required_sections = ("## Blocking Findings", "## Recommended Changes", "## Rejected Suggestions", "## Round Summary")
        for section in required_sections:
            if section not in aggregate_text:
                issues.append(f"{stage}:missing:{section}")
        patch_heading = "## Design Owner Patch Brief" if stage == "production_readiness" else "## Generator Patch Brief"
        if patch_heading not in aggregate_text:
            issues.append(f"{stage}:missing:{patch_heading}")
        if stage_focus:
            if stage == "scene_set":
                markers = SCENE_SET_GATE_MARKERS
            elif stage == "scene_detail":
                markers = SCENE_DETAIL_GATE_MARKERS
            else:
                markers = CUT_BLUEPRINT_GATE_MARKERS
            for marker in markers:
                if marker not in aggregate_text:
                    issues.append(f"{stage}:missing:{marker}")
                elif not marker_value_resolved(aggregate_text, marker):
                    issues.append(f"{stage}:unresolved:{marker}")
    return issues


def _selector_sort_key(selector: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    raw = str(selector or "").strip()
    if not raw.startswith("scene"):
        return ((10**9,), (10**9,))
    body = raw[len("scene") :]
    if "_cut" in body:
        scene_part, cut_part = body.split("_cut", 1)
    else:
        scene_part, cut_part = body, None
    return (
        dotted_id_sort_key(scene_part),
        dotted_id_sort_key(cut_part) if cut_part is not None else (0,),
    )


def _load_script_reveal_constraints(run_dir: Path) -> list[dict[str, str]]:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        return []
    _, data = load_structured_document(script_path)
    if not isinstance(data, dict):
        return []
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    raw_items = contract.get("reveal_constraints")
    if not isinstance(raw_items, list):
        return []
    constraints: list[dict[str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = {
            "subject_type": str(raw.get("subject_type") or "").strip(),
            "subject_id": str(raw.get("subject_id") or "").strip(),
            "rule": str(raw.get("rule") or "").strip(),
            "selector": str(raw.get("selector") or "").strip(),
        }
        if all(item.values()):
            constraints.append(item)
    return constraints


def _load_script_change_request_contract(run_dir: Path) -> dict[str, Any]:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
    _, data = load_structured_document(script_path)
    if not isinstance(data, dict):
        return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}

    issues: list[str] = []
    expected_request_ids: set[str] = set()
    request_ids_by_selector: dict[str, set[str]] = {}

    for scene in as_list(data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue

        scene_review = scene.get("human_review") if isinstance(scene.get("human_review"), dict) else {}
        scene_status = str(scene_review.get("status") or "").strip().lower() if isinstance(scene_review, dict) else ""
        scene_request_ids = {str(item).strip() for item in as_list(scene_review.get("change_request_ids")) if str(item).strip()}
        if scene_status == "changes_requested":
            selector = make_scene_cut_selector(scene_id)
            if not scene_request_ids:
                issues.append(f"human_change_request_missing_request_id:{selector}")
            expected_request_ids.update(scene_request_ids)
            request_ids_by_selector.setdefault(selector, set()).update(scene_request_ids)

        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            cut_id = as_dotted_str(cut.get("cut_id"))
            if cut_id is None:
                continue
            review = cut.get("human_review") if isinstance(cut.get("human_review"), dict) else {}
            status = str(review.get("status") or "").strip().lower() if isinstance(review, dict) else ""
            request_ids = {str(item).strip() for item in as_list(review.get("change_request_ids")) if str(item).strip()}
            if status != "changes_requested":
                continue
            selector = make_scene_cut_selector(scene_id, cut_id)
            if not request_ids:
                issues.append(f"human_change_request_missing_request_id:{selector}")
                continue
            expected_request_ids.update(request_ids)
            request_ids_by_selector.setdefault(selector, set()).update(request_ids)

    request_map = {
        str(item.get("request_id") or "").strip(): item
        for item in as_list(data.get("human_change_requests"))
        if isinstance(item, dict) and str(item.get("request_id") or "").strip()
    }
    for selector, request_ids in request_ids_by_selector.items():
        for request_id in sorted(request_ids):
            if request_id not in request_map:
                issues.append(f"human_change_request_missing_definition:{selector}:{request_id}")

    return {
        "expected_request_ids": expected_request_ids,
        "request_ids_by_selector": request_ids_by_selector,
        "issues": issues,
    }


def _human_change_request_issues(manifest: dict[str, Any], *, run_dir: Path | None = None) -> list[str]:
    issues: list[str] = []
    script_contract = _load_script_change_request_contract(run_dir) if run_dir else {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
    issues.extend(list(script_contract.get("issues") or []))
    raw_requests = manifest.get("human_change_requests")
    manifest_request_map: dict[str, dict[str, Any]] = {}
    if isinstance(raw_requests, list):
        for raw in raw_requests:
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "").strip().lower()
            request_id = str(raw.get("request_id") or "<unknown>").strip()
            manifest_request_map[request_id] = raw
            if status not in {"verified", "waived"}:
                issues.append(f"human_change_request_unresolved:{request_id}")
    for request_id in sorted(script_contract.get("expected_request_ids") or set()):
        if request_id not in manifest_request_map:
            issues.append(f"human_change_request_missing_from_manifest:{request_id}")

    for selector, node in _iter_manifest_nodes_with_selectors(manifest):
        implementation_trace = node.get("implementation_trace") if isinstance(node.get("implementation_trace"), dict) else {}
        source_request_ids = [str(item).strip() for item in as_list(implementation_trace.get("source_request_ids")) if str(item).strip()]
        trace_status = str(implementation_trace.get("status") or "").strip().lower()
        expected_request_ids = set((script_contract.get("request_ids_by_selector") or {}).get(selector, set()))
        combined_request_ids = sorted(set(source_request_ids) | expected_request_ids)
        if expected_request_ids and not source_request_ids:
            issues.append(f"human_change_request_trace_missing:{selector}")
        if source_request_ids and trace_status not in {"implemented", "verified", "waived"}:
            issues.append(f"human_change_request_trace_missing:{selector}")

        for key, path in (
            ("audio", ["narration", "applied_request_ids"]),
            ("image_generation", ["applied_request_ids"]),
            ("video_generation", ["applied_request_ids"]),
        ):
            cur: Any = node.get(key) if isinstance(node.get(key), dict) else {}
            for part in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(part)
            applied_ids = [str(item).strip() for item in as_list(cur) if str(item).strip()]
            if combined_request_ids and not set(combined_request_ids).issubset(set(applied_ids)):
                issues.append(f"human_change_request_trace_missing:{selector}:{key}")

        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        if image_generation:
            if "location_ids" in image_generation and not isinstance(image_generation.get("location_ids"), list):
                issues.append(f"dotted_selector_invalid:{selector}:location_ids")
            if "location_variant_ids" in image_generation and not isinstance(image_generation.get("location_variant_ids"), list):
                issues.append(f"dotted_selector_invalid:{selector}:location_variant_ids")

        still_assets = node.get("still_assets")
        if still_assets is None:
            continue
        if not isinstance(still_assets, list):
            issues.append(f"still_asset_missing:{selector}")
            continue
        known_asset_ids = {
            str(asset.get("asset_id") or "").strip()
            for asset in still_assets
            if isinstance(asset, dict) and str(asset.get("asset_id") or "").strip()
        }
        for asset in still_assets:
            if not isinstance(asset, dict):
                issues.append(f"still_asset_missing:{selector}")
                continue
            asset_id = str(asset.get("asset_id") or "<unknown>").strip()
            if not isinstance(asset.get("image_generation"), dict):
                issues.append(f"still_asset_missing:{selector}:{asset_id}")
            for dep_key in ("derived_from_asset_ids", "reference_asset_ids"):
                for dep in [str(item).strip() for item in as_list(asset.get(dep_key)) if str(item).strip()]:
                    if dep not in known_asset_ids:
                        issues.append(f"still_asset_dependency_missing:{selector}:{asset_id}:{dep}")
            for usage in as_list(asset.get("reference_usage")):
                if not isinstance(usage, dict):
                    continue
                target_asset_id = str(usage.get("asset_id") or "").strip()
                if target_asset_id and target_asset_id not in known_asset_ids:
                    issues.append(f"reference_usage_target_missing:{selector}:{asset_id}:{target_asset_id}")

        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        referenced_video_asset_ids = [
            str(item).strip()
            for item in as_list(video_generation.get("reference_asset_ids"))
            if str(item).strip()
        ]
        for key in ("input_asset_id", "first_frame_asset_id", "last_frame_asset_id"):
            value = str(video_generation.get(key) or "").strip()
            if value and value not in known_asset_ids:
                issues.append(f"video_asset_reference_missing:{selector}:{key}:{value}")
        for ref_id in referenced_video_asset_ids:
            if ref_id not in known_asset_ids:
                issues.append(f"video_asset_reference_missing:{selector}:reference_asset_ids:{ref_id}")

    return sorted(set(issues))


def _group_issue_messages(issues: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for issue in issues:
        code = str(issue).split(":", 1)[0].strip()
        if not code:
            continue
        grouped.setdefault(code, []).append(issue)
    return grouped


def _manifest_checks(checks: list[dict[str, Any]], body_text: str, data: dict[str, Any], *, profile: str, flow: str, path_label: str) -> None:
    add_check(checks, f"{path_label}.structured", bool(data), f"{path_label} contains structured YAML output")
    if not data:
        return

    scenes = as_list(data.get("scenes"))
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    manifest_phase = str(data.get("manifest_phase") or "production").strip().lower()
    is_production = manifest_phase == "production"
    experience_value = str(nested_get(data, ["video_metadata", "experience"]) or "").strip().lower()
    strict_cut_contract = profile == "standard" and (flow == "immersive" or experience_value == "cinematic_story")
    add_check(checks, f"{path_label}.scenes", len(scenes) >= 1, f"{path_label} contains scenes", kind="rubric")
    add_check(checks, f"{path_label}.nodes", len(nodes) >= 1, f"{path_label} exposes renderable nodes", kind="rubric")

    if profile == "standard":
        add_check(checks, f"{path_label}.no_todo", not has_todo(body_text), f"{path_label} does not contain TODO/TBD markers", kind="rubric")

    duration_ok = True
    narration_field_ok = True
    narration_text_ok = True
    ids_ok = True
    prompt_motion_leak_issues: list[str] = []
    api_prompt_v1_issues: list[str] = []
    for node in nodes:
        video_generation = node.get("video_generation") if isinstance(node, dict) else None
        image_generation = node.get("image_generation") if isinstance(node, dict) else None
        audio = node.get("audio") if isinstance(node, dict) else None

        if isinstance(video_generation, dict):
            duration = video_generation.get("duration_seconds")
            if isinstance(duration, int) and duration > 15:
                duration_ok = False

        if isinstance(image_generation, dict):
            if "character_ids" not in image_generation or "object_ids" not in image_generation:
                ids_ok = False
            selector = str(node.get("selector") or node.get("cut_id") or node.get("scene_id") or "node")
            prompt = _image_api_prompt_text(image_generation)
            api_prompt_v1_issues.extend(_image_api_prompt_v1_issues(selector, image_generation))
            if any(token in prompt for token in MOTION_LEAK_TOKENS):
                prompt_motion_leak_issues.append(selector)

        narration = (audio or {}).get("narration") if isinstance(audio, dict) else None
        if not isinstance(narration, dict):
            narration_field_ok = False
            narration_text_ok = False
            continue
        if "text" not in narration:
            narration_field_ok = False
            narration_text_ok = False
            continue
        narration_tool = str(narration.get("tool") or "").strip().lower()
        silence_contract = narration.get("silence_contract") if isinstance(narration, dict) else None
        if narration_tool == "silent":
            if not (
                isinstance(silence_contract, dict)
                and bool(silence_contract.get("intentional"))
                and bool(silence_contract.get("confirmed_by_human"))
                and non_empty(silence_contract.get("kind"))
                and non_empty(silence_contract.get("reason"))
            ):
                narration_text_ok = False
        elif profile == "standard" and not non_empty(narration.get("text")):
            narration_text_ok = False

    add_check(checks, f"{path_label}.cut_duration", duration_ok, "cut duration is <= 15 seconds", kind="rubric")
    add_check(checks, f"{path_label}.narration_field", narration_field_ok, "each renderable node has audio.narration.text", kind="rubric")
    if profile == "standard":
        add_check(checks, f"{path_label}.narration_text", narration_text_ok, "spoken cuts have non-empty narration text and silent cuts declare silence_contract", kind="rubric")
    add_check(checks, f"{path_label}.asset_ids", ids_ok, "image_generation includes explicit character_ids/object_ids", kind="rubric")
    if profile == "standard":
        add_check(
            checks,
            f"{path_label}.prompt_leaks_motion_brief",
            not prompt_motion_leak_issues,
            "p600 image prompts do not leak p800 motion-only context"
            + (f" (issues: {', '.join(prompt_motion_leak_issues[:8])})" if prompt_motion_leak_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            f"{path_label}.api_prompt_v1_contract",
            not api_prompt_v1_issues,
            "image_api_prompt_v1 entries keep API prompts separate from debug/internal fields and include drawable shot/location/delta/blocking contracts"
            + (f" (issues: {', '.join(api_prompt_v1_issues[:8])})" if api_prompt_v1_issues else ""),
            kind="rubric",
        )

    if flow == "immersive":
        experience = nested_get(data, ["video_metadata", "experience"])
        prompt_mentions_text_rule = ("画面内テキスト" in body_text) or ("No on-screen text" in body_text)
        minimum_cut_issues = _minimum_cut_issues(data)
        add_check(checks, f"{path_label}.experience", non_empty(experience), "immersive manifest records video_metadata.experience", kind="rubric")
        add_check(checks, f"{path_label}.no_onscreen_text_rule", prompt_mentions_text_rule, "immersive manifest includes no on-screen text invariant", kind="rubric")
        add_check(
            checks,
            f"{path_label}.minimum_scene_cuts",
            not minimum_cut_issues,
            "immersive manifest gives every production scene enough cuts for cinematic density"
            + (f" (issues: {', '.join(minimum_cut_issues[:8])})" if minimum_cut_issues else ""),
            kind="rubric",
        )
        if profile == "standard":
            shot_mix_issues = _scene_shot_mix_plan_v1_issues(scenes)
            add_check(
                checks,
                f"{path_label}.scene_shot_mix_plan",
                not shot_mix_issues,
                "image_api_prompt_v1 scenes declare scene_shot_mix_plan and avoid repetitive adjacent shot role/scale"
                + (f" (issues: {', '.join(shot_mix_issues[:8])})" if shot_mix_issues else ""),
                kind="rubric",
            )
            coverage_issues: list[str] = []
            redundancy_issues: list[str] = []
            handoff_issues: list[str] = []
            composite_issues: list[str] = []
            triangulation_issues: list[str] = []
            for index, scene in enumerate(scenes, start=1):
                if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
                    continue
                scene_id = as_dotted_str(scene.get("scene_id")) or str(index)
                cuts = [
                    cut
                    for cut in as_list(scene.get("cuts"))
                    if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
                ]
                coverage_issues.extend(_scene_cut_coverage_plan_issues(scene, scene_id=scene_id, cuts=cuts))
                redundancy_issues.extend(_scene_cut_redundancy_issues(scene, scene_id=scene_id, cuts=cuts))
                handoff_issues.extend(_scene_cut_handoff_issues(scene, scene_id=scene_id, cuts=cuts))
                if is_production:
                    composite = as_dict(scene.get("scene_composite_review"))
                    if not composite or str(composite.get("status") or "").strip().lower() not in {"passed", "approved"}:
                        composite_issues.append(f"scene{scene_id}:scene_composite_review")
                    else:
                        for key in (
                            "scene_obligation_covered_by_cut_group",
                            "no_duplicate_story_fact_without_new_evidence",
                            "scene_meaning_visualized_across_cuts",
                        ):
                            if composite.get(key) is not True:
                                composite_issues.append(f"scene{scene_id}:scene_composite_review.{key}")
                    for cut in cuts:
                        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "cut")
                        triangulation_issues.extend(_triangulation_review_issues(cut, selector=selector))
            add_check(
                checks,
                f"{path_label}.scene_cut_coverage_plan",
                not coverage_issues,
                "scene_cut_coverage_plan assigns every scene obligation to real cuts"
                + (f" (issues: {', '.join(coverage_issues[:8])})" if coverage_issues else ""),
                kind="rubric",
            )
            add_check(
                checks,
                f"{path_label}.scene_cut_redundancy",
                not redundancy_issues,
                "anti_redundancy_key is present and unique within each scene"
                + (f" (issues: {', '.join(redundancy_issues[:8])})" if redundancy_issues else ""),
                kind="rubric",
            )
            add_check(
                checks,
                f"{path_label}.cut_handoff_chain",
                not handoff_issues,
                "adjacent cuts connect by explicit handoff anchors"
                + (f" (issues: {', '.join(handoff_issues[:8])})" if handoff_issues else ""),
                kind="rubric",
            )
            if is_production:
                add_check(
                    checks,
                    f"{path_label}.scene_composite_review",
                    not composite_issues,
                    "production scenes have passed scene_composite_review gates"
                    + (f" (issues: {', '.join(composite_issues[:8])})" if composite_issues else ""),
                    kind="rubric",
                )
                add_check(
                    checks,
                    f"{path_label}.triangulation_review",
                    not triangulation_issues,
                    "production cuts pass image/narration/video triangulation review"
                    + (f" (issues: {', '.join(triangulation_issues[:8])})" if triangulation_issues else ""),
                    kind="rubric",
                )


def check_manifest_single(run_dir: Path, profile: str, flow: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "video_manifest.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    add_check(checks, "manifest.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("manifest", path.name, checks), updates

    text, data = load_structured_document(path)
    body_text = flatten_without_keys(data, excluded={"cut_contract", "scene_contract", "review_contract", "evaluation_contract"}) or text
    _append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    raw_manifest_phase = data.get("manifest_phase")
    manifest_phase = str(raw_manifest_phase or "production").strip().lower()
    add_check(checks, "manifest.phase", manifest_phase == "production", f"video_manifest.md is production phase (got {manifest_phase or '(unset)'})", kind="rubric")
    _manifest_checks(checks, body_text, data, profile=profile, flow=flow, path_label="manifest")
    if flow == "immersive":
        add_check(
            checks,
            "p400.skeleton_manifest_phase",
            non_empty(raw_manifest_phase) and manifest_phase in {"skeleton", "production"},
            f"p400 manifest explicitly declares skeleton or promoted production phase (got {str(raw_manifest_phase or '').strip() or '(unset)'})",
            kind="rubric",
        )
        target_seconds, actual_seconds, cut_count = _manifest_duration_summary(data)
        add_check(
            checks,
            "p400.target_duration_range",
            300 <= target_seconds <= 600,
            f"p400 target duration is 5-10 minutes (got {target_seconds:.0f}s)",
            kind="rubric",
        )
        add_check(
            checks,
            "p400.duration_coverage",
            bool(target_seconds) and actual_seconds >= target_seconds * 0.9,
            f"p400 cut durations cover at least 90% of target ({actual_seconds:.0f}/{target_seconds:.0f}s across {cut_count} cuts)",
            kind="rubric",
        )
        script_selectors = _script_selectors_from_run(run_dir)
        manifest_selectors = _manifest_selectors(data)
        selector_mismatch = sorted((script_selectors - manifest_selectors) | (manifest_selectors - script_selectors))
        script_readiness_issues = _script_readiness_issues_from_run(run_dir)
        manifest_scene_event_issues = _scene_event_readiness_issues(as_list(data.get("scenes")), prefix="manifest")
        script_readiness_issues.extend(manifest_scene_event_issues)
        add_check(
            checks,
            "p400.script_readiness_contract",
            not script_readiness_issues,
            "p400 script scene readiness contract is satisfied before downstream stages"
            + (f" (issues: {', '.join(script_readiness_issues[:8])})" if script_readiness_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            "p400.script_manifest_selector_match",
            bool(script_selectors) and not selector_mismatch,
            "p450 manifest selectors correspond exactly to script.md scene/cut selectors"
            + (f" (mismatch: {', '.join(selector_mismatch[:8])})" if selector_mismatch else ""),
            kind="rubric",
        )
        review_issues = _review_report_issues(run_dir)
        add_check(
            checks,
            "p400.review_report_integrity",
            not review_issues,
            "p400 review reports have required passed status, p435 council sections, and no duration deferral"
            + (f" (issues: {', '.join(review_issues[:8])})" if review_issues else ""),
            kind="rubric",
        )
        loop_issues = _review_loop_integrity_issues(run_dir)
        add_check(
            checks,
            "p400.review_loop_integrity",
            not loop_issues,
            "p400 review loops include five critic reports, aggregate report, and required patch brief sections"
            + (f" (issues: {', '.join(loop_issues[:8])})" if loop_issues else ""),
            kind="rubric",
        )
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    experience_value = str(nested_get(data, ["video_metadata", "experience"]) or "").strip().lower()
    strict_cut_contract = profile == "standard" and (flow == "immersive" or experience_value == "cinematic_story")
    reveal_constraints = _load_script_reveal_constraints(run_dir)
    human_change_issues = _human_change_request_issues(data, run_dir=run_dir)
    contract_missing = False
    contract_structure_issues: list[str] = []
    must_show_failed = False
    must_avoid_failed = False
    reveal_failed = False
    for selector, node in nodes_with_selectors:
        image_generation_for_prompt = (node.get("image_generation") or {}) if isinstance(node.get("image_generation"), dict) else {}
        combined = "\n".join(
            [
                _image_api_prompt_text(image_generation_for_prompt),
                str(((node.get("video_generation") or {}) if isinstance(node.get("video_generation"), dict) else {}).get("motion_prompt") or ""),
                str(((((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration") or {}) if isinstance(((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration"), dict) else {}).get("text") or ""),
            ]
        )
        contract = _node_cut_contract(node, allow_legacy=not strict_cut_contract)
        if not contract:
            contract_missing = True
            continue
        if isinstance(node.get("cut_contract"), dict):
            for issue in _cut_contract_structure_issues(contract):
                contract_structure_issues.append(f"{selector}:{issue}")
        elif strict_cut_contract:
            contract_missing = True
        must_show = _contract_list_paths(contract, "must_show", "viewer_contract.must_show")
        if _image_api_prompt_policy(image_generation_for_prompt) == IMAGE_API_PROMPT_POLICY_VERSION:
            must_show = [term for term in must_show if not IMAGE_API_PROMPT_ABSTRACT_TERM_RE.search(str(term))]
        must_avoid = _contract_list_paths(contract, "must_avoid", "viewer_contract.must_avoid", "motion_contract.must_not_add")
        if must_show and not all(term in combined for term in must_show):
            must_show_failed = True
        if must_avoid and any(term in combined for term in must_avoid):
            must_avoid_failed = True
        if reveal_constraints:
            image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
            declared_character_ids = set(as_list(image_generation.get("character_ids"))) if isinstance(image_generation, dict) else set()
            prompt = _image_api_prompt_text(image_generation) if isinstance(image_generation, dict) else ""
            for constraint in reveal_constraints:
                if constraint["rule"] != "must_not_appear_before":
                    continue
                if _selector_sort_key(selector) >= _selector_sort_key(constraint["selector"]):
                    continue
                if constraint["subject_type"] == "character":
                    subject_id = constraint["subject_id"]
                    if subject_id in declared_character_ids or subject_id in prompt:
                        reveal_failed = True
    if contract_missing:
        add_check(checks, "manifest.contract_missing", False, "one or more scene/cut nodes are missing cut_contract or legacy scene_contract.", kind="rubric")
    if contract_structure_issues:
        add_check(
            checks,
            "manifest.cut_contract_structure",
            False,
            "one or more cut_contract nodes are missing required viewer/first-frame/motion/narration fields"
            + (f" (issues: {', '.join(contract_structure_issues[:8])})" if contract_structure_issues else ""),
            kind="rubric",
        )
    if must_show_failed:
        add_check(checks, "manifest.contract_must_show_unmet", False, "scene/cut contract must_show items are not fully represented.", kind="rubric")
    if must_avoid_failed:
        add_check(checks, "manifest.contract_must_avoid_violated", False, "scene/cut contract must_avoid items are still present.", kind="rubric")
    if reveal_failed:
        add_check(checks, "manifest.reveal_constraints_violated", False, "one or more scene/cut nodes violate script reveal_constraints.", kind="rubric")
    if human_change_issues:
        for reason_key, grouped_issues in sorted(_group_issue_messages(human_change_issues).items()):
            add_check(
                checks,
                f"manifest.{reason_key}",
                False,
                f"{reason_key} remains unresolved: " + ", ".join(sorted(grouped_issues)[:8]),
                kind="rubric",
            )
    rubric_scores = _manifest_rubric(nodes, body_text)
    _append_rubric_findings(checks=checks, stage="manifest", rubric_scores=rubric_scores)
    updates["eval.manifest.score"] = f"{score_from_checks(checks):.4f}"
    if flow == "immersive":
        p400_gate_checks = [check for check in checks if check["id"] in P400_READINESS_CHECK_IDS or check["id"].startswith("p400.")]
        p400_ready = bool(p400_gate_checks) and all(check["passed"] for check in p400_gate_checks)
        updates["eval.p400_readiness.status"] = "approved" if p400_ready else "changes_requested"
        updates["eval.p400_readiness.reason_keys"] = ",".join(check["id"] for check in p400_gate_checks if not check["passed"])
    return make_stage("manifest", path.name, checks, rubric_scores=rubric_scores), updates


def check_manifest_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    manifest_paths = [scene_dir / "video_manifest.md" for scene_dir in scene_dirs]

    add_check(checks, "manifest.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "manifest.scene_files", all(path.exists() for path in manifest_paths), "each scene has video_manifest.md")
    _append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    if not scene_dirs or not all(path.exists() for path in manifest_paths):
        return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}), {
            "eval.manifest.score": f"{score_from_checks(checks):.4f}"
        }

    nested_ok = True
    phase_ok = True
    for path in manifest_paths:
        text, data = load_structured_document(path)
        local_checks: list[dict[str, Any]] = []
        body_text = flatten_without_keys(data, excluded={"cut_contract", "scene_contract", "review_contract", "evaluation_contract"}) or text
        if str(data.get("manifest_phase") or "production").strip().lower() != "production":
            phase_ok = False
        _manifest_checks(local_checks, body_text, data, profile=profile, flow="scene-series", path_label=path.name)
        if not all(check["passed"] for check in local_checks):
            nested_ok = False
    add_check(checks, "manifest.scene_phase", phase_ok, "scene manifests are in production phase", kind="rubric")
    add_check(checks, "manifest.scene_contracts", nested_ok, "scene manifests satisfy render contract checks", kind="rubric")
    rubric_scores = {
        "beat_clarity": 1.0 if nested_ok else 0.4,
        "visual_specificity": 1.0 if nested_ok else 0.4,
        "continuity_readiness": 1.0 if nested_ok else 0.4,
        "narration_alignment": 1.0 if nested_ok else 0.4,
        "production_readiness": 1.0 if nested_ok else 0.4,
    }
    _append_rubric_findings(checks=checks, stage="manifest", rubric_scores=rubric_scores)
    updates = {"eval.manifest.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}, rubric_scores=rubric_scores), updates


def _probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None or not path.exists():
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _video_checks(checks: list[dict[str, Any]], *, video_path: Path, state: dict[str, str], run_dir: Path) -> None:
    video_exists = video_path.exists()
    add_check(checks, "video.file_exists", video_exists, f"{video_path.name} exists")
    if not video_exists:
        return

    render_status = state.get("runtime.render.status", "").strip().lower()
    add_check(checks, "video.render_status", render_status in {"success", "started", ""}, f"render status is set to success/started (got {render_status or '(unset)'})", kind="rubric")

    review_status = state.get("review.video.status", "").strip().lower()
    add_check(checks, "video.review_status", review_status in {"pending", "approved", "changes_requested"}, f"review.video.status is present (got {review_status or '(unset)'})", kind="rubric")

    report_exists = (run_dir / "run_report.md").exists()
    if report_exists:
        add_check(checks, "video.run_report", True, "run_report.md exists", kind="rubric")

    narration_list = run_dir / "video_narration_list.txt"
    if narration_list.exists():
        audio_paths = [Path(line.strip()) for line in narration_list.read_text(encoding="utf-8").splitlines() if line.strip()]
        resolved = [(path if path.is_absolute() else run_dir / path) for path in audio_paths]
        add_check(checks, "video.narration_list", all(path.exists() for path in resolved), "all narration files in video_narration_list.txt exist", kind="rubric")

    video_duration = _probe_duration(video_path)
    if video_duration is not None:
        add_check(checks, "video.duration", video_duration > 0.0, f"video duration is positive ({video_duration:.2f}s)", kind="rubric")


def check_video_single(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    _video_checks(checks, video_path=run_dir / "video.mp4", state=state, run_dir=run_dir)
    manifest_path = run_dir / "video_manifest.md"
    contract = {}
    if manifest_path.exists():
        _, manifest = load_structured_document(manifest_path)
        quality_check = manifest.get("quality_check") if isinstance(manifest.get("quality_check"), dict) else {}
        contract = quality_check.get("review_contract") if isinstance(quality_check.get("review_contract"), dict) else {}
    if not contract:
        add_check(checks, "video.contract_missing", False, "quality_check.review_contract is missing for the video stage.", kind="rubric")
    else:
        must_have = contract_list(contract, "must_have_artifacts")
        if must_have and not all((run_dir / item).exists() for item in must_have):
            add_check(checks, "video.contract_must_have_unmet", False, "video review contract requires artifacts that are still missing.", kind="rubric")
    rubric_scores = _video_rubric(run_dir, state, checks)
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "video.mp4", checks, rubric_scores=rubric_scores), updates


def check_video_scene_series(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    checks: list[dict[str, Any]] = []
    add_check(checks, "video.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    video_paths = [scene_dir / "video.mp4" for scene_dir in scene_dirs]
    add_check(checks, "video.scene_files", all(path.exists() for path in video_paths), "each scene has video.mp4")
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    rubric_scores = {
        "render_integrity": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "asset_completeness": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "review_readiness": 0.8,
        "audio_packaging": 0.8,
        "publish_readiness": score_from_ratio(sum(1 for check in checks if check["passed"]), len(checks)),
    }
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "scenes/*/video.mp4", checks, details={"scene_count": len(scene_dirs)}, rubric_scores=rubric_scores), updates


def evaluate_stage(run_dir: Path, *, stage: str, profile: str, flow: str | None = None) -> tuple[dict[str, Any], dict[str, str], str]:
    resolved_flow = flow or detect_flow(run_dir)
    if stage == "research":
        result, updates = check_research(run_dir, profile)
    elif stage == "story":
        result, updates = check_story(run_dir, profile)
    elif stage == "visual_value":
        result, updates = check_visual_value(run_dir, profile)
    elif stage == "script":
        if resolved_flow == "scene-series":
            result, updates = check_script_scene_series(run_dir, profile)
        else:
            result, updates = check_script_single(run_dir, profile)
    elif stage == "manifest":
        if resolved_flow == "scene-series":
            result, updates = check_manifest_scene_series(run_dir, profile)
        else:
            result, updates = check_manifest_single(run_dir, profile, resolved_flow)
    elif stage == "video":
        if resolved_flow == "scene-series":
            result, updates = check_video_scene_series(run_dir)
        else:
            result, updates = check_video_single(run_dir)
    else:
        raise ValueError(f"Unsupported stage: {stage}")
    return result, updates, resolved_flow


def render_stage_review(*, run_dir: Path, stage_result: dict[str, Any], stage: str, flow: str, profile: str) -> str:
    failed = [check for check in stage_result["checks"] if not check["passed"]]
    lines = [
        f"# {stage.title()} Evaluator Review",
        "",
        f"- run_dir: `{run_dir}`",
        f"- flow: `{flow}`",
        f"- profile: `{profile}`",
        f"- stage: `{stage}`",
        f"- status: `{'approved' if stage_result['passed'] else 'changes_requested'}`",
        f"- score: `{stage_result['score']:.4f}`",
        f"- overall_rubric: `{stage_result.get('overall_rubric', 0.0):.4f}`",
        f"- findings: `{len(failed)}`",
        "",
    ]
    if stage_result.get("rubric_scores"):
        lines.append("## Rubric")
        lines.append("")
        for key, value in stage_result["rubric_scores"].items():
            lines.append(f"- {key}: `{value:.4f}`")
        lines.append("")
    if stage_result.get("details"):
        lines.append("## Details")
        lines.append("")
        for key, value in stage_result["details"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    lines.append("## Checks")
    lines.append("")
    for check in stage_result["checks"]:
        lines.append(f"- [{'PASS' if check['passed'] else 'FAIL'}] `{check['id']}`: {check['message']}")
    return "\n".join(lines) + "\n"


def append_stage_review_state(*, run_dir: Path, stage: str, stage_result: dict[str, Any], updates: dict[str, str], report_path: Path) -> None:
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        return
    finding_count = sum(1 for check in stage_result["checks"] if not check["passed"])
    artifact_key_map = {
        "research": "artifact.research_review",
        "story": "artifact.story_review",
        "script": "artifact.script_review",
        "manifest": "artifact.manifest_review",
        "video": "artifact.video_review_report",
    }
    state_updates = dict(updates)
    state_updates[f"eval.{stage}.status"] = "approved" if stage_result["passed"] else "changes_requested"
    if stage == "story":
        state_updates["review.story.status"] = "approved" if stage_result["passed"] else "changes_requested"
    state_updates[f"eval.{stage}.findings"] = str(finding_count)
    state_updates[f"eval.{stage}.reason_keys"] = ",".join(stage_result.get("reason_keys") or [])
    state_updates[f"eval.{stage}.overall_rubric"] = f"{float(stage_result.get('overall_rubric', 0.0)):.4f}"
    for key, value in dict(stage_result.get("rubric_scores") or {}).items():
        state_updates[f"eval.{stage}.rubric.{key}"] = f"{float(value):.4f}"
    state_updates[artifact_key_map[stage]] = str(report_path.resolve())
    append_state_snapshot(state_path, state_updates)
