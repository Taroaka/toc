"""Canonical research, visual-value, and story evaluation policy."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document, parse_state_file
from toc.image_prompt_projection_registry import projection_trace_issues
from toc.immersive_manifest import dotted_id_sort_key, make_scene_cut_selector
from toc.semantic_review import (
    check_semantic_review,
    semantic_review_currentness_issues,
    semantic_review_relpaths,
)

from .common import (
    IMAGE_API_PROMPT_FORBIDDEN_GATES,
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION_V2,
    IMAGE_API_PROMPT_V2_BASE_GROUPS,
    IMAGE_API_PROMPT_V2_GROUPS,
    SCENE_STATE_PROGRESSION_MODES,
    STAGE_RUBRIC_WEIGHTS,
    STORY_REQUIRED_SCENE_FIELDS,
    _append_grounding_checks,
    _append_rubric_findings,
    _node_cut_contract,
    _scene_cut_selector,
    add_check,
    as_dict,
    as_dotted_str,
    as_list,
    contract_list,
    flatten_without_keys,
    has_todo,
    make_stage,
    nested_get,
    non_empty,
    scene_time_of_day_contract_marker,
    scene_time_of_day_contract_missing,
    scene_time_of_day_visual_basis_contract_marker,
    scene_time_of_day_visual_basis_issues,
    score_from_checks,
    score_from_ratio,
)
from .manifest_nodes import _p300_production_artifact_issues

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


def _image_api_prompt_payload(image_generation: dict[str, Any]) -> dict[str, Any]:
    payload = image_generation.get("api_prompt_payload")
    return payload if isinstance(payload, dict) else {}


def _image_api_prompt_text(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("prompt") or image_generation.get("prompt") or "")


def _image_api_prompt_policy(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("policy_version") or image_generation.get("prompt_policy_version") or "").strip()


def _image_api_prompt_line_value(prompt: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", prompt)
    return match.group(1).strip() if match else ""


def _truthy_prompt_contract_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "はい"}


def _drawable_prompt_v2_ir(image_generation: dict[str, Any]) -> dict[str, Any]:
    payload = _image_api_prompt_payload(image_generation)
    ir = payload.get("drawable_prompt_ir")
    return ir if isinstance(ir, dict) else {}


def _drawable_prompt_v2_dependencies(image_generation: dict[str, Any], ir: dict[str, Any]) -> dict[str, Any]:
    raw = ir.get("dependencies")
    dependencies = dict(raw) if isinstance(raw, dict) else {}
    for key in ("character_ids", "object_ids", "location_ids", "references"):
        dependencies[key] = [str(value).strip() for value in as_list(dependencies.get(key)) if str(value).strip()]
    dependencies["required_groups"] = [
        str(value).strip()
        for value in as_list(dependencies.get("required_groups"))
        if str(value).strip()
    ]
    for key in ("story_time", "time_of_day"):
        dependencies[key] = str(dependencies.get(key) or "").strip()
    return dependencies


def _drawable_prompt_v2_fragment_groups(ir: dict[str, Any]) -> tuple[set[str], list[str], list[str]]:
    groups: set[str] = set()
    empty_groups: list[str] = []
    unknown_groups: list[str] = []
    fragments = ir.get("included_fragments")
    if not isinstance(fragments, list):
        return groups, empty_groups, unknown_groups
    for index, fragment in enumerate(fragments, start=1):
        if not isinstance(fragment, dict):
            empty_groups.append(f"entry_{index}")
            continue
        group = str(fragment.get("group") or "").strip()
        text = str(fragment.get("text") or "").strip()
        if not group:
            empty_groups.append(f"entry_{index}")
            continue
        groups.add(group)
        if group not in IMAGE_API_PROMPT_V2_GROUPS:
            unknown_groups.append(group)
        if not text:
            empty_groups.append(group)
    return groups, empty_groups, unknown_groups


def _image_api_prompt_v2_issues(
    selector: str,
    image_generation: dict[str, Any],
    *,
    expected_story_time: str | None = None,
    expected_time_of_day: str | None = None,
) -> list[str]:
    if _image_api_prompt_policy(image_generation) != IMAGE_API_PROMPT_POLICY_VERSION_V2:
        return []
    prompt = str(_image_api_prompt_payload(image_generation).get("prompt") or "").strip()
    issues: list[str] = []
    if not prompt:
        return [f"{selector}:api_prompt_missing_for_new_prompt_policy"]
    for gate_name, pattern in IMAGE_API_PROMPT_FORBIDDEN_GATES:
        if pattern.search(prompt):
            issues.append(f"{selector}:{gate_name}")

    ir = _drawable_prompt_v2_ir(image_generation)
    if not ir:
        issues.append(f"{selector}:api_prompt_v2_drawable_prompt_ir_missing")
        return issues
    if str(ir.get("schema_version") or "").strip() != "drawable_prompt_ir_v1":
        issues.append(f"{selector}:api_prompt_v2_drawable_prompt_ir_schema")
    if not isinstance(ir.get("dependencies"), dict):
        issues.append(f"{selector}:api_prompt_v2_dependencies_missing")
    if not isinstance(ir.get("included_fragments"), list):
        issues.append(f"{selector}:api_prompt_v2_included_fragments_missing")

    dependencies = _drawable_prompt_v2_dependencies(image_generation, ir)
    for key in ("character_ids", "object_ids", "location_ids", "references"):
        declared = [
            str(value).strip()
            for value in as_list(image_generation.get(key))
            if str(value).strip()
        ]
        if dependencies.get(key, []) != declared:
            issues.append(f"{selector}:api_prompt_v2_{key}_dependency_mismatch")
    groups, empty_groups, unknown_groups = _drawable_prompt_v2_fragment_groups(ir)
    issues.extend(f"{selector}:api_prompt_v2_included_fragment_empty:{group}" for group in empty_groups)
    issues.extend(f"{selector}:api_prompt_v2_unknown_fragment_group:{group}" for group in sorted(set(unknown_groups)))
    registry_issues = projection_trace_issues(
        prompt=prompt,
        dependencies=dependencies,
        included_fragments=ir.get("included_fragments"),
        expected_story_time=expected_story_time,
        expected_time_of_day=expected_time_of_day,
        first_frame_visual_plan=(
            image_generation.get("first_frame_visual_plan")
            if isinstance(image_generation.get("first_frame_visual_plan"), dict)
            else {}
        ),
    )
    issues.extend(f"{selector}:{issue.code}" for issue in registry_issues)
    registry_issue_codes = {issue.code for issue in registry_issues}

    required_groups = set(IMAGE_API_PROMPT_V2_BASE_GROUPS)
    required_groups.update(dependencies.get("required_groups") or [])
    dependency_groups = {
        "story_time": bool(dependencies.get("story_time")),
        "time_of_day": bool(dependencies.get("time_of_day")),
        "characters": bool(dependencies.get("character_ids")),
        "objects": bool(dependencies.get("object_ids")),
        "location": bool(dependencies.get("location_ids")),
        "references": bool(dependencies.get("references")),
    }
    required_groups.update(group for group, required in dependency_groups.items() if required)
    for group in sorted(required_groups):
        issue_group = {
            "characters": "character",
            "objects": "object",
        }.get(group, group)
        if f"api_prompt_v2_unneeded_{issue_group}_fragment" in registry_issue_codes:
            continue
        if group not in groups:
            issues.append(f"{selector}:api_prompt_v2_missing_{issue_group}_fragment")
    return issues


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
    payload = _image_api_prompt_payload(image_generation)
    shot_payload = payload.get("shot_design_contract") if isinstance(payload.get("shot_design_contract"), dict) else {}
    location_payload = payload.get("cut_location_frame_plan") if isinstance(payload.get("cut_location_frame_plan"), dict) else {}
    delta_payload = payload.get("cut_visual_delta") if isinstance(payload.get("cut_visual_delta"), dict) else {}
    blocking_payload = payload.get("blocking_and_interaction") if isinstance(payload.get("blocking_and_interaction"), dict) else {}
    if not str(shot_payload.get("shot_role") or "").strip():
        issues.append(f"{selector}:api_prompt_has_shot_role")
    if not str(location_payload.get("location_zone_id") or location_payload.get("location_zone_description") or "").strip():
        issues.append(f"{selector}:api_prompt_has_location_zone")
    if not str(delta_payload.get("this_cut_new_information") or delta_payload.get("cut_delta_visible_in_still") or "").strip():
        issues.append(f"{selector}:api_prompt_has_previous_cut_delta")
    if not isinstance(blocking_payload.get("character_blocking"), dict):
        issues.append(f"{selector}:api_prompt_has_character_blocking")
    prompt_body_requirements = {
        "api_prompt_body_has_naturalized_shot_role": "この一枚は",
        "api_prompt_body_has_naturalized_location_zone": "場所は",
        "api_prompt_body_has_naturalized_cut_delta": "この画像では",
        "api_prompt_body_has_naturalized_character_blocking": "姿勢は",
    }
    for gate_name, needle in prompt_body_requirements.items():
        if needle not in prompt:
            issues.append(f"{selector}:{gate_name}")
    for gate_name, needle in {
        "api_prompt_has_visible_face_behavior": "表情",
        "api_prompt_has_visible_gaze_behavior": "視線",
        "api_prompt_has_visible_posture_behavior": "姿勢",
        "api_prompt_has_visible_distance_behavior": "距離",
    }.items():
        if needle not in prompt:
            issues.append(f"{selector}:{gate_name}")
    object_interaction = blocking_payload.get("object_interaction") if isinstance(blocking_payload.get("object_interaction"), dict) else {}
    if as_list(image_generation.get("object_ids")) and not str(object_interaction.get("contact_state") or "").strip():
        issues.append(f"{selector}:api_prompt_has_object_contact_state_if_object_present")
    if as_list(image_generation.get("object_ids")) and "小道具への接触状態" not in prompt:
        issues.append(f"{selector}:api_prompt_body_has_object_contact_state_if_object_present")
    for required_payload in ("shot_design_contract", "cut_location_frame_plan", "cut_visual_delta", "blocking_and_interaction"):
        if not isinstance(_image_api_prompt_payload(image_generation).get(required_payload), dict):
            issues.append(f"{selector}:{required_payload}_missing")
    shot = _image_api_prompt_payload(image_generation).get("shot_design_contract")
    shot = shot if isinstance(shot, dict) else {}
    expected_role = str(shot.get("shot_role") or "").strip()
    expected_scale = str(shot.get("shot_scale") or "").strip()
    prompt_role = _image_api_prompt_line_value(prompt, "shot_role")
    prompt_scale = _image_api_prompt_line_value(prompt, "shot_scale")
    if expected_role and prompt_role and prompt_role != expected_role:
        issues.append(f"{selector}:api_prompt_body_shot_role_mismatch_with_payload")
    if expected_scale and prompt_scale and prompt_scale != expected_scale:
        issues.append(f"{selector}:api_prompt_body_shot_scale_mismatch_with_payload")
    if expected_role in {"insert", "object_proof"}:
        prompt_has_detail = bool(
            re.search(
                r"should_show_object_detail\s*:\s*yes|close[- ]?up|foreground|前景|手元|鍵穴|取っ手|大きく|細部|詳細",
                prompt,
                re.I,
            )
        )
        if not _truthy_prompt_contract_value(shot.get("should_show_object_detail")) and not prompt_has_detail:
            issues.append(f"{selector}:insert_cut_missing_object_detail")
    if expected_role == "reaction":
        has_visible_reaction = (
            "[人物の見える演技]" in prompt
            and
            re.search(r"表情|face|expression", prompt, re.I)
            and re.search(r"視線|gaze|eyeline", prompt, re.I)
            and re.search(r"姿勢|posture|body", prompt, re.I)
        )
        if not has_visible_reaction:
            issues.append(f"{selector}:reaction_cut_missing_visible_reaction_behavior")
    if expected_role == "handoff":
        if not re.search(r"次|導線|渡す|path|next|gaze direction|視線.*(?:外|庭|奥|向こう|抜け|移る)", prompt, re.I):
            issues.append(f"{selector}:handoff_cut_missing_next_scene_visual_path")
    return issues


def _planned_scene_shots(scene: dict[str, Any]) -> dict[str, tuple[str, str]]:
    candidates: list[Any] = []
    shot_mix_plan = scene.get("scene_shot_mix_plan")
    if isinstance(shot_mix_plan, dict):
        candidates.extend(as_list(shot_mix_plan.get("shots")))
        candidates.extend(as_list(shot_mix_plan.get("actual_shots")))
        nested_shot_mix = shot_mix_plan.get("shot_mix")
        if isinstance(nested_shot_mix, dict):
            candidates.extend(as_list(nested_shot_mix.get("actual_shots")))
    film_plan = scene.get("scene_film_coverage_plan")
    if isinstance(film_plan, dict):
        shot_mix = film_plan.get("shot_mix")
        if isinstance(shot_mix, dict):
            candidates.extend(as_list(shot_mix.get("actual_shots")))
    result: dict[str, tuple[str, str]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        selector = str(item.get("selector") or "").strip()
        if not selector:
            continue
        result[selector] = (str(item.get("shot_role") or "").strip(), str(item.get("shot_scale") or "").strip())
    return result


def _scene_shot_mix_plan_v1_issues(scenes: list[Any]) -> list[str]:
    issues: list[str] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        cuts = as_list(scene.get("cuts")) or [scene]
        v1_shots: list[tuple[str, str, str]] = []
        planned_shots = _planned_scene_shots(scene)
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
            actual_role = str(shot.get("shot_role") or "").strip()
            actual_scale = str(shot.get("shot_scale") or "").strip()
            v1_shots.append((selector, actual_role, actual_scale))
            planned_role, planned_scale = planned_shots.get(selector, ("", ""))
            if planned_role and actual_role and planned_role != actual_role:
                issues.append(f"{selector}:api_prompt_shot_role_mismatch_with_scene_shot_mix")
            if planned_scale and actual_scale and planned_scale != actual_scale:
                issues.append(f"{selector}:api_prompt_shot_scale_mismatch_with_scene_shot_mix")
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


def _scene_state_progression_plan_issues(scenes: list[Any]) -> list[str]:
    issues: list[str] = []

    def normalized_for_prompt_compare(value: Any) -> str:
        return re.sub(r"[\s、。,.]+", "", str(value or ""))

    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = [
            cut
            for cut in as_list(scene.get("cuts"))
            if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
        ]
        has_api_prompt_v1 = any(
            _image_api_prompt_policy(as_dict(cut.get("image_generation"))) == IMAGE_API_PROMPT_POLICY_VERSION
            for cut in cuts
        )
        if not has_api_prompt_v1:
            continue
        scene_id = as_dotted_str(scene.get("scene_id")) or str(scene_index)
        plan = as_dict(scene.get("scene_state_progression_plan"))
        if not plan:
            issues.append(f"scene{scene_id}:scene_state_progression_plan_exists")
            continue
        if str(plan.get("policy_version") or "").strip() != "scene_state_progression_v1":
            issues.append(f"scene{scene_id}:scene_state_progression_plan.policy_version")
        mode = str(plan.get("progression_mode") or "").strip()
        if mode not in SCENE_STATE_PROGRESSION_MODES:
            issues.append(f"scene{scene_id}:scene_state_progression_plan.progression_mode")
        map_by_selector = {
            str(item.get("cut_selector") or "").strip(): item
            for item in as_list(plan.get("cut_progression_map"))
            if isinstance(item, dict) and str(item.get("cut_selector") or "").strip()
        }
        if mode == "sequential_state_progression" and not map_by_selector:
            issues.append(f"scene{scene_id}:scene_state_progression_plan.cut_progression_map")
        for cut_index, cut in enumerate(cuts, start=1):
            image_generation = as_dict(cut.get("image_generation"))
            if _image_api_prompt_policy(image_generation) != IMAGE_API_PROMPT_POLICY_VERSION:
                continue
            selector = _scene_cut_selector(scene_id, cut) or str(cut.get("selector") or cut.get("cut_id") or f"cut{cut_index}")
            contract = _node_cut_contract(cut)
            cut_state = as_dict(contract.get("cut_state_progression"))
            prompt = _image_api_prompt_text(image_generation)
            mapped_state = as_dict(map_by_selector.get(selector))
            if mode == "sequential_state_progression":
                if not cut_state:
                    issues.append(f"{selector}:cut_state_progression_missing")
                    continue
                if str(cut_state.get("policy_version") or "").strip() != "cut_state_progression_v1":
                    issues.append(f"{selector}:cut_state_progression.policy_version")
                if str(cut_state.get("progression_mode") or "").strip() != "sequential_state_progression":
                    issues.append(f"{selector}:cut_state_progression.progression_mode")
                if mapped_state:
                    expected_state = str(mapped_state.get("state_visible_in_this_cut") or "").strip()
                    actual_state = str(cut_state.get("state_visible_in_first_frame") or "").strip()
                    if expected_state and actual_state and expected_state != actual_state:
                        issues.append(f"{selector}:cut_state_progression.mismatch_with_scene_plan")
                required_fields = (
                    "first_frame_temporal_role",
                    "state_after_previous_cut",
                    "state_visible_in_first_frame",
                    "must_not_advance_beyond",
                    "done_when",
                )
                for field in required_fields:
                    if field == "done_when":
                        if not as_list(cut_state.get(field)):
                            issues.append(f"{selector}:cut_state_progression.{field}")
                    elif not non_empty(cut_state.get(field)):
                        issues.append(f"{selector}:cut_state_progression.{field}")
                if cut_index > 1 and not non_empty(cut_state.get("visible_state_delta_from_previous_cut")):
                    issues.append(f"{selector}:cut_state_progression_delta_missing")
                first_frame = as_dict(contract.get("first_frame_contract"))
                visible_start = as_dict(first_frame.get("visible_start_state"))
                visible_state_text = " / ".join(
                    str(value)
                    for value in (
                        cut_state.get("state_visible_in_first_frame"),
                        visible_start.get("character_state"),
                        first_frame.get("first_frame_brief"),
                        _image_api_prompt_line_value(prompt, "cut_visible_moment"),
                        _image_api_prompt_line_value(prompt, "this_cut_delta"),
                    )
                    if str(value or "").strip()
                )
                must_not_revert = str(cut_state.get("must_not_revert_to") or "").strip()
                if cut_index > 1:
                    reverted_to_explicit_state = bool(must_not_revert and must_not_revert in visible_state_text)
                    reverted_to_generic_start = bool(re.search(r"まだ行為を完了していない|開始前|行為直前|乗る前|待機", visible_state_text))
                    if reverted_to_explicit_state or reverted_to_generic_start:
                        issues.append(f"{selector}:cut_first_frame_reverts_to_scene_start")
                if cut_index > 1 and _image_api_prompt_line_value(prompt, "action_completion_state") in {"pre_action", "early_action"}:
                    issues.append(f"{selector}:cut_state_progression_action_completion_not_progressed")
                if (
                    must_not_revert
                    and normalized_for_prompt_compare(must_not_revert) not in normalized_for_prompt_compare(prompt)
                    and cut_index > 1
                ):
                    issues.append(f"{selector}:cut_state_progression_must_not_revert_missing_from_api_prompt")
            elif mode == "suspended_moment":
                if cut_state and str(cut_state.get("progression_mode") or "").strip() not in {"", "suspended_moment"}:
                    issues.append(f"{selector}:suspended_moment_cut_state_progression_mode")
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

    state = parse_state_file(run_dir / "state.txt")
    semantic_paths = semantic_review_relpaths("story")
    semantic_artifacts_present = any((run_dir / relpath).exists() for relpath in semantic_paths.values())
    semantic_review_required = (
        state.get("review.policy.story", "").strip().lower() == "required"
        or semantic_artifacts_present
    )
    if semantic_review_required:
        semantic_result = check_semantic_review(run_dir, "story")
        add_check(
            checks,
            "story.semantic_review",
            semantic_result.passed,
            "story semantic review passed with exact entry coverage and no blockers"
            + (f" (issues: {', '.join(semantic_result.errors[:8])})" if semantic_result.errors else ""),
            kind="rubric",
        )
        currentness_issues = semantic_review_currentness_issues(run_dir, "story")
        add_check(
            checks,
            "story.semantic_review_current",
            not currentness_issues,
            "story semantic review is bound to the current research/story revision"
            + (f" (issues: {', '.join(currentness_issues[:8])})" if currentness_issues else ""),
            kind="rubric",
        )

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

    time_contract_declared, time_contract_valid = scene_time_of_day_contract_marker(
        data, artifact="story"
    )
    if time_contract_declared:
        add_check(
            checks,
            "story.scene_time_of_day_contract",
            time_contract_valid,
            "story_metadata.scene_time_of_day_contract is required_v1",
            kind="rubric",
        )
    missing_time_of_day = scene_time_of_day_contract_missing(data, artifact="story")
    if missing_time_of_day is not None:
        if missing_time_of_day:
            details["missing_time_of_day_scene_ids"] = ",".join(missing_time_of_day[:20])
        add_check(
            checks,
            "story.scene_time_of_day",
            not missing_time_of_day,
            "all newly authored story scenes include non-empty time_of_day"
            + (f" (missing: {', '.join(missing_time_of_day[:8])})" if missing_time_of_day else ""),
            kind="rubric",
        )
    basis_contract_declared, basis_contract_valid = (
        scene_time_of_day_visual_basis_contract_marker(data, artifact="story")
    )
    if basis_contract_declared:
        add_check(
            checks,
            "story.scene_time_of_day_visual_basis_contract",
            basis_contract_valid,
            "story_metadata.scene_time_of_day_visual_basis_contract is required_v1",
            kind="rubric",
        )
    basis_issues = scene_time_of_day_visual_basis_issues(data, artifact="story")
    if basis_issues is not None:
        add_check(
            checks,
            "story.scene_time_of_day_visual_basis",
            not basis_issues,
            "all newly authored story scenes define lighting evidence for 光源, 明るさ, 影, 色温度"
            + (f" (issues: {', '.join(basis_issues[:8])})" if basis_issues else ""),
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
                _image_api_prompt_text(image_generation).strip(),
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


