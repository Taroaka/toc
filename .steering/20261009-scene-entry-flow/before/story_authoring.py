"""Lossless research packing and deterministic story-authoring checks.

The Story Architect and Scene Author are responsible for writing story prose.
This module deliberately does not try to write that prose.  It gives those
authors an ID-addressable copy of every research field and checks the small
number of contracts which must remain deterministic: source-event ownership,
scene lifecycle, references, and neighbouring handoffs.

The functions in this module operate on ordinary dictionaries because the
canonical artifacts are YAML/Markdown documents and may contain extension
keys.  Unknown keys are retained rather than discarded.
"""

from __future__ import annotations

from toc.story_selection import selected_event_order, StorySelectionError

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
import json
from typing import Any


REGISTRY_VERSION = "research_registry_v1"
STORY_CONTRACT_VERSION = "story_scene_contract_v1"


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return None


def _path_value(root: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = root
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _collection(root: Mapping[str, Any], *paths: Sequence[str]) -> list[Any]:
    """Return a collection without changing the source shape.

    A few early research artifacts represented a collection as a mapping keyed
    by ID.  Accepting that form makes the registry useful for both old and new
    research files while keeping each record intact.
    """

    for path in paths:
        value = _path_value(root, path)
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, Mapping):
            return list(value.values())
    return []


