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
    target_duration = _dict(story.get("story_metadata")).get("target_duration_seconds")
    if target_duration is None:
        target_duration = _dict(research.get("metadata")).get("target_duration_seconds")
    return {
        "id": "story:foundation",
        "stage": "story",
        "review_scope": "research_to_story_scene_allocation",
        "source_path": "story.md",
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
