"""Research/story foundation collectors for pre-cut semantic review."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document


SUPPORTED_STAGES = {"research", "story"}
_RESEARCH_REF_RE = re.compile(r"research\.(?P<section>[A-Za-z0-9_.]+)\[(?P<entry_id>[^\]]+)\]")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_structured_document(path)[1]
    if not data:
        raise ValueError(f"{path.name} must contain a valid structured YAML document")
    return data


def _research_core(data: dict[str, Any]) -> dict[str, Any]:
    materials = _dict(data.get("story_materials"))
    legacy_baseline = _dict(data.get("story_baseline"))
    legacy_synopsis = _dict(legacy_baseline.get("canonical_synopsis"))
    chronological_events = [item for item in _list(materials.get("chronological_events")) if isinstance(item, dict)]
    if not chronological_events:
        chronological_events = [item for item in _list(legacy_synopsis.get("beat_sheet")) if isinstance(item, dict)]
    return {
        "canonical_story_dump": materials.get("canonical_story_dump")
        or legacy_synopsis.get("short_summary")
        or legacy_synopsis.get("one_liner"),
        "chronological_events": chronological_events,
        "characters": [item for item in _list(materials.get("characters")) if isinstance(item, dict)],
        "setting": materials.get("setting"),
        "symbols_and_themes": materials.get("symbols_and_themes"),
        "emotional_material": materials.get("emotional_material"),
        "conflicts": [item for item in _list(data.get("conflicts")) if isinstance(item, dict)],
        "handoff_to_story": data.get("handoff_to_story"),
        "evaluation_contract": data.get("evaluation_contract"),
        "target_duration_seconds": _dict(data.get("metadata")).get("target_duration_seconds"),
    }


def _known_research_ids(research: dict[str, Any]) -> dict[str, set[str]]:
    materials = _dict(research.get("story_materials"))
    return {
        "story_materials.chronological_events": {
            _text(item.get("event_id"))
            for item in _list(materials.get("chronological_events"))
            if isinstance(item, dict) and _text(item.get("event_id"))
        },
        "source_passages": {
            _text(item.get("passage_id"))
            for item in _list(research.get("source_passages"))
            if isinstance(item, dict) and _text(item.get("passage_id"))
        },
        "conflicts": {
            _text(item.get("conflict_id"))
            for item in _list(research.get("conflicts"))
            if isinstance(item, dict) and _text(item.get("conflict_id"))
        },
    }


def _story_reference_diagnostics(research: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any]:
    known = _known_research_ids(research)
    unresolved: list[dict[str, str]] = []
    allocation: dict[str, list[str]] = {event_id: [] for event_id in sorted(known["story_materials.chronological_events"])}
    for index, scene in enumerate(scenes, start=1):
        scene_id = _text(scene.get("scene_id")) or str(index)
        for raw_ref in _list(scene.get("research_refs")):
            ref = _text(raw_ref)
            match = _RESEARCH_REF_RE.fullmatch(ref)
            if not match:
                unresolved.append({"scene_id": scene_id, "ref": ref, "reason": "unparseable_internal_reference"})
                continue
            section = match.group("section")
            entry_id = match.group("entry_id")
            known_ids = known.get(section)
            if known_ids is None or entry_id not in known_ids:
                unresolved.append({"scene_id": scene_id, "ref": ref, "reason": "missing_internal_target"})
                continue
            if section == "story_materials.chronological_events":
                allocation.setdefault(entry_id, []).append(scene_id)
    return {
        "unresolved_refs": unresolved,
        "event_to_scene_ids": allocation,
        "unassigned_event_ids": [event_id for event_id, scene_ids in allocation.items() if not scene_ids],
    }


_REQUIRED_LOCATION_SEGMENT_TEXT_FIELDS = (
    "responsibility",
    "primary_subject",
    "visible_action",
    "motion_brief",
    "motion_end_state",
)
_REQUIRED_LOCATION_SEGMENT_LIST_FIELDS = (
    "required_visual_evidence",
    "required_roles",
)


def _scene_location_route_status(scene: dict[str, Any], index: int) -> dict[str, Any]:
    """Summarize whether an authored multi-location route is cut-design ready.

    Missing legacy location data stays distinguishable from a malformed declared
    route. Once `location.mode: sequence` (or a multi-item sequence) is authored,
    every location must have one ordered, drawable segment; downstream review
    must not infer the missing transition from scene prose.
    """

    result: dict[str, Any] = {"scene_id": scene.get("scene_id", index)}
    if "location" not in scene:
        result["status"] = "undeclared"
        return result
    raw_location = scene.get("location")
    if not isinstance(raw_location, dict):
        result.update({"status": "invalid", "errors": ["location_invalid_type"]})
        return result

    mode = _text(raw_location.get("mode"))
    raw_sequence = raw_location.get("sequence")
    sequence = [_text(value) for value in _list(raw_sequence)]
    raw_segments = raw_location.get("segments")
    segments = [item for item in _list(raw_segments) if isinstance(item, dict)]
    segment_locations = [_text(item.get("location")) for item in segments]
    result.update(
        {
            "mode": mode,
            "sequence": sequence,
            "segment_locations": segment_locations,
        }
    )

    sequence_route_declared = mode == "sequence" or len(sequence) > 1
    if not sequence_route_declared:
        errors: list[str] = []
        if mode not in {"", "single"}:
            errors.append("location_mode_invalid")
        if raw_sequence is not None and not isinstance(raw_sequence, list):
            errors.append("location_sequence_invalid_type")
        if any(not value for value in sequence):
            errors.append("location_sequence_blank")
        result["status"] = "invalid" if errors else "valid_single"
        if errors:
            result["errors"] = errors
        return result

    errors = []
    if mode != "sequence":
        errors.append("location_mode_must_be_sequence")
    if not isinstance(raw_sequence, list):
        errors.append("location_sequence_invalid_type")
    if not sequence or any(not value for value in sequence):
        errors.append("location_sequence_missing_or_blank")
    if len(set(sequence)) != len(sequence):
        errors.append("location_sequence_duplicate")
    if not isinstance(raw_segments, list):
        errors.append("location_segments_invalid_type")
    if len(segments) != len(_list(raw_segments)):
        errors.append("location_segment_invalid_type")

    missing_locations = [value for value in sequence if value not in segment_locations]
    extra_locations = [value for value in segment_locations if value not in sequence]
    duplicate_locations = sorted(
        {value for value in segment_locations if value and segment_locations.count(value) > 1}
    )
    if missing_locations:
        errors.append("location_segments_missing_locations")
    if extra_locations:
        errors.append("location_segments_extra_locations")
    if duplicate_locations:
        errors.append("location_segments_duplicate_locations")
    if segment_locations != sequence:
        errors.append("location_segments_order_mismatch")

    malformed_segments: list[dict[str, Any]] = []
    for segment_index, segment in enumerate(segments, start=1):
        missing_fields = [
            field
            for field in _REQUIRED_LOCATION_SEGMENT_TEXT_FIELDS
            if not _text(segment.get(field))
        ]
        missing_fields.extend(
            field
            for field in _REQUIRED_LOCATION_SEGMENT_LIST_FIELDS
            if not [value for value in _list(segment.get(field)) if _text(value)]
        )
        if missing_fields:
            malformed_segments.append(
                {
                    "segment_index": segment_index,
                    "location": _text(segment.get("location")),
                    "missing_fields": missing_fields,
                }
            )
    if malformed_segments:
        errors.append("location_segment_drawable_contract_missing")

    result.update(
        {
            "status": "invalid" if errors else "valid",
            "missing_segment_locations": missing_locations,
            "extra_segment_locations": extra_locations,
            "duplicate_segment_locations": duplicate_locations,
            "segment_order_matches_sequence": segment_locations == sequence,
            "malformed_segments": malformed_segments,
        }
    )
    if errors:
        result["errors"] = errors
    return result


def _research_entry(run_dir: Path) -> dict[str, Any]:
    data = _load(run_dir / "research.md")
    return {
        "id": "research:foundation",
        "stage": "research",
        "review_scope": "internal_story_foundation",
        "source_path": "research.md",
        **_research_core(data),
    }


def _story_entry(run_dir: Path) -> dict[str, Any]:
    research = _load(run_dir / "research.md")
    story = _load(run_dir / "story.md")
    scenes = [item for item in _list(_dict(story.get("script")).get("scenes")) if isinstance(item, dict)]
    story_metadata = _dict(story.get("story_metadata"))
    target_duration = story_metadata.get("target_duration_seconds")
    if target_duration is None:
        target_duration = _dict(research.get("metadata")).get("target_duration_seconds")
    time_of_day_contract_declared = (
        str(story_metadata.get("scene_time_of_day_contract") or "").strip() == "required_v1"
    )
    scene_time_of_day_statuses: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        raw_time_of_day = scene.get("time_of_day")
        if "time_of_day" not in scene:
            status = "missing"
        elif not isinstance(raw_time_of_day, str):
            status = "invalid_type"
        elif not raw_time_of_day.strip():
            status = "blank"
        else:
            status = "valid"
        item: dict[str, Any] = {
            "scene_id": scene.get("scene_id", index),
            "status": status,
        }
        if status == "valid":
            item["time_of_day"] = raw_time_of_day.strip()
        elif status == "invalid_type":
            item["raw_value"] = raw_time_of_day
        scene_time_of_day_statuses.append(item)
    scene_location_route_statuses = [
        _scene_location_route_status(scene, index)
        for index, scene in enumerate(scenes, start=1)
    ]
    return {
        "id": "story:foundation",
        "stage": "story",
        "review_scope": "research_to_story_scene_allocation",
        "source_path": "story.md",
        "story_time": story_metadata.get("time"),
        "time_of_day_contract_declared": time_of_day_contract_declared,
        "scene_time_of_day_statuses": scene_time_of_day_statuses,
        "scene_location_route_statuses": scene_location_route_statuses,
        "target_duration_seconds": target_duration,
        "research_baseline": _research_core(research),
        "selection": story.get("selection"),
        "story_structure": story.get("story_structure"),
        "story_decomposition": story.get("story_decomposition"),
        "scenes": scenes,
        "internal_reference_diagnostics": _story_reference_diagnostics(research, scenes),
    }


def collect_entries(
    stage: str,
    run_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    del manifest
    if stage not in SUPPORTED_STAGES:
        raise ValueError(f"Unsupported foundation semantic stage: {stage}")
    return [_research_entry(run_dir)] if stage == "research" else [_story_entry(run_dir)]
