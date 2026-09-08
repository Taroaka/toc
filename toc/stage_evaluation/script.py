"""Structural script/scene helpers.

Scene authoring remains responsible for meaning and dramatic quality. This
module only checks that authored YAML has usable scene/cut types, IDs, and
declared provider contracts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    EVENT_TIME_POSITION_VALUES,
    FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS,
    SCENE_COVERAGE_REVIEW_REQUIRED_KEYS,
    SCENE_GENERATION_REQUIRED_BLOCKS,
    SCENE_GENERATION_REQUIRED_OUTPUTS,
    SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE,
    SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE,
    STORY_REQUIRED_SCENE_FIELDS,
    _contract_string,
    _cut_contract_structure_issues,
    _node_cut_contract,
    _scene_cut_selector,
    add_check,
    as_dict,
    as_dotted_str,
    as_int,
    as_list,
    flatten_text,
    make_stage,
    nested_get,
    non_empty,
)
from .pipeline import (
    _append_script_structure_checks,
    check_script_scene_series,
    check_script_single,
)


def _scene_id_for_issue(scene: dict[str, Any], fallback: str = "?") -> str:
    return as_dotted_str(scene.get("scene_id")) or str(scene.get("scene_id") or fallback)


def _scene_event(scene: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scene.get("scene_event"))


def _scene_event_sequence(scene: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in as_list(_scene_event(scene).get("event_sequence")) if isinstance(item, dict)]


def _scene_event_beat_id(beat: dict[str, Any]) -> str:
    return as_dotted_str(beat.get("beat_id")) or ""


def _scene_event_beat_function(beat: dict[str, Any]) -> str:
    return str(beat.get("function") or beat.get("beat_function") or "").strip()


def _scene_event_beat_ids(scene: dict[str, Any]) -> list[str]:
    return [value for value in (_scene_event_beat_id(item) for item in _scene_event_sequence(scene)) if value]


def _scene_event_source_story_beat_refs(scene_event: dict[str, Any]) -> list[str]:
    return [str(item).strip() for item in as_list(scene_event.get("source_story_beat_refs")) if str(item).strip()]


def _scene_event_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    """Return structural scene-event issues grouped for compatibility callers."""

    selector = f"scene{_scene_id_for_issue(scene)}"
    event = scene.get("scene_event")
    if event is None:
        return {}
    issues: dict[str, list[str]] = {}
    if not isinstance(event, dict):
        issues["exists"] = [f"{selector}:scene_event.type"]
        return issues
    sequence = event.get("event_sequence")
    if sequence is not None and not isinstance(sequence, list):
        issues["sequence_complete"] = [f"{selector}:event_sequence.type"]
    if isinstance(sequence, list):
        ids = [_scene_event_beat_id(item) for item in sequence if isinstance(item, dict)]
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            issues["beat_ids_unique"] = [f"{selector}:event_sequence.beat_ids"]
    for key in FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS:
        if key in event:
            issues.setdefault("no_forbidden_directing_fields", []).append(f"{selector}:{key}")
    return issues


def _scene_generation_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    generation = scene.get("scene_generation")
    if generation is None:
        return {}
    selector = f"scene{_scene_id_for_issue(scene)}"
    if not isinstance(generation, dict):
        return {"payload_exists": [f"{selector}:scene_generation.type"]}
    issues: dict[str, list[str]] = {}
    payload = generation.get("scene_prompt_payload")
    if payload is not None and not isinstance(payload, dict):
        issues.setdefault("payload_exists", []).append(f"{selector}:scene_prompt_payload.type")
    if isinstance(payload, dict):
        for key in ("first_frame_brief", "motion_brief", "api_prompt_payload"):
            if key in payload:
                issues.setdefault("payload_no_downstream_fields", []).append(f"{selector}:{key}")
        payload_text = flatten_text(payload)
        if SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE.search(payload_text):
            issues.setdefault("payload_no_image_directing_terms", []).append(selector)
        if SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE.search(payload_text):
            issues.setdefault("payload_no_fixed_cut_count", []).append(selector)
    return issues


def _scene_readiness_issues(scenes: list[Any]) -> list[str]:
    """Return malformed scene/cut shape issues; no quality or review fields."""

    issues: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene{index}:type")
            continue
        selector = f"scene{_scene_id_for_issue(scene, str(index))}"
        issues.extend(f"{selector}:{key}" for key in _scene_event_issue_map(scene).get("beat_ids_unique", []))
        cuts = scene.get("cuts")
        if cuts is not None and not isinstance(cuts, list):
            issues.append(f"{selector}:cuts.type")
    return issues


def _scene_cut_coverage_plan(scene: dict[str, Any]) -> dict[str, Any]:
    value = scene.get("scene_cut_coverage_plan")
    return value if isinstance(value, dict) else {}


def _coverage_authored_obligation_ids(plan: dict[str, Any]) -> set[str]:
    values = plan.get("assignments") if isinstance(plan, dict) else []
    result: set[str] = set()
    for item in as_list(values):
        if isinstance(item, dict):
            result.update(str(value).strip() for value in as_list(item.get("obligation_ids")) if str(value).strip())
    return result


def _coverage_authored_event_beat_ids(plan: dict[str, Any]) -> set[str]:
    values = plan.get("assignments") if isinstance(plan, dict) else []
    result: set[str] = set()
    for item in as_list(values):
        if isinstance(item, dict):
            result.update(str(value).strip() for value in as_list(item.get("event_beat_ids")) if str(value).strip())
    return result


def _coverage_minimum_cut_count(plan: dict[str, Any]) -> int:
    value = as_int(as_dict(plan.get("min_cut_count")).get("selected")) if isinstance(plan, dict) else None
    return max(value or 0, 0)


def _cinematic_min_cuts_for_scene(scene: dict[str, Any]) -> int:
    # The former calculated floor was a quality gate. Structural callers only
    # need to know whether a cuts list was declared.
    return 0 if str(scene.get("kind") or "").strip().endswith("_reference") else 1


def _scene_cut_coverage_plan_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    del scene, scene_id, cuts
    return []


def _scene_cut_redundancy_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    del scene, scene_id, cuts
    return []


def _scene_cut_handoff_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    del scene, scene_id, cuts
    return []


def _cut_event_ref_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    sequence_ids = set(_scene_event_beat_ids(scene))
    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict):
            continue
        contract = cut.get("cut_contract")
        if not isinstance(contract, dict):
            continue
        source = as_dict(contract.get("source_event_contract"))
        references = [str(value).strip() for value in as_list(source.get("source_event_beat_ids")) if str(value).strip()]
        if any(reference not in sequence_ids for reference in references):
            issues.setdefault("refs_valid", []).append(f"{_scene_id_for_issue(scene)}:{cut.get('cut_id')}:source_event_beat_ids")
    return issues


def _cut_has_blueprint(cut: dict[str, Any]) -> bool:
    return bool(_node_cut_contract(cut, allow_legacy=True))


def _append_p400_scene_cut_checks(
    checks: list[dict[str, Any]],
    data: dict[str, Any],
    scenes: list[Any],
    *,
    run_dir: Path | None = None,
    deterministic_preapproval: bool = False,
) -> None:
    del run_dir, deterministic_preapproval
    renderable = [scene for scene in scenes if isinstance(scene, dict) and not str(scene.get("kind") or "").strip().endswith("_reference")]
    missing_cuts = [
        _scene_id_for_issue(scene, str(index))
        for index, scene in enumerate(renderable, start=1)
        if "cuts" not in scene or not isinstance(scene.get("cuts"), list)
    ]
    add_check(checks, "script.renderable_scenes_have_cuts", not missing_cuts, "renderable scenes declare cuts" + (f" (missing: {','.join(missing_cuts[:8])})" if missing_cuts else ""))
    contract_issues: list[str] = []
    for scene in renderable:
        scene_id = _scene_id_for_issue(scene)
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict) or "cut_contract" not in cut:
                continue
            contract_issues.extend(f"scene{scene_id}_cut{cut.get('cut_id') or '?'}:{issue}" for issue in _cut_contract_structure_issues(cut.get("cut_contract")))
    add_check(checks, "script.cut_contract_structure", not contract_issues, "declared cut contracts have valid structure" + (f" (issues: {','.join(contract_issues[:8])})" if contract_issues else ""))


__all__ = [
    "STORY_REQUIRED_SCENE_FIELDS",
    "_append_p400_scene_cut_checks",
    "_cinematic_min_cuts_for_scene",
    "_coverage_authored_event_beat_ids",
    "_coverage_authored_obligation_ids",
    "_coverage_minimum_cut_count",
    "_cut_event_ref_issue_map",
    "_cut_has_blueprint",
    "_scene_cut_coverage_plan",
    "_scene_cut_coverage_plan_issues",
    "_scene_cut_handoff_issues",
    "_scene_cut_redundancy_issues",
    "_scene_event_issue_map",
    "_scene_event_sequence",
    "_scene_readiness_issues",
    "check_script_scene_series",
    "check_script_single",
]
