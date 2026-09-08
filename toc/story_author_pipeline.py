"""LLM-backed orchestration for producing a grounded ``story.md`` document.

The authoring functions in :mod:`toc.story_authoring` intentionally stop at
the boundary between deterministic plumbing and prose.  This module owns the
small orchestration layer around that boundary:

* build one lossless research registry and one replayable architect prompt;
* ask an injected Story Architect for semantic scene ownership;
* ask one Scene Author turn for every frozen scene in architect order;
* assemble the scene responses while injecting request metadata locally; and
* publish a result only when the deterministic story validator passes.

No fallback prose is generated here.  An injected runner is required so the
same pipeline can be used by the real Codex adapter and by deterministic tests
without coupling this module to a transport implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import os
from pathlib import Path
import tempfile
from typing import Any, TypeAlias

from .story_authoring import (
    AUDIENCE_MEANING_INSTRUCTION,
    STORY_CONTRACT_VERSION,
    SCENE_CAUSAL_CONNECTION_INSTRUCTION,
    build_research_registry,
    build_story_architect_prompt,
    research_registry_prompt_view,
    validate_story_document,
)
from .story_duration import build_duration_plan, normalize_target_duration


class StoryAuthoringError(RuntimeError):
    """Raised when an author turn or its deterministic contract is unsafe."""

    def __init__(
        self,
        message: str,
        *,
        validation_errors: Sequence[str] = (),
        result: "StoryAuthoringResult | None" = None,
    ) -> None:
        super().__init__(message)
        self.validation_errors = tuple(str(error) for error in validation_errors)
        # A partial result is useful to a caller that wants to inspect a
        # failed validation report, but it is never published by this module.
        self.result = result


@dataclass(frozen=True)
class StoryAuthoringResult:
    """Result of a successful authoring run.

    ``repair_rounds`` is deliberately part of the public result even though
    this first implementation is fail-closed and does not silently repair an
    invalid document.  Future repair implementations can append structured
    round records without changing the successful result shape.
    """

    story: dict[str, Any]
    registry: dict[str, Any]
    source_digest: str
    validation_errors: tuple[str, ...] = ()
    selection: Any = None
    architect: dict[str, Any] = field(default_factory=dict)
    authored_scenes: tuple[dict[str, Any], ...] = ()
    repair_rounds: tuple[dict[str, Any], ...] = ()
    max_repair_rounds: int = 0

    @property
    def repairs(self) -> tuple[dict[str, Any], ...]:
        """Compatibility/readability alias for future repair records."""

        return self.repair_rounds

    @property
    def repair_count(self) -> int:
        """Number of repair records materialized in this result."""

        return len(self.repair_rounds)


TurnRunnerResult: TypeAlias = Mapping[str, Any] | Any
TurnRunner: TypeAlias = Callable[..., TurnRunnerResult | Awaitable[TurnRunnerResult]]


# These schemas intentionally leave authored prose and extension fields open.
# The deterministic validator is the source of truth for cross-scene
# invariants; the schemas only tell a structured provider which top-level
# objects are expected.
ARCHITECT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "story_metadata": {"type": "object"},
        "story_structure": {"type": "object"},
        "engagement_design": {"type": "object"},
        "adaptation_source_contract": {"type": "object"},
        "selection": {"type": "object"},
        "scene_plan": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "scene_id",
                    "title",
                    "phase",
                    "source_event_ids",
                    "incoming_state_id",
                    "outgoing_state_id",
                    "previous_scene_id",
                    "next_scene_id",
                ],
                "properties": {
                    "scene_id": {"type": "string"},
                    "title": {"type": "string"},
                    "phase": {"type": "string"},
                    "source_event_ids": {"type": "array", "items": {"type": "string"}},
                    "incoming_state_id": {"type": "string"},
                    "outgoing_state_id": {"type": "string"},
                    "previous_scene_id": {"type": ["string", "null"]},
                    "causal_connection_from_previous": {"type": ["string", "null"]},
                    "next_scene_id": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
    },
    "required": [
        "story_metadata",
        "adaptation_source_contract",
        "selection",
        "scene_plan",
    ],
    "additionalProperties": True,
}

SCENE_AUTHOR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "scene_id",
        "title",
        "phase",
        "purpose",
        "conflict",
        "turn",
        "affect",
        "visualizable_action",
        "grounding_note",
        "source_basis",
        "location",
        "time_of_day",
        "time_of_day_visual_basis",
        "scene_intent",
        "start_state",
        "event_sequence",
        "turning_event",
        "end_state",
        "handoff_chain",
        "preservation",
    ],
    "properties": {
        "scene_id": {"type": "string"},
        "title": {"type": "string"},
        "phase": {"type": "string"},
        "purpose": {"type": "string"},
        "conflict": {"type": "string"},
        "turn": {"type": "string"},
        "affect": {"type": "object"},
        "visualizable_action": {"type": "string"},
        "grounding_note": {"type": "string"},
        "source_basis": {
            "type": "object",
            "required": ["event_ids"],
            "properties": {
                "event_ids": {"type": "array", "items": {"type": "string"}},
                "passage_ids": {"type": "array", "items": {"type": "string"}},
                "source_ids": {"type": "array", "items": {"type": "string"}},
                "character_ids": {"type": "array", "items": {"type": "string"}},
                "place_ids": {"type": "array", "items": {"type": "string"}},
                "world_rule_ids": {"type": "array", "items": {"type": "string"}},
                "symbol_ids": {"type": "array", "items": {"type": "string"}},
                "fact_ids": {"type": "array", "items": {"type": "string"}},
                "conflict_ids": {"type": "array", "items": {"type": "string"}},
                "variant_ids": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": True,
        },
        "location": {
            "type": "object",
            "required": ["name", "sequence"],
            "properties": {
                "location_id": {"type": "string"},
                "name": {"type": "string"},
                "sequence": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": True,
        },
        "time_of_day": {"type": "string"},
        "time_of_day_visual_basis": {"type": "string"},
        "scene_intent": {"type": "object"},
        "start_state": {
            "type": "object",
            "required": ["state_id"],
            "properties": {"state_id": {"type": "string"}},
            "additionalProperties": True,
        },
        "event_sequence": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "beat_id",
                    "beat_function",
                    "source_event_ids",
                    "what_happens",
                    "visible_action",
                    "immediate_consequence",
                    "required_visual_evidence",
                ],
                "properties": {
                    "beat_id": {"type": "string"},
                    "beat_function": {"type": "string"},
                    "source_event_ids": {"type": "array", "items": {"type": "string"}},
                    "what_happens": {"type": "string"},
                    "visible_action": {"type": "string"},
                    "immediate_consequence": {"type": "string"},
                    "required_visual_evidence": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
        },
        "turning_event": {
            "type": "object",
            "required": ["beat_id", "irreversible_change"],
            "properties": {
                "beat_id": {"type": "string"},
                "irreversible_change": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "end_state": {
            "type": "object",
            "required": ["state_id"],
            "properties": {"state_id": {"type": "string"}},
            "additionalProperties": True,
        },
        "handoff_chain": {"type": "object"},
        "preservation": {"type": "object"},
    },
    "additionalProperties": True,
}

SCENE_BATCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": deepcopy(SCENE_AUTHOR_OUTPUT_SCHEMA),
        }
    },
    "additionalProperties": False,
}

REPAIR_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["scene_id", "replacement_scene"],
    "properties": {
        "scene_id": {"type": "string"},
        "replacement_scene": {"type": "object"},
        "addressed_errors": {"type": "array", "items": {"type": "string"}},
    },
    # A repair turn is never allowed to return a replacement story.  Unknown
    # keys are retained for auditability, but the orchestrator only imports
    # the two fields above.
    "additionalProperties": True,
}


def _canonical_json(value: Any) -> bytes:
    """Return the repository-style canonical JSON bytes for hashing."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StoryAuthoringError(
            "research input must be JSON-serializable for story authoring"
        ) from exc


