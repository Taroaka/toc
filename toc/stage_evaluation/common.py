"""Shared structural validation helpers for production artifacts.

This module intentionally contains no rubric, score, reviewer, or approval
logic. A stage result records ordinary structural checks and whether those
checks passed; content quality is authored in the production artifact itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.image_prompt_projection_registry import registered_drawable_group_order
from toc.immersive_manifest import normalize_dotted_id


EVENT_TIME_POSITION_VALUES = {
    "before_trigger",
    "trigger_moment",
    "early_action",
    "mid_action",
    "consequence",
    "reaction_after",
    "handoff_after",
}

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
IMAGE_API_PROMPT_V2_BASE_GROUPS = {"style", "setting", "lighting", "composition"}

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
    r"\b(?:cut_count|fixed_cut_count)\s*[:=]\s*\d+\b|"
    r"(?:cut数|カット数)\s*(?:は|:|=)?\s*\d+|"
    r"\d+\s*(?:cuts|カット)\s*(?:で|に)?\s*(?:固定|する|作る)",
    re.I,
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

SCENE_STATE_PROGRESSION_MODES = {
    "suspended_moment",
    "sequential_state_progression",
}

VISIBLE_BEHAVIOR_FIELDS = ("face", "gaze", "posture", "hands", "feet", "distance")


def non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value is not None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_dotted_str(value: Any) -> str | None:
    return normalize_dotted_id(value)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def nested_get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(flatten_text(item) for item in value)
    return ""


def flatten_without_keys(value: Any, *, excluded: set[str]) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(
            flatten_without_keys(item, excluded=excluded)
            for key, item in value.items()
            if str(key) not in excluded
        )
    if isinstance(value, list):
        return "\n".join(flatten_without_keys(item, excluded=excluded) for item in value)
    return ""


def contract_list(contract: dict[str, Any], key: str) -> list[str]:
    value = contract.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _contract_value(contract: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value: Any = contract
        for key in path.split("."):
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
        else:
            if non_empty(value):
                return value
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


def _cut_source_event_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict) or _contract_string(contract, "schema_version") != "3.0":
        return {}
    return as_dict(contract.get("source_event_contract"))


def _cut_primary_event_beat_id(contract: dict[str, Any]) -> str:
    return _contract_string(_cut_source_event_contract(contract), "primary_event_beat_id")


def _cut_source_event_beat_ids(contract: dict[str, Any]) -> list[str]:
    return _contract_list_paths(_cut_source_event_contract(contract), "source_event_beat_ids")


def _cut_contract_complete(contract: dict[str, Any]) -> bool:
    return not _cut_contract_structure_issues(contract)


def _cut_contract_structure_issues(contract: dict[str, Any]) -> list[str]:
    """Validate cut contract shape and references without judging its quality."""

    if not isinstance(contract, dict) or not contract:
        return ["cut_contract:missing"]
    issues: list[str] = []
    if _contract_string(contract, "schema_version") != "3.0":
        issues.append("schema_version:3.0")
    source = _cut_source_event_contract(contract)
    if not source:
        issues.append("source_event_contract")
    else:
        for key in ("primary_event_beat_id", "event_beat_function", "event_time_position"):
            if not non_empty(source.get(key)):
                issues.append(f"source_event_contract.{key}")
        if _contract_string(source, "event_time_position") not in EVENT_TIME_POSITION_VALUES:
            issues.append("source_event_contract.event_time_position.enum")
        if not isinstance(source.get("source_event_beat_ids"), list):
            issues.append("source_event_contract.source_event_beat_ids")

    required_objects = (
        "first_frame_contract",
        "motion_contract",
        "narration_contract",
        "asset_dependency",
        "downstream_handoff",
        "intent_budget",
        "rhythm_contract",
    )
    for key in required_objects:
        if not isinstance(contract.get(key), dict):
            issues.append(key)

    first_frame = as_dict(contract.get("first_frame_contract"))
    if first_frame:
        for key in ("source_event_beat_id", "event_time_position", "first_frame_brief"):
            if not non_empty(first_frame.get(key)):
                issues.append(f"first_frame_contract.{key}")
        if first_frame.get("imageable") is not True:
            issues.append("first_frame_contract.imageable")

    motion = as_dict(contract.get("motion_contract"))
    if motion:
        for key in ("source_event_beat_id", "end_state"):
            if not non_empty(motion.get(key)):
                issues.append(f"motion_contract.{key}")
        if not isinstance(motion.get("must_not_advance_to_event_beat_ids"), list):
            issues.append("motion_contract.must_not_advance_to_event_beat_ids")

    narration = as_dict(contract.get("narration_contract"))
    if narration:
        for key in ("role", "target_function", "source_event_beat_ids"):
            if not non_empty(narration.get(key)):
                issues.append(f"narration_contract.{key}")
        if not isinstance(narration.get("source_event_beat_ids"), list):
            issues.append("narration_contract.source_event_beat_ids")

    dependency = as_dict(contract.get("asset_dependency"))
    if dependency:
        for key in ("character_ids_required", "location_ids_required"):
            if not isinstance(dependency.get(key), list):
                issues.append(f"asset_dependency.{key}")

    return issues


def add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    message: str,
    *,
    kind: str = "structural",
) -> None:
    # ``kind`` remains a small compatibility field for callers that classify
    # diagnostics. It has no scoring semantics and stage results never emit a
    # score or rubric.
    checks.append({"id": check_id, "passed": bool(passed), "kind": kind, "message": message})


def make_stage(
    stage: str,
    artifact: str,
    checks: list[dict[str, Any]],
    *,
    details: dict[str, Any] | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """Build a structural stage result.

    ``**_ignored`` keeps old internal callers import-compatible while making
    rubric arguments inert and preventing them from reappearing in output.
    """

    return {
        "stage": stage,
        "artifact": artifact,
        "passed": all(bool(check.get("passed")) for check in checks),
        "reason_keys": [
            str(check.get("id"))
            for check in checks
            if check.get("passed") is False
        ],
        "checks": checks,
        "details": details or {},
    }


def detect_flow(run_dir: Path) -> str:
    if (run_dir / "scenes").is_dir():
        return "scene-series"
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _text, data = load_structured_document(manifest_path)
        if nested_get(data, ["video_metadata", "experience"]):
            return "immersive"
    return "toc-run"


def has_todo(text: str) -> bool:
    # Retained for compatibility with callers that need a basic authoring
    # diagnostic; stage validators do not treat this heuristic as a review.
    upper = text.upper()
    return "TODO" in upper or "TBD" in upper


def scene_time_of_day_contract_marker(data: dict[str, Any], *, artifact: str) -> tuple[bool, bool]:
    metadata_key = {"story": "story_metadata", "script": "script_metadata", "manifest": "video_metadata"}.get(artifact)
    if metadata_key is None:
        raise ValueError(f"Unsupported scene time artifact: {artifact}")
    metadata = data.get(metadata_key)
    if not isinstance(metadata, dict) or "scene_time_of_day_contract" not in metadata:
        return False, True
    return True, metadata.get("scene_time_of_day_contract") == "required_v1"


def _scenes_for_artifact(data: dict[str, Any], artifact: str) -> list[Any]:
    if artifact == "story":
        return as_list(nested_get(data, ["script", "scenes"], []))
    return as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))


def scene_time_of_day_contract_missing(data: dict[str, Any], *, artifact: str) -> list[str] | None:
    declared, valid = scene_time_of_day_contract_marker(data, artifact=artifact)
    if not declared:
        return None
    missing: list[str] = []
    if not valid:
        missing.append("contract:required_v1")
    for index, scene in enumerate(_scenes_for_artifact(data, artifact), start=1):
        scene_id = str(scene.get("scene_id") or index) if isinstance(scene, dict) else str(index)
        if not isinstance(scene, dict) or not isinstance(scene.get("time_of_day"), str) or not scene.get("time_of_day", "").strip():
            missing.append(scene_id)
    return missing


def scene_time_of_day_visual_basis_contract_marker(data: dict[str, Any], *, artifact: str) -> tuple[bool, bool]:
    metadata_key = {"story": "story_metadata", "script": "script_metadata", "manifest": "video_metadata"}.get(artifact)
    if metadata_key is None:
        raise ValueError(f"Unsupported scene time artifact: {artifact}")
    metadata = data.get(metadata_key)
    if not isinstance(metadata, dict):
        return False, True
    declared = "scene_time_of_day_contract" in metadata or "scene_time_of_day_visual_basis_contract" in metadata
    if not declared:
        return False, True
    return True, metadata.get("scene_time_of_day_visual_basis_contract") == "required_v1"


def scene_time_of_day_visual_basis_issues(data: dict[str, Any], *, artifact: str) -> list[str] | None:
    declared, valid = scene_time_of_day_visual_basis_contract_marker(data, artifact=artifact)
    if not declared:
        return None
    issues = [] if valid else ["contract:required_v1"]
    required_dimensions = ("光源", "明るさ", "影", "色温度")
    for index, scene in enumerate(_scenes_for_artifact(data, artifact), start=1):
        scene_id = str(scene.get("scene_id") or index) if isinstance(scene, dict) else str(index)
        basis = scene.get("time_of_day_visual_basis") if isinstance(scene, dict) else None
        if not isinstance(basis, str) or not basis.strip():
            issues.append(f"{scene_id}:missing")
            continue
        missing = [dimension for dimension in required_dimensions if dimension not in basis]
        if missing:
            issues.append(f"{scene_id}:missing-{'+'.join(missing)}")
    return issues


def _scene_cut_selector(scene_id: str, cut: dict[str, Any]) -> str:
    scene = normalize_dotted_id(scene_id) or str(scene_id)
    cut_id = normalize_dotted_id(cut.get("cut_id"))
    if cut_id:
        return f"scene{scene}_cut{cut_id}"
    return f"scene{scene}"
