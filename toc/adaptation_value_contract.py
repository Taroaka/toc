"""Deterministic contracts for preserving and amplifying an existing story's value.

The authored artifacts remain Markdown/YAML dictionaries.  This module owns only
stable key names, local shape checks, enums, and source-value reference integrity;
whether an adaptation is moving or cinematically effective remains semantic review.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


from toc.visual_planning_contract import (
    planning_declared,
    planning_marker,
    validate_planning_projection,
    validate_visual_value_document,
)


ADAPTATION_VALUE_MARKER = "required_v1"
ADAPTATION_SOURCE_SCHEMA = "adaptation_source_contract_v1"
ADAPTATION_INTENT_SCHEMA = "adaptation_intent_v1"
SCENE_AMPLIFICATION_SCHEMA = "scene_value_amplification_v1"
CUT_EXPRESSIVE_SCHEMA = "cut_expressive_contract_v1"

EXPRESSIVE_FUNCTIONS = frozenset(
    {
        "recognition",
        "withhold",
        "pressure",
        "release",
        "contrast",
        "reaction",
        "reframe",
        "afterimage",
        "spectacle",
        "transition",
    }
)

SOURCE_REQUIRED_STRINGS = ("schema_version", "mode", "source_story_promise")
SOURCE_REQUIRED_LISTS = (
    "non_negotiable_events",
    "non_negotiable_meanings",
    "iconic_moments",
    "forbidden_value_distortions",
)
CORE_VALUE_REQUIRED_STRINGS = ("value_id", "statement", "audience_effect")
INTENT_REQUIRED_STRINGS = ("schema_version", "effect_fidelity_goal", "adaptation_angle")
INTENT_REQUIRED_LISTS = (
    "source_value_ids",
    "visual_principles",
    "performance_principles",
    "sound_principles",
    "editorial_principles",
    "forbidden_generic_treatments",
)
SCENE_REQUIRED_STRINGS = (
    "schema_version",
    "why_this_scene_matters",
    "audience_state_before",
    "audience_state_after",
    "emotional_contradiction",
    "iconic_moment_target",
)
SCENE_REQUIRED_LISTS = (
    "source_value_refs",
    "must_preserve_story_facts",
    "must_not_reduce_to",
    "success_evidence",
)
SCENE_CINEMATIC_GAIN_KEYS = (
    "performance",
    "blocking_and_space",
    "camera_and_composition",
    "edit_and_rhythm",
    "sound",
)
CUT_REQUIRED_STRINGS = (
    "schema_version",
    "scene_amplification_ref",
    "audience_experience_delta",
    "expressive_function",
    "performance_beat",
    "visual_pressure",
    "attention_shift",
    "edit_trigger",
    "sound_function",
    "emotional_afterimage",
)
CUT_REQUIRED_LISTS = ("source_value_refs", "must_not_reduce_to")


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _marker(data: Mapping[str, Any], metadata_key: str) -> str:
    return _text(_dict(data.get(metadata_key)).get("adaptation_value_contract"))


def _marker_issues(data: Mapping[str, Any], metadata_key: str) -> tuple[bool, list[str]]:
    metadata = _dict(data.get(metadata_key))
    if "adaptation_value_contract" not in metadata:
        return False, []
    marker = _text(metadata.get("adaptation_value_contract"))
    if marker != ADAPTATION_VALUE_MARKER:
        return False, [f"{metadata_key}.adaptation_value_contract:{ADAPTATION_VALUE_MARKER}"]
    return True, []


def _required_string_issues(block: Mapping[str, Any], keys: Iterable[str], prefix: str) -> list[str]:
    return [
        f"{prefix}.{key}:missing_or_non_string"
        for key in keys
        if not isinstance(block.get(key), str) or not block[key].strip()
    ]


def _non_empty_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    if not all(isinstance(item, str) for item in value):
        return []
    items = [_text(item) for item in value]
    return items if items and all(items) else []


def _required_list_issues(block: Mapping[str, Any], keys: Iterable[str], prefix: str) -> list[str]:
    return [
        f"{prefix}.{key}:missing_or_non_string"
        for key in keys
        if not _non_empty_string_list(block.get(key))
    ]


def _reference_issues(
    refs: Any,
    *,
    source_value_ids: set[str] | None,
    prefix: str,
) -> list[str]:
    if source_value_ids is None:
        return []
    return [
        f"{prefix}:unknown:{ref}"
        for ref in _non_empty_string_list(refs)
        if ref and ref not in source_value_ids
    ]


def source_value_ids(story: Mapping[str, Any]) -> set[str]:
    """Return declared value IDs from an adaptation-aware story artifact."""
    contract = _dict(story.get("adaptation_source_contract"))
    return {
        value_id
        for value in _list(contract.get("core_values"))
        if (value_id := _text(_dict(value).get("value_id")))
    }


def story_adaptation_issues(data: Mapping[str, Any]) -> list[str]:
    enabled, issues = _marker_issues(data, "story_metadata")
    if not enabled:
        return issues
    contract = _dict(data.get("adaptation_source_contract"))
    if not contract:
        return [*issues, "adaptation_source_contract:missing"]
    prefix = "adaptation_source_contract"
    issues.extend(_required_string_issues(contract, SOURCE_REQUIRED_STRINGS, prefix))
    issues.extend(_required_list_issues(contract, SOURCE_REQUIRED_LISTS, prefix))
    if not _list(contract.get("core_values")):
        issues.append(f"{prefix}.core_values:missing")
    if _text(contract.get("schema_version")) != ADAPTATION_SOURCE_SCHEMA:
        issues.append(f"{prefix}.schema_version:{ADAPTATION_SOURCE_SCHEMA}")
    if _text(contract.get("mode")) != "existing_story":
        issues.append(f"{prefix}.mode:existing_story")

    seen: set[str] = set()
    for index, raw_value in enumerate(_list(contract.get("core_values"))):
        value = _dict(raw_value)
        value_prefix = f"{prefix}.core_values[{index}]"
        if not value:
            issues.append(f"{value_prefix}:mapping")
            continue
        issues.extend(_required_string_issues(value, CORE_VALUE_REQUIRED_STRINGS, value_prefix))
        if not _non_empty_string_list(value.get("source_event_refs")):
            issues.append(f"{value_prefix}.source_event_refs:missing_or_non_string")
        value_id = _text(value.get("value_id"))
        if value_id in seen:
            issues.append(f"{value_prefix}.value_id:duplicate:{value_id}")
        elif value_id:
            seen.add(value_id)
    return issues


def _scene_amplification_issues(
    block: Any,
    *,
    source_value_ids: set[str] | None,
    prefix: str,
) -> list[str]:
    amplification = _dict(block)
    if not amplification:
        return [f"{prefix}:missing"]
    issues = _required_string_issues(amplification, SCENE_REQUIRED_STRINGS, prefix)
    issues.extend(_required_list_issues(amplification, SCENE_REQUIRED_LISTS, prefix))
    if _text(amplification.get("schema_version")) != SCENE_AMPLIFICATION_SCHEMA:
        issues.append(f"{prefix}.schema_version:{SCENE_AMPLIFICATION_SCHEMA}")
    gain = _dict(amplification.get("cinematic_gain"))
    if not gain:
        issues.append(f"{prefix}.cinematic_gain:missing")
    else:
        issues.extend(_required_string_issues(gain, SCENE_CINEMATIC_GAIN_KEYS, f"{prefix}.cinematic_gain"))
    issues.extend(
        _reference_issues(
            amplification.get("source_value_refs"),
            source_value_ids=source_value_ids,
            prefix=f"{prefix}.source_value_refs",
        )
    )
    return issues


def visual_value_adaptation_issues(
    data: Mapping[str, Any],
    *,
    source_value_ids: set[str] | None = None,
    story: Mapping[str, Any] | None = None,
    research: Mapping[str, Any] | None = None,
) -> list[str]:
    if planning_declared(data, "visual_value_metadata"):
        if story is None:
            return ["visual_value.source_story_required"]
        return validate_visual_value_document(data, story, research)
    enabled, issues = _marker_issues(data, "visual_value_metadata")
    if not enabled:
        return issues
    intent = _dict(data.get("adaptation_intent"))
    if not intent:
        issues.append("adaptation_intent:missing")
        intent_value_ids: set[str] = set()
    else:
        issues.extend(_required_string_issues(intent, INTENT_REQUIRED_STRINGS, "adaptation_intent"))
        issues.extend(_required_list_issues(intent, INTENT_REQUIRED_LISTS, "adaptation_intent"))
        if _text(intent.get("schema_version")) != ADAPTATION_INTENT_SCHEMA:
            issues.append(f"adaptation_intent.schema_version:{ADAPTATION_INTENT_SCHEMA}")
        issues.extend(
            _reference_issues(
                intent.get("source_value_ids"),
                source_value_ids=source_value_ids,
                prefix="adaptation_intent.source_value_ids",
            )
        )
        intent_value_ids = set(_non_empty_string_list(intent.get("source_value_ids")))
    scene_values = _list(data.get("scene_visual_values"))
    if not scene_values:
        issues.append("scene_visual_values:missing")
    for index, raw_scene in enumerate(scene_values):
        scene = _dict(raw_scene)
        prefix = f"scene_visual_values[{index}].scene_value_amplification"
        issues.extend(
            _scene_amplification_issues(
                scene.get("scene_value_amplification"),
                source_value_ids=source_value_ids,
                prefix=prefix,
            )
        )
        amplification = _dict(scene.get("scene_value_amplification"))
        for value_ref in _non_empty_string_list(amplification.get("source_value_refs")):
            if value_ref not in intent_value_ids:
                issues.append(f"{prefix}.source_value_refs:not_in_intent:{value_ref}")
    return issues


def _scene_cuts(scene: Mapping[str, Any]) -> list[Any]:
    cuts = scene.get("cuts")
    if isinstance(cuts, list):
        return cuts
    return _list(_dict(scene.get("script")).get("cuts"))


def _expressive_issues(
    block: Any,
    *,
    source_value_ids: set[str] | None,
    scene_value_refs: set[str],
    expected_scene_ref: str,
    prefix: str,
) -> list[str]:
    expressive = _dict(block)
    if not expressive:
        return [f"{prefix}:missing"]
    issues = _required_string_issues(expressive, CUT_REQUIRED_STRINGS, prefix)
    issues.extend(_required_list_issues(expressive, CUT_REQUIRED_LISTS, prefix))
    if _text(expressive.get("schema_version")) != CUT_EXPRESSIVE_SCHEMA:
        issues.append(f"{prefix}.schema_version:{CUT_EXPRESSIVE_SCHEMA}")
    if _text(expressive.get("expressive_function")) not in EXPRESSIVE_FUNCTIONS:
        issues.append(f"{prefix}.expressive_function:enum")
    issues.extend(
        _reference_issues(
            expressive.get("source_value_refs"),
            source_value_ids=source_value_ids,
            prefix=f"{prefix}.source_value_refs",
        )
    )
    actual_scene_ref = _text(expressive.get("scene_amplification_ref"))
    if actual_scene_ref and actual_scene_ref != expected_scene_ref:
        issues.append(f"{prefix}.scene_amplification_ref:mismatch:{expected_scene_ref}")
    for value_ref in _non_empty_string_list(expressive.get("source_value_refs")):
        if value_ref not in scene_value_refs:
            issues.append(f"{prefix}.source_value_refs:not_in_scene:{value_ref}")
    return issues


def _scenes_adaptation_issues(
    data: Mapping[str, Any],
    *,
    source_value_ids: set[str] | None,
) -> list[str]:
    issues: list[str] = []
    scenes = _list(data.get("scenes")) or _list(_dict(data.get("script")).get("scenes"))
    if not scenes:
        return [*issues, "scenes:missing"]
    seen_scene_ids: set[str] = set()
    for scene_index, raw_scene in enumerate(scenes):
        scene = _dict(raw_scene)
        scene_id = _text(scene.get("scene_id")) or str(scene_index + 1)
        scene_prefix = f"scenes[{scene_id}]"
        if scene_id in seen_scene_ids:
            issues.append(f"scene_id:duplicate:{scene_id}")
        seen_scene_ids.add(scene_id)
        intent = _dict(scene.get("scene_intent"))
        amplification = _dict(intent.get("scene_value_amplification"))
        issues.extend(
            _scene_amplification_issues(
                amplification,
                source_value_ids=source_value_ids,
                prefix=f"{scene_prefix}.scene_intent.scene_value_amplification",
            )
        )
        scene_value_refs = set(_non_empty_string_list(amplification.get("source_value_refs")))
        expected_scene_ref = f"scene{scene_id}.scene_intent.scene_value_amplification"
        cuts = _scene_cuts(scene)
        if not cuts:
            issues.append(f"{scene_prefix}.cuts:missing")
        seen_cut_ids: set[str] = set()
        for cut_index, raw_cut in enumerate(cuts):
            cut = _dict(raw_cut)
            cut_id = _text(cut.get("cut_id")) or str(cut_index + 1)
            if cut_id in seen_cut_ids:
                issues.append(f"{scene_prefix}.cut_id:duplicate:{cut_id}")
            seen_cut_ids.add(cut_id)
            prefix = f"{scene_prefix}.cuts[{cut_id}].cut_contract.expressive_contract"
            issues.extend(
                _expressive_issues(
                    _dict(cut.get("cut_contract")).get("expressive_contract"),
                    source_value_ids=source_value_ids,
                    scene_value_refs=scene_value_refs,
                    expected_scene_ref=expected_scene_ref,
                    prefix=prefix,
                )
            )
    return issues


def script_adaptation_issues(
    data: Mapping[str, Any],
    *,
    source_value_ids: set[str] | None = None,
    visual_value: Mapping[str, Any] | None = None,
) -> list[str]:
    if planning_declared(data, "script_metadata") or (visual_value is not None and planning_declared(visual_value, "visual_value_metadata")):
        issues = validate_planning_projection(data, "script_metadata", visual_value)
        if visual_value is None:
            issues.append("visual_value:missing_for_source_first_projection")
        if _marker(data, "script_metadata") != ADAPTATION_VALUE_MARKER:
            issues.append("script_metadata.adaptation_value_contract:missing_projection")
        return issues
    enabled, issues = _marker_issues(data, "script_metadata")
    if not enabled:
        return issues
    issues.extend(_scenes_adaptation_issues(data, source_value_ids=source_value_ids))
    if visual_value is not None:
        issues.extend(_visual_projection_issues(data, visual_value))
    return issues


def _selector_key(value: Any) -> str:
    text = _text(value).lower()
    if text.startswith("scene"):
        text = text[5:]
    parts = text.split(".")
    if parts and all(part.isdigit() for part in parts):
        return ".".join(str(int(part)) for part in parts)
    return text


def _visual_projection_issues(script: Mapping[str, Any], visual_value: Mapping[str, Any]) -> list[str]:
    metadata = _dict(visual_value.get("visual_value_metadata"))
    if metadata.get("adaptation_value_contract") != ADAPTATION_VALUE_MARKER:
        return ["visual_value_metadata.adaptation_value_contract:missing_projection_source"]
    issues: list[str] = []
    visual_scenes: dict[str, dict[str, Any]] = {}
    for raw_scene in _list(visual_value.get("scene_visual_values")):
        scene = _dict(raw_scene)
        key = _selector_key(scene.get("scene_selector") or scene.get("scene_id"))
        if not scene or not key:
            continue
        if key in visual_scenes:
            issues.append(f"scene_visual_values[{key}]:duplicate_selector")
        visual_scenes[key] = scene

    raw_script_scenes = _list(script.get("scenes")) or _list(_dict(script.get("script")).get("scenes"))
    script_scene_ids = [
        _text(scene.get("scene_id")) or str(index + 1)
        for index, item in enumerate(raw_script_scenes)
        if (scene := _dict(item))
    ]
    seen_script_ids: set[str] = set()
    for scene_id in script_scene_ids:
        key = _selector_key(scene_id)
        if key in seen_script_ids:
            issues.append(f"scenes[{scene_id}]:duplicate_projection_source")
        seen_script_ids.add(key)

    script_scenes = _scene_map(script)
    expected_keys = {_selector_key(scene_id) for scene_id in script_scenes}
    for key in sorted(set(visual_scenes) - expected_keys):
        issues.append(f"scene_visual_values[{key}]:unexpected_projection")
    for scene_id, script_scene in script_scenes.items():
        visual_scene = visual_scenes.get(_selector_key(scene_id))
        if visual_scene is None:
            issues.append(f"scenes[{scene_id}].scene_value_amplification:visual_projection_missing")
            continue
        script_block = _dict(_dict(script_scene.get("scene_intent")).get("scene_value_amplification"))
        visual_block = _dict(visual_scene.get("scene_value_amplification"))
        if script_block != visual_block:
            issues.append(f"scenes[{scene_id}].scene_value_amplification:visual_projection_mismatch")
    return issues


def _scene_map(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    scenes = _list(data.get("scenes")) or _list(_dict(data.get("script")).get("scenes"))
    return {
        scene_id: scene
        for index, raw_scene in enumerate(scenes)
        if (scene := _dict(raw_scene))
        and (scene_id := _text(scene.get("scene_id")) or str(index + 1))
    }


def _cut_map(scene: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw_cut in enumerate(_scene_cuts(scene)):
        cut = _dict(raw_cut)
        if not cut:
            continue
        key = _text(cut.get("selector")) or _text(cut.get("cut_id")) or str(index + 1)
        result[key] = cut
    return result


def _projection_issues(manifest: Mapping[str, Any], script: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    raw_manifest_scenes = [scene for item in _list(manifest.get("scenes")) if (scene := _dict(item))]
    manifest_scene_ids = [
        _text(scene.get("scene_id")) or str(index + 1)
        for index, scene in enumerate(raw_manifest_scenes)
    ]
    seen_scene_ids: set[str] = set()
    for scene_id in manifest_scene_ids:
        if scene_id in seen_scene_ids:
            issues.append(f"scene_id:duplicate:{scene_id}")
        seen_scene_ids.add(scene_id)
    manifest_scenes = _scene_map(manifest)
    raw_script_scenes = [scene for item in _list(script.get("scenes")) if (scene := _dict(item))]
    if not raw_script_scenes:
        raw_script_scenes = [
            scene
            for item in _list(_dict(script.get("script")).get("scenes"))
            if (scene := _dict(item))
        ]
    script_scene_ids = [
        _text(scene.get("scene_id")) or str(index + 1)
        for index, scene in enumerate(raw_script_scenes)
    ]
    seen_script_scene_ids: set[str] = set()
    for scene_id in script_scene_ids:
        if scene_id in seen_script_scene_ids:
            issues.append(f"script.scene_id:duplicate:{scene_id}")
        seen_script_scene_ids.add(scene_id)
    script_scenes = _scene_map(script)
    for scene_id in sorted(set(manifest_scenes) - set(script_scenes)):
        issues.append(f"scenes[{scene_id}]:unexpected_projection")
    for scene_id, script_scene in script_scenes.items():
        manifest_scene = manifest_scenes.get(scene_id)
        if manifest_scene is None:
            issues.append(f"scenes[{scene_id}]:projection_missing")
            continue
        script_amplification = _dict(_dict(script_scene.get("scene_intent")).get("scene_value_amplification"))
        manifest_amplification = _dict(_dict(manifest_scene.get("scene_intent")).get("scene_value_amplification"))
        if manifest_amplification != script_amplification:
            issues.append(f"scenes[{scene_id}].scene_value_amplification:projection_mismatch")

        raw_manifest_cuts = [cut for item in _scene_cuts(manifest_scene) if (cut := _dict(item))]
        manifest_cut_keys = [
            _text(cut.get("selector")) or _text(cut.get("cut_id")) or str(index + 1)
            for index, cut in enumerate(raw_manifest_cuts)
        ]
        seen_cut_keys: set[str] = set()
        for cut_key in manifest_cut_keys:
            if cut_key in seen_cut_keys:
                issues.append(f"scenes[{scene_id}].cut_key:duplicate:{cut_key}")
            seen_cut_keys.add(cut_key)
        manifest_cuts = _cut_map(manifest_scene)
        raw_script_cuts = [cut for item in _scene_cuts(script_scene) if (cut := _dict(item))]
        script_cut_keys = [
            _text(cut.get("selector")) or _text(cut.get("cut_id")) or str(index + 1)
            for index, cut in enumerate(raw_script_cuts)
        ]
        seen_script_cut_keys: set[str] = set()
        for cut_key in script_cut_keys:
            if cut_key in seen_script_cut_keys:
                issues.append(f"script.scenes[{scene_id}].cut_key:duplicate:{cut_key}")
            seen_script_cut_keys.add(cut_key)
        script_cuts = _cut_map(script_scene)
        for cut_key in sorted(set(manifest_cuts) - set(script_cuts)):
            issues.append(f"scenes[{scene_id}].cuts[{cut_key}]:unexpected_projection")
        for cut_key, script_cut in script_cuts.items():
            manifest_cut = manifest_cuts.get(cut_key)
            if manifest_cut is None:
                issues.append(f"scenes[{scene_id}].cuts[{cut_key}]:projection_missing")
                continue
            script_expressive = _dict(_dict(script_cut.get("cut_contract")).get("expressive_contract"))
            manifest_expressive = _dict(_dict(manifest_cut.get("cut_contract")).get("expressive_contract"))
            if manifest_expressive != script_expressive:
                issues.append(
                    f"scenes[{scene_id}].cuts[{cut_key}].expressive_contract:projection_mismatch"
                )
    return issues


def manifest_adaptation_issues(
    data: Mapping[str, Any],
    *,
    source_value_ids: set[str] | None = None,
    script: Mapping[str, Any] | None = None,
) -> list[str]:
    if planning_declared(data, "video_metadata") or (script is not None and planning_declared(script, "script_metadata")):
        issues = validate_planning_projection(data, "video_metadata")
        if _marker(data, "video_metadata") != ADAPTATION_VALUE_MARKER:
            issues.append("video_metadata.adaptation_value_contract:missing_projection")
        if not script:
            return [*issues, "script:missing_for_source_first_projection"]
        issues.extend(validate_planning_projection(script, "script_metadata"))
        if planning_marker(data, "video_metadata") != planning_marker(script, "script_metadata"):
            issues.append("visual_planning.version_mismatch")
        if _dict(data.get("video_metadata")).get("source_visual_value") != _dict(script.get("script_metadata")).get("source_visual_value"):
            issues.append("visual_planning.binding_mismatch")
        script_scenes = _list(script.get("scenes"))
        manifest_scenes = _list(data.get("scenes"))
        projection = lambda scenes: [(s.get("scene_id"), s.get("source_story_scene_id"), _dict(s.get("scene_intent")).get("visual_notes")) for s in scenes if isinstance(s, dict)]
        if projection(script_scenes) != projection(manifest_scenes):
            issues.append("visual_planning.scene_projection_mismatch")
        issues.extend(_projection_issues(data, script))
        return issues
    script_requires_contract = bool(script) and _marker(script or {}, "script_metadata") == ADAPTATION_VALUE_MARKER
    metadata = _dict(data.get("video_metadata"))
    marker_present = "adaptation_value_contract" in metadata
    enabled, issues = _marker_issues(data, "video_metadata")
    if script_requires_contract and not marker_present:
        issues.append("video_metadata.adaptation_value_contract:missing_projection")
    if not enabled:
        return issues
    if not script:
        issues.append("script:missing_for_adaptation_projection")
    elif not script_requires_contract:
        issues.append("script_metadata.adaptation_value_contract:missing_projection_source")
    issues.extend(_scenes_adaptation_issues(data, source_value_ids=source_value_ids))
    if script:
        issues.extend(_projection_issues(data, script))
    return issues
