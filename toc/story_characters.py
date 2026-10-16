"""Typed, story-neutral character index for canonical scene output."""

from collections.abc import Mapping
from typing import Any


SCENE_CHARACTER_BINDING_CONTRACT = "scene_character_binding_v1"


def collect_scene_character_ids(scene: Mapping[str, Any]) -> tuple[list[str], bool]:
    """Collect explicit references only; report malformed input without hiding it.

    The direct scene.character_ids index is deliberately not an input. It is
    derived from source references and lifecycle layers, including arrivals
    after the opening state. Names, prose and fixed protagonist IDs are never
    interpreted as references.
    """
    result: list[str] = []
    seen: set[str] = set()
    valid = True

    def add(values: Any, *, state_records: bool = False) -> None:
        nonlocal valid
        if not isinstance(values, list):
            valid = False
            return
        for value in values:
            if state_records and isinstance(value, Mapping):
                value = value.get("character_id")
            if not isinstance(value, str) or not value.strip():
                valid = False
                continue
            if value != value.strip():
                valid = False
            if value not in seen:
                seen.add(value)
                result.append(value)

    basis = scene.get("source_basis")
    if isinstance(basis, Mapping) and "character_ids" in basis:
        add(basis["character_ids"])
    start = scene.get("start_state")
    if isinstance(start, Mapping) and "characters" in start:
        add(start["characters"], state_records=True)
    beats = scene.get("event_sequence")
    if isinstance(beats, list):
        for beat in beats:
            if not isinstance(beat, Mapping):
                valid = False
                continue
            present = False
            for field in ("participants", "character_ids"):
                if field in beat:
                    present = True
                    add(beat[field])
            if not present:
                valid = False
    else:
        valid = False
    end = scene.get("end_state")
    if isinstance(end, Mapping) and "characters" in end:
        add(end["characters"], state_records=True)
    return result, valid