def _text_id(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    text = str(value).strip()
    return text


def _record_id(record: Any, id_keys: Sequence[str]) -> str:
    if not isinstance(record, Mapping):
        return ""
    for key in id_keys:
        candidate = _text_id(record.get(key))
        if candidate:
            return candidate
    return ""


def _referenced_ids(records: Iterable[Any], keys: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for key in keys:
            values = record.get(key)
            if isinstance(values, (list, tuple, set)):
                candidates = values
            else:
                candidates = [values]
            for value in candidates:
                item = _text_id(value)
                if item and item not in seen:
                    seen.add(item)
                    result.append(item)
    return result


def _index_records(
    records: Sequence[Any],
    *,
    id_keys: Sequence[str],
    fallback_prefix: str,
    referenced: Sequence[str] = (),
) -> tuple[list[Any], dict[str, Any], list[str]]:
    """Clone records and index them by stable IDs.

    Research templates normally include IDs.  When a legacy record lacks one,
    a referenced ID is used if there is an unambiguous positional match;
    otherwise a deterministic ordinal ID is used.  The generated key is only
    an index key: the original record is never modified.  The returned list
    therefore remains lossless even when duplicate IDs occur.
    """

    cloned_records = [deepcopy(record) for record in records]
    result: dict[str, Any] = {}
    duplicates: list[str] = []
    used_references: set[str] = set()
    fallback_number = 1

    for record in cloned_records:
        key = _record_id(record, id_keys)
        if not key:
            for candidate in referenced:
                candidate_text = _text_id(candidate)
                if candidate_text and candidate_text not in used_references:
                    key = candidate_text
                    used_references.add(candidate_text)
                    break
        if not key:
            while True:
                key = f"{fallback_prefix}_{fallback_number:02d}"
                fallback_number += 1
                if key not in result:
                    break
        if key in result:
            duplicates.append(key)
            # Keep the first record addressable while preserving the duplicate
            # in the lossless ``*_items`` collection.
            continue
        result[key] = record
    return cloned_records, result, duplicates


def _walk_id_fields(value: Any, path: tuple[str, ...] = ()) -> dict[str, list[dict[str, Any]]]:
    """Collect every explicit ``*_id`` field for diagnostics and prompting."""

    found: dict[str, list[dict[str, Any]]] = {}
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = (*path, key_text)
            if key_text.endswith("_id") and not isinstance(child, (Mapping, list, tuple)):
                item_id = _text_id(child)
                if item_id:
                    found.setdefault(item_id, []).append(
                        {"path": ".".join(child_path), "value": deepcopy(child)}
                    )
            nested = _walk_id_fields(child, child_path)
            for item_id, occurrences in nested.items():
                found.setdefault(item_id, []).extend(occurrences)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            nested = _walk_id_fields(child, (*path, str(index)))
            for item_id, occurrences in nested.items():
                found.setdefault(item_id, []).extend(occurrences)
    return found


def build_research_registry(research: Mapping[str, Any]) -> dict[str, Any]:
    """Build a lossless, ID-addressable registry from parsed ``research.md``.

    ``raw_research`` is a deep copy of the complete input and every indexed
    record is also copied in full.  No field is summarized, sliced, or
    truncated.  The conventional aliases (``passages`` and ``source_passages``
    for example) are provided to keep callers independent of the research
    template generation.
    """

    raw: dict[str, Any]
    if isinstance(research, Mapping):
        raw = deepcopy(dict(research))
    else:
        # The public type is Mapping, but returning a valid registry for bad
        # input lets callers report a normal validation error instead of
        # failing while constructing a prompt.
        raw = {}

    event_records = _collection(
        raw,
        ("story_materials", "chronological_events"),
        ("chronological_events",),
    )
    character_records = _collection(
        raw,
        ("story_materials", "characters"),
        ("characters",),
    )
    place_records = _collection(
        raw,
        ("story_materials", "setting", "places"),
        ("setting", "places"),
        ("places",),
    )
    world_rule_records = _collection(
        raw,
        ("story_materials", "setting", "world_rules"),
        ("setting", "world_rules"),
        ("world_rules",),
    )
    symbol_records = _collection(
        raw,
        ("story_materials", "symbols_and_themes"),
        ("symbols_and_themes",),
        ("symbols",),
    )
    passage_records = _collection(raw, ("source_passages",), ("passages",))
    source_records = _collection(raw, ("source_inventory",), ("sources",))
    variant_records = _collection(raw, ("variants",))
    conflict_records = _collection(raw, ("conflicts",))
    fact_records = _collection(raw, ("facts", "items"), ("facts",))
    hook_records = _collection(raw, ("engagement", "hooks"), ("hooks",))
    question_records = _collection(raw, ("open_questions",), ("questions",))

    # Legacy/minimal records sometimes omit a rule/place ID while events still
    # refer to one.  Positional references retain those records in the ID map
    # without pretending that the research prose itself contained another key.
    event_refs_for_places = _referenced_ids(event_records, ("place_ids", "location_ids"))
    event_refs_for_rules = _referenced_ids(event_records, ("world_rule_ids", "rule_ids"))

    event_items, events, event_duplicates = _index_records(
        event_records,
        id_keys=("event_id", "source_event_id", "id"),
        fallback_prefix="event",
    )
    character_items, characters, character_duplicates = _index_records(
        character_records,
        id_keys=("character_id", "person_id", "id"),
        fallback_prefix="character",
    )
    place_items, places, place_duplicates = _index_records(
        place_records,
        id_keys=("place_id", "location_id", "id"),
        fallback_prefix="place",
        referenced=event_refs_for_places,
    )
    world_rule_items, world_rules, world_rule_duplicates = _index_records(
        world_rule_records,
        id_keys=("world_rule_id", "rule_id", "id"),
        fallback_prefix="world_rule",
        referenced=event_refs_for_rules,
    )
    symbol_items, symbols, symbol_duplicates = _index_records(
        symbol_records,
        id_keys=("symbol_id", "item_id", "id"),
        fallback_prefix="symbol",
    )
    passage_items, passages, passage_duplicates = _index_records(
        passage_records,
        id_keys=("passage_id", "id"),
        fallback_prefix="passage",
    )
    source_items, sources, source_duplicates = _index_records(
        source_records,
        id_keys=("source_id", "id"),
        fallback_prefix="source",
    )
    variant_items, variants, variant_duplicates = _index_records(
        variant_records,
        id_keys=("variant_id", "id"),
        fallback_prefix="variant",
    )
    conflict_items, conflicts, conflict_duplicates = _index_records(
        conflict_records,
        id_keys=("conflict_id", "id"),
        fallback_prefix="conflict",
    )
    fact_items, facts, fact_duplicates = _index_records(
        fact_records,
        id_keys=("fact_id", "id"),
        fallback_prefix="fact",
    )
    hook_items, hooks, hook_duplicates = _index_records(
        hook_records,
        id_keys=("hook_id", "id"),
        fallback_prefix="hook",
    )
    question_items, questions, question_duplicates = _index_records(
        question_records,
        id_keys=("question_id", "id"),
        fallback_prefix="question",
    )

    maps: dict[str, dict[str, Any]] = {
        "events": events,
        "characters": characters,
        "places": places,
        "world_rules": world_rules,
        "symbols": symbols,
        "passages": passages,
        "sources": sources,
        "variants": variants,
        "conflicts": conflicts,
        "facts": facts,
        "hooks": hooks,
        "questions": questions,
    }

    # Keep every list as well as its map.  This matters for duplicate IDs and
    # for records that intentionally have no ID yet.
    item_lists: dict[str, list[Any]] = {
        "events": event_items,
        "characters": character_items,
        "places": place_items,
        "world_rules": world_rule_items,
        "symbols": symbol_items,
        "passages": passage_items,
        "sources": source_items,
        "variants": variant_items,
        "conflicts": conflict_items,
        "facts": fact_items,
        "hooks": hook_items,
        "questions": question_items,
    }
    duplicate_ids = {
        name: values
        for name, values in {
            "events": event_duplicates,
            "characters": character_duplicates,
            "places": place_duplicates,
            "world_rules": world_rule_duplicates,
            "symbols": symbol_duplicates,
            "passages": passage_duplicates,
            "sources": source_duplicates,
            "variants": variant_duplicates,
            "conflicts": conflict_duplicates,
            "facts": fact_duplicates,
            "hooks": hook_duplicates,
            "questions": question_duplicates,
        }.items()
        if values
    }

    # ``source_passages`` and ``source_inventory`` are the names in the
    # research template; aliases make validation and prompt consumers simpler.
    registry: dict[str, Any] = {
        "registry_version": REGISTRY_VERSION,
        "raw": deepcopy(raw),
        "raw_research": deepcopy(raw),
        "research": deepcopy(raw),
        "events": events,
        "characters": characters,
        "places": places,
        "world_rules": world_rules,
        "rules": world_rules,
        "symbols": symbols,
        "symbols_and_themes": symbols,
        "passages": passages,
        "source_passages": passages,
        "sources": sources,
        "source_inventory": sources,
        "variants": variants,
        "conflicts": conflicts,
        "facts": facts,
        "hooks": hooks,
        "questions": questions,
        "id_maps": deepcopy(maps),
        "events_by_id": deepcopy(events),
        "characters_by_id": deepcopy(characters),
        "places_by_id": deepcopy(places),
        "world_rules_by_id": deepcopy(world_rules),
        "symbols_by_id": deepcopy(symbols),
        "passages_by_id": deepcopy(passages),
        "sources_by_id": deepcopy(sources),
        "variants_by_id": deepcopy(variants),
        "conflicts_by_id": deepcopy(conflicts),
        "facts_by_id": deepcopy(facts),
        "hooks_by_id": deepcopy(hooks),
        "questions_by_id": deepcopy(questions),
        "items": item_lists,
        "duplicate_ids": duplicate_ids,
        "event_order": list(events),
        "all_ids": sorted(
            {
                item_id
                for category in maps.values()
                for item_id in category
                if _text_id(item_id)
            }
        ),
        "id_occurrences": _walk_id_fields(raw),
    }
    return registry


def research_registry_prompt_view(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Return one lossless research copy plus compact deterministic indexes."""

    return {
        "registry_version": deepcopy(registry.get("registry_version")),
        "raw_research": deepcopy(registry.get("raw_research", {})),
        "story_selection": deepcopy(registry.get("story_selection")),
        "event_order": deepcopy(registry.get("event_order", [])),
        "all_ids": deepcopy(registry.get("all_ids", [])),
        "duplicate_ids": deepcopy(registry.get("duplicate_ids", {})),
        "id_occurrences": deepcopy(registry.get("id_occurrences", {})),
    }


SCENE_CAUSAL_CONNECTION_INSTRUCTION = (
    "For every scene after the first scene, explain why it happens BECAUSE (なぜなら) "
    "of a concrete event, choice, discovery, or unresolved consequence in the immediately "
    "previous scene, never merely AND THEN (そしてそれから). "
    "The Architect must write causal_connection_from_previous in each scene plan: "
    "name the previous cause, its consequence, and the action or constraint it motivates here; "
    "use null for the first scene, which establishes the initial situation. "
    "Scene Authors must preserve this planned reason in the first event_sequence trigger, "
    "start_state, and handoff_chain.incoming, and make the outgoing consequence support "
    "the next scene (the final scene needs no next-scene cause). "
    "Ask whether removing the preceding event would leave this scene equally motivated; "
    "if so, strengthen the source-grounded connection during planning. "
    "Do not invent factual causation or change source chronology to force a link: "
    "explicitly identify unsupported causation as a source gap in the connection and "
    "grounding_note. A temporal or thematic link alone is not causal evidence. "
    "These are design explanations, not mandatory narration connectives. "
    "During repair, preserve the frozen causal reason and source ownership."
)


# Runtime counterpart of docs/story-creation.md: 観客の理解と意味の設計.
# Shared by planning, single/batched scene authoring, and bounded repair.
AUDIENCE_MEANING_INSTRUCTION = (
    "Consider audience understanding and meaning as optional authoring tools, "
    "not another plot formula. Plan what the audience can initially understand, "
    "which source-grounded experiences support or question that understanding, "
    "and what remains at the end. Deepening, confirmation, uncertainty, competing "
    "interpretations, and unchanged characters are valid; do not require positive "
    "growth, a hero, a return, a moral, a reversal, or a resolved ending. "
    "Keep world facts, each character's beliefs, audience knowledge, and intended "
    "affect distinct. Where repetition serves this story, connect an element's "
    "earlier and later context through concrete evidence; an element may be an "
    "action, relationship, sound, situation, place, or object. Repetition and "
    "changed meaning are optional, with no fixed count or mandatory symbol. "
    "Show relevant world rules and viewpoints through choices, behavior, "
    "relationships, and consequences. Ground claims about real cultures, history, "
    "and traditions in research; for fictional worlds follow the authored setting "
    "and mark creative additions explicitly. Do not treat one viewpoint as "
    "everyone's belief. "
    "During architecture, stay at scene-plan scope and preserve source-event "
    "ownership. During scene authoring, use the existing start_state and "
    "end_state audience_knowledge, event_sequence audience_knowledge_delta, "
    "required_visual_evidence, and reveal_contract to make these intentions "
    "concrete. Knowledge may be reinforced or maintained; every beat need not "
    "introduce a new fact. Keep creative interpretation explicit and preserve "
    "source-backed meanings, endings, ambiguity, and reveal order. Do not add "
    "scenes, events, assets, or required schema fields just to fit these tools. "
    "A coping strategy may produce practical success and relational loss at the same time; preserve both source-backed consequences. "
    "External success is not automatically personal growth. A sincere self-explanation can differ from observable action without being a deliberate lie. "
    "Only beliefs important to this character's identity or coping need motivate conflict; do not make every disagreement an identity crisis. "
    "For original fiction these are optional invention tools; for adaptations do not fabricate a wound, motive, conversion, reconciliation, or moral. "
    "A maintained-state scene is valid: conflict and turn can be empty strings and turning_event can be an empty mapping. "
    "When a turn is authored, retain its real beat reference; never invent one to fill the schema. "
    "Each visible beat becomes one cut unless it explicitly supplies ordered cut_transitions. "
    "For a beat needing multiple shots, author cut_transitions with unique transition_id, "
    "first_frame_brief (only the visible start), motion_brief, and motion_end_state. "
    "Keep each transition inside its parent beat; never repeat earlier action after its result. "
    "Supply enough meaningful transitions for the requested scene duration and provider limits; "
    "do not add unrelated gestures to fill time. Preserve source_event_ids on every beat. "
    "During repair, preserve the source-grounded intent and planned reveal order "
    "while correcting fields identified by the supplied structural errors."
)


def build_story_architect_prompt(
    registry: Mapping[str, Any],
    topic: str = "",
    target_duration_seconds: int | float | None = None,
) -> str:
    """Serialize the complete research registry into a Story Architect prompt.

    The return value is valid JSON by design.  Keeping the instructions and
    registry in one JSON document makes it possible to hash/replay the exact
    provider input, while ``ensure_ascii=False`` keeps source prose readable.
    There is intentionally no preview mode, character limit, excerpt, or
    ellipsis substitution here.
    """

    if not isinstance(registry, Mapping):
        registry = build_research_registry({})
    prompt_registry = research_registry_prompt_view(registry)
    payload = {
        "prompt_contract": "story_architect_prompt_v2",
        "role": "Story Architect",
        "instructions": [
            SCENE_CAUSAL_CONNECTION_INSTRUCTION,
            AUDIENCE_MEANING_INSTRUCTION,
            "Use every research field available in full; do not truncate, summarize away, or invent source facts.",
            "When the user specifies a version, honor it. Otherwise select ONE story version most widely familiar to the intended audience; do not choose by publication age, event count, or exhaustiveness. If no audience is specified, consider the general audience of the request language.",
            "Research is a source inventory, not a checklist of scenes to include. Unselected versions and supplementary information need not appear. Never concatenate retellings merely to cover all research events; never silently hybridize conflicting versions.",
            "Record selection.event_selection_contract=story_event_selection_v1, selected_variant_ids (exactly one known variant, or [] for research without variants), selected_event_ids (known IDs in source order), selection_rationale, familiarity_basis, and omitted_events [{event_id, reason}].",
            "Base familiarity_basis on available research and state uncertainty when recognition evidence is limited; do not invent popularity statistics. Use the most familiar supported coherent story, not an obscure variant for novelty. A user-specified version takes priority even when less familiar.",
            "Select events that preserve the chosen story's causal spine, iconic moments and ending. Other events may be omitted for coherence and duration; explain omissions within the selected version in omitted_events. Unselected versions require no event-by-event omission justification.",
            "Assign every selected_event_id exactly once to a semantic scene in chronological order. Coverage applies ONLY to selected_event_ids, never to the full research inventory.",
            "Return only the architectural scene plan at this turn: stable scene_id, title, phase, source_event_ids, incoming_state_id, outgoing_state_id, previous_scene_id, next_scene_id, and causal_connection_from_previous.",
            "Do not author event_sequence or full scene prose in the Architect turn; a dedicated Scene Author will expand each frozen plan.",
            "Keep source-backed facts and creative complements explicitly distinguishable.",
            "Author story_metadata including the research-grounded time/era, and an adaptation_source_contract_v1 whose core values, non-negotiable events, iconic moments and ending belong ONLY to the adopted version and selected events. Do not promote unselected versions or supplementary research into mandatory story requirements, and do not use a generic hero template.",
            "Return a story_scene_contract_v1 document; scene count must follow semantic events rather than duration-only padding.",
        ],
        "topic": topic,
        "target_duration_seconds": target_duration_seconds,
        "truncation": {"policy": "none", "source": "full_research_registry"},
        "research_registry": prompt_registry,
    }
    # ``default`` is deliberately not used: silently stringifying an
    # unsupported object would violate the lossless input contract.
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


def _registry_for_validation(registry: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(registry, Mapping):
        return build_research_registry({})
    if isinstance(registry.get("events"), Mapping):
        return registry
    if isinstance(registry.get("story_materials"), Mapping) or isinstance(
        registry.get("chronological_events"), (list, tuple, Mapping)
    ):
        return build_research_registry(registry)
    return registry


def _map_from_registry(registry: Mapping[str, Any], names: Sequence[str]) -> dict[str, Any]:
    for name in names:
        value = registry.get(name)
        if isinstance(value, Mapping):
            return {_text_id(key): item for key, item in value.items() if _text_id(key)}
    id_maps = registry.get("id_maps")
    if isinstance(id_maps, Mapping):
        for name in names:
            value = id_maps.get(name)
            if isinstance(value, Mapping):
                return {_text_id(key): item for key, item in value.items() if _text_id(key)}
    return {}


def _registry_maps(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "events": _map_from_registry(registry, ("events", "chronological_events")),
        "characters": _map_from_registry(registry, ("characters",)),
        "places": _map_from_registry(registry, ("places", "locations")),
        "world_rules": _map_from_registry(registry, ("world_rules", "rules")),
        "symbols": _map_from_registry(registry, ("symbols", "symbols_and_themes")),
        "passages": _map_from_registry(registry, ("passages", "source_passages")),
        "sources": _map_from_registry(registry, ("sources", "source_inventory")),
        "variants": _map_from_registry(registry, ("variants",)),
        "conflicts": _map_from_registry(registry, ("conflicts",)),
        "facts": _map_from_registry(registry, ("facts",)),
        "hooks": _map_from_registry(registry, ("hooks",)),
        "questions": _map_from_registry(registry, ("questions", "open_questions")),
    }


def _ids(value: Any) -> tuple[list[str], bool]:
    """Return normalized IDs and whether the input had the expected shape."""

    if isinstance(value, (list, tuple)):
        result = [_text_id(item) for item in value if _text_id(item)]
        return result, True
    if value is None:
        return [], False
    item = _text_id(value)
    return ([item] if item else []), False


def _first_present(mapping: Mapping[str, Any], keys: Sequence[str]) -> tuple[Any, bool]:
    for key in keys:
        if key in mapping:
            return mapping.get(key), True
    return None, False


def _scene_event_ids(scene: Mapping[str, Any]) -> tuple[list[str], bool, bool]:
    basis = _mapping(scene.get("source_basis"))
    if basis is not None:
        value, present = _first_present(
            basis,
            ("event_ids", "source_event_ids", "owned_event_ids", "owned_source_event_ids"),
        )
        if present:
            result, shape_ok = _ids(value)
            return result, True, shape_ok
    value, present = _first_present(
        scene,
        ("event_ids", "source_event_ids", "owned_event_ids", "owned_source_event_ids"),
    )
    if present:
        result, shape_ok = _ids(value)
        return result, True, shape_ok
    return [], False, False


def _state_token(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("state_id", "handoff_state_id", "id"):
            token = _text_id(value.get(key))
            if token:
                return token
        try:
            return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return repr(value)
    return _text_id(value)


def _state_id(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("state_id", "handoff_state_id", "id"):
            token = _text_id(value.get(key))
            if token:
                return token
    return _text_id(value)


def _append_error(errors: list[str], code: str) -> None:
    if code not in errors:
        errors.append(code)


def _validate_ids(
    values: Any,
    valid: set[str],
    errors: list[str],
    *,
    malformed_code: str = "story.scene_id_list_invalid",
    unknown_code: str = "story.scene_unknown_id",
) -> list[str]:
    normalized, shape_ok = _ids(values)
    if values is not None and not shape_ok:
        _append_error(errors, malformed_code)
    for item_id in normalized:
        if item_id not in valid:
            _append_error(errors, unknown_code)
    return normalized


def _source_basis(scene: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = scene.get("source_basis")
    return _mapping(value)


def _validate_source_basis(
    scene: Mapping[str, Any],
    maps: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> None:
    basis = _source_basis(scene)
    if basis is None:
        return
    specs = (
        ("event_ids", "events"),
        ("source_event_ids", "events"),
        ("owned_event_ids", "events"),
        ("passage_ids", "passages"),
        ("source_passage_ids", "passages"),
        ("source_ids", "sources"),
        ("character_ids", "characters"),
        ("place_ids", "places"),
        ("location_ids", "places"),
        ("world_rule_ids", "world_rules"),
        ("rule_ids", "world_rules"),
        ("symbol_ids", "symbols"),
        ("fact_ids", "facts"),
        ("conflict_ids", "conflicts"),
        ("variant_ids", "variants"),
    )
    for field, category in specs:
        if field in basis:
            _validate_ids(basis.get(field), set(maps[category]), errors)


def _character_binding_values(registry: Mapping[str, Any]) -> set[str]:
    """Return the exact subject tokens that the downstream character binder accepts.

    Research character records are addressed by their registry key and by the
    source IDs carried in each record.  Their display name is also a valid
    authored subject.  The generated pipeline has one stable protagonist
    alias, ``protagonist``; expose it only when the registry identifies a
    protagonist so an empty or unrelated character registry does not invent a
    subject binding.
    """

    characters = _registry_maps(registry)["characters"]
    values: set[str] = set()
    protagonist_found = False
    for registry_id, record in characters.items():
        registry_id = _text_id(registry_id)
        if registry_id:
            values.add(registry_id)
        if not isinstance(record, Mapping):
            continue
        record_ids = [
            _text_id(record.get(key))
            for key in (
                "character_id",
                "source_character_id",
                "person_id",
                "id",
            )
        ]
        values.update(item_id for item_id in record_ids if item_id)
        name = _text_id(record.get("name"))
        if name:
            values.add(name)
        if (
            registry_id.casefold() == "protagonist"
            or any(item_id.casefold() == "protagonist" for item_id in record_ids if item_id)
            or _text_id(record.get("role")).casefold() == "protagonist"
            or "主人公" in _text_id(record.get("role"))
        ):
            protagonist_found = True
    if protagonist_found:
        values.add("protagonist")
    return values


def _iter_explicit_subject_values(segment: Mapping[str, Any]) -> Iterable[str]:
    """Yield authored subject values from one location segment.

    Only the subject-bearing keys in the segment contract are inspected.  In
    particular, prose such as ``visible_action`` is not searched for names;
    subject binding is an exact field-level contract rather than a substring
    heuristic.
    """

    def value_text(value: Any) -> str:
        # An absent value and an explicitly empty optional value both mean
        # inheritance.  Other shapes remain visible as a non-matching token,
        # which makes malformed authored subject data fail closed.
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value)
        return _text_id(value)

    if "primary_subject" in segment:
        subject = value_text(segment.get("primary_subject"))
        if subject:
            yield subject

    by_function = segment.get("primary_subject_by_function")
    if isinstance(by_function, Mapping):
        for value in by_function.values():
            subject = value_text(value)
            if subject:
                yield subject

    def walk_override(value: Any) -> Iterable[str]:
        if not isinstance(value, Mapping):
            return
        if "primary_subject" in value:
            subject = value_text(value.get("primary_subject"))
            if subject:
                yield subject
        obligation_overrides = value.get("obligation_overrides")
        if isinstance(obligation_overrides, Mapping):
            for obligation_override in obligation_overrides.values():
                yield from walk_override(obligation_override)

    beat_overrides = segment.get("beat_overrides")
    if isinstance(beat_overrides, Mapping):
        for override in beat_overrides.values():
            yield from walk_override(override)


def _validate_segment_subject_bindings(
    scene: Mapping[str, Any],
    registry: Mapping[str, Any],
    errors: list[str],
) -> None:
    """Reject authored segment subjects that cannot resolve to one character.

    This runs at the story/scene boundary, before p420 materializes cut
    blueprints.  Optional subject fields are not required; when present they
    must be one exact supported name, ID, or protagonist alias.
    """

    location = _mapping(scene.get("location"))
    if location is None:
        return
    segments = location.get("segments")
    if not isinstance(segments, (list, tuple)):
        return
    supported = _character_binding_values(registry)
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        if any(subject not in supported for subject in _iter_explicit_subject_values(segment)):
            _append_error(errors, "story.scene_primary_subject_binding_invalid")
            return


def _validate_scene_references(
    scene: Mapping[str, Any],
    maps: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> None:
    """Validate source-facing IDs in scene and authored beats."""

    all_source_ids = set().union(*(set(category) for category in maps.values()))
    _validate_source_basis(scene, maps, errors)

    # Direct scene-level references are accepted as a convenience for author
    # adapters which have not nested them under source_basis yet.
    direct_specs = (
        ("character_ids", "characters"),
        ("place_ids", "places"),
        ("location_ids", "places"),
        ("world_rule_ids", "world_rules"),
        ("rule_ids", "world_rules"),
        ("symbol_ids", "symbols"),
        ("fact_ids", "facts"),
        ("source_ids", "sources"),
        ("passage_ids", "passages"),
    )
    for field, category in direct_specs:
        if field in scene:
            _validate_ids(scene.get(field), set(maps[category]), errors)

    research_refs = scene.get("research_refs")
    if research_refs is not None:
        refs, shape_ok = _ids(research_refs)
        if not shape_ok:
            _append_error(errors, "story.scene_id_list_invalid")
        for ref in refs:
            # Dotted source paths such as research.story_materials[...] are
            # valid trace references rather than registry IDs.
            if ref.startswith("research."):
                continue
            if ref not in all_source_ids:
                _append_error(errors, "story.scene_unknown_id")

    sequence = _list(scene.get("event_sequence"))
    if sequence is None:
        for alternate in ("events", "beats"):
            sequence = _list(scene.get(alternate))
            if sequence is not None:
                break
    if sequence is None:
        return

    for beat in sequence:
        if not isinstance(beat, Mapping):
            _append_error(errors, "story.scene_event_sequence_invalid")
            continue
        beat_values, present = _first_present(beat, ("source_event_ids", "event_ids"))
        if not present and "source_event_id" in beat:
            beat_values = [beat.get("source_event_id")]
            present = True
        if present:
            _validate_ids(beat_values, set(maps["events"]), errors)
        for field, category in (
            ("participants", "characters"),
            ("character_ids", "characters"),
            ("place_ids", "places"),
            ("location_ids", "places"),
            ("world_rule_ids", "world_rules"),
            ("rule_ids", "world_rules"),
            ("symbol_ids", "symbols"),
            ("fact_ids", "facts"),
            ("conflict_ids", "conflicts"),
        ):
            if field in beat:
                _validate_ids(beat.get(field), set(maps[category]), errors)
        if "location_id" in beat:
            # ``location_id`` is singular in a beat; normalize it to a list
            # before applying the list-shaped reference validator.
            _validate_ids([beat.get("location_id")], set(maps["places"]), errors)
        if "source_refs" in beat:
            refs, shape_ok = _ids(beat.get("source_refs"))
            if not shape_ok:
                _append_error(errors, "story.scene_id_list_invalid")
            for ref in refs:
                if ref.startswith("research."):
                    continue
                if ref not in all_source_ids:
                    _append_error(errors, "story.scene_unknown_id")


def _sequence_beats(scene: Mapping[str, Any]) -> list[Any] | None:
    for field in ("event_sequence", "events", "beats"):
        value = _list(scene.get(field))
        if value is not None:
            return value
    return None


def _validate_scene_authoring_surface(
    scene: Mapping[str, Any], errors: list[str]
) -> None:
    """Keep the rich author output consumable by the existing p300/p400 lane."""

    for field in (
        "title",
        "phase",
        "purpose",
        "visualizable_action",
        "grounding_note",
        "time_of_day",
    ):
        if not _text_id(scene.get(field)):
            _append_error(errors, "story.scene_overview_missing")
    for field in ("conflict", "turn"):
        if not isinstance(scene.get(field), str):
            _append_error(errors, "story.scene_overview_missing")
    if not isinstance(scene.get("affect"), Mapping):
        _append_error(errors, "story.scene_overview_missing")
    location = _mapping(scene.get("location"))
    if location is None or not _text_id(location.get("name")):
        _append_error(errors, "story.scene_location_invalid")
    visual_basis = _text_id(scene.get("time_of_day_visual_basis"))
    if not visual_basis or any(
        dimension not in visual_basis
        for dimension in ("光源", "明るさ", "影", "色温度")
    ):
        _append_error(errors, "story.scene_time_of_day_visual_basis_invalid")


def _beat_source_ids(beat: Mapping[str, Any]) -> list[str]:
    value, present = _first_present(beat, ("source_event_ids", "event_ids"))
    if present:
        return _ids(value)[0]
    if "source_event_id" in beat:
        return _ids([beat.get("source_event_id")])[0]
    return []


def _validate_scene_lifecycle(
    scene: Mapping[str, Any],
    errors: list[str],
) -> tuple[str, str]:
    """Check authored lifecycle fields and return start/end state tokens."""

    required_maps = (
        "scene_intent",
        "start_state",
        "turning_event",
        "end_state",
        "handoff_chain",
    )
    missing = False
    for field in required_maps:
        if not isinstance(scene.get(field), Mapping):
            missing = True
    if not isinstance(scene.get("preservation"), Mapping) and not isinstance(
        scene.get("reveal_contract"), Mapping
    ):
        missing = True
    beats = _sequence_beats(scene)
    if not beats:
        missing = True
    if missing:
        _append_error(errors, "story.scene_lifecycle_missing")

    start = _mapping(scene.get("start_state")) or {}
    end = _mapping(scene.get("end_state")) or {}
    start_token = _state_token(start)
    end_token = _state_token(end)
    start_id = _state_id(start)
    end_id = _state_id(end)

    turning = _mapping(scene.get("turning_event"))
    if turning and beats is not None:
        turning_beat_id = _text_id(turning.get("beat_id") or turning.get("event_beat_id"))
        beat_ids = {
            _text_id(beat.get("beat_id"))
            for beat in beats
            if isinstance(beat, Mapping) and _text_id(beat.get("beat_id"))
        }
        if not turning_beat_id or turning_beat_id not in beat_ids:
            _append_error(errors, "story.scene_turning_event_invalid")
        if not _text_id(
            turning.get("irreversible_change")
            or turning.get("change")
            or turning.get("what_changes")
        ):
            _append_error(errors, "story.scene_turning_event_invalid")

    if beats is not None:
        for beat in beats:
            if not isinstance(beat, Mapping):
                _append_error(errors, "story.scene_event_sequence_invalid")
                continue
            if not _text_id(beat.get("beat_id")):
                _append_error(errors, "story.scene_event_sequence_invalid")
            source_ids = _beat_source_ids(beat)
            if not source_ids:
                _append_error(errors, "story.scene_event_sequence_coverage")
            if not _text_id(
                beat.get("what_happens")
                or beat.get("concrete_event")
                or beat.get("action")
            ):
                _append_error(errors, "story.scene_event_sequence_invalid")
            if not _text_id(beat.get("immediate_consequence") or beat.get("consequence")):
                _append_error(errors, "story.scene_event_sequence_invalid")
            participants = beat.get("participants") or beat.get("character_ids")
            locations = (
                beat.get("location_id")
                or beat.get("place_ids")
                or beat.get("location_ids")
                or beat.get("location")
            )
            visual_evidence = beat.get("required_visual_evidence")
            if (
                not participants
                or not locations
                or not isinstance(visual_evidence, (list, tuple))
                or not any(_text_id(item) for item in visual_evidence)
                or not _text_id(
                    beat.get("visible_action")
                    or (_mapping(beat.get("action")) or {}).get("visible_action")
                )
            ):
                _append_error(errors, "story.scene_event_beat_grounding_missing")

    return start_id or start_token, end_id or end_token


def _validate_handoffs(
    scenes: Sequence[Any],
    scene_states: Mapping[str, tuple[str, str]],
    errors: list[str],
) -> None:
    scene_ids = [
        _text_id(scene.get("scene_id"))
        for scene in scenes
        if isinstance(scene, Mapping) and _text_id(scene.get("scene_id"))
    ]
    for index, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            continue
        scene_id = _text_id(scene.get("scene_id"))
        if not scene_id:
            continue
        start, end = scene_states.get(scene_id, ("", ""))
        chain = _mapping(scene.get("handoff_chain"))
        if chain is None:
            continue
        incoming = _mapping(chain.get("incoming")) or {}
        outgoing = _mapping(chain.get("outgoing")) or {}
        incoming_state = _state_token(incoming.get("state_id") or incoming.get("state"))
        outgoing_state = _state_token(outgoing.get("state_id") or outgoing.get("state"))
        if start and incoming_state and start != incoming_state:
            _append_error(errors, "story.scene_handoff_state_mismatch")
        if end and outgoing_state and end != outgoing_state:
            _append_error(errors, "story.scene_handoff_state_mismatch")

        expected_previous = scene_ids[index - 1] if index else ""
        expected_next = scene_ids[index + 1] if index + 1 < len(scene_ids) else ""
        producer = _text_id(incoming.get("producer_scene_id"))
        consumer = _text_id(outgoing.get("consumer_scene_id"))
        if expected_previous:
            if producer and producer != expected_previous:
                _append_error(errors, "story.scene_handoff_reference_mismatch")
        elif producer:
            _append_error(errors, "story.scene_handoff_reference_mismatch")
        if expected_next:
            if consumer and consumer != expected_next:
                _append_error(errors, "story.scene_handoff_reference_mismatch")
        elif consumer:
            _append_error(errors, "story.scene_handoff_reference_mismatch")

        if isinstance(scene.get("start_state"), Mapping):
            incoming_from = _text_id(scene["start_state"].get("incoming_from"))
            if expected_previous and incoming_from and incoming_from != expected_previous:
                _append_error(errors, "story.scene_handoff_reference_mismatch")
            if not expected_previous and incoming_from:
                _append_error(errors, "story.scene_handoff_reference_mismatch")

    for previous, current in zip(scenes, scenes[1:]):
        if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
            continue
        previous_id = _text_id(previous.get("scene_id"))
        current_id = _text_id(current.get("scene_id"))
        previous_start, previous_end = scene_states.get(previous_id, ("", ""))
        current_start, _current_end = scene_states.get(current_id, ("", ""))
        if previous_end and current_start and previous_end != current_start:
            _append_error(errors, "story.scene_handoff_state_mismatch")

        previous_chain = _mapping(previous.get("handoff_chain")) or {}
        current_chain = _mapping(current.get("handoff_chain")) or {}
        previous_outgoing = _mapping(previous_chain.get("outgoing")) or {}
        current_incoming = _mapping(current_chain.get("incoming")) or {}
        previous_outgoing_state = _state_token(
            previous_outgoing.get("state_id") or previous_outgoing.get("state")
        )
        current_incoming_state = _state_token(
            current_incoming.get("state_id") or current_incoming.get("state")
        )
        if (
            previous_outgoing_state
            and current_incoming_state
            and previous_outgoing_state != current_incoming_state
        ):
            _append_error(errors, "story.scene_handoff_state_mismatch")


_REVEAL_RANK = {
    "withheld": 0,
    "unknown": 0,
    "hinted": 1,
    "suspected": 1,
    "revealed": 2,
    "carried": 2,
    "known": 3,
}


def _reveal_side(scene: Mapping[str, Any], side: str) -> Any:
    keys = (
        f"reveal_state_{side}",
        f"audience_knowledge_{side}",
        f"knowledge_{side}",
        f"{side}_reveal_state",
    )
    value, present = _first_present(scene, keys)
    if present:
        return value
    for container_name in ("reveal_contract", "preservation", "scene_intent"):
        container = _mapping(scene.get(container_name))
        if container is None:
            continue
        value, present = _first_present(container, keys)
        if present:
            return value
        value, present = _first_present(container, (side, f"{side}_state"))
        if present:
            return value
    return None


def _reveal_pairs(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, Mapping):
        result: list[tuple[str, str]] = []
        for key, state in value.items():
            if isinstance(state, Mapping):
                state_value = state.get("state") or state.get("status") or state.get("reveal_state")
            else:
                state_value = state
            state_text = _text_id(state_value).lower()
            if state_text in _REVEAL_RANK:
                result.append((_text_id(key) or "__scene__", state_text))
        return result
    state_text = _text_id(value).lower()
    if state_text in _REVEAL_RANK:
        return [("__scene__", state_text)]
    return []


def _validate_reveal_monotonicity(scenes: Sequence[Any], errors: list[str]) -> None:
    previous_after: dict[str, str] = {}
    for scene in scenes:
        if not isinstance(scene, Mapping):
            continue
        before = dict(_reveal_pairs(_reveal_side(scene, "before")))
        after = dict(_reveal_pairs(_reveal_side(scene, "after")))
        for info_id, state in after.items():
            prior = before.get(info_id)
            if prior and _REVEAL_RANK[state] < _REVEAL_RANK[prior]:
                _append_error(errors, "story.scene_reveal_state_rollback")
        for info_id, state in before.items():
            prior = previous_after.get(info_id)
            if prior and _REVEAL_RANK[state] < _REVEAL_RANK[prior]:
                _append_error(errors, "story.scene_reveal_state_rollback")
        previous_after.update(after)


def validate_story_document(
    story: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[str]:
    """Return deterministic contract error keys for an authored story.

    An empty list means the document satisfies the checks implemented here.
    The function intentionally returns stable reason keys rather than prose so
    a repair loop can send only the failing scene/key back to the same author.
    """

    errors: list[str] = []
    if not isinstance(story, Mapping):
        return ["story.document_invalid"]
    registry = _registry_for_validation(registry)
    maps = _registry_maps(registry)
    try:
        expected_event_order = selected_event_order(story, registry)
    except StorySelectionError as exc:
        return [str(exc)]

    script = _mapping(story.get("script"))
    scenes_value = script.get("scenes") if script is not None else None
    scenes = _list(scenes_value)
    if script is None or scenes is None:
        return ["story.scenes_missing"]

    scene_ids: list[str] = []
    scene_event_ids: list[str] = []
    scene_states: dict[str, tuple[str, str]] = {}
    seen_scene_ids: set[str] = set()

    for scene in scenes:
        if not isinstance(scene, Mapping):
            _append_error(errors, "story.scene_invalid")
            continue
        scene_id = _text_id(scene.get("scene_id"))
        if not scene_id:
            _append_error(errors, "story.scene_id_missing")
        elif scene_id in seen_scene_ids:
            _append_error(errors, "story.scene_id_duplicate")
        else:
            seen_scene_ids.add(scene_id)
            scene_ids.append(scene_id)

        owned, owned_present, owned_shape_ok = _scene_event_ids(scene)
        if not owned_present or not owned_shape_ok:
            _append_error(errors, "story.scene_source_event_coverage")
        scene_event_ids.extend(owned)
        _validate_scene_authoring_surface(scene, errors)
        _validate_scene_references(scene, maps, errors)
        _validate_segment_subject_bindings(scene, registry, errors)

        beats = _sequence_beats(scene)
        if beats is not None:
            beat_event_ids: list[str] = []
            for beat in beats:
                if isinstance(beat, Mapping):
                    beat_event_ids.extend(_beat_source_ids(beat))
            if set(owned) - set(beat_event_ids):
                _append_error(errors, "story.scene_event_sequence_coverage")
            if set(beat_event_ids) - set(owned):
                _append_error(errors, "story.scene_event_ownership_mismatch")

        if scene_id:
            scene_states[scene_id] = _validate_scene_lifecycle(scene, errors)
        else:
            _validate_scene_lifecycle(scene, errors)

    if expected_event_order:
        expected_set = set(expected_event_order)
        actual_set = set(scene_event_ids)
        if actual_set != expected_set or len(scene_event_ids) != len(expected_event_order):
            _append_error(errors, "story.scene_source_event_coverage")
        if len(scene_event_ids) != len(set(scene_event_ids)):
            _append_error(errors, "story.scene_source_event_duplicate")
        if (
            actual_set == expected_set
            and len(scene_event_ids) == len(expected_event_order)
            and scene_event_ids != expected_event_order
        ):
            _append_error(errors, "story.scene_source_event_order")

    _validate_handoffs(scenes, scene_states, errors)
    _validate_reveal_monotonicity(scenes, errors)
    return errors


__all__ = [
    "REGISTRY_VERSION",
    "STORY_CONTRACT_VERSION",
    "build_research_registry",
    "build_story_architect_prompt",
    "research_registry_prompt_view",
    "validate_story_document",
]
