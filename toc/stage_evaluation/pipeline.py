"""Structural checks used by the ToC production pipeline.

The old implementation in this module was an evaluator: it calculated
rubrics, inspected review reports, and wrote approval state.  Production now
only needs deterministic contract checks.  These functions deliberately avoid
quality heuristics and return a small ``stage`` result with ordinary checks.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from toc.adaptation_value_contract import (
    manifest_adaptation_issues,
    script_adaptation_issues,
    source_value_ids as adaptation_source_value_ids,
    story_adaptation_issues,
)
from toc.harness import load_structured_document, parse_state_file
from toc.story_duration import audit_duration, normalize_target_duration

from .common import (
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION_V2,
    SCENE_GENERATION_REQUIRED_BLOCKS,
    SCENE_GENERATION_REQUIRED_OUTPUTS,
    SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE,
    SCENE_PROMPT_PAYLOAD_FORBIDDEN_DOWNSTREAM_FIELDS,
    SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE,
    STORY_REQUIRED_SCENE_FIELDS,
    _cut_contract_structure_issues,
    _node_cut_contract,
    _scene_cut_selector,
    add_check,
    as_dict,
    as_dotted_str,
    as_int,
    as_list,
    detect_flow,
    make_stage,
    nested_get,
    non_empty,
    scene_time_of_day_contract_missing,
    scene_time_of_day_contract_marker,
    scene_time_of_day_visual_basis_contract_marker,
    scene_time_of_day_visual_basis_issues,
)


DurationProbe = Callable[[Path], float | None]


def _document(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.is_file():
        return "", {}
    return load_structured_document(path)


def _scenes(data: dict[str, Any]) -> list[Any]:
    return as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))


def _scene_id(scene: Any, fallback: int) -> str:
    return as_dotted_str(scene.get("scene_id")) if isinstance(scene, dict) and scene.get("scene_id") is not None else str(fallback)


def _validate_unique_ids(
    values: list[Any],
    *,
    id_key: str,
    label: str,
    checks: list[dict[str, Any]],
) -> None:
    missing: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            missing.append(str(index))
            continue
        identifier = as_dotted_str(value.get(id_key))
        if not identifier:
            missing.append(str(index))
            continue
        if identifier in seen:
            duplicates.append(identifier)
        seen.add(identifier)
    add_check(
        checks,
        f"{label}.ids",
        not missing and not duplicates,
        f"{label} entries use unique {id_key} values"
        + (f" (missing: {','.join(missing[:8])})" if missing else "")
        + (f" (duplicates: {','.join(duplicates[:8])})" if duplicates else ""),
    )


def _valid_relative_path(run_dir: Path, value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value.strip())
    if path.is_absolute():
        return False
    try:
        (run_dir / path).resolve().relative_to(run_dir.resolve())
    except ValueError:
        return False
    return True


def compact_research_pack_ok(
    *,
    sources: list[Any],
    passage_count: int,
    canonical_story: Any,
    conflict_items: list[Any],
    handoff_to_story: Any,
) -> bool:
    """Compatibility helper for callers that describe a focused research pack."""

    return bool(
        non_empty(canonical_story)
        and passage_count >= 3
        and (len(sources) >= 1 or bool(conflict_items) or non_empty(handoff_to_story))
    )


def dense_story_scene_count(scenes: list[Any]) -> int:
    return sum(
        1
        for scene in scenes
        if isinstance(scene, dict)
        and as_dotted_str(scene.get("scene_id"))
        and as_list(scene.get("research_refs"))
    )


def story_scene_coverage_ok(scenes: list[Any]) -> bool:
    # Kept for API compatibility. It is no longer used as a quality threshold
    # by any production check.
    return bool(scenes)


def _research_structure_checks(
    checks: list[dict[str, Any]],
    data: dict[str, Any],
) -> dict[str, int]:
    sources = as_list(data.get("source_inventory") or data.get("sources"))
    passages = as_list(data.get("source_passages"))
    facts_value = data.get("facts")
    facts = as_list(facts_value.get("items")) if isinstance(facts_value, dict) else as_list(facts_value)
    story_materials = data.get("story_materials")
    synopsis = nested_get(data, ["story_baseline", "canonical_synopsis", "short_summary"]) or nested_get(
        data, ["story_baseline", "canonical_synopsis", "one_liner"]
    )
    events = as_list(nested_get(data, ["story_materials", "chronological_events"], []))
    conflicts = data.get("conflicts")
    handoff = data.get("handoff_to_story")

    add_check(checks, "research.structured", bool(data), "research.md contains structured YAML output")
    add_check(
        checks,
        "research.sources_type",
        isinstance(data.get("source_inventory", data.get("sources")), list),
        "research source inventory is a list",
    )
    add_check(
        checks,
        "research.story_materials_type",
        isinstance(story_materials, dict) or non_empty(synopsis),
        "research contains story material or a canonical synopsis",
    )
    add_check(
        checks,
        "research.passages_type",
        isinstance(data.get("source_passages"), list) if "source_passages" in data else True,
        "research source_passages is a list when declared",
    )
    add_check(
        checks,
        "research.facts_type",
        isinstance(facts_value, (list, dict)) if facts_value is not None else True,
        "research facts are a list or items mapping when declared",
    )
    add_check(
        checks,
        "research.conflicts_type",
        isinstance(conflicts, (list, dict)) if conflicts is not None else True,
        "research conflicts are a list or mapping when declared",
    )
    add_check(
        checks,
        "research.handoff_type",
        isinstance(handoff, (dict, list, str)) if handoff is not None else True,
        "research handoff_to_story has a serializable shape when declared",
    )
    return {
        "sources": len(sources),
        "passages": len(passages),
        "facts": len(facts),
        "events": len(events),
    }


def check_research(run_dir: Path, profile: str = "standard") -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "research.md"
    checks: list[dict[str, Any]] = []
    add_check(checks, "research.file_exists", path.is_file(), f"{path.name} exists")
    if not path.is_file():
        return make_stage("research", path.name, checks), {}
    text, data = _document(path)
    counts = _research_structure_checks(checks, data)
    return make_stage("research", path.name, checks, details=counts), {}


def _story_scenes(data: dict[str, Any]) -> list[Any]:
    return as_list(nested_get(data, ["script", "scenes"], [])) or as_list(data.get("scenes"))


def check_story(run_dir: Path, profile: str = "standard") -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "story.md"
    checks: list[dict[str, Any]] = []
    add_check(checks, "story.file_exists", path.is_file(), f"{path.name} exists")
    if not path.is_file():
        return make_stage("story", path.name, checks), {}
    _text, data = _document(path)
    add_check(checks, "story.structured", bool(data), "story.md contains structured YAML output")
    scenes = _story_scenes(data)
    add_check(checks, "story.scenes_type", isinstance(nested_get(data, ["script", "scenes"], data.get("scenes")), list), "story scenes are represented as a list")
    _validate_unique_ids(scenes, id_key="scene_id", label="story.scene", checks=checks)
    invalid_refs: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        refs = scene.get("research_refs")
        if refs is not None and not isinstance(refs, list):
            invalid_refs.append(_scene_id(scene, index))
    add_check(checks, "story.research_refs_type", not invalid_refs, "declared scene research_refs values are lists" + (f" (invalid: {','.join(invalid_refs[:8])})" if invalid_refs else ""))

    selection = data.get("selection")
    if selection is not None:
        add_check(checks, "story.selection_type", isinstance(selection, dict), "selection is a mapping when declared")
        if isinstance(selection, dict):
            candidates = selection.get("candidates")
            if candidates is not None:
                add_check(checks, "story.candidates_type", isinstance(candidates, list), "selection.candidates is a list when declared")
                if isinstance(candidates, list):
                    _validate_unique_ids(candidates, id_key="candidate_id", label="story.candidate", checks=checks)
            chosen = selection.get("chosen_candidate_id")
            if chosen is not None and candidates and isinstance(candidates, list):
                candidate_ids = {as_dotted_str(item.get("candidate_id")) for item in candidates if isinstance(item, dict)}
                add_check(checks, "story.choice_reference", as_dotted_str(chosen) in candidate_ids, "chosen_candidate_id references a declared candidate")

    declared, valid = scene_time_of_day_contract_marker(data, artifact="story")
    if declared:
        missing = scene_time_of_day_contract_missing(data, artifact="story") or []
        add_check(checks, "story.scene_time_of_day_contract", valid and not missing, "declared story time-of-day contract has valid scene values" + (f" (issues: {','.join(missing[:8])})" if missing else ""))
    basis_declared, basis_valid = scene_time_of_day_visual_basis_contract_marker(data, artifact="story")
    if basis_declared:
        issues = scene_time_of_day_visual_basis_issues(data, artifact="story") or []
        add_check(checks, "story.scene_time_of_day_visual_basis", basis_valid and not issues, "declared story lighting basis has required fields" + (f" (issues: {','.join(issues[:8])})" if issues else ""))

    if isinstance(data.get("story_metadata"), dict) and "adaptation_value_contract" in data["story_metadata"]:
        issues = story_adaptation_issues(data)
        add_check(checks, "story.adaptation_value_contract", not issues, "declared adaptation source contract is structurally consistent" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    return make_stage("story", path.name, checks, details={"scene_count": len(scenes)}), {}


def _script_scenes(data: dict[str, Any]) -> list[Any]:
    return as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))


def _scene_contract_issues(scene: dict[str, Any], *, selector: str) -> list[str]:
    issues: list[str] = []
    scene_event = scene.get("scene_event")
    if scene_event is not None:
        if not isinstance(scene_event, dict):
            issues.append(f"{selector}:scene_event.type")
        else:
            sequence = scene_event.get("event_sequence")
            if sequence is not None and not isinstance(sequence, list):
                issues.append(f"{selector}:scene_event.event_sequence.type")
            if isinstance(sequence, list):
                beat_ids = [as_dotted_str(item.get("beat_id")) for item in sequence if isinstance(item, dict)]
                if any(not beat_id for beat_id in beat_ids) or len(set(beat_ids)) != len(beat_ids):
                    issues.append(f"{selector}:scene_event.beat_ids")
            forbidden = scene_event.get("forbidden_event_changes")
            if forbidden is not None and not isinstance(forbidden, list):
                issues.append(f"{selector}:scene_event.forbidden_event_changes.type")
            for key, value in scene_event.items():
                if key in {"event_sequence", "forbidden_event_changes"}:
                    continue
                if key in {"camera", "lens", "framing", "shot", "image_prompt", "video_prompt", "motion_prompt"}:
                    issues.append(f"{selector}:scene_event.forbidden_directing_field:{key}")
    generation = scene.get("scene_generation")
    if generation is not None:
        if not isinstance(generation, dict):
            issues.append(f"{selector}:scene_generation.type")
        else:
            for key in SCENE_GENERATION_REQUIRED_BLOCKS:
                if key in generation and not isinstance(generation[key], (dict, list, str)):
                    issues.append(f"{selector}:scene_generation.{key}.type")
            for key in SCENE_GENERATION_REQUIRED_OUTPUTS:
                if key in generation and generation[key] is None:
                    issues.append(f"{selector}:scene_generation.{key}.null")
            payload = generation.get("scene_prompt_payload")
            if isinstance(payload, dict):
                for key in SCENE_PROMPT_PAYLOAD_FORBIDDEN_DOWNSTREAM_FIELDS:
                    if key in payload:
                        issues.append(f"{selector}:scene_prompt_payload.forbidden_field:{key}")
                payload_text = " ".join(str(value) for value in payload.values())
                if SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE.search(payload_text):
                    issues.append(f"{selector}:scene_prompt_payload.directing_terms")
                if SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE.search(payload_text):
                    issues.append(f"{selector}:scene_prompt_payload.fixed_cut_count")
    cuts = scene.get("cuts")
    if cuts is not None:
        if not isinstance(cuts, list):
            issues.append(f"{selector}:cuts.type")
        else:
            _seen: set[str] = set()
            for index, cut in enumerate(cuts, start=1):
                if not isinstance(cut, dict):
                    issues.append(f"{selector}:cut[{index}].type")
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if not cut_id:
                    issues.append(f"{selector}:cut[{index}].cut_id")
                elif cut_id in _seen:
                    issues.append(f"{selector}:cut[{index}].cut_id.duplicate")
                _seen.add(cut_id or f"#{index}")
                if "cut_contract" in cut:
                    issues.extend(f"{selector}_cut{cut_id or index}:{issue}" for issue in _cut_contract_structure_issues(cut.get("cut_contract")))
                for key in ("image_generation", "video_generation", "audio"):
                    if key in cut and not isinstance(cut[key], dict):
                        issues.append(f"{selector}_cut{cut_id or index}:{key}.type")
    return issues


def _append_script_structure_checks(
    checks: list[dict[str, Any]],
    data: dict[str, Any],
    *,
    label: str = "script",
) -> dict[str, Any]:
    scenes = _script_scenes(data)
    add_check(checks, f"{label}.scenes_type", isinstance(data.get("scenes"), list) or isinstance(nested_get(data, ["script", "scenes"], None), list), f"{label} scenes are represented as a list")
    _validate_unique_ids(scenes, id_key="scene_id", label=f"{label}.scene", checks=checks)
    contract_issues: list[str] = []
    invalid_refs: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            contract_issues.append(f"{label}.scene[{index}].type")
            continue
        selector = _scene_id(scene, index)
        contract_issues.extend(_scene_contract_issues(scene, selector=f"scene{selector}"))
        refs = scene.get("research_refs")
        if refs is not None and not isinstance(refs, list):
            invalid_refs.append(selector)
    add_check(checks, f"{label}.contracts", not contract_issues, f"{label} scene/cut contracts have valid structure" + (f" (issues: {','.join(contract_issues[:8])})" if contract_issues else ""))
    add_check(checks, f"{label}.research_refs_type", not invalid_refs, f"{label} scene research_refs values are lists" + (f" (invalid: {','.join(invalid_refs[:8])})" if invalid_refs else ""))
    return {"scene_count": len(scenes), "contract_issue_count": len(contract_issues)}


def _script_text_quality_checks(checks: list[dict[str, Any]], text: str, data: dict[str, Any], profile: str) -> None:
    """Compatibility helper retaining only parse/type checks."""

    add_check(checks, "script.content_present", bool(text.strip()), "script contains source text")
    if data:
        _append_script_structure_checks(checks, data)


def check_script_single(run_dir: Path, profile: str = "standard", *, target_slot: str = "p450") -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "script.md"
    checks: list[dict[str, Any]] = []
    add_check(checks, "script.file_exists", path.is_file(), f"{path.name} exists")
    if not path.is_file():
        return make_stage("script", path.name, checks), {}
    text, data = _document(path)
    add_check(checks, "script.structured", bool(data), "script.md contains structured YAML output")
    details = _append_script_structure_checks(checks, data)
    declared, valid = scene_time_of_day_contract_marker(data, artifact="script")
    if declared:
        missing = scene_time_of_day_contract_missing(data, artifact="script") or []
        add_check(checks, "script.scene_time_of_day_contract", valid and not missing, "declared script time-of-day contract has valid scene values" + (f" (issues: {','.join(missing[:8])})" if missing else ""))
    basis_declared, basis_valid = scene_time_of_day_visual_basis_contract_marker(data, artifact="script")
    if basis_declared:
        issues = scene_time_of_day_visual_basis_issues(data, artifact="script") or []
        add_check(checks, "script.scene_time_of_day_visual_basis", basis_valid and not issues, "declared script lighting basis has required fields" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    if isinstance(data.get("script_metadata"), dict) and "adaptation_value_contract" in data["script_metadata"]:
        story_data = _document(run_dir / "story.md")[1]
        visual_value_data = _document(run_dir / "visual_value.md")[1]
        issues = script_adaptation_issues(data, source_value_ids=adaptation_source_value_ids(story_data), visual_value=visual_value_data)
        add_check(checks, "script.adaptation_value_contract", not issues, "declared script adaptation contract is structurally consistent" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    return make_stage("script", path.name, checks, details=details), {}


def check_script_scene_series(run_dir: Path, profile: str = "standard", *, target_slot: str = "p450") -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted(path for path in (run_dir / "scenes").glob("scene*") if path.is_dir())
    script_paths = [scene_dir / "script.md" for scene_dir in scene_dirs]
    add_check(checks, "script.scene_dirs", bool(scene_dirs), f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "script.scene_files", bool(scene_dirs) and all(path.is_file() for path in script_paths), "each scene has script.md")
    issue_values: list[str] = []
    for path in script_paths:
        if not path.is_file():
            continue
        _text, data = _document(path)
        issue_values.extend(_append_script_structure_checks([], data, label=path.parent.name).get("contract_issue_count", 0) * [path.parent.name])
    add_check(checks, "script.scene_contracts", not issue_values, "scene-series script contracts have valid structure" + (f" (issues: {','.join(issue_values[:8])})" if issue_values else ""))
    return make_stage("script", "scenes/*/script.md", checks, details={"scene_count": len(scene_dirs)}), {}


def _iter_manifest_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for scene in as_list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            nodes.extend(cut for cut in cuts if isinstance(cut, dict) and str(cut.get("cut_status") or "").lower() != "deleted")
        else:
            nodes.append(scene)
    return nodes


def _iter_manifest_nodes_with_selectors(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    values: list[tuple[str, dict[str, Any]]] = []
    for scene in as_list(manifest.get("scenes")):
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut in cuts:
                if not isinstance(cut, dict) or str(cut.get("cut_status") or "").lower() == "deleted":
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if cut_id:
                    values.append((_scene_cut_selector(scene_id, cut), cut))
        else:
            values.append((_scene_cut_selector(scene_id, {}), scene))
    return values


def _manifest_checks(
    checks: list[dict[str, Any]],
    text: str,
    data: dict[str, Any],
    *,
    profile: str,
    flow: str,
    path_label: str,
    run_dir: Path | None = None,
    script_data: dict[str, Any] | None = None,
) -> None:
    del run_dir, script_data
    scenes = as_list(data.get("scenes"))
    add_check(checks, f"{path_label}.scenes_type", isinstance(data.get("scenes"), list), f"{path_label} scenes are represented as a list")
    _validate_unique_ids(scenes, id_key="scene_id", label=f"{path_label}.scene", checks=checks)
    nodes = _iter_manifest_nodes(data)
    invalid: list[str] = []
    path_issues: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            invalid.append(str(index))
            continue
        scene_id = _scene_id(scene, index)
        cuts = scene.get("cuts")
        if cuts is not None and not isinstance(cuts, list):
            invalid.append(f"scene{scene_id}:cuts")
        if isinstance(cuts, list):
            seen_cut_ids: set[str] = set()
            for cut_index, cut in enumerate(cuts, start=1):
                if not isinstance(cut, dict):
                    invalid.append(f"scene{scene_id}:cut{cut_index}")
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if cut_id and cut_id in seen_cut_ids:
                    invalid.append(f"scene{scene_id}:cut{cut_id}:duplicate")
                if cut_id:
                    seen_cut_ids.add(cut_id)
        for node in ([scene] if not isinstance(cuts, list) or not cuts else [cut for cut in cuts if isinstance(cut, dict)]):
            for key in ("image_generation", "video_generation", "audio"):
                if key in node and not isinstance(node[key], dict):
                    invalid.append(f"scene{scene_id}:{key}.type")
            image = as_dict(node.get("image_generation"))
            for key in ("character_ids", "object_ids", "location_ids"):
                if key in image and not isinstance(image[key], list):
                    invalid.append(f"scene{scene_id}:{key}.type")
            video = as_dict(node.get("video_generation"))
            duration = video.get("duration_seconds", node.get("duration_seconds"))
            if duration is not None and (not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0 or duration > 15):
                invalid.append(f"scene{scene_id}:duration_seconds")
            audio = as_dict(node.get("audio"))
            narration = audio.get("narration")
            if narration is not None and not isinstance(narration, dict):
                invalid.append(f"scene{scene_id}:audio.narration.type")
            elif isinstance(narration, dict) and "output" in narration:
                raw_output = str(narration.get("output") or "").strip()
                output_path = Path(raw_output)
                if output_path.is_absolute() or ".." in output_path.parts:
                    path_issues.append(f"scene{scene_id}:audio.narration.output")
            image_payload = image.get("api_prompt_payload")
            if image_payload is not None and not isinstance(image_payload, dict):
                invalid.append(f"scene{scene_id}:image_generation.api_prompt_payload.type")
            elif isinstance(image_payload, dict) and "prompt" in image_payload and not isinstance(image_payload.get("prompt"), str):
                invalid.append(f"scene{scene_id}:image_generation.api_prompt_payload.prompt.type")
    add_check(checks, f"{path_label}.node_types", not invalid, f"{path_label} scene/cut nodes use valid field types" + (f" (issues: {','.join(invalid[:8])})" if invalid else ""))
    add_check(checks, f"{path_label}.output_paths", not path_issues, f"{path_label} declared output paths are relative files" + (f" (issues: {','.join(path_issues[:8])})" if path_issues else ""))
    declared, valid = scene_time_of_day_contract_marker(data, artifact="manifest")
    if declared:
        missing = scene_time_of_day_contract_missing(data, artifact="manifest") or []
        add_check(checks, f"{path_label}.scene_time_of_day_contract", valid and not missing, f"{path_label} declared time-of-day contract has valid scene values" + (f" (issues: {','.join(missing[:8])})" if missing else ""))
    basis_declared, basis_valid = scene_time_of_day_visual_basis_contract_marker(data, artifact="manifest")
    if basis_declared:
        issues = scene_time_of_day_visual_basis_issues(data, artifact="manifest") or []
        add_check(checks, f"{path_label}.scene_time_of_day_visual_basis", basis_valid and not issues, f"{path_label} declared lighting basis has required fields" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    if flow == "immersive":
        experience = nested_get(data, ["video_metadata", "experience"])
        if experience is not None:
            add_check(checks, f"{path_label}.experience_type", isinstance(experience, str), f"{path_label} video_metadata.experience is a string")


def _minimum_cut_issues(manifest: dict[str, Any], *, min_cuts_per_scene: int | None = None) -> list[str]:
    """Return only malformed scene/cut shape issues.

    Cut-count quality floors belonged to the removed evaluator and are no
    longer enforced here.
    """

    issues: list[str] = []
    for index, scene in enumerate(as_list(manifest.get("scenes")), start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene[{index}]:invalid")
            continue
        cuts = scene.get("cuts")
        if cuts is not None and not isinstance(cuts, list):
            issues.append(f"scene{_scene_id(scene, index)}:cuts:type")
    return issues


def check_manifest_single(
    run_dir: Path,
    profile: str = "standard",
    flow: str = "toc-run",
    *,
    require_review_artifacts: bool | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    # The keyword remains accepted for old callers while having no effect.
    # Review reports are never consulted by the structural validator.
    del require_review_artifacts
    path = run_dir / "video_manifest.md"
    checks: list[dict[str, Any]] = []
    add_check(checks, "manifest.file_exists", path.is_file(), f"{path.name} exists")
    if not path.is_file():
        return make_stage("manifest", path.name, checks), {}
    text, data = _document(path)
    add_check(checks, "manifest.structured", bool(data), "video_manifest.md contains structured YAML output")
    _manifest_checks(checks, text, data, profile=profile, flow=flow, path_label="manifest")
    phase = data.get("manifest_phase")
    if phase is not None:
        phase_value = str(phase).strip().lower()
        add_check(checks, "manifest.phase", phase_value in {"skeleton", "production"}, f"manifest_phase is skeleton or production (got {phase_value or '(unset)'})")
    metadata = as_dict(data.get("video_metadata"))
    if "target_duration_seconds" in metadata:
        raw_target = metadata.get("target_duration_seconds")
        try:
            normalized = normalize_target_duration(raw_target)
        except (TypeError, ValueError):
            normalized = None
        add_check(checks, "manifest.target_duration_type", normalized is not None, "video_metadata.target_duration_seconds is a valid 300-1200 second value")
    story_data = _document(run_dir / "story.md")[1]
    script_data = _document(run_dir / "script.md")[1]
    if isinstance(data.get("video_metadata"), dict) and "adaptation_value_contract" in data["video_metadata"]:
        issues = manifest_adaptation_issues(data, source_value_ids=adaptation_source_value_ids(story_data), script=script_data or None)
        add_check(checks, "manifest.adaptation_value_contract", not issues, "declared manifest adaptation contract is structurally consistent" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    return make_stage("manifest", path.name, checks, details={"node_count": len(_iter_manifest_nodes(data))}), {}


def check_manifest_scene_series(run_dir: Path, profile: str = "standard") -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted(path for path in (run_dir / "scenes").glob("scene*") if path.is_dir())
    manifest_paths = [scene_dir / "video_manifest.md" for scene_dir in scene_dirs]
    add_check(checks, "manifest.scene_dirs", bool(scene_dirs), f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "manifest.scene_files", bool(scene_dirs) and all(path.is_file() for path in manifest_paths), "each scene has video_manifest.md")
    issues: list[str] = []
    for path in manifest_paths:
        if not path.is_file():
            continue
        text, data = _document(path)
        local: list[dict[str, Any]] = []
        _manifest_checks(local, text, data, profile=profile, flow="scene-series", path_label=path.parent.name)
        issues.extend(str(check["id"]) for check in local if not check.get("passed"))
    add_check(checks, "manifest.scene_contracts", not issues, "scene-series manifests have valid structure" + (f" (issues: {','.join(issues[:8])})" if issues else ""))
    return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}), {}


def _slot_number(value: str | None, *, default: int) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else default


def _probe_duration(path: Path) -> float | None:
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        value = float(completed.stdout.strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def append_video_checks(
    checks: list[dict[str, Any]],
    *,
    video_path: Path,
    state: dict[str, str],
    run_dir: Path,
    duration_probe: DurationProbe,
) -> None:
    exists = video_path.is_file()
    add_check(checks, "video.file_exists", exists, f"{video_path.name} exists")
    if not exists:
        return
    render_status = str(state.get("runtime.render.status") or "").strip().lower()
    if render_status:
        add_check(checks, "video.render_status", render_status in {"success", "started", "completed"}, f"render status is a known terminal/in-progress value (got {render_status})")
    narration_list = run_dir / "video_narration_list.txt"
    if narration_list.is_file():
        missing = []
        for line in narration_list.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value:
                continue
            path = Path(value)
            candidate = path if path.is_absolute() else run_dir / path
            if not candidate.is_file():
                missing.append(value)
        add_check(checks, "video.narration_list", not missing, "all files in video_narration_list.txt exist" + (f" (missing: {','.join(missing[:8])})" if missing else ""))
    duration = duration_probe(video_path)
    if duration is not None:
        add_check(checks, "video.duration", duration > 0, f"video duration is positive ({duration:.2f}s)")
        _text, manifest = _document(run_dir / "video_manifest.md")
        raw_target = nested_get(manifest, ["video_metadata", "target_duration_seconds"])
        if raw_target is not None:
            try:
                target = normalize_target_duration(raw_target)
            except (TypeError, ValueError):
                target = None
            if target is not None:
                audit = audit_duration(target_seconds=target, actual_seconds=duration, measurement_layer="final_media_ffprobe")
                add_check(checks, "video.duration_fit", audit.passed, f"final video reaches the declared runtime floor ({duration:g}/{target}s)")


def check_video_single(run_dir: Path, *, target_slot: str = "p930", duration_probe: DurationProbe | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    state = parse_state_file(run_dir / "state.txt")
    append_video_checks(checks, video_path=run_dir / "video.mp4", state=state, run_dir=run_dir, duration_probe=duration_probe or _probe_duration)
    return make_stage("video", "video.mp4", checks), {}


def check_video_scene_series(run_dir: Path, *, target_slot: str = "p930", duration_probe: DurationProbe | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted(path for path in (run_dir / "scenes").glob("scene*") if path.is_dir())
    add_check(checks, "video.scene_dirs", bool(scene_dirs), f"scene-series has scene directories (got {len(scene_dirs)})")
    paths = [path / "video.mp4" for path in scene_dirs]
    add_check(checks, "video.scene_files", bool(paths) and all(path.is_file() for path in paths), "each scene has video.mp4")
    state = parse_state_file(run_dir / "state.txt")
    probe = duration_probe or _probe_duration
    for path in paths:
        if path.is_file():
            append_video_checks(checks, video_path=path, state=state, run_dir=path.parent, duration_probe=probe)
    return make_stage("video", "scenes/*/video.mp4", checks, details={"scene_count": len(scene_dirs)}), {}


__all__ = [
    "STORY_REQUIRED_SCENE_FIELDS",
    "_iter_manifest_nodes",
    "_iter_manifest_nodes_with_selectors",
    "_manifest_checks",
    "_minimum_cut_issues",
    "_probe_duration",
    "_script_text_quality_checks",
    "_slot_number",
    "append_video_checks",
    "check_manifest_scene_series",
    "check_manifest_single",
    "check_research",
    "check_script_scene_series",
    "check_script_single",
    "check_story",
    "check_video_scene_series",
    "check_video_single",
    "compact_research_pack_ok",
    "dense_story_scene_count",
    "make_stage",
    "story_scene_coverage_ok",
]