def _source_digest(research: Mapping[str, Any]) -> str:
    """Hash only the source research, excluding generated registry indexes."""

    return "sha256:" + hashlib.sha256(_canonical_json(dict(research))).hexdigest()


def _text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _ids(value: Any) -> tuple[list[str], bool]:
    """Normalize a declared ID list and report whether its shape is valid."""

    if isinstance(value, (list, tuple)):
        return [_text(item) for item in value if _text(item)], True
    return ([], False)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _payload(value: Any, *, role: str) -> dict[str, Any]:
    """Accept mapping payloads and runtime-result objects without coercion."""

    candidate = value
    payload_attr = getattr(candidate, "payload", None)
    if payload_attr is not None:
        candidate = payload_attr
    if not isinstance(candidate, Mapping):
        raise StoryAuthoringError(f"{role} turn must return a JSON object")
    return deepcopy(dict(candidate))


async def _run_turn(turn_runner: TurnRunner, **kwargs: Any) -> dict[str, Any]:
    """Invoke an injected callable or runner object and await if necessary."""

    runner: Any = turn_runner
    if not callable(runner):
        for name in ("run", "run_turn", "author"):
            candidate = getattr(turn_runner, name, None)
            if callable(candidate):
                runner = candidate
                break
    if not callable(runner):
        raise StoryAuthoringError("turn_runner must be callable")

    try:
        result = runner(**kwargs)
        if inspect.isawaitable(result):
            result = await result
    except StoryAuthoringError:
        raise
    except Exception as exc:
        role = _text(kwargs.get("role")) or "author"
        raise StoryAuthoringError(f"{role} turn failed: {exc}") from exc
    return _payload(result, role=_text(kwargs.get("role")) or "author")


def _plan_event_ids(plan: Mapping[str, Any]) -> tuple[list[str], bool]:
    for key in (
        "source_event_ids",
        "event_ids",
        "owned_event_ids",
        "owned_source_event_ids",
    ):
        if key in plan:
            return _ids(plan.get(key))
    source_basis = _mapping(plan.get("source_basis"))
    if source_basis is not None:
        for key in (
            "source_event_ids",
            "event_ids",
            "owned_event_ids",
            "owned_source_event_ids",
        ):
            if key in source_basis:
                return _ids(source_basis.get(key))
    return [], False


def _authored_event_ids(scene: Mapping[str, Any]) -> tuple[list[str], bool]:
    source_basis = _mapping(scene.get("source_basis"))
    if source_basis is not None:
        for key in (
            "event_ids",
            "source_event_ids",
            "owned_event_ids",
            "owned_source_event_ids",
        ):
            if key in source_basis:
                return _ids(source_basis.get(key))
    for key in (
        "event_ids",
        "source_event_ids",
        "owned_event_ids",
        "owned_source_event_ids",
    ):
        if key in scene:
            return _ids(scene.get(key))
    return [], False


def _beat_event_ids(scene: Mapping[str, Any]) -> list[str]:
    sequence = scene.get("event_sequence")
    if not isinstance(sequence, (list, tuple)):
        for key in ("events", "beats"):
            if isinstance(scene.get(key), (list, tuple)):
                sequence = scene.get(key)
                break
    if not isinstance(sequence, (list, tuple)):
        return []
    result: list[str] = []
    for beat in sequence:
        if not isinstance(beat, Mapping):
            continue
        for key in ("source_event_ids", "event_ids"):
            if key in beat:
                values, _shape_ok = _ids(beat.get(key))
                result.extend(values)
                break
        else:
            if "source_event_id" in beat:
                value = _text(beat.get("source_event_id"))
                if value:
                    result.append(value)
    return result


def _validate_architect_plan(
    architect: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate and freeze the architect's ordered semantic scene plan."""

    raw_plan = architect.get("scene_plan")
    if not isinstance(raw_plan, (list, tuple)):
        raise StoryAuthoringError("architect output must contain a scene_plan list")

    event_map = registry.get("events")
    known_events = (
        {_text(key) for key in event_map.keys() if _text(key)}
        if isinstance(event_map, Mapping)
        else set()
    )
    expected_event_order = [
        _text(item)
        for item in registry.get("event_order", list(known_events))
        if _text(item)
    ]

    plans: list[dict[str, Any]] = []
    seen_scene_ids: set[str] = set()
    owned_event_ids: list[str] = []
    for index, raw in enumerate(raw_plan):
        if not isinstance(raw, Mapping):
            raise StoryAuthoringError(
                f"architect scene_plan[{index}] must be an object"
            )
        plan = deepcopy(dict(raw))
        scene_id = _text(plan.get("scene_id"))
        if not scene_id:
            raise StoryAuthoringError(
                f"architect scene_plan[{index}] is missing scene_id"
            )
        if scene_id in seen_scene_ids:
            raise StoryAuthoringError(f"architect scene_plan has duplicate scene_id: {scene_id}")
        seen_scene_ids.add(scene_id)

        event_ids, shape_ok = _plan_event_ids(plan)
        if not shape_ok:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] is missing source_event_ids"
            )
        unknown = [event_id for event_id in event_ids if event_id not in known_events]
        if unknown:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] references unknown event IDs: "
                + ", ".join(unknown)
            )
        if not event_ids:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] must own at least one source event"
            )
        owned_event_ids.extend(event_ids)
        plans.append(plan)

    if owned_event_ids != expected_event_order:
        if len(owned_event_ids) != len(set(owned_event_ids)):
            reason = "duplicate source event ownership"
        elif set(owned_event_ids) != set(expected_event_order):
            reason = "source event coverage mismatch"
        else:
            reason = "source event order mismatch"
        raise StoryAuthoringError(f"architect scene_plan {reason}")

    for index, plan in enumerate(plans):
        scene_id = _text(plan.get("scene_id"))
        expected_previous = _text(plans[index - 1].get("scene_id")) if index else ""
        expected_next = (
            _text(plans[index + 1].get("scene_id"))
            if index + 1 < len(plans)
            else ""
        )
        incoming_state = _text(plan.get("incoming_state_id"))
        outgoing_state = _text(plan.get("outgoing_state_id"))
        if not incoming_state or not outgoing_state:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] must freeze incoming/outgoing state IDs"
            )
        if _text(plan.get("previous_scene_id")) != expected_previous:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] previous_scene_id mismatch"
            )
        if _text(plan.get("next_scene_id")) != expected_next:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] next_scene_id mismatch"
            )
        if index and _text(plans[index - 1].get("outgoing_state_id")) != incoming_state:
            raise StoryAuthoringError(
                f"architect scene_plan[{scene_id}] incoming state does not match previous outgoing state"
            )

    return plans


