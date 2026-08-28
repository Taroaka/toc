"""Deterministic projections required after semantic producer repair."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable


class SemanticRepairReconciliationError(RuntimeError):
    """Raised when reconciliation would require guessing story meaning."""


@dataclass(frozen=True)
class SemanticRepairReconciliationResult:
    changed_cut_selectors: tuple[str, ...]
    changed_scene_ids: tuple[str, ...]
    replaced_character_ids: tuple[tuple[str, str], ...]
    unresolved_character_ids: tuple[str, ...]
    script_changed: bool
    manifest_changed: bool
    asset_plan_changed: bool


SCENE_PROJECTION_KEYS = (
    "canonical_scene_index",
    "phase",
    "time_of_day",
    "time_of_day_visual_basis",
    "location_mode",
    "location_sequence",
    "location_segments",
    "importance",
    "target_duration_seconds",
    "estimated_duration_seconds",
    "research_refs",
    "handoff_to_next_scene",
    "terminal_resolution",
    "scene_intent",
    "scene_event",
    "scene_character_state_timeline",
    "scene_film_coverage_plan",
    "scene_state_progression_plan",
    "semantic_contract",
    "scene_cut_coverage_plan",
    "scene_shot_mix_plan",
    "coverage_review",
)

EVENT_TIME_POSITION_BY_BEAT_FUNCTION = {
    "setup": "before_trigger",
    "pressure": "early_action",
    "turn": "trigger_moment",
    "payoff": "consequence",
}

EVENT_TIME_POSITION_BY_COMPLETION_STATE = {
    "pre_action": "before_trigger",
    "scene_start_state": "before_trigger",
    "early_action": "early_action",
    "progressed_state": "mid_action",
    "handoff_state": "consequence",
    "completed_state": "consequence",
}

UNGROUNDED_VISUAL_FILLER = {
    "床や道具に残る痕跡",
    "助力の発生源",
    "変化前後の差",
}

STORY_FUNCTION_BY_ELEMENT_TYPE = {
    "character": "status_marker",
    "object": "proof",
    "location": "threshold",
    "gesture": "pressure",
    "trace": "proof",
    "rule": "deadline",
    "relationship": "obstacle",
    "event": "handoff",
    "visual_evidence": "proof",
}
CONCRETE_STORY_FUNCTIONS = frozenset(
    {
        "obstacle",
        "proof",
        "temptation",
        "deadline",
        "status_marker",
        "secret_holder",
        "memory_trigger",
        "threshold",
        "handoff",
        "contrast",
        "pressure",
        "reward",
        "loss",
    }
)
VISIBLE_PROOF_FIELDS = ("face", "gaze", "posture", "hands", "feet", "distance")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _remove_ungrounded_visual_filler(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_ungrounded_visual_filler(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        cleaned: list[Any] = []
        for item in value:
            projected = _remove_ungrounded_visual_filler(item)
            if projected is not None and projected != "":
                cleaned.append(projected)
        return cleaned
    if isinstance(value, str):
        return "" if value.strip() in UNGROUNDED_VISUAL_FILLER else value
    return value


def _scene_id(scene: dict[str, Any]) -> str:
    return _text(scene.get("scene_id"))


def _selector(scene: dict[str, Any], cut: dict[str, Any], index: int) -> str:
    return _text(cut.get("selector")) or f"scene{_scene_id(scene)}_cut{index:02d}"


def _beats(scene: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    sequence = [
        beat
        for beat in _list(_dict(scene.get("scene_event")).get("event_sequence"))
        if isinstance(beat, dict) and _text(beat.get("beat_id"))
    ]
    order = [_text(beat.get("beat_id")) for beat in sequence]
    return order, {_text(beat.get("beat_id")): beat for beat in sequence}


def _normalize_scene_event_authoring(scene: dict[str, Any]) -> None:
    """Promote repaired concrete events into every scene-level projection."""

    if isinstance(scene.get("scene_intent"), dict):
        scene["scene_intent"] = _remove_ungrounded_visual_filler(
            scene["scene_intent"]
        )
    if isinstance(scene.get("semantic_contract"), dict):
        scene["semantic_contract"] = _remove_ungrounded_visual_filler(
            scene["semantic_contract"]
        )
    scene_event = _dict(
        _remove_ungrounded_visual_filler(scene.get("scene_event"))
    )
    sequence = [
        beat
        for beat in _list(scene_event.get("event_sequence"))
        if isinstance(beat, dict)
    ]
    beats_by_id: dict[str, dict[str, Any]] = {}
    scalar_keys = (
        "primary_subject",
        "where",
        "what_happens",
        "conflict_or_constraint",
        "artifact_continuity_state",
        "visible_action",
        "visible_reaction",
        "immediate_consequence",
        "motion_brief",
        "motion_end_state",
        "motion_attention_target",
    )
    list_keys = (
        "who",
        "object_or_trace",
        "required_visual_evidence",
        "first_frame_excluded_object_ids",
        "allowed_new_reveal_elements",
        "allowed_reveal_info_ids",
    )
    for beat in sequence:
        beat_id = _text(beat.get("beat_id"))
        if not beat_id:
            continue
        concrete = _dict(beat.get("concrete_event"))
        for key in scalar_keys:
            value = _text(concrete.get(key))
            if value:
                beat[key] = value
        for key in list_keys:
            if isinstance(concrete.get(key), list):
                beat[key] = deepcopy(concrete[key])
        if isinstance(concrete.get("who"), list):
            beat["required_roles"] = _unique(concrete["who"])
        for key in (
            "first_frame_character_asset_overrides",
            "visible_character_state",
            "obligation_overrides",
        ):
            if isinstance(concrete.get(key), dict):
                beat[key] = deepcopy(concrete[key])
        obligation_overrides = _dict(concrete.get("obligation_overrides"))
        visible_character_state = _dict(
            concrete.get("visible_character_state")
        )
        if visible_character_state:
            if not _text(visible_character_state.get("posture")):
                visible_character_state["posture"] = _text(
                    concrete.get("visible_action")
                )
            if not _text(visible_character_state.get("gaze")):
                visible_character_state["gaze"] = _text(
                    concrete.get("visible_reaction")
                )
            concrete["visible_character_state"] = visible_character_state
            beat["visible_character_state"] = deepcopy(
                visible_character_state
            )
        motion_attention_target = _text(
            concrete.get("motion_attention_target")
            or beat.get("motion_attention_target")
            or concrete.get("primary_subject")
            or beat.get("primary_subject")
            or concrete.get("visible_reaction")
        )
        if motion_attention_target:
            concrete["motion_attention_target"] = motion_attention_target
            beat["motion_attention_target"] = concrete[
                "motion_attention_target"
            ]
        spatial_transition = _dict(
            obligation_overrides.get("spatial_transition")
        )
        if spatial_transition:
            spatial_updates = {
                "visible_action": _text(concrete.get("visible_action")),
                "visible_reaction": _text(concrete.get("visible_reaction")),
                "motion_attention_target": _text(
                    concrete.get("motion_attention_target")
                    or concrete.get("primary_subject")
                    or concrete.get("visible_reaction")
                ),
                "motion_brief": _text(concrete.get("motion_brief")),
                "motion_end_state": _text(concrete.get("motion_end_state")),
            }
            spatial_transition.update(
                {
                    key: value
                    for key, value in spatial_updates.items()
                    if value
                }
            )
            obligation_overrides["spatial_transition"] = spatial_transition
            concrete["obligation_overrides"] = obligation_overrides
            beat["concrete_event"] = concrete
            beat["obligation_overrides"] = deepcopy(obligation_overrides)
        symbolic_proof = _dict(obligation_overrides.get("symbolic_proof"))
        if symbolic_proof:
            symbolic_scalar_updates = {
                "visible_action": _text(
                    concrete.get("visible_action") or beat.get("visible_action")
                ),
                "visible_reaction": _text(
                    concrete.get("visible_reaction") or beat.get("visible_reaction")
                ),
                "primary_subject": _text(
                    concrete.get("primary_subject") or beat.get("primary_subject")
                ),
                "motion_attention_target": _text(
                    concrete.get("motion_attention_target")
                    or beat.get("motion_attention_target")
                    or concrete.get("primary_subject")
                    or beat.get("primary_subject")
                ),
                "motion_brief": _text(
                    concrete.get("motion_brief") or beat.get("motion_brief")
                ),
                "motion_end_state": _text(
                    concrete.get("motion_end_state")
                    or beat.get("motion_end_state")
                ),
            }
            symbolic_proof.update(
                {
                    key: value
                    for key, value in symbolic_scalar_updates.items()
                    if value
                }
            )
            symbolic_evidence = _list(
                concrete.get("required_visual_evidence")
            ) or _list(beat.get("required_visual_evidence"))
            if symbolic_evidence:
                symbolic_proof["required_visual_evidence"] = deepcopy(
                    symbolic_evidence
                )
            symbolic_roles = _list(concrete.get("who")) or _list(
                beat.get("required_roles")
            )
            if symbolic_roles:
                symbolic_proof["required_roles"] = deepcopy(symbolic_roles)
            obligation_overrides["symbolic_proof"] = symbolic_proof
            concrete["obligation_overrides"] = obligation_overrides
            beat["concrete_event"] = concrete
            beat["obligation_overrides"] = deepcopy(obligation_overrides)
        beats_by_id[beat_id] = beat

        required_roles = set(_unique(beat.get("required_roles") or []))
        grounding = _dict(beat.get("story_grounding"))
        if grounding:
            concrete_story_elements = [
                deepcopy(element)
                for element in _list(grounding.get("concrete_story_elements"))
                if isinstance(element, dict)
            ]
            for element in concrete_story_elements:
                story_function = _text(element.get("story_function"))
                if story_function in CONCRETE_STORY_FUNCTIONS:
                    continue
                inferred = STORY_FUNCTION_BY_ELEMENT_TYPE.get(
                    _text(element.get("element_type"))
                )
                if not inferred:
                    raise SemanticRepairReconciliationError(
                        "concrete story element has no deterministic story function"
                    )
                element["story_function"] = inferred
            if concrete_story_elements:
                grounding["concrete_story_elements"] = concrete_story_elements
        if grounding and "protagonist" not in required_roles:
            grounding["non_replaceable_elements"] = [
                item
                for item in _list(grounding.get("non_replaceable_elements"))
                if not (
                    isinstance(item, dict)
                    and _text(item.get("element_id")) == "protagonist"
                )
            ]
            grounding["concrete_story_elements"] = [
                item
                for item in _list(grounding.get("concrete_story_elements"))
                if not (
                    isinstance(item, dict)
                    and _text(item.get("element_id")) == "protagonist_state"
                )
            ]
            grounding["asset_story_function_usage"] = [
                item
                for item in _list(grounding.get("asset_story_function_usage"))
                if not (
                    isinstance(item, dict)
                    and "protagonist" in _text(item.get("asset_id")).lower()
                )
            ]
        if grounding:
            beat["story_grounding"] = grounding

    turning_event = _dict(scene_event.get("turning_event"))
    if turning_event:
        turn_ids = [
            beat_id
            for beat_id, beat in beats_by_id.items()
            if _text(beat.get("beat_function")) == "turn"
        ]
        turning_ref = _text(turning_event.get("source_event_beat_id"))
        if turn_ids and turning_ref not in turn_ids:
            if len(turn_ids) != 1:
                raise SemanticRepairReconciliationError(
                    "turning event cannot resolve to exactly one turn beat"
                )
            turning_event["source_event_beat_id"] = turn_ids[0]
        elif not turn_ids and turning_ref not in beats_by_id:
            raise SemanticRepairReconciliationError(
                "turning event references an unknown event beat"
            )
        causal_turn = _text(_dict(scene.get("scene_intent")).get("causal_turn"))
        if not causal_turn:
            selected_turn = beats_by_id.get(
                _text(turning_event.get("source_event_beat_id"))
            )
            causal_turn = _text(
                _dict(selected_turn).get("immediate_consequence")
                or _dict(selected_turn).get("what_happens")
            )
        if not causal_turn:
            raise SemanticRepairReconciliationError(
                "turning event has no grounded irreversible change"
            )
        scene_intent_for_turn = _dict(scene.get("scene_intent"))
        if not _text(scene_intent_for_turn.get("causal_turn")):
            scene_intent_for_turn["causal_turn"] = causal_turn
            scene["scene_intent"] = scene_intent_for_turn
        turning_event["irreversible_change"] = causal_turn
        turning_event["causal_turn_ref"] = "scene_intent.causal_turn"
        scene_event["turning_event"] = turning_event

    timeline = _dict(scene.get("scene_character_state_timeline"))
    if timeline:
        characters = [
            character
            for character in _list(timeline.get("characters"))
            if isinstance(character, dict)
        ]
        for character in characters:
            character_name = _text(
                character.get("character_name") or character.get("character_id")
            )
            for state_key in ("start_state", "midpoint_state", "end_state"):
                state = _dict(character.get(state_key))
                if not state:
                    continue
                trigger = beats_by_id.get(
                    _text(state.get("trigger_event_beat_id"))
                )
                if trigger is None:
                    raise SemanticRepairReconciliationError(
                        f"visible proof references an unknown trigger beat for {character_name or '<unknown>'}.{state_key}"
                    )
                trigger = _dict(trigger)
                proof = _dict(state.get("visible_proof"))
                candidates = {
                    "face": [state.get("emotion")],
                    "gaze": [
                        state.get("gaze_target"),
                        trigger.get("motion_attention_target"),
                        trigger.get("visible_reaction"),
                    ],
                    "posture": [
                        state.get("body_state"),
                        trigger.get("visible_action"),
                    ],
                    "hands": [
                        state.get("hands"),
                        trigger.get("visible_action"),
                    ],
                    "feet": [
                        state.get("feet"),
                        trigger.get("motion_end_state"),
                        state.get("body_state"),
                    ],
                    "distance": [
                        state.get("relationship_to_others"),
                        state.get("relationship_shift"),
                        state.get("relationship_after_scene"),
                        trigger.get("motion_end_state"),
                    ],
                }
                for field in VISIBLE_PROOF_FIELDS:
                    if (
                        isinstance(proof.get(field), str)
                        and _text(proof.get(field))
                    ):
                        continue
                    value = next(
                        (
                            _text(candidate)
                            for candidate in candidates[field]
                            if _text(candidate)
                        ),
                        "",
                    )
                    if not value:
                        raise SemanticRepairReconciliationError(
                            f"visible proof cannot be grounded for {character_name or '<unknown>'}.{state_key}.{field}"
                        )
                    labels = {
                        "face": "表情",
                        "gaze": "視線",
                        "posture": "姿勢",
                        "hands": "手元",
                        "feet": "足元",
                        "distance": "距離関係",
                    }
                    proof[field] = f"{labels[field]}: {value}"
                state["visible_proof"] = proof
                character[state_key] = state
        timeline["characters"] = characters
        scene["scene_character_state_timeline"] = timeline

    if sequence:
        final_beat = sequence[-1]
        end_situation = _dict(scene_event.get("end_situation"))
        if end_situation:
            end_situation["character_position"] = "。".join(
                _unique(
                    [
                        final_beat.get("visible_action"),
                        final_beat.get("visible_reaction"),
                    ]
                )
            )
            scene_event["end_situation"] = end_situation

    coverage_plan = _dict(scene.get("scene_cut_coverage_plan"))
    inventory = _list(coverage_plan.get("event_beat_inventory"))
    for record in inventory:
        if not isinstance(record, dict):
            continue
        source_beat = beats_by_id.get(_text(record.get("beat_id")))
        if source_beat is not None:
            record["beat_function"] = _text(
                source_beat.get("beat_function")
            )
    if coverage_plan:
        coverage_plan["event_beat_inventory"] = inventory
        scene["scene_cut_coverage_plan"] = coverage_plan

    scene_intent = _dict(scene.get("scene_intent"))
    handoff_chain = _dict(scene_intent.get("handoff_chain"))
    outgoing_handoff = _dict(handoff_chain.get("outgoing"))
    canonical_handoff = _text(scene.get("handoff_to_next_scene"))
    if outgoing_handoff and canonical_handoff:
        outgoing_handoff["visible_or_audible_form"] = canonical_handoff
        handoff_chain["outgoing"] = outgoing_handoff
        scene_intent["handoff_chain"] = handoff_chain
    obligations = _list(scene_intent.get("story_event_obligations"))
    for obligation in obligations:
        if not isinstance(obligation, dict):
            continue
        source_ids = _unique(
            [
                obligation.get("source_event_beat_id"),
                *_list(obligation.get("source_event_beat_ids")),
            ]
        )
        if not source_ids:
            raise SemanticRepairReconciliationError(
                "story_event_obligation is missing explicit source event beat ids"
            )
        if len(source_ids) != 1:
            raise SemanticRepairReconciliationError(
                "story_event_obligation must resolve to exactly one source event beat"
            )
        beat_id = source_ids[0]
        beat = beats_by_id.get(beat_id)
        if beat is None:
            raise SemanticRepairReconciliationError(
                f"story_event_obligation references missing beat: {beat_id}"
            )
        obligation.update(
            {
                "source_events": [_text(beat.get("what_happens"))],
                "audience_knowledge_delta": _text(
                    beat.get("immediate_consequence")
                ),
                "causal_proof": _text(beat.get("visible_action")),
                "visual_evidence": deepcopy(
                    _list(beat.get("required_visual_evidence"))
                ),
                "required_roles": deepcopy(_list(beat.get("required_roles"))),
            }
        )

    knowledge = _dict(scene_intent.get("audience_knowledge_delta"))
    learned = _unique(knowledge.get("learned_during_scene") or [])
    withheld = _unique(
        [
            *_list(knowledge.get("still_unknown_after_scene")),
            *_list(knowledge.get("forbidden_early_reveals")),
        ]
    )
    leaking_indexes = [
        index
        for index, item in enumerate(learned)
        if any(token in item for token in withheld)
    ]
    if leaking_indexes:
        turning = _dict(scene_event.get("turning_event"))
        irreversible = _text(turning.get("irreversible_change"))
        source_beat = beats_by_id.get(
            _text(turning.get("source_event_beat_id"))
        )
        cause = _text(_dict(source_beat).get("what_happens"))
        if not irreversible or not cause:
            raise SemanticRepairReconciliationError(
                "withheld reveal leaked into audience knowledge without a deterministic turning-event repair"
            )
        repaired = list(learned)
        replacement = (
            f"観客は「{irreversible}」が「{cause}」から生じた不可逆な出来事だと理解する"
        )
        if any(token in replacement for token in withheld):
            raise SemanticRepairReconciliationError(
                "audience knowledge repair still leaks withheld information"
            )
        for index in leaking_indexes:
            repaired[index] = replacement
        knowledge["learned_during_scene"] = _unique(repaired)
        scene_intent["audience_knowledge_delta"] = knowledge
        knowledge_plan = _unique(
            scene_intent.get("audience_knowledge_plan") or []
        )
        if knowledge_plan:
            scene_intent["audience_knowledge_plan"] = _unique(
                replacement
                if any(token in item for token in withheld)
                else item
                for item in knowledge_plan
            )
    scene["scene_intent"] = _remove_ungrounded_visual_filler(scene_intent)
    scene["scene_event"] = scene_event
    if isinstance(scene.get("semantic_contract"), dict):
        scene["semantic_contract"] = _remove_ungrounded_visual_filler(
            scene["semantic_contract"]
        )


def _reconcile_adjacent_scene_handoffs(scenes: list[Any]) -> None:
    """Make each declared incoming boundary equal the previous scene output."""

    previous_scene: dict[str, Any] | None = None
    for candidate in scenes:
        if not isinstance(candidate, dict):
            continue
        if previous_scene is None:
            previous_scene = candidate
            continue
        previous_handoff = _text(previous_scene.get("handoff_to_next_scene"))
        previous_id = _scene_id(previous_scene)
        if not previous_handoff or not previous_id:
            previous_scene = candidate
            continue

        incoming = (
            f"scene{previous_id}から渡る物理的原因: {previous_handoff}"
        )
        scene_intent = _dict(candidate.get("scene_intent"))

        story_specificity = _dict(scene_intent.get("story_specificity"))
        concrete_handoff = _dict(
            story_specificity.get("concrete_handoff")
        )
        if "incoming_trigger" in concrete_handoff:
            concrete_handoff["incoming_trigger"] = incoming
            story_specificity["concrete_handoff"] = concrete_handoff
            scene_intent["story_specificity"] = story_specificity

        handoff_notes = _dict(scene_intent.get("handoff_notes"))
        if "incoming" in handoff_notes:
            handoff_notes["incoming"] = incoming
            scene_intent["handoff_notes"] = handoff_notes

        handoff_chain = _dict(scene_intent.get("handoff_chain"))
        incoming_handoff = _dict(handoff_chain.get("incoming"))
        if "visible_or_audible_form" in incoming_handoff:
            incoming_handoff["visible_or_audible_form"] = incoming
            handoff_chain["incoming"] = incoming_handoff
            scene_intent["handoff_chain"] = handoff_chain

        candidate["scene_intent"] = scene_intent
        previous_scene = candidate


def _sync_contract(
    contract: dict[str, Any],
    *,
    order: list[str],
    beats: dict[str, dict[str, Any]],
    forbidden: list[Any],
    cut_blueprint: dict[str, Any],
) -> None:
    source = _dict(contract.get("source_event_contract"))
    if not source:
        return
    primary_id = _text(source.get("primary_event_beat_id"))
    primary = beats.get(primary_id)
    if primary is None:
        raise SemanticRepairReconciliationError(
            f"missing primary event beat: {primary_id or '<empty>'}"
        )
    source_ids = _unique(
        [primary_id, *(_list(source.get("source_event_beat_ids")))]
    )
    missing = [beat_id for beat_id in source_ids if beat_id not in beats]
    if missing:
        raise SemanticRepairReconciliationError(
            "missing source event beats: " + ", ".join(missing)
        )
    source_beats = [beats[beat_id] for beat_id in source_ids]
    source_indexes = [order.index(beat_id) for beat_id in source_ids]
    max_source_index = max(source_indexes)
    beat_function = _text(primary.get("beat_function"))
    progression = _dict(contract.get("cut_state_progression"))
    completion_state = _text(progression.get("action_completion_state"))
    event_time_position = EVENT_TIME_POSITION_BY_COMPLETION_STATE.get(
        completion_state
    )
    if not event_time_position:
        event_time_position = EVENT_TIME_POSITION_BY_BEAT_FUNCTION.get(
            beat_function
        )
    if not event_time_position:
        primary_index = order.index(primary_id)
        if len(order) == 1:
            event_time_position = "trigger_moment"
        elif primary_index == 0:
            event_time_position = "before_trigger"
        elif primary_index == len(order) - 1:
            event_time_position = "consequence"
        else:
            event_time_position = "mid_action"
    allowed_reveal_ids = _unique(
        value
        for beat in source_beats
        for key in (
            "story_information_revealed_ids",
            "story_information_hinted_ids",
        )
        for value in _list(beat.get(key))
    )
    forbidden_reveal_ids = _unique(
        value
        for index, beat_id in enumerate(order)
        if index > max_source_index
        for key in (
            "story_information_revealed_ids",
            "story_information_hinted_ids",
        )
        for value in _list(beats[beat_id].get(key))
    )
    if _text(progression.get("progression_mode")) == "sequential_state_progression":
        blocked_beat_ids = [
            beat_id
            for index, beat_id in enumerate(order)
            if index > max_source_index
        ]
    else:
        blocked_beat_ids = [
            beat_id
            for beat_id in order
            if beat_id not in source_ids
        ]
    action = _text(primary.get("visible_action"))
    reaction = _text(primary.get("visible_reaction"))
    evidence = deepcopy(_list(primary.get("required_visual_evidence")))
    cut_evidence = _unique(
        [
            *evidence,
            *_list(cut_blueprint.get("must_show")),
            *_list(cut_blueprint.get("visual_evidence")),
        ]
    )
    facts = [
        _text(beat.get("what_happens"))
        for beat in source_beats
        if _text(beat.get("what_happens"))
    ]
    source.update(
        {
            "source_event_beat_ids": deepcopy(source_ids),
            "event_beat_function": beat_function,
            "event_time_position": event_time_position,
            "source_event_summary": _text(primary.get("what_happens")),
            "canonical_source_visible_action": action,
            "source_visible_action": action,
            "source_visible_reaction": reaction,
            "canonical_source_required_visual_evidence": evidence,
            "source_required_visual_evidence": deepcopy(evidence),
            "canonical_event_facts_to_preserve": facts,
            "event_facts_to_preserve": deepcopy(facts),
            "event_facts_not_to_invent": deepcopy(forbidden),
            "allowed_reveal_info_ids": allowed_reveal_ids,
            "forbidden_reveal_info_ids": forbidden_reveal_ids,
            "source_concrete_events": [
                deepcopy(_dict(beat.get("concrete_event")))
                for beat in source_beats
            ],
            "source_story_grounding": [
                deepcopy(_dict(beat.get("story_grounding")))
                for beat in source_beats
            ],
            "source_non_replaceable_elements": [
                deepcopy(element)
                for beat in source_beats
                for element in _list(
                    _dict(beat.get("story_grounding")).get(
                        "non_replaceable_elements"
                    )
                )
                if isinstance(element, dict)
            ],
            "source_story_information_revealed_ids": _unique(
                value
                for beat in source_beats
                for value in _list(beat.get("story_information_revealed_ids"))
            ),
            "source_story_information_hinted_ids": _unique(
                value
                for beat in source_beats
                for value in _list(beat.get("story_information_hinted_ids"))
            ),
        }
    )
    contract["source_event_contract"] = source
    viewer_contract = _dict(contract.get("viewer_contract"))
    if viewer_contract:
        viewer_contract["must_show"] = deepcopy(evidence)
        contract["viewer_contract"] = viewer_contract
    if isinstance(contract.get("must_show"), list):
        contract["must_show"] = deepcopy(evidence)

    context = _dict(contract.get("event_context_for_cut"))
    neighbors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_id in source_ids:
        source_index = order.index(source_id)
        for neighbor_index in (source_index - 1, source_index + 1):
            if not 0 <= neighbor_index < len(order):
                continue
            neighbor_id = order[neighbor_index]
            if neighbor_id in source_ids or neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            neighbors.append(deepcopy(beats[neighbor_id]))
    context.update(
        {
            "derived_from": [
                "scene_event.event_sequence[]",
                "cut_contract.source_event_contract",
            ],
            "editable": False,
            "primary_event_beat": deepcopy(primary),
            "source_event_beats": [deepcopy(beat) for beat in source_beats],
            "neighboring_event_beats": neighbors,
            "forbidden_event_changes": deepcopy(forbidden),
        }
    )
    contract["event_context_for_cut"] = context

    concrete_event = _dict(primary.get("concrete_event"))
    motion_brief = _text(
        cut_blueprint.get("motion_brief")
        or primary.get("motion_brief")
        or concrete_event.get("motion_brief")
    )
    motion_end_state = _text(
        cut_blueprint.get("motion_end_state")
        or primary.get("motion_end_state")
        or concrete_event.get("motion_end_state")
    )
    first_frame = _dict(contract.get("first_frame_contract"))
    first_frame.update(
        {
            "source_event_beat_id": primary_id,
            "event_time_position": event_time_position,
            "action_completion_state": _text(
                progression.get("action_completion_state")
                or first_frame.get("action_completion_state")
            ),
            "event_fact_visible_in_still": action,
            "first_frame_brief": _text(
                cut_blueprint.get("first_frame_brief") or action
            ),
            "must_include": deepcopy(cut_evidence),
        }
    )
    contract["first_frame_contract"] = first_frame

    motion = _dict(contract.get("motion_contract"))
    motion["source_event_beat_id"] = primary_id
    motion["must_not_advance_to_event_beat_ids"] = deepcopy(blocked_beat_ids)
    if motion_brief:
        motion["motion_brief"] = motion_brief
        motion["subject_motion"] = motion_brief
    if motion_end_state:
        motion["end_state"] = motion_end_state
        motion["end_frame_brief"] = motion_end_state
    contract["motion_contract"] = motion

    narration = _dict(contract.get("narration_contract"))
    narration["source_event_beat_ids"] = deepcopy(source_ids)
    narration["must_not_advance_to_event_beat_ids"] = deepcopy(blocked_beat_ids)
    narration["allowed_info_ids"] = _unique(
        [
            *source.get("source_story_information_revealed_ids", []),
            *source.get("source_story_information_hinted_ids", []),
        ]
    )
    contract["narration_contract"] = narration


def _sync_first_frame_visual_plan(
    cut: dict[str, Any],
    *,
    primary: dict[str, Any],
    contract: dict[str, Any],
    cut_blueprint: dict[str, Any],
) -> None:
    image = _dict(cut.get("image_generation"))
    if not image:
        return
    plan = _dict(image.get("first_frame_visual_plan"))
    if plan:
        source = _dict(contract.get("source_event_contract"))
        action = _text(primary.get("visible_action"))
        reaction = _text(primary.get("visible_reaction"))
        evidence = _unique(
            [
                *_list(primary.get("required_visual_evidence")),
                *_list(cut_blueprint.get("must_show")),
                *_list(cut_blueprint.get("visual_evidence")),
            ]
        )
        source_grounding = _dict(plan.get("source_grounding"))
        source_grounding.update(
            {
                "source_event_beat_id": _text(primary.get("beat_id")),
                "source_event_beat_ids": deepcopy(
                    _list(source.get("source_event_beat_ids"))
                ),
                "event_beat_function": _text(primary.get("beat_function")),
                "what_happens": _text(primary.get("what_happens")),
                "visible_action": action,
                "visible_reaction": reaction,
                "event_facts_to_preserve": deepcopy(
                    _list(source.get("event_facts_to_preserve"))
                ),
                "event_facts_not_to_invent": deepcopy(
                    _list(source.get("event_facts_not_to_invent"))
                ),
                "allowed_reveal_info_ids": deepcopy(
                    _list(source.get("allowed_reveal_info_ids"))
                ),
                "forbidden_reveal_info_ids": deepcopy(
                    _list(source.get("forbidden_reveal_info_ids"))
                ),
            }
        )
        plan["source_grounding"] = source_grounding
        visual_translation = _dict(plan.get("visual_translation"))
        visual_translation["concrete_visible_evidence"] = [
            {
                "visible_substitute": item,
                "must_be_drawn_as": item,
            }
            for item in evidence
        ]
        visual_translation["imageable_causal_proof"] = reaction or action
        plan["visual_translation"] = visual_translation
        temporal = _dict(plan.get("temporal_boundary"))
        first_frame = _dict(contract.get("first_frame_contract"))
        temporal["event_time_position"] = _text(
            first_frame.get("event_time_position")
        )
        temporal["action_completion_state"] = _text(
            first_frame.get("action_completion_state")
        )
        first_frame_brief = _text(
            cut_blueprint.get("first_frame_brief") or action
        )
        temporal["event_fact_visible_in_still"] = action
        temporal["first_visible_moment"] = first_frame_brief
        forbidden_facts = _unique(
            [
                *_list(source.get("event_facts_not_to_invent")),
                *_list(source.get("forbidden_reveal_info_ids")),
            ]
        )
        blocked_beats = deepcopy(
            _list(
                _dict(contract.get("motion_contract")).get(
                    "must_not_advance_to_event_beat_ids"
                )
            )
        )
        temporal["not_yet_happened_in_still"] = deepcopy(forbidden_facts)
        temporal["forbidden_future_event_beat_ids"] = blocked_beats
        temporal["forbidden_future_outcomes"] = deepcopy(forbidden_facts)
        plan["temporal_boundary"] = temporal
        motion_affordance = _dict(plan.get("motion_affordance"))
        motion_affordance["must_not_resolve_in_image"] = deepcopy(
            forbidden_facts
        )
        motion_ceiling = _dict(motion_affordance.get("motion_ceiling"))
        motion_ceiling["must_stop_before_event_beat_ids"] = deepcopy(
            blocked_beats
        )
        motion_ceiling["must_not_complete_outcomes"] = deepcopy(
            forbidden_facts
        )
        motion_affordance["motion_ceiling"] = motion_ceiling
        plan["motion_affordance"] = motion_affordance
        image["first_frame_visual_plan"] = plan
    # Any compiled payload is bound to the old plan revision. The existing
    # compiler runs immediately after reconciliation and will restore it.
    image.pop("api_prompt_payload", None)
    cut["image_generation"] = image


def _sync_scene_cuts(scene: dict[str, Any]) -> list[str]:
    order, beats = _beats(scene)
    forbidden = deepcopy(
        _list(_dict(scene.get("scene_event")).get("forbidden_event_changes"))
    )
    changed: list[str] = []
    for index, cut in enumerate(_list(scene.get("cuts")), start=1):
        if not isinstance(cut, dict):
            continue
        before = deepcopy(cut)
        cut_blueprint = _dict(cut.get("cut_blueprint"))
        cut_contract = _dict(cut.get("cut_contract"))
        _sync_contract(
            cut_contract,
            order=order,
            beats=beats,
            forbidden=forbidden,
            cut_blueprint=cut_blueprint,
        )
        cut["cut_contract"] = cut_contract
        scene_contract = _dict(cut.get("scene_contract"))
        if scene_contract:
            _sync_contract(
                scene_contract,
                order=order,
                beats=beats,
                forbidden=forbidden,
                cut_blueprint=cut_blueprint,
            )
            cut["scene_contract"] = scene_contract
        primary_id = _text(
            _dict(cut_contract.get("source_event_contract")).get(
                "primary_event_beat_id"
            )
        )
        if primary_id in beats:
            _sync_first_frame_visual_plan(
                cut,
                primary=beats[primary_id],
                contract=cut_contract,
                cut_blueprint=cut_blueprint,
            )
        if cut != before:
            changed.append(_selector(scene, cut, index))
    return changed


def _project_script_into_manifest(
    script: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    changed: list[str] = []
    script_scenes = {
        _scene_id(scene): scene
        for scene in _list(script.get("scenes"))
        if isinstance(scene, dict) and _scene_id(scene)
    }
    for manifest_scene in _list(manifest.get("scenes")):
        if not isinstance(manifest_scene, dict):
            continue
        scene_id = _scene_id(manifest_scene)
        script_scene = script_scenes.get(scene_id)
        if script_scene is None:
            continue
        before = deepcopy(manifest_scene)
        for key in SCENE_PROJECTION_KEYS:
            if key in script_scene:
                manifest_scene[key] = deepcopy(script_scene[key])
        script_cuts = {
            _selector(script_scene, cut, index): cut
            for index, cut in enumerate(_list(script_scene.get("cuts")), start=1)
            if isinstance(cut, dict)
        }
        for index, manifest_cut in enumerate(
            _list(manifest_scene.get("cuts")), start=1
        ):
            if not isinstance(manifest_cut, dict):
                continue
            script_cut = script_cuts.get(
                _selector(manifest_scene, manifest_cut, index)
            )
            if script_cut is None:
                continue
            for key in ("cut_blueprint", "cut_contract", "scene_contract"):
                if key in script_cut:
                    manifest_cut[key] = deepcopy(script_cut[key])
        if manifest_scene != before:
            changed.append(scene_id)
    return changed


def _validate_scene_and_cut_shape(
    script: dict[str, Any], manifest: dict[str, Any]
) -> None:
    script_scenes = _list(script.get("scenes"))
    manifest_scenes = _list(manifest.get("scenes"))
    if not all(isinstance(scene, dict) for scene in script_scenes):
        raise SemanticRepairReconciliationError(
            "script.scenes must contain only mappings"
        )
    if not all(isinstance(scene, dict) for scene in manifest_scenes):
        raise SemanticRepairReconciliationError(
            "manifest.scenes must contain only mappings"
        )
    script_ids = [_scene_id(scene) for scene in script_scenes]
    manifest_ids = [_scene_id(scene) for scene in manifest_scenes]
    if not all(script_ids) or len(set(script_ids)) != len(script_ids):
        raise SemanticRepairReconciliationError(
            f"script scene ids must be non-empty and unique: {script_ids}"
        )
    if not all(manifest_ids) or len(set(manifest_ids)) != len(manifest_ids):
        raise SemanticRepairReconciliationError(
            f"manifest scene ids must be non-empty and unique: {manifest_ids}"
        )
    if script_ids != manifest_ids:
        raise SemanticRepairReconciliationError(
            "scene id/order mismatch: "
            f"script={script_ids}, manifest={manifest_ids}"
        )
    for script_scene, manifest_scene in zip(
        script_scenes, manifest_scenes, strict=True
    ):
        if not isinstance(script_scene.get("cuts"), list):
            raise SemanticRepairReconciliationError(
                f"scene {_scene_id(script_scene)} script cuts must be a list"
            )
        if not isinstance(manifest_scene.get("cuts"), list):
            raise SemanticRepairReconciliationError(
                f"scene {_scene_id(script_scene)} manifest cuts must be a list"
            )
        script_cuts = script_scene["cuts"]
        manifest_cuts = manifest_scene["cuts"]
        if not all(isinstance(cut, dict) for cut in script_cuts):
            raise SemanticRepairReconciliationError(
                f"scene {_scene_id(script_scene)} script cuts must contain only mappings"
            )
        if not all(isinstance(cut, dict) for cut in manifest_cuts):
            raise SemanticRepairReconciliationError(
                f"scene {_scene_id(script_scene)} manifest cuts must contain only mappings"
            )
        def identities(
            scene: dict[str, Any], cuts: list[dict[str, Any]]
        ) -> list[tuple[str, str, str]]:
            values = [
                (
                    _text(cut.get("cut_id")),
                    _selector(scene, cut, index),
                    _text(cut.get("cut_status") or cut.get("status") or "active").lower(),
                )
                for index, cut in enumerate(cuts, start=1)
            ]
            cut_ids = [value[0] for value in values]
            selectors = [value[1] for value in values]
            if (
                not all(cut_ids)
                or len(set(cut_ids)) != len(cut_ids)
                or len(set(selectors)) != len(selectors)
            ):
                raise SemanticRepairReconciliationError(
                    f"scene {_scene_id(scene)} cut ids/selectors must be non-empty and unique"
                )
            return values

        script_identities = identities(script_scene, script_cuts)
        manifest_identities = identities(manifest_scene, manifest_cuts)
        if script_identities != manifest_identities:
            raise SemanticRepairReconciliationError(
                f"scene {_scene_id(script_scene)} cut identity/order mismatch: "
                f"script={script_identities}, manifest={manifest_identities}"
            )


def _parent_map(asset_plan: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in _list(asset_plan.get("assets")):
        if not isinstance(entry, dict):
            continue
        asset_id = _text(entry.get("asset_id"))
        parent = _text(
            _dict(entry.get("reuse_contract")).get("derived_from_asset_id")
            or _dict(entry.get("generation_plan")).get("derived_from_asset_id")
            or entry.get("derived_from_asset_id")
        )
        if asset_id and parent:
            result[asset_id] = parent
    return result


def _allowed_characters(scene: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    timeline = _dict(scene.get("scene_character_state_timeline"))
    for character in _list(timeline.get("characters")):
        if not isinstance(character, dict):
            continue
        character_id = _text(character.get("character_id"))
        if character_id:
            result.add(character_id)
        result.update(_unique(character.get("appearance_asset_ids") or []))
    return result


def _cut_character_ids(cut: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    contract = _dict(cut.get("cut_contract"))
    result.update(
        _unique(
            _dict(contract.get("asset_dependency")).get(
                "character_ids_required"
            )
            or []
        )
    )
    image = _dict(cut.get("image_generation"))
    result.update(_unique(image.get("character_ids") or []))
    plan = _dict(image.get("first_frame_visual_plan"))
    binding = _dict(plan.get("reference_binding"))
    for reference in _list(binding.get("character_references")):
        if isinstance(reference, dict):
            target = _text(reference.get("target_character_id"))
            if target:
                result.add(target)
    return result


def _ancestor(
    asset_id: str, *, allowed: set[str], parents: dict[str, str]
) -> str | None:
    current = asset_id
    seen: set[str] = set()
    while current and current not in seen:
        if current in allowed:
            return current
        seen.add(current)
        current = parents.get(current, "")
    return None


def _find_scene_replacements(
    document: dict[str, Any], parents: dict[str, str]
) -> tuple[dict[str, dict[str, str]], set[str]]:
    replacements_by_scene: dict[str, dict[str, str]] = {}
    unresolved: set[str] = set()
    for scene in _list(document.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_replacements: dict[str, str] = {}
        allowed = _allowed_characters(scene)
        for cut in _list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            for asset_id in _cut_character_ids(cut):
                if asset_id in allowed:
                    continue
                resolved = _ancestor(asset_id, allowed=allowed, parents=parents)
                if resolved is None:
                    unresolved.add(asset_id)
                else:
                    scene_replacements[asset_id] = resolved
        if scene_replacements:
            replacements_by_scene[_scene_id(scene)] = scene_replacements
    return replacements_by_scene, unresolved


def _replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        replaced = [_replace(item, replacements) for item in value]
        return _unique(replaced) if all(isinstance(item, str) for item in replaced) else replaced
    if not isinstance(value, str):
        return value
    if value in replacements:
        return replacements[value]
    for old, new in replacements.items():
        value = value.replace(f"/{old}.", f"/{new}.")
    return value


def _apply_scene_replacements(
    document: dict[str, Any],
    replacements_by_scene: dict[str, dict[str, str]],
) -> None:
    for scene in _list(document.get("scenes")):
        if not isinstance(scene, dict):
            continue
        replacements = replacements_by_scene.get(_scene_id(scene))
        if not replacements:
            continue
        replaced = _replace(scene, replacements)
        scene.clear()
        scene.update(replaced)


def _refresh_asset_selectors(
    asset_plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    selectors: dict[str, list[str]] = {}
    for scene in _list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        for index, cut in enumerate(_list(scene.get("cuts")), start=1):
            if not isinstance(cut, dict):
                continue
            selector = _selector(scene, cut, index)
            for asset_id in _cut_character_ids(cut):
                selectors.setdefault(asset_id, [])
                if selector not in selectors[asset_id]:
                    selectors[asset_id].append(selector)
    for entry in _list(asset_plan.get("assets")):
        if not isinstance(entry, dict):
            continue
        asset_id = _text(entry.get("asset_id"))
        if asset_id and _text(entry.get("asset_type")).startswith("character"):
            entry["source_script_selectors"] = selectors.get(asset_id, [])


def _asset_kind(entry: dict[str, Any]) -> str:
    asset_type = _text(entry.get("asset_type")).lower()
    if asset_type.startswith("character"):
        return "character"
    if asset_type.startswith("object"):
        return "object"
    if asset_type.startswith("location"):
        return "location"
    return ""


def _asset_catalog(
    asset_plan: dict[str, Any],
) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {
        "character": {},
        "object": {},
        "location": {},
    }
    directories = {
        "character": "characters",
        "object": "objects",
        "location": "locations",
    }
    for entry in _list(asset_plan.get("assets")):
        if not isinstance(entry, dict):
            continue
        kind = _asset_kind(entry)
        asset_id = _text(entry.get("asset_id"))
        if not kind or not asset_id:
            continue
        output = _text(_dict(entry.get("generation_plan")).get("output"))
        catalog[kind][asset_id] = (
            output or f"assets/{directories[kind]}/{asset_id}.png"
        )
    return catalog


def _rebind_document_asset_references(
    document: dict[str, Any], asset_plan: dict[str, Any]
) -> None:
    catalog = _asset_catalog(asset_plan)
    if not any(catalog.values()):
        return
    keys = {
        "character": "character_ids_required",
        "object": "object_ids_required",
        "location": "location_ids_required",
    }
    image_keys = {
        "character": "character_ids",
        "object": "object_ids",
        "location": "location_ids",
    }
    for scene in _list(document.get("scenes")):
        if not isinstance(scene, dict):
            continue
        for index, cut in enumerate(_list(scene.get("cuts")), start=1):
            if not isinstance(cut, dict):
                continue
            selector = _selector(scene, cut, index)
            cut_contract = _dict(cut.get("cut_contract"))
            dependency = _dict(cut_contract.get("asset_dependency"))
            image = _dict(cut.get("image_generation"))
            has_image_projection = bool(image)
            expected: dict[str, list[str]] = {}
            for kind, dependency_key in keys.items():
                expected[kind] = _unique(dependency.get(dependency_key) or [])
                image_ids = _unique(image.get(image_keys[kind]) or [])
                if has_image_projection and image_ids != expected[kind]:
                    raise SemanticRepairReconciliationError(
                        f"{selector} {kind} dependency/image ids mismatch: "
                        f"dependency={expected[kind]}, image={image_ids}"
                    )
                unknown = [
                    asset_id
                    for asset_id in expected[kind]
                    if asset_id not in catalog[kind]
                ]
                if unknown:
                    raise SemanticRepairReconciliationError(
                        f"{selector} unknown {kind} asset ids: "
                        + ", ".join(unknown)
                    )

            for contract_name in ("cut_contract", "scene_contract"):
                contract = _dict(cut.get(contract_name))
                if not contract:
                    continue
                if not isinstance(contract.get("asset_dependency"), dict):
                    continue
                contract_dependency = _dict(contract.get("asset_dependency"))
                for kind, dependency_key in keys.items():
                    declared = _unique(
                        contract_dependency.get(dependency_key) or []
                    )
                    if declared != expected[kind]:
                        raise SemanticRepairReconciliationError(
                            f"{selector} {contract_name} {kind} asset ids mismatch"
                        )
                contract_dependency["reusable_anchor_ids"] = _unique(
                    [
                        *expected["character"],
                        *expected["object"],
                        *expected["location"],
                    ]
                )
                contract["asset_dependency"] = contract_dependency
                cut[contract_name] = contract

            if not has_image_projection:
                continue

            represented_directories = {
                "character": "assets/characters/",
                "object": "assets/objects/",
                "location": "assets/locations/",
            }
            references = [
                ref
                for ref in _unique(image.get("references") or [])
                if not any(
                    catalog[kind]
                    and ref.startswith(represented_directories[kind])
                    for kind in represented_directories
                )
            ]
            references.extend(
                catalog[kind][asset_id]
                for kind in ("character", "object", "location")
                for asset_id in expected[kind]
                if asset_id in catalog[kind]
            )
            image["references"] = _unique(references)

            plan = _dict(image.get("first_frame_visual_plan"))
            binding = _dict(plan.get("reference_binding"))
            existing_character_refs = {
                _text(item.get("target_character_id")): item
                for item in _list(binding.get("character_references"))
                if isinstance(item, dict)
                and _text(item.get("target_character_id"))
            }
            if catalog["character"]:
                character_refs: list[dict[str, Any]] = []
                for asset_id in expected["character"]:
                    item = deepcopy(existing_character_refs.get(asset_id) or {})
                    item["target_character_id"] = asset_id
                    item["path"] = catalog["character"][asset_id]
                    character_refs.append(item)
                binding["character_references"] = character_refs
            if catalog["object"]:
                binding["object_references"] = [
                    catalog["object"][asset_id]
                    for asset_id in expected["object"]
                ]
            if catalog["location"]:
                binding["location_references"] = [
                    catalog["location"][asset_id]
                    for asset_id in expected["location"]
                ]
            plan["reference_binding"] = binding
            image["first_frame_visual_plan"] = plan
            cut["image_generation"] = image


def reconcile_semantic_repair_documents(
    *,
    script: dict[str, Any],
    manifest: dict[str, Any],
    asset_plan: dict[str, Any] | None = None,
) -> SemanticRepairReconciliationResult:
    """Mutate supplied documents into one deterministic repaired projection."""

    if not isinstance(script.get("scenes"), list):
        raise SemanticRepairReconciliationError("script.scenes must be a list")
    if not isinstance(manifest.get("scenes"), list):
        raise SemanticRepairReconciliationError("manifest.scenes must be a list")
    script_before = deepcopy(script)
    manifest_before = deepcopy(manifest)
    caller_asset_plan = asset_plan if isinstance(asset_plan, dict) else None
    asset_before = (
        deepcopy(caller_asset_plan)
        if caller_asset_plan is not None
        else {"assets": []}
    )
    working_script = deepcopy(script_before)
    working_manifest = deepcopy(manifest_before)
    working_asset_plan = deepcopy(asset_before)
    _validate_scene_and_cut_shape(working_script, working_manifest)

    cuts: list[str] = []
    scenes: list[str] = []
    script_scenes = _list(working_script.get("scenes"))
    for scene in script_scenes:
        if isinstance(scene, dict):
            _normalize_scene_event_authoring(scene)
    _reconcile_adjacent_scene_handoffs(script_scenes)
    for scene in script_scenes:
        if isinstance(scene, dict):
            cuts.extend(_sync_scene_cuts(scene))
    scenes.extend(
        _project_script_into_manifest(working_script, working_manifest)
    )
    for scene in _list(working_manifest.get("scenes")):
        if isinstance(scene, dict):
            cuts.extend(_sync_scene_cuts(scene))

    parents = _parent_map(working_asset_plan)
    replacements_by_document: list[dict[str, dict[str, str]]] = []
    replacements: dict[tuple[str, str], None] = {}
    unresolved: set[str] = set()
    for document in (working_script, working_manifest):
        found, missing = _find_scene_replacements(document, parents)
        replacements_by_document.append(found)
        for scene_replacements in found.values():
            for old, new in scene_replacements.items():
                replacements[(old, new)] = None
        unresolved.update(missing)
    if unresolved:
        raise SemanticRepairReconciliationError(
            "unresolved repaired character references: "
            + ", ".join(sorted(unresolved))
        )
    _apply_scene_replacements(working_script, replacements_by_document[0])
    _apply_scene_replacements(working_manifest, replacements_by_document[1])

    _rebind_document_asset_references(working_script, working_asset_plan)
    _rebind_document_asset_references(working_manifest, working_asset_plan)

    _refresh_asset_selectors(working_asset_plan, working_manifest)
    if working_manifest != manifest_before:
        for scene in _list(working_manifest.get("scenes")):
            if not isinstance(scene, dict):
                continue
            old = next(
                (
                    candidate
                    for candidate in _list(manifest_before.get("scenes"))
                    if isinstance(candidate, dict)
                    and _scene_id(candidate) == _scene_id(scene)
                ),
                None,
            )
            if old == scene:
                continue
            scenes.append(_scene_id(scene))
            cuts.extend(
                _selector(scene, cut, index)
                for index, cut in enumerate(_list(scene.get("cuts")), start=1)
                if isinstance(cut, dict)
            )

    result = SemanticRepairReconciliationResult(
        changed_cut_selectors=tuple(_unique(cuts)),
        changed_scene_ids=tuple(_unique(scenes)),
        replaced_character_ids=tuple(sorted(replacements)),
        unresolved_character_ids=(),
        script_changed=working_script != script_before,
        manifest_changed=working_manifest != manifest_before,
        asset_plan_changed=working_asset_plan != asset_before,
    )
    script.clear()
    script.update(working_script)
    manifest.clear()
    manifest.update(working_manifest)
    if caller_asset_plan is not None:
        caller_asset_plan.clear()
        caller_asset_plan.update(working_asset_plan)
    return result
