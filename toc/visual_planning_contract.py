"""Source-bound visual planning; creative notes may be empty, source coverage may not."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

from scripts.world_walk_source import read_regular_file_nofollow
from toc.harness import extract_yaml_block

VISUAL_PLANNING_CONTRACT = "source_first_v2"
LEGACY_PLANNING_KEYS = {"adaptation_intent", "anchor_cut_candidates", "asset_bible_candidates"}


def planning_marker(data: Mapping[str, Any], metadata: str) -> str:
    value = data.get(metadata)
    return str(value.get("visual_planning_contract") or "") if isinstance(value, dict) else ""


def planning_declared(data: Mapping[str, Any], metadata: str) -> bool:
    value = data.get(metadata)
    return isinstance(value, dict) and "visual_planning_contract" in value


def story_scenes(story: Mapping[str, Any]) -> list[dict[str, Any]]:
    script = story.get("script")
    rows = script.get("scenes") if isinstance(script, dict) else None
    rows = rows if isinstance(rows, list) else story.get("scenes")
    return rows if isinstance(rows, list) else []


def decode_document(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8")
    try:
        text = extract_yaml_block(text)
    except ValueError:
        pass
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("structured document must be a mapping")
    return data


def source_binding(path: str, raw: bytes) -> dict[str, str]:
    return {"path": path, "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()}


def bind_visual_value(draft: dict[str, Any], sources: dict[str, bytes]) -> dict[str, Any]:
    doc = deepcopy(draft)
    metadata = doc.get("visual_value_metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("visual_value_metadata must be a mapping")
    marker = metadata.get("visual_planning_contract", VISUAL_PLANNING_CONTRACT)
    if marker != VISUAL_PLANNING_CONTRACT:
        raise ValueError("unsupported visual planning contract")
    doc["visual_value_metadata"] = {
        **metadata,
        "visual_planning_contract": VISUAL_PLANNING_CONTRACT,
        "source_bindings": {name: source_binding(f"{name}.md", sources[name]) for name in ("research", "story")},
    }
    return doc


def _strings(value: Any, *, empty: bool = True) -> bool:
    return isinstance(value, list) and (empty or bool(value)) and all(isinstance(x, str) and x.strip() for x in value)


def _pointer(root: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ValueError("invalid JSON pointer")
    value = root
    for part in pointer.split("/")[1:] if pointer else []:
        if re.search(r"~(?![01])", part):
            raise ValueError("invalid JSON pointer escape")
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise ValueError("invalid array index")
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError("pointer does not address a container")
    return value


def validate_visual_value_document(doc: Any, story: Mapping[str, Any], research: Mapping[str, Any] | None = None) -> list[str]:
    if not isinstance(doc, dict):
        return ["visual_value.document_invalid"]
    errors = []
    if planning_marker(doc, "visual_value_metadata") != VISUAL_PLANNING_CONTRACT:
        errors.append("visual_value.contract_invalid")
    metadata = doc.get("visual_value_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    if "adaptation_value_contract" in metadata or LEGACY_PLANNING_KEYS.intersection(doc):
        errors.append("visual_value.mixed_legacy_contract")
    bindings = metadata.get("source_bindings")
    for name in ("research", "story"):
        binding = bindings.get(name) if isinstance(bindings, dict) else None
        if not isinstance(binding, dict) or binding.get("path") != f"{name}.md" or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(binding.get("sha256", ""))):
            errors.append(f"visual_value.source_binding_invalid:{name}")
    expected = [str(s.get("scene_id", "")) if isinstance(s, dict) else "" for s in story_scenes(story)]
    if not expected or any(not sid for sid in expected) or len(set(expected)) != len(expected):
        errors.append("visual_value.story_scene_ids_invalid")
    rows = doc.get("scene_visual_values")
    actual = []
    if not isinstance(rows, list):
        errors.append("visual_value.scenes_invalid")
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("visual_value.scene_invalid")
            continue
        actual.append(str(row.get("scene_selector", "")))
        if not _strings(row.get("notes")):
            errors.append("visual_value.notes_invalid")
        if "scene_value_amplification" in row:
            errors.append("visual_value.mixed_legacy_contract")
        if metadata.get("b_roll_policy") is not None:
            from toc.b_roll import POLICY, validate_boundary
            try:
                if metadata['b_roll_policy'] != POLICY:
                    raise ValueError('b_roll.policy_invalid')
                source_scene = next(s for s in story_scenes(story) if str(s['scene_id']) == str(row.get('scene_selector')))
                validate_boundary(row.get('boundary_b_roll'), beat_ids=[b['beat_id'] for b in source_scene.get('event_sequence', [])])
            except (ValueError, KeyError, StopIteration, TypeError) as exc:
                errors.append(f'visual_value.b_roll_invalid:{exc}')
    if actual != expected:
        errors.append("visual_value.scene_coverage_or_order")
    if "global_visual_identity" in doc:
        global_notes = doc["global_visual_identity"]
        if not isinstance(global_notes, dict) or not _strings(global_notes.get("notes")):
            errors.append("visual_value.global_notes_invalid")
    continuity = doc.get("continuity_notes", [])
    if not isinstance(continuity, list):
        return [*errors, "visual_value.continuity_invalid"]
    for item in continuity:
        if not isinstance(item, dict):
            errors.append("visual_value.continuity_invalid")
            continue
        if not isinstance(item.get("note"), str) or not item["note"].strip():
            errors.append("visual_value.continuity_note_invalid")
        selectors = item.get("scene_selectors")
        if not _strings(selectors, empty=False) or any(s not in expected for s in selectors):
            errors.append("visual_value.continuity_scene_invalid")
        refs = item.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append("visual_value.continuity_source_missing")
            continue
        for ref in refs:
            try:
                source = {"story": story, "research": research}[ref["source"]]
                # In-memory projection checks may omit research; file validation never does.
                if source is not None:
                    _pointer(source, ref["pointer"])
            except (KeyError, IndexError, ValueError, TypeError):
                errors.append("visual_value.continuity_pointer_invalid")
    return errors


def validate_visual_value_files(run_dir: Path, doc: dict[str, Any] | None = None) -> list[str]:
    try:
        if doc is None:
            doc = decode_document(read_regular_file_nofollow(run_dir, "visual_value.md"))
        sources = {name: read_regular_file_nofollow(run_dir, f"{name}.md") for name in ("research", "story")}
        errors = validate_visual_value_document(doc, decode_document(sources["story"]), decode_document(sources["research"]))
        metadata = doc.get("visual_value_metadata", {})
        bindings = metadata.get("source_bindings", {}) if isinstance(metadata, dict) else {}
        for name, raw in sources.items():
            if not isinstance(bindings, dict) or bindings.get(name) != source_binding(f"{name}.md", raw):
                errors.append(f"visual_value.source_stale:{name}")
        return errors
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return [f"visual_value.source_read_invalid:{exc}"]


def validate_planning_projection(data: Mapping[str, Any], metadata_key: str, visual: Mapping[str, Any] | None = None) -> list[str]:
    errors = []
    if planning_marker(data, metadata_key) != VISUAL_PLANNING_CONTRACT:
        errors.append("visual_planning.contract_missing_or_unknown")
    metadata = data.get(metadata_key)
    binding = metadata.get("source_visual_value") if isinstance(metadata, dict) else None
    if not isinstance(binding, dict) or binding.get("path") != "visual_value.md" or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(binding.get("sha256", ""))):
        errors.append("visual_planning.binding_invalid")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return [*errors, "visual_planning.scenes_missing"]
    ids, runtime_ids = [], []
    notes = []
    for scene in scenes:
        if not isinstance(scene, dict):
            errors.append("visual_planning.scene_invalid")
            continue
        sid = scene.get("source_story_scene_id")
        if not isinstance(sid, str) or not sid:
            errors.append("visual_planning.source_scene_missing")
        ids.append(sid if isinstance(sid, str) else "")
        runtime_ids.append(str(scene.get("scene_id", "")))
        intent = scene.get("scene_intent")
        intent = intent if isinstance(intent, dict) else {}
        if "scene_value_amplification" in intent:
            errors.append("visual_planning.mixed_legacy_contract")
        if not _strings(intent.get("visual_notes")):
            errors.append("visual_planning.notes_invalid")
        notes.append(intent.get("visual_notes"))
        cuts = scene.get("cuts")
        if not isinstance(cuts, list) or not cuts:
            errors.append("visual_planning.cuts_missing")
            continue
        cut_ids = []
        for cut in cuts:
            if not isinstance(cut, dict):
                errors.append("visual_planning.cut_invalid")
                continue
            cut_ids.append(str(cut.get("selector") or cut.get("cut_id") or ""))
            contract = cut.get("cut_contract")
            if not isinstance(contract, dict) or contract.get("visual_planning_contract") != VISUAL_PLANNING_CONTRACT:
                errors.append("visual_planning.cut_version_mismatch")
            if isinstance(contract, dict) and "expressive_contract" in contract:
                errors.append("visual_planning.mixed_legacy_contract")
        if any(not cid for cid in cut_ids) or len(set(cut_ids)) != len(cut_ids):
            errors.append("visual_planning.cut_ids_invalid")
    if len(set(ids)) != len(ids) or any(not sid for sid in runtime_ids) or len(set(runtime_ids)) != len(runtime_ids):
        errors.append("visual_planning.scene_ids_invalid")
    if visual is not None:
        if planning_marker(visual, "visual_value_metadata") != VISUAL_PLANNING_CONTRACT:
            errors.append("visual_planning.source_version_mismatch")
        rows = visual.get("scene_visual_values", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            errors.append("visual_planning.source_scenes_invalid")
        elif ids != [str(row.get("scene_selector", "")) for row in rows] or notes != [row.get("notes") for row in rows]:
            errors.append("visual_planning.source_projection_mismatch")
    return errors


def validate_planning_source_files(run_dir: Path, data: Mapping[str, Any], metadata_key: str) -> list[str]:
    try:
        raw = read_regular_file_nofollow(run_dir, "visual_value.md")
        visual = decode_document(raw)
        errors = validate_visual_value_files(run_dir, visual)
        errors.extend(validate_planning_projection(data, metadata_key, visual))
        metadata = data.get(metadata_key)
        if not isinstance(metadata, dict) or metadata.get("source_visual_value") != source_binding("visual_value.md", raw):
            errors.append("visual_planning.source_stale")
        return errors
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return [f"visual_planning.source_read_invalid:{exc}"]