def _records_for_ids(
    registry: Mapping[str, Any],
    category: str,
    ids: Sequence[str],
) -> list[Any]:
    values = registry.get(category)
    if not isinstance(values, Mapping):
        return []
    return [deepcopy(values[item_id]) for item_id in ids if item_id in values]


def _scene_research_slice(
    registry: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a complete, ID-addressable slice for one scene author."""

    event_ids, _ = _plan_event_ids(plan)
    events = _records_for_ids(registry, "events", event_ids)
    character_ids: list[str] = []
    place_ids: list[str] = []
    rule_ids: list[str] = []
    passage_ids: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        for key, target in (
            ("involved_characters", character_ids),
            ("character_ids", character_ids),
            ("place_ids", place_ids),
            ("location_ids", place_ids),
            ("world_rule_ids", rule_ids),
            ("rule_ids", rule_ids),
            ("sources", passage_ids),
            ("source_refs", passage_ids),
            ("passage_ids", passage_ids),
        ):
            values = event.get(key)
            if isinstance(values, (list, tuple)):
                for value in values:
                    item = _text(value)
                    if item and item not in target:
                        target.append(item)
    return {
        "events": events,
        "characters": _records_for_ids(registry, "characters", character_ids),
        "places": _records_for_ids(registry, "places", place_ids),
        "world_rules": _records_for_ids(registry, "world_rules", rule_ids),
        "passages": _records_for_ids(registry, "passages", passage_ids),
    }


def build_scene_author_prompt(
    registry: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    *,
    topic: str = "",
    target_duration_seconds: int | float | None = None,
    source_digest: str = "",
    previous_scene_plan: Mapping[str, Any] | None = None,
    next_scene_plan: Mapping[str, Any] | None = None,
) -> str:
    """Build a replayable scene-author prompt without truncating research.

    The scene slice makes the immediate task easy to read; the complete
    registry remains alongside it so a scene author never loses relationships,
    variants, conflicts, confidence, or source passages that happen not to be
    mentioned by an event's convenience fields.
    """

    payload = {
        "prompt_contract": "story_scene_author_prompt_v1",
        "role": "Scene Author",
        "instructions": [
            SCENE_CAUSAL_CONNECTION_INSTRUCTION,
            AUDIENCE_MEANING_INSTRUCTION,
            "Author only the declared scene; do not move source events between scenes.",
            "Preserve every source-backed fact and keep creative complements explicit.",
            "Define the complete lifecycle: start_state, event_sequence, turning_event, end_state, preservation/reveal contract, and handoff_chain.",
            "Make each event_sequence beat concrete, observable, causally consequential, and traceable to source event IDs.",
            "Also author the downstream story overview fields title, phase, purpose, conflict, turn, affect, visualizable_action, grounding_note, location, time_of_day, and time_of_day_visual_basis from the same lifecycle; do not use generic filler.",
            "location must name the authored place and preserve its ordered sequence; purpose/conflict/turn must be specific projections of this scene rather than template prose.",
            "Do not add camera, lens, provider prompt, or fixed cut-count instructions to story.md.",
        ],
        "topic": topic,
        "target_duration_seconds": target_duration_seconds,
        "source_digest": source_digest,
        "scene_plan": deepcopy(dict(scene_plan)),
        "previous_scene_plan": deepcopy(dict(previous_scene_plan)) if previous_scene_plan else None,
        "next_scene_plan": deepcopy(dict(next_scene_plan)) if next_scene_plan else None,
        "scene_research_slice": _scene_research_slice(registry, scene_plan),
        "research_registry": research_registry_prompt_view(registry),
        "truncation": {"policy": "none", "source": "full_research_registry"},
    }
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StoryAuthoringError(
            f"scene author prompt for {_text(scene_plan.get('scene_id'))} is not serializable"
        ) from exc


def build_scene_batch_author_prompt(
    registry: Mapping[str, Any],
    plans: Sequence[Mapping[str, Any]],
    *,
    topic: str = "",
    target_duration_seconds: int | float | None = None,
    source_digest: str = "",
) -> str:
    payload = {
        "prompt_contract": "story_scene_batch_author_prompt_v1",
        "role": "Scene Author",
        "instructions": [
            SCENE_CAUSAL_CONNECTION_INSTRUCTION,
            AUDIENCE_MEANING_INSTRUCTION,
            "Author every frozen scene plan in order and return one scenes array.",
            "Do not add, remove, reorder, merge, or split plans or source-event ownership.",
            "For every scene write the complete lifecycle and all concrete causal beats; one source event may expand into multiple beats.",
            "Each beat must name participants, location, visible action, visible evidence, consequence, and source event IDs.",
            "Preserve adjacent state IDs and handoffs exactly as frozen by the Architect.",
            "Use specific research details rather than generic filler; keep source facts and creative complements distinguishable.",
            "Author all downstream overview fields from the same lifecycle, including time-of-day visual basis with 光源, 明るさ, 影, and 色温度.",
            "Do not add camera, lens, provider prompt, or fixed cut-count instructions.",
        ],
        "topic": topic,
        "target_duration_seconds": target_duration_seconds,
        "source_digest": source_digest,
        "scene_plans": [deepcopy(dict(plan)) for plan in plans],
        "scene_research_slices": [
            {
                "scene_id": _text(plan.get("scene_id")),
                "research": _scene_research_slice(registry, plan),
            }
            for plan in plans
        ],
        "research_registry": research_registry_prompt_view(registry),
        "truncation": {"policy": "none", "source": "full_research_registry"},
    }
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StoryAuthoringError("scene batch author prompt is not serializable") from exc


def _ensure_scene_binding(
    scene: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    authored = deepcopy(dict(scene))
    expected_scene_id = _text(plan.get("scene_id"))
    actual_scene_id = _text(authored.get("scene_id"))
    if actual_scene_id != expected_scene_id:
        raise StoryAuthoringError(
            f"scene_author scene_id mismatch: expected {expected_scene_id}, got {actual_scene_id or '<missing>'}"
        )

    expected_events, expected_shape = _plan_event_ids(plan)
    actual_events, actual_shape = _authored_event_ids(authored)
    if not expected_shape or not actual_shape:
        raise StoryAuthoringError(
            f"scene_author {expected_scene_id} must preserve source_event_ids"
        )
    if actual_events != expected_events:
        raise StoryAuthoringError(
            f"scene_author {expected_scene_id} source event ownership mismatch"
        )
    beat_events = _beat_event_ids(authored)
    first_appearance_order = list(dict.fromkeys(beat_events))
    if beat_events and first_appearance_order != actual_events:
        raise StoryAuthoringError(
            f"scene_author {expected_scene_id} event_sequence ownership mismatch"
        )
    expected_start = _text(plan.get("incoming_state_id"))
    expected_end = _text(plan.get("outgoing_state_id"))
    expected_previous = _text(plan.get("previous_scene_id"))
    expected_next = _text(plan.get("next_scene_id"))
    # Architect-owned identity keys are not model-editable. Reconcile only
    # these frozen keys deterministically while retaining all authored state
    # descriptions, character/object layers, anchors, and physical forms.
    start_state = authored.get("start_state")
    end_state = authored.get("end_state")
    handoff_chain = authored.get("handoff_chain")
    if not isinstance(start_state, dict) or not isinstance(end_state, dict):
        raise StoryAuthoringError(
            f"scene_author {expected_scene_id} must return start/end state objects"
        )
    if not isinstance(handoff_chain, dict):
        raise StoryAuthoringError(
            f"scene_author {expected_scene_id} must return handoff_chain"
        )
    incoming = handoff_chain.get("incoming")
    outgoing = handoff_chain.get("outgoing")
    physical_form = _text(
        handoff_chain.get("handoff")
        or handoff_chain.get("visible_or_audible_form")
    )
    if not isinstance(incoming, dict):
        incoming = {
            "anchor_id": f"{expected_scene_id}_incoming",
            "visible_or_audible_form": physical_form,
        }
        handoff_chain["incoming"] = incoming
    if not isinstance(outgoing, dict):
        outgoing = {
            "anchor_id": f"{expected_scene_id}_outgoing",
            "visible_or_audible_form": physical_form,
        }
        handoff_chain["outgoing"] = outgoing
    start_state["state_id"] = expected_start
    end_state["state_id"] = expected_end
    incoming["state_id"] = expected_start
    outgoing["state_id"] = expected_end
    incoming["producer_scene_id"] = expected_previous
    outgoing["consumer_scene_id"] = expected_next
    source_basis = _mapping(authored.get("source_basis")) or {}
    character_ids, _ = _ids(source_basis.get("character_ids"))
    place_ids, _ = _ids(
        source_basis.get("place_ids") or source_basis.get("location_ids")
    )
    location = _mapping(authored.get("location")) or {}
    beats = authored.get("event_sequence")
    authored["title"] = _text(authored.get("title")) or _text(plan.get("title"))
    authored["phase"] = _text(authored.get("phase")) or _text(plan.get("phase"))
    scene_intent = _mapping(authored.get("scene_intent")) or {}
    turning_event = _mapping(authored.get("turning_event")) or {}
    authored["purpose"] = _text(authored.get("purpose")) or _text(
        scene_intent.get("story_purpose")
    )
    authored["turn"] = _text(authored.get("turn")) or _text(
        turning_event.get("irreversible_change")
        or turning_event.get("change")
    )
    visual_actions: list[str] = []
    if isinstance(beats, list):
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            action = _mapping(beat.get("action")) or {}
            beat["what_happens"] = _text(beat.get("what_happens")) or _text(
                action.get("what_happens")
            )
            beat["visible_action"] = _text(beat.get("visible_action")) or _text(
                action.get("visible_action") or beat.get("what_happens")
            )
            beat["immediate_consequence"] = _text(
                beat.get("immediate_consequence") or beat.get("consequence")
            )
            if beat["visible_action"]:
                visual_actions.append(beat["visible_action"])
            # These are deterministic typed aliases from the scene's frozen
            # source_basis, not authored prose. They keep legacy consumers
            # from losing actor/location bindings when the model expresses
            # them only once at scene scope.
            if not (beat.get("participants") or beat.get("character_ids")):
                beat["participants"] = list(character_ids)
            if not (
                beat.get("location_id")
                or beat.get("place_ids")
                or beat.get("location_ids")
                or beat.get("location")
            ):
                if place_ids:
                    beat["location_id"] = place_ids[0]
                elif _text(location.get("name")):
                    beat["location"] = _text(location.get("name"))
    first_beat = (
        next((beat for beat in beats if isinstance(beat, dict)), {})
        if isinstance(beats, list)
        else {}
    )
    if isinstance(beats, list):
        object_beats = [beat for beat in beats if isinstance(beat, dict)]
        for beat_index, beat in enumerate(object_beats):
            if not _text(beat.get("immediate_consequence")):
                next_beat = (
                    object_beats[beat_index + 1]
                    if beat_index + 1 < len(object_beats)
                    else {}
                )
                beat["immediate_consequence"] = _text(
                    next_beat.get("what_happens") or expected_end
                )
            evidence = beat.get("required_visual_evidence")
            if not isinstance(evidence, list) or not any(
                _text(value) for value in evidence
            ):
                beat["required_visual_evidence"] = [
                    value
                    for value in (
                        _text(beat.get("visible_action")),
                        _text(location.get("name")),
                    )
                    if value
                ]
    authored["conflict"] = _text(authored.get("conflict")) or _text(
        scene_intent.get("conflict")
        or first_beat.get("conflict_or_constraint")
        or scene_intent.get("dramatic_question")
    )
    authored["visualizable_action"] = _text(
        authored.get("visualizable_action")
    ) or " → ".join(visual_actions)
    if not _text(authored.get("grounding_note")):
        authored["grounding_note"] = "source_basis: " + ", ".join(
            _text(value)
            for key in sorted(source_basis)
            for value in (
                source_basis.get(key)
                if isinstance(source_basis.get(key), list)
                else []
            )
            if _text(value)
        )
    if not isinstance(authored.get("affect"), Mapping):
        affect_transition = scene_intent.get("affect_transition")
        authored["affect"] = (
            deepcopy(dict(affect_transition))
            if isinstance(affect_transition, Mapping)
            else {"transition": _text(affect_transition) or _text(authored["turn"])}
        )
    visual_basis = _text(authored.get("time_of_day_visual_basis"))
    missing_visual_dimensions = [
        dimension
        for dimension in ("光源", "明るさ", "影", "色温度")
        if dimension not in visual_basis
    ]
    if visual_basis and missing_visual_dimensions:
        authored["time_of_day_visual_basis"] = " ".join(
            f"{dimension}: {_text(authored.get('time_of_day'))}の描写として設定。"
            for dimension in missing_visual_dimensions
        ) + " " + visual_basis
    return authored


def _state_token(value: Any) -> str:
    """Read a lifecycle state ID without depending on validator internals."""

    if isinstance(value, Mapping):
        for key in ("state_id", "handoff_state_id", "id"):
            token = _text(value.get(key))
            if token:
                return token
        try:
            return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return repr(value)
    return _text(value)


def _scene_state(scene: Mapping[str, Any], field: str) -> str:
    value = scene.get(field)
    return _state_token(value)


def _handoff_state(scene: Mapping[str, Any], side: str) -> str:
    chain = _mapping(scene.get("handoff_chain")) or {}
    handoff = _mapping(chain.get(side)) or {}
    return _state_token(handoff.get("state_id") or handoff.get("state"))


def _handoff_scene_id(scene: Mapping[str, Any], side: str) -> str:
    chain = _mapping(scene.get("handoff_chain")) or {}
    handoff = _mapping(chain.get(side)) or {}
    key = "producer_scene_id" if side == "incoming" else "consumer_scene_id"
    return _text(handoff.get(key))


def _failing_scene_ids(
    story: Mapping[str, Any],
    validation_errors: Sequence[str],
    plans: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any],
) -> list[str]:
    """Localize deterministic validation errors to one repair candidate.

    ``validate_story_document`` intentionally returns stable aggregate reason
    keys rather than paths.  This helper reconstructs the relevant scene for
    the common lifecycle errors, keeping a repair request scene-scoped.  If a
    future validator adds a reason that cannot be localized safely, no repair
    target is guessed and the caller remains fail-closed.
    """

    script = _mapping(story.get("script"))
    raw_scenes = script.get("scenes") if script is not None else None
    scenes = list(raw_scenes) if isinstance(raw_scenes, (list, tuple)) else []
    scene_ids = [
        _text(scene.get("scene_id"))
        for scene in scenes
        if isinstance(scene, Mapping) and _text(scene.get("scene_id"))
    ]
    plan_ids = [_text(plan.get("scene_id")) for plan in plans if _text(plan.get("scene_id"))]

    candidates: list[str] = []
    def add(scene_id: str) -> None:
        if scene_id and scene_id in scene_ids and scene_id not in candidates:
            candidates.append(scene_id)

    lifecycle_errors = {
        "story.scene_handoff_state_mismatch",
        "story.scene_handoff_reference_mismatch",
        "story.scene_lifecycle_missing",
        "story.scene_turning_event_invalid",
        "story.scene_event_sequence_invalid",
        "story.scene_event_sequence_coverage",
        "story.scene_event_beat_grounding_missing",
        "story.scene_event_ownership_mismatch",
        "story.scene_unknown_id",
        "story.scene_id_list_invalid",
        "story.scene_reveal_state_rollback",
        "story.scene_overview_missing",
        "story.scene_location_invalid",
        "story.scene_time_of_day_visual_basis_invalid",
    }
    if any(error not in lifecycle_errors for error in validation_errors):
        # Coverage/order failures should normally have been caught while
        # binding each author result.  They are not safely repairable as a
        # single scene if they get this far.
        return []

    for index, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            continue
        scene_id = _text(scene.get("scene_id"))
        if not scene_id:
            continue
        previous = scenes[index - 1] if index else None
        next_scene = scenes[index + 1] if index + 1 < len(scenes) else None
        start = _scene_state(scene, "start_state")
        end = _scene_state(scene, "end_state")
        incoming = _handoff_state(scene, "incoming")
        outgoing = _handoff_state(scene, "outgoing")
        if "story.scene_handoff_state_mismatch" in validation_errors:
            if (start and incoming and start != incoming) or (end and outgoing and end != outgoing):
                add(scene_id)
            if isinstance(previous, Mapping):
                previous_end = _scene_state(previous, "end_state")
                current_start = start
                previous_outgoing = _handoff_state(previous, "outgoing")
                if (previous_end and current_start and previous_end != current_start) or (
                    previous_outgoing and incoming and previous_outgoing != incoming
                ):
                    add(scene_id)
        if "story.scene_handoff_reference_mismatch" in validation_errors:
            expected_previous = _text(scenes[index - 1].get("scene_id")) if index else ""
            expected_next = _text(scenes[index + 1].get("scene_id")) if index + 1 < len(scenes) else ""
            if _handoff_scene_id(scene, "incoming") != expected_previous and (
                _handoff_scene_id(scene, "incoming") or expected_previous
            ):
                add(scene_id)
            if _handoff_scene_id(scene, "outgoing") != expected_next and (
                _handoff_scene_id(scene, "outgoing") or expected_next
            ):
                add(scene_id)
        if "story.scene_lifecycle_missing" in validation_errors:
            required = ("scene_intent", "start_state", "event_sequence", "turning_event", "end_state", "handoff_chain")
            if any(not isinstance(scene.get(field), Mapping if field != "event_sequence" else (list, tuple)) for field in required):
                add(scene_id)
        if "story.scene_overview_missing" in validation_errors:
            overview_fields = (
                "title",
                "phase",
                "purpose",
                "conflict",
                "turn",
                "visualizable_action",
                "grounding_note",
                "time_of_day",
            )
            if any(not _text(scene.get(field)) for field in overview_fields) or not isinstance(
                scene.get("affect"), Mapping
            ):
                add(scene_id)
        if "story.scene_location_invalid" in validation_errors:
            location = _mapping(scene.get("location")) or {}
            if not _text(location.get("name")):
                add(scene_id)
        if "story.scene_time_of_day_visual_basis_invalid" in validation_errors:
            visual_basis = _text(scene.get("time_of_day_visual_basis"))
            if not visual_basis or any(
                dimension not in visual_basis
                for dimension in ("光源", "明るさ", "影", "色温度")
            ):
                add(scene_id)
            if not isinstance(scene.get("preservation"), Mapping) and not isinstance(scene.get("reveal_contract"), Mapping):
                add(scene_id)
        if "story.scene_turning_event_invalid" in validation_errors:
            turning = _mapping(scene.get("turning_event")) or {}
            beats = scene.get("event_sequence")
            beat_ids = {
                _text(beat.get("beat_id"))
                for beat in beats
                if isinstance(beat, Mapping) and _text(beat.get("beat_id"))
            } if isinstance(beats, (list, tuple)) else set()
            if not _text(turning.get("beat_id") or turning.get("event_beat_id")) in beat_ids or not _text(
                turning.get("irreversible_change") or turning.get("change") or turning.get("what_changes")
            ):
                add(scene_id)
        if (
            "story.scene_event_sequence_invalid" in validation_errors
            or "story.scene_event_sequence_coverage" in validation_errors
            or "story.scene_event_beat_grounding_missing" in validation_errors
        ):
            beats = scene.get("event_sequence")
            if not isinstance(beats, (list, tuple)) or not beats:
                add(scene_id)
            else:
                plan = plans[index] if index < len(plans) else {}
                expected, _ = _plan_event_ids(plan)
                actual, _ = _authored_event_ids(scene)
                beat_events = _beat_event_ids(scene)
                if actual != expected or (beat_events and beat_events != actual):
                    add(scene_id)
                if any(
                    not isinstance(beat, Mapping)
                    or not _text(beat.get("beat_id"))
                    or not _beat_event_ids({"event_sequence": [beat]})
                    or not _text(beat.get("what_happens") or beat.get("concrete_event") or beat.get("action"))
                    or not _text(beat.get("immediate_consequence") or beat.get("consequence"))
                    or not (beat.get("participants") or beat.get("character_ids"))
                    or not (
                        beat.get("location_id")
                        or beat.get("place_ids")
                        or beat.get("location_ids")
                        or beat.get("location")
                    )
                    or not beat.get("required_visual_evidence")
                    or not _text(
                        beat.get("visible_action")
                        or (_mapping(beat.get("action")) or {}).get("visible_action")
                    )
                    for beat in beats
                ):
                    add(scene_id)
        if "story.scene_unknown_id" in validation_errors or "story.scene_id_list_invalid" in validation_errors:
            probe_errors = validate_story_document(
                {"script": {"scenes": [deepcopy(dict(scene))]}},
                registry,
            )
            if (
                "story.scene_unknown_id" in probe_errors
                or "story.scene_id_list_invalid" in probe_errors
            ):
                add(scene_id)
    if candidates:
        return candidates
    # A reveal rollback or an otherwise localizable scene-level issue may not
    # expose a richer path.  Select the first scene in canonical order only
    # when there is exactly one safe candidate; multiple guesses would violate
    # the scene-only repair contract.
    if len(scene_ids) == 1:
        return scene_ids
    if plan_ids:
        # For a generic scene-level reason, the first canonical scene is the
        # only deterministic target available. Handoff errors are handled
        # above and do not reach this fallback in normal operation.
        if "story.scene_reveal_state_rollback" in validation_errors:
            return [scene_id for scene_id in plan_ids if scene_id in scene_ids][:1]
    return []


def _build_repair_prompt(
    *,
    validation_errors: Sequence[str],
    current_story: Mapping[str, Any],
    scene_id: str,
    scene_plan: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_digest: str,
    topic: str,
    target_duration_seconds: int | float | None,
) -> str:
    repair_requirements: list[str] = []
    if "story.scene_time_of_day_visual_basis_invalid" in validation_errors:
        repair_requirements.append(
            "time_of_day_visual_basis must explicitly contain all four literal dimension labels: 光源, 明るさ, 影, 色温度"
        )
    if "story.scene_event_beat_grounding_missing" in validation_errors:
        repair_requirements.append(
            "every event beat must retain participants, location, visible_action, required_visual_evidence, and immediate_consequence"
        )
    payload = {
        "prompt_contract": "story_scene_repair_prompt_v1",
        "role": "Scene Repair Author",
        "instructions": [
            SCENE_CAUSAL_CONNECTION_INSTRUCTION,
            AUDIENCE_MEANING_INSTRUCTION,
            "Repair only the named scene and return scene_id plus replacement_scene.",
            "Do not return or rewrite the complete story; neighboring scenes are read-only context.",
            "Preserve the frozen source event ownership and handoff contract.",
            "Address every supplied deterministic validation error in the replacement scene.",
        ],
        "topic": topic,
        "target_duration_seconds": target_duration_seconds,
        "source_digest": source_digest,
        "validation_errors": list(validation_errors),
        "repair_requirements": repair_requirements,
        "scene_id": scene_id,
        "failing_scene_plan": deepcopy(dict(scene_plan)),
        "current_story": deepcopy(dict(current_story)),
        "research_registry": research_registry_prompt_view(registry),
        "truncation": {"policy": "none", "source": "full_research_registry"},
    }
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StoryAuthoringError(
            f"repair prompt for {scene_id} is not serializable"
        ) from exc


def _metadata_injected(
    existing: Mapping[str, Any] | None,
    *,
    topic: str,
    target_duration_seconds: int | float | None,
    source_digest: str,
    source_research: str,
) -> dict[str, Any]:
    metadata = deepcopy(dict(existing)) if isinstance(existing, Mapping) else {}
    # These are request-bound values and must not be trusted from the model.
    metadata.update(
        {
            "scene_authoring_contract": STORY_CONTRACT_VERSION,
            "source_digest": source_digest,
            "topic": topic,
            "target_duration_seconds": target_duration_seconds,
            "source_research": source_research,
            "scene_time_of_day_contract": "required_v1",
            "scene_time_of_day_visual_basis_contract": "required_v1",
        }
    )
    # The template has used both names over time.  Keep the canonical seconds
    # key authoritative and provide the legacy alias only when a target was
    # actually supplied by the caller.
    if target_duration_seconds is not None:
        metadata["target_duration"] = target_duration_seconds
    return metadata


def _assemble_story(
    architect: Mapping[str, Any],
    scenes: Sequence[Mapping[str, Any]],
    *,
    topic: str,
    target_duration_seconds: int | float | None,
    source_digest: str,
    source_research: str,
) -> dict[str, Any]:
    story = deepcopy(dict(architect))
    # scene_plan is a useful immutable authoring trace; ``script.scenes`` is
    # the canonical authored document consumed by the next stage.
    story["scene_plan"] = deepcopy(list(architect.get("scene_plan") or []))
    metadata = _mapping(story.get("story_metadata"))
    story["story_metadata"] = _metadata_injected(
        metadata,
        topic=topic,
        target_duration_seconds=target_duration_seconds,
        source_digest=source_digest,
        source_research=source_research,
    )
    script = _mapping(story.get("script"))
    assembled_script = deepcopy(dict(script)) if script is not None else {}
    assembled_script["scenes"] = deepcopy([dict(scene) for scene in scenes])
    story["script"] = assembled_script

    # Preserve selection exactly as returned by the Architect.  It is not
    # scored or rewritten by this plumbing layer.
    if "selection" in architect:
        story["selection"] = deepcopy(architect.get("selection"))
    return story


def _bind_scene_timing(
    story: dict[str, Any],
    *,
    target_duration_seconds: int | float | None,
) -> None:
    """Bind request-owned timing without changing authored scene semantics.

    Scene boundaries belong to the Story Architect. Duration planning may
    distribute time across those scenes, but it must never pad the story by
    cloning or splitting a semantic scene merely to satisfy a runtime floor.
    """

    if target_duration_seconds is None:
        return
    target = normalize_target_duration(target_duration_seconds)
    script = _mapping(story.get("script"))
    scenes = script.get("scenes") if script is not None else None
    if not isinstance(scenes, list) or not scenes:
        raise StoryAuthoringError("cannot bind duration without authored scenes")

    scene_base, scene_remainder = divmod(target, len(scenes))
    if scene_base <= 0:
        raise StoryAuthoringError(
            "authored scene count exceeds positive duration allocation capacity"
        )
    narration_total = build_duration_plan(target).minimum_narration_seconds
    narration_base, narration_remainder = divmod(narration_total, len(scenes))
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise StoryAuthoringError("cannot bind duration to a non-object scene")
        scene["target_duration_seconds"] = scene_base + (
            1 if index < scene_remainder else 0
        )
        scene["narration_target_seconds"] = narration_base + (
            1 if index < narration_remainder else 0
        )
        scene["canonical_scene_index"] = index + 1
        source_basis = _mapping(scene.get("source_basis")) or {}
        ref_specs = (
            ("event_ids", "story_materials.chronological_events"),
            ("passage_ids", "source_passages"),
            ("character_ids", "story_materials.characters"),
            ("place_ids", "story_materials.setting.places"),
            ("world_rule_ids", "story_materials.setting.world_rules"),
            ("symbol_ids", "story_materials.symbols_and_themes"),
            ("variant_ids", "variants"),
            ("conflict_ids", "conflicts"),
            ("fact_ids", "facts.items"),
            ("hook_ids", "engagement.hooks"),
        )
        refs: list[str] = []
        for key, path in ref_specs:
            values, shape_ok = _ids(source_basis.get(key))
            if not shape_ok:
                continue
            refs.extend(f"research.{path}[{item_id}]" for item_id in values)
        scene["research_refs"] = list(dict.fromkeys(refs))
    metadata = _mapping(story.get("story_metadata"))
    if not isinstance(metadata, dict):
        raise StoryAuthoringError("story_metadata became invalid during duration binding")
    metadata["duration_binding"] = {
        "schema_version": "story_duration_binding_v1",
        "target_seconds": target,
        "scene_ids": [_text(scene.get("scene_id")) for scene in scenes],
        "scene_allocations": [
            {
                "scene_id": _text(scene.get("scene_id")),
                "seconds": int(scene["target_duration_seconds"]),
            }
            for scene in scenes
        ],
        "sum_seconds": sum(int(scene["target_duration_seconds"]) for scene in scenes),
        "minimum_narration_seconds": narration_total,
        "source": "request",
        "semantic_scene_ids_unchanged": True,
    }


def _validation_result(
    *,
    story: dict[str, Any],
    registry: dict[str, Any],
    source_digest: str,
    architect: dict[str, Any],
    authored_scenes: Sequence[dict[str, Any]],
    max_repair_rounds: int,
    validation_errors: Sequence[str],
    repair_rounds: Sequence[Mapping[str, Any]] = (),
) -> StoryAuthoringResult:
    selection = deepcopy(architect.get("selection")) if "selection" in architect else None
    return StoryAuthoringResult(
        story=deepcopy(story),
        registry=deepcopy(registry),
        source_digest=source_digest,
        validation_errors=tuple(str(error) for error in validation_errors),
        selection=selection,
        architect=deepcopy(architect),
        authored_scenes=tuple(deepcopy(dict(scene)) for scene in authored_scenes),
        repair_rounds=tuple(deepcopy(dict(round_record)) for round_record in repair_rounds),
        max_repair_rounds=max_repair_rounds,
    )


def _publish_story(path: Path, story: Mapping[str, Any]) -> None:
    """Atomically publish a validated story document when requested."""

    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - environment normally has PyYAML
        raise StoryAuthoringError("PyYAML is required when publishing story.md") from exc

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "# 物語（story）\n\n```yaml\n"
    text += yaml.safe_dump(
        dict(story),
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    text += "```\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


async def author_story_from_research(
    research: Mapping[str, Any],
    *,
    topic: str = "",
    target_duration_seconds: int | float | None = None,
    turn_runner: TurnRunner,
    max_repair_rounds: int = 0,
    source_research: str = "research.md",
    output_path: str | Path | None = None,
    story_path: str | Path | None = None,
) -> StoryAuthoringResult:
    """Author a research-grounded story through injected LLM turns.

    The call order is intentionally explicit and stable: one ``architect``
    turn, followed by one batched ``scene_author`` turn containing every
    frozen scene plan in order. Validation failures raise
    :class:`StoryAuthoringError`; an output
    path is written only after validation succeeds.
    """

    if not isinstance(research, Mapping):
        raise StoryAuthoringError("research must be a mapping")
    if not isinstance(topic, str):
        raise StoryAuthoringError("topic must be a string")
    if not isinstance(source_research, str) or not source_research.strip():
        raise StoryAuthoringError("source_research must be a non-empty string")
    if (
        isinstance(max_repair_rounds, bool)
        or not isinstance(max_repair_rounds, int)
        or max_repair_rounds < 0
    ):
        raise StoryAuthoringError("max_repair_rounds must be a non-negative integer")

    registry = build_research_registry(research)
    source_digest = _source_digest(research)
    architect_prompt = build_story_architect_prompt(
        registry,
        topic=topic,
        target_duration_seconds=target_duration_seconds,
    )
    architect = await _run_turn(
        turn_runner,
        role="architect",
        prompt=architect_prompt,
        output_schema=deepcopy(ARCHITECT_OUTPUT_SCHEMA),
        registry=deepcopy(registry),
        topic=topic,
        target_duration_seconds=target_duration_seconds,
        source_digest=source_digest,
    )
    plans = _validate_architect_plan(architect, registry)

    plan_batches = [[plan] for plan in plans]
    scene_batch_semaphore = asyncio.Semaphore(min(5, max(1, len(plan_batches))))

    async def author_scene_batch(
        batch_index: int, batch_plans: Sequence[Mapping[str, Any]]
    ) -> list[Any]:
        scene_prompt = build_scene_batch_author_prompt(
            registry,
            batch_plans,
            topic=topic,
            target_duration_seconds=target_duration_seconds,
            source_digest=source_digest,
        )
        async with scene_batch_semaphore:
            scene_batch = await _run_turn(
                turn_runner,
                role="scene_author",
                prompt=scene_prompt,
                output_schema=deepcopy(SCENE_BATCH_OUTPUT_SCHEMA),
                registry=deepcopy(registry),
                scene_plans=deepcopy(list(batch_plans)),
                scene_batch_index=batch_index,
                scene_batch_count=len(plan_batches),
                scene_count=len(plans),
                topic=topic,
                target_duration_seconds=target_duration_seconds,
                source_digest=source_digest,
            )
        raw_batch_scenes = scene_batch.get("scenes")
        if not isinstance(raw_batch_scenes, list) or len(raw_batch_scenes) != len(
            batch_plans
        ):
            raise StoryAuthoringError(
                "scene_author batch must return exactly one scene for every frozen plan"
            )
        return raw_batch_scenes

    raw_scene_batches = await asyncio.gather(
        *(
            author_scene_batch(batch_index, batch_plans)
            for batch_index, batch_plans in enumerate(plan_batches, start=1)
        )
    )
    raw_scenes = [scene for batch in raw_scene_batches for scene in batch]
    scenes = [
        _ensure_scene_binding(authored, plan)
        for authored, plan in zip(raw_scenes, plans, strict=True)
        if isinstance(authored, Mapping)
    ]
    if len(scenes) != len(plans):
        raise StoryAuthoringError("scene_author batch contains a non-object scene")

    story = _assemble_story(
        architect,
        scenes,
        topic=topic,
        target_duration_seconds=target_duration_seconds,
        source_digest=source_digest,
        source_research=source_research,
    )
    validation_errors = tuple(validate_story_document(story, registry))
    repair_rounds: list[dict[str, Any]] = []

    # Repair is deliberately scene-local.  A round may replace exactly one
    # scene, then the complete assembled story is validated again.  If an
    # aggregate validator reason cannot be localized safely, the pipeline
    # stops rather than asking a model to rewrite the whole document.
    for round_number in range(1, max_repair_rounds + 1):
        if not validation_errors:
            break
        failing_scene_ids = _failing_scene_ids(
            story, validation_errors, plans, registry
        )
        if not failing_scene_ids:
            break
        failing_scene_id = failing_scene_ids[0]
        failing_index = next(
            (
                index
                for index, scene in enumerate(scenes)
                if _text(scene.get("scene_id")) == failing_scene_id
            ),
            None,
        )
        if failing_index is None:
            break
        failing_plan = plans[failing_index]
        repair_prompt = _build_repair_prompt(
            validation_errors=validation_errors,
            current_story=story,
            scene_id=failing_scene_id,
            scene_plan=failing_plan,
            registry=registry,
            source_digest=source_digest,
            topic=topic,
            target_duration_seconds=target_duration_seconds,
        )
        repair = await _run_turn(
            turn_runner,
            role="repair",
            prompt=repair_prompt,
            output_schema=deepcopy(REPAIR_OUTPUT_SCHEMA),
            validation_errors=list(validation_errors),
            current_story=deepcopy(story),
            scene_id=failing_scene_id,
            scene_plan=deepcopy(failing_plan),
            failing_scene_plan=deepcopy(failing_plan),
            registry=deepcopy(registry),
            source_digest=source_digest,
            topic=topic,
            target_duration_seconds=target_duration_seconds,
            repair_round=round_number,
        )
        returned_scene_id = _text(repair.get("scene_id"))
        if returned_scene_id != failing_scene_id:
            raise StoryAuthoringError(
                "repair scene_id mismatch: "
                f"expected {failing_scene_id}, got {returned_scene_id or '<missing>'}",
                validation_errors=validation_errors,
            )
        replacement = repair.get("replacement_scene")
        if not isinstance(replacement, Mapping):
            raise StoryAuthoringError(
                f"repair for {failing_scene_id} must return replacement_scene",
                validation_errors=validation_errors,
            )
        # A repair response is not allowed to smuggle in a complete story or
        # script replacement.  The only imported payload is this one scene.
        if "story" in repair or "script" in repair or "scenes" in repair:
            raise StoryAuthoringError(
                f"repair for {failing_scene_id} attempted a whole-story rewrite",
                validation_errors=validation_errors,
            )
        replacement_scene = _ensure_scene_binding(replacement, failing_plan)
        scenes[failing_index] = replacement_scene
        script = _mapping(story.get("script"))
        if script is None or not isinstance(script.get("scenes"), list):
            raise StoryAuthoringError(
                "assembled story script became invalid during scene repair",
                validation_errors=validation_errors,
            )
        # Replace one list element only; metadata, selection, and all other
        # scene objects retain their original assembled values.
        script["scenes"][failing_index] = deepcopy(replacement_scene)
        repair_rounds.append(
            {
                "round": round_number,
                "scene_id": failing_scene_id,
                "validation_errors": list(validation_errors),
                "addressed_errors": deepcopy(repair.get("addressed_errors") or []),
            }
        )
        validation_errors = tuple(validate_story_document(story, registry))

    if not validation_errors:
        _bind_scene_timing(
            story,
            target_duration_seconds=target_duration_seconds,
        )
        # Keep the public authored-scene view identical to the canonical
        # document after request-owned timing has been bound.
        script = _mapping(story.get("script"))
        canonical_scenes = script.get("scenes") if script is not None else None
        if isinstance(canonical_scenes, list):
            scenes = [
                deepcopy(scene)
                for scene in canonical_scenes
                if isinstance(scene, Mapping)
            ]
        validation_errors = tuple(validate_story_document(story, registry))

    result = _validation_result(
        story=story,
        registry=registry,
        source_digest=source_digest,
        architect=architect,
        authored_scenes=scenes,
        max_repair_rounds=max_repair_rounds,
        validation_errors=validation_errors,
        repair_rounds=repair_rounds,
    )
    if validation_errors:
        repair_note = (
            "; no safe scene-local repair target"
            if max_repair_rounds and not repair_rounds
            else ""
        )
        raise StoryAuthoringError(
            "story authoring validation failed: " + ", ".join(validation_errors) + repair_note,
            validation_errors=validation_errors,
            result=result,
        )

    requested_path = output_path if output_path is not None else story_path
    if requested_path is not None:
        _publish_story(Path(requested_path), story)
    return result


__all__ = [
    "ARCHITECT_OUTPUT_SCHEMA",
    "SCENE_BATCH_OUTPUT_SCHEMA",
    "SCENE_AUTHOR_OUTPUT_SCHEMA",
    "StoryAuthoringError",
    "StoryAuthoringResult",
    "author_story_from_research",
    "build_scene_author_prompt",
    "build_scene_batch_author_prompt",
]
