"""Shared stage-evaluation constants and primitives."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from toc.grounding import grounding_validation
from toc.harness import load_structured_document
from toc.image_prompt_projection_registry import (
    drawable_projection_rules,
    registered_drawable_group_order,
)
from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id

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


STORY_GROUNDING_SOURCE_ORIGINS: tuple[str, ...] = (
    "user_input",
    "script",
    "canonical_reference",
    "asset_bible",
    "inferred",
    "adaptation_choice",
    "invented_candidate",
)


CONCRETE_STORY_ELEMENT_FUNCTIONS: tuple[str, ...] = (
    "obstacle",
    "proof",
    "temptation",
    "deadline",
    "status_marker",
    "secret_holder",
    "memory_trigger",
    "threshold",
    "handoff",
    "contrast",
    "pressure",
    "reward",
    "loss",
)


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


SCENE_GENERATION_REQUIRED_BLOCKS: tuple[str, ...] = (
    "scene_authoring_context",
    "scene_prompt_payload",
    "scene_debug_prompt_source",
    "scene_generation_contract",
)


SCENE_GENERATION_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "scene_intent",
    "scene_event",
    "scene_character_state_timeline",
    "scene_film_coverage_plan",
    "scene_cut_coverage_plan",
    "forbidden_event_changes",
)


SCENE_PROMPT_PAYLOAD_FORBIDDEN_DOWNSTREAM_FIELDS: tuple[str, ...] = (
    "first_frame_brief",
    "motion_brief",
    "api_prompt_payload",
)


SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE = re.compile(
    r"\b(?:camera|lens|framing|shot)\b|カメラ|レンズ|画角|フレーミング|ショット",
    re.I,
)


SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE = re.compile(
    r"\b(?:cut_count|fixed_cut_count)\s*[:=]\s*\d+\b|(?:cut数|カット数)\s*(?:は|:|=)?\s*\d+|"
    r"\d+\s*(?:cuts|カット)\s*(?:で|に)?\s*(?:固定|する|作る)",
    re.I,
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


def scene_time_of_day_contract_missing(data: dict[str, Any], *, artifact: str) -> list[str] | None:
    """Return scene ids missing ``time_of_day`` when the new time contract is declared.

    The explicit metadata contract marker is the compatibility gate. Historical
    ``time`` and optional legacy scene fields remain independent and may exist in
    older artifacts without activating the new required-field contract.
    """
    metadata_key_by_artifact = {
        "story": "story_metadata",
        "script": "script_metadata",
        "manifest": "video_metadata",
    }
    metadata_key = metadata_key_by_artifact.get(artifact)
    if metadata_key is None:
        raise ValueError(f"Unsupported scene time artifact: {artifact}")
    metadata = data.get(metadata_key)
    scenes = (
        as_list(nested_get(data, ["script", "scenes"], []))
        if artifact == "story"
        else as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    )
    contract_declared = isinstance(metadata, dict) and "scene_time_of_day_contract" in metadata
    if not contract_declared:
        return None

    return [
        str(scene.get("scene_id") or index) if isinstance(scene, dict) else str(index)
        for index, scene in enumerate(scenes, start=1)
        if not isinstance(scene, dict)
        or not isinstance(scene.get("time_of_day"), str)
        or not str(scene.get("time_of_day")).strip()
    ]


def scene_time_of_day_contract_marker(data: dict[str, Any], *, artifact: str) -> tuple[bool, bool]:
    """Return ``(declared, valid)`` for the explicit scene-daypart contract marker."""

    metadata_key_by_artifact = {
        "story": "story_metadata",
        "script": "script_metadata",
        "manifest": "video_metadata",
    }
    metadata_key = metadata_key_by_artifact.get(artifact)
    if metadata_key is None:
        raise ValueError(f"Unsupported scene time artifact: {artifact}")
    metadata = data.get(metadata_key)
    if not isinstance(metadata, dict) or "scene_time_of_day_contract" not in metadata:
        return False, True
    return True, metadata.get("scene_time_of_day_contract") == "required_v1"


def scene_time_of_day_visual_basis_contract_marker(
    data: dict[str, Any], *, artifact: str
) -> tuple[bool, bool]:
    """Require the visual-basis marker whenever the scene daypart contract is active."""

    metadata_key_by_artifact = {
        "story": "story_metadata",
        "script": "script_metadata",
        "manifest": "video_metadata",
    }
    metadata_key = metadata_key_by_artifact.get(artifact)
    if metadata_key is None:
        raise ValueError(f"Unsupported scene time artifact: {artifact}")
    metadata = data.get(metadata_key)
    if not isinstance(metadata, dict):
        return False, True
    declared = (
        "scene_time_of_day_contract" in metadata
        or "scene_time_of_day_visual_basis_contract" in metadata
    )
    if not declared:
        return False, True
    return (
        True,
        metadata.get("scene_time_of_day_visual_basis_contract") == "required_v1",
    )


def scene_time_of_day_visual_basis_issues(
    data: dict[str, Any], *, artifact: str
) -> list[str] | None:
    """Return scene-local omissions from the required lighting evidence contract."""

    declared, _valid = scene_time_of_day_visual_basis_contract_marker(
        data, artifact=artifact
    )
    if not declared:
        return None
    scenes = (
        as_list(nested_get(data, ["script", "scenes"], []))
        if artifact == "story"
        else as_list(data.get("scenes"))
        or as_list(nested_get(data, ["script", "scenes"], []))
    )
    issues: list[str] = []
    required_dimensions = ("光源", "明るさ", "影", "色温度")
    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id") or index) if isinstance(scene, dict) else str(index)
        value = scene.get("time_of_day_visual_basis") if isinstance(scene, dict) else None
        if not isinstance(value, str) or not value.strip():
            issues.append(f"{scene_id}:missing")
            continue
        missing_dimensions = [
            dimension for dimension in required_dimensions if dimension not in value
        ]
        if missing_dimensions:
            issues.append(f"{scene_id}:missing-{'+'.join(missing_dimensions)}")
    return issues


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
    scored_checks = [check for check in checks if check.get("kind") != "warning"]
    if not scored_checks:
        return 0.0
    passed = sum(1 for check in scored_checks if check["passed"])
    return round(passed / len(scored_checks), 4)


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
        "passed": all(check["passed"] for check in checks if check.get("kind") != "warning"),
        "score": score,
        "overall_rubric": overall_rubric,
        "rubric_scores": rubric_scores,
        "reason_keys": [check["id"] for check in checks if not check["passed"]],
        "warning_keys": [check["id"] for check in checks if check.get("kind") == "warning"],
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


STORY_REQUIRED_SCENE_FIELDS = [
    "purpose",
    "conflict",
    "turn",
    "affect",
    "visualizable_action",
    "grounding_note",
]


IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v1"


IMAGE_API_PROMPT_POLICY_VERSION_V2 = "image_api_prompt_v2"


IMAGE_API_PROMPT_V2_GROUPS = set(registered_drawable_group_order())


IMAGE_API_PROMPT_V2_BASE_GROUPS = {
    rule.group for rule in drawable_projection_rules() if rule.relevance == "required" and rule.group
}


IMAGE_API_PROMPT_FORBIDDEN_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "api_prompt_contains_no_scene_cut_ids",
        re.compile(
            r"\bscene\d+(?:\.\d+)?(?:[_-](?:cut|event)[A-Za-z0-9_.-]*)?\b|\b_event_[A-Za-z0-9_]+\b",
            re.I,
        ),
    ),
    (
        "api_prompt_contains_no_yaml_field_names",
        re.compile(
            r"first_frame_visual_plan|cut_contract|scene_event|source_event_contract|event_context_for_cut|validation_gates|"
            r"source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief|debug_prompt_source|api_prompt_payload|"
            r"scene_character_state_timeline|scene_film_coverage_plan|cut_character_emotion_transition|cut_film_grammar_contract|"
            r"scene_state_progression_plan|cut_state_progression|emotion_label|emotion_from|emotion_to|transition_mode|"
            r"drawable_prompt_ir|dependencies|included_fragments|omitted_groups|required_groups|compiler_version|"
            r"shot_design_contract|cut_location_frame_plan|cut_visual_delta|blocking_and_interaction",
            re.I,
        ),
    ),
    ("api_prompt_contains_no_boolean_gate_values", re.compile(r"\b(?:true|false|null|none)\b", re.I)),
    ("api_prompt_contains_no_legacy_additional_description", re.compile(r"追加の具体描写|追加具体描写")),
    ("api_prompt_contains_no_abstract_story_terms", re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")),
    ("api_prompt_contains_no_unresolved_generic_placeholders", re.compile(r"\b(?:TODO|TBD|placeholder|approved_story_evidence|primary_visible_object|primary_visible_zone)\b", re.I)),
)


IMAGE_API_PROMPT_ABSTRACT_TERM_RE = re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")


SCENE_STATE_PROGRESSION_MODES = {"suspended_moment", "sequential_state_progression"}


VISIBLE_BEHAVIOR_FIELDS = ("face", "gaze", "posture", "hands", "feet", "distance")


def _scene_cut_selector(scene_id: str, cut: dict[str, Any]) -> str:
    selector = str(cut.get("selector") or "").strip()
    if selector:
        return selector
    cut_id = as_dotted_str(cut.get("cut_id"))
    if cut_id is None:
        return ""
    return make_scene_cut_selector(scene_id, cut_id)


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


