"""Canonical script and scene/cut evaluation policy."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from toc.cut_context_packet import WARNING_KEY_BY_DIAGNOSTIC, cut_context_packet_issue_map
from toc.harness import load_structured_document

from .common import (
    CONCRETE_STORY_ELEMENT_FUNCTIONS,
    EVENT_TIME_POSITION_VALUES,
    FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS,
    GENERIC_HANDOFF_ONLY_PHRASES,
    GENERIC_SCENE_TEMPLATE_PHRASES,
    IMAGE_API_PROMPT_POLICY_VERSION,
    SCENE_COVERAGE_REVIEW_REQUIRED_KEYS,
    SCENE_GENERATION_REQUIRED_BLOCKS,
    SCENE_GENERATION_REQUIRED_OUTPUTS,
    SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE,
    SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE,
    SCENE_PROMPT_PAYLOAD_FORBIDDEN_DOWNSTREAM_FIELDS,
    STORY_GROUNDING_SOURCE_ORIGINS,
    TRIANGULATION_REQUIRED_KEYS,
    VISIBLE_BEHAVIOR_FIELDS,
    _append_grounding_checks,
    _append_rubric_findings,
    _contract_string,
    _cut_contract_complete,
    _cut_source_event_contract,
    _node_cut_contract,
    _scene_cut_selector,
    add_check,
    as_dict,
    as_dotted_str,
    as_int,
    as_list,
    contract_list,
    flatten_text,
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
)
from .research_story import _image_api_prompt_policy, _script_rubric

def _script_text_quality_checks(checks: list[dict[str, Any]], text: str, data: dict[str, Any], profile: str) -> None:
    meaningful_len = len("".join(text.split()))
    add_check(checks, "script.content_length", meaningful_len >= 80, f"script content length is meaningful (got {meaningful_len} chars)", kind="rubric")
    if profile == "standard":
        add_check(checks, "script.no_todo", not has_todo(text), "script does not contain TODO/TBD markers", kind="rubric")
    generic_hits = [phrase for phrase in GENERIC_SCENE_TEMPLATE_PHRASES if phrase in text]
    add_check(
        checks,
        "script.no_generic_scene_template_phrases",
        not generic_hits,
        "script scene design does not rely on banned generic scene placeholders"
        + (f" (hits: {', '.join(generic_hits)})" if generic_hits else ""),
        kind="rubric",
    )

    scenes = []
    if isinstance(data.get("scenes"), list):
        scenes = as_list(data.get("scenes"))
    elif isinstance(nested_get(data, ["script", "scenes"], []), list):
        scenes = as_list(nested_get(data, ["script", "scenes"], []))
    if scenes:
        add_check(checks, "script.structured_scenes", len(scenes) >= 1, "structured script includes scene list", kind="rubric")


def _scene_has_intent(scene: dict[str, Any]) -> bool:
    return not _scene_intent_issue_map(scene)


def _scene_id_for_issue(scene: dict[str, Any], fallback: str = "?") -> str:
    return as_dotted_str(scene.get("scene_id")) or str(scene.get("scene_id") or fallback)


def _dict_has_any_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(non_empty(v) for v in value.values())
    if isinstance(value, list):
        return bool(value)
    return non_empty(value)


def _contains_generic_scene_language(value: Any) -> bool:
    text = flatten_text(value)
    return any(phrase in text for phrase in GENERIC_SCENE_TEMPLATE_PHRASES)


def _looks_only_generic_handoff(value: Any) -> bool:
    text = "".join(flatten_text(value).split())
    return bool(text) and len(text) <= 18 and any(phrase in text for phrase in GENERIC_HANDOFF_ONLY_PHRASES)


def _has_story_specific_terms(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return sum(1 for item in value if str(item).strip()) >= 2


def _has_actor_force_pressure(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    people_keys = ("protagonist", "opposing", "helping", "observing", "witness", "community", "authority")
    has_people = any(non_empty(value.get(key)) for key in people_keys)
    pressure_keys = ("pressure_method", "pressure", "visible_pressure", "obstacle", "leverage")
    has_pressure = any(non_empty(value.get(key)) for key in pressure_keys)
    return has_people and has_pressure


def _scene_intent_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "dramatic_question": [],
        "value_shift": [],
        "causal_turn": [],
        "visual_thesis": [],
        "story_specificity": [],
        "conflict_engine": [],
        "handoff_chain": [],
        "coverage_review": [],
    }
    intent = scene.get("scene_intent")
    if not isinstance(intent, dict):
        for key in issues:
            issues[key].append(f"scene{scene_id}:scene_intent")
        return {key: values for key, values in issues.items() if values}
    required_keys = {
        "story_purpose",
        "dramatic_question",
        "scene_spine",
        "value_shift",
        "causal_turn",
        "audience_information",
        "withheld_information",
        "reveal_constraints",
        "affect_transition",
        "character_state",
        "visual_thesis",
        "story_specificity",
        "visual_value_source",
        "production_risks",
        "handoff_notes",
    }
    missing_required = sorted(required_keys - set(intent))
    if missing_required:
        issues["story_specificity"].extend(f"scene{scene_id}:scene_intent.{key}" for key in missing_required)
    if not non_empty(intent.get("story_purpose")):
        issues["story_specificity"].append(f"scene{scene_id}:story_purpose")
    if not non_empty(intent.get("affect_transition")):
        issues["story_specificity"].append(f"scene{scene_id}:affect_transition")
    if not isinstance(intent.get("handoff_notes"), dict):
        issues["handoff_chain"].append(f"scene{scene_id}:handoff_notes")

    if not non_empty(intent.get("dramatic_question")):
        issues["dramatic_question"].append(f"scene{scene_id}:dramatic_question")
    if not non_empty(intent.get("scene_spine")):
        issues["dramatic_question"].append(f"scene{scene_id}:scene_spine")
    if not non_empty(intent.get("causal_turn")):
        issues["causal_turn"].append(f"scene{scene_id}:causal_turn")
    if not non_empty(intent.get("visual_thesis")):
        issues["visual_thesis"].append(f"scene{scene_id}:visual_thesis")

    value_shift = intent.get("value_shift")
    if not isinstance(value_shift, dict):
        issues["value_shift"].append(f"scene{scene_id}:value_shift")
    else:
        for key in ("from", "to"):
            if not non_empty(value_shift.get(key)):
                issues["value_shift"].append(f"scene{scene_id}:value_shift.{key}")
        if not as_list(value_shift.get("visible_evidence")):
            issues["value_shift"].append(f"scene{scene_id}:value_shift.visible_evidence")

    character_state = intent.get("character_state")
    if not isinstance(character_state, dict):
        issues["story_specificity"].append(f"scene{scene_id}:character_state")
    else:
        for key in ("start", "end"):
            if not non_empty(character_state.get(key)):
                issues["story_specificity"].append(f"scene{scene_id}:character_state.{key}")
        if not as_list(character_state.get("visible_behavior")):
            issues["story_specificity"].append(f"scene{scene_id}:character_state.visible_behavior")

    specificity = intent.get("story_specificity")
    if not isinstance(specificity, dict):
        issues["story_specificity"].append(f"scene{scene_id}:story_specificity")
    else:
        for key in ("non_compressible_beat", "scene_promotion_reason", "unique_scene_responsibility"):
            if not non_empty(specificity.get(key)):
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.{key}")
        if not _dict_has_any_value(specificity.get("actor_forces")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.actor_forces")
        elif not _has_actor_force_pressure(specificity.get("actor_forces")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.actor_forces.pressure_method")
        if not _dict_has_any_value(specificity.get("meaning_ladder")):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.meaning_ladder")
        concrete_handoff = specificity.get("concrete_handoff")
        if not isinstance(concrete_handoff, dict):
            issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff")
        else:
            for key in ("incoming_trigger", "outgoing_anchor", "outgoing_pressure"):
                if not non_empty(concrete_handoff.get(key)):
                    issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff.{key}")
                elif _looks_only_generic_handoff(concrete_handoff.get(key)):
                    issues["handoff_chain"].append(f"scene{scene_id}:story_specificity.concrete_handoff.{key}.generic")
        anti_template = specificity.get("anti_template_language")
        if not isinstance(anti_template, dict):
            issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language")
        else:
            if anti_template.get("banned_generic_phrases_absent") is not True:
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language.banned_generic_phrases_absent")
            if not _has_story_specific_terms(anti_template.get("story_specific_terms")):
                issues["story_specificity"].append(f"scene{scene_id}:story_specificity.anti_template_language.story_specific_terms")

    conflict_engine = intent.get("scene_conflict_engine")
    if not isinstance(conflict_engine, dict):
        issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine")
    else:
        for key in ("desire", "obstacle", "stakes", "escalation", "no_return_point"):
            if not non_empty(conflict_engine.get(key)):
                issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine.{key}")
        if not as_list(conflict_engine.get("visible_pressure")):
            issues["conflict_engine"].append(f"scene{scene_id}:scene_conflict_engine.visible_pressure")

    knowledge_delta = intent.get("audience_knowledge_delta")
    if not isinstance(knowledge_delta, dict):
        issues["dramatic_question"].append(f"scene{scene_id}:audience_knowledge_delta")
    else:
        for key in ("before_scene", "learned_during_scene", "still_unknown_after_scene", "forbidden_early_reveals"):
            if not as_list(knowledge_delta.get(key)):
                issues["dramatic_question"].append(f"scene{scene_id}:audience_knowledge_delta.{key}")

    handoff_chain = intent.get("handoff_chain")
    if not isinstance(handoff_chain, dict):
        issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain")
    else:
        incoming = handoff_chain.get("incoming")
        outgoing = handoff_chain.get("outgoing")
        if not isinstance(incoming, dict) or not non_empty(incoming.get("anchor_type")) or not non_empty(incoming.get("visible_or_audible_form")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.incoming")
        if not isinstance(outgoing, dict) or not non_empty(outgoing.get("anchor_id")) or not non_empty(outgoing.get("anchor_type")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing")
        if isinstance(outgoing, dict) and not (non_empty(outgoing.get("next_scene_selector")) or str(outgoing.get("anchor_type") or "") == "terminal"):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing.next_scene_selector")
        if isinstance(outgoing, dict) and _looks_only_generic_handoff(outgoing.get("required_next_scene_start_pressure")):
            issues["handoff_chain"].append(f"scene{scene_id}:handoff_chain.outgoing.required_next_scene_start_pressure.generic")

    coverage = scene.get("coverage_review")
    if not isinstance(coverage, dict):
        issues["coverage_review"].append(f"scene{scene_id}:coverage_review")
    else:
        for key in SCENE_COVERAGE_REVIEW_REQUIRED_KEYS:
            if coverage.get(key) is not True:
                issues["coverage_review"].append(f"scene{scene_id}:{key}")

    if _contains_generic_scene_language(intent):
        issues["story_specificity"].append(f"scene{scene_id}:generic_scene_template_phrase")

    return {key: values for key, values in issues.items() if values}


def _iter_mapping_keys_recursive(value: Any, *, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            keys.append(path)
            keys.extend(_iter_mapping_keys_recursive(child, prefix=path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            keys.extend(_iter_mapping_keys_recursive(child, prefix=f"{prefix}[{index}]" if prefix else f"[{index}]"))
    return keys


def _scene_event(scene: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scene.get("scene_event"))


def _scene_event_sequence(scene: dict[str, Any]) -> list[dict[str, Any]]:
    event = _scene_event(scene)
    return [beat for beat in as_list(event.get("event_sequence")) if isinstance(beat, dict)]


def _scene_event_beat_id(beat: dict[str, Any]) -> str:
    return str(beat.get("beat_id") or "").strip()


def _scene_event_beat_function(beat: dict[str, Any]) -> str:
    return str(beat.get("beat_function") or beat.get("function") or "").strip().lower()


def _scene_event_beat_ids(scene: dict[str, Any]) -> list[str]:
    return [_scene_event_beat_id(beat) for beat in _scene_event_sequence(scene) if _scene_event_beat_id(beat)]


def _scene_event_source_story_beat_refs(scene_event: dict[str, Any]) -> list[str]:
    refs = scene_event.get("source_story_beat_ids")
    return [str(item).strip() for item in refs if str(item).strip()] if isinstance(refs, list) else []


def _story_grounding_source_refs(grounding: dict[str, Any]) -> list[str]:
    refs = grounding.get("source_story_beat_ids")
    return [str(item).strip() for item in refs if str(item).strip()] if isinstance(refs, list) else []


def _concrete_story_elements(grounding: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in as_list(grounding.get("concrete_story_elements")) if isinstance(item, dict)]


def _asset_story_function_usage(grounding: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in as_list(grounding.get("asset_story_function_usage")) if isinstance(item, dict)]


def _scene_event_top_level_matrix(data: dict[str, Any]) -> dict[str, Any]:
    direct = as_dict(data.get("canonical_event_coverage_matrix"))
    if direct:
        return direct
    return as_dict(as_dict(data.get("script")).get("canonical_event_coverage_matrix"))


def _scene_generation_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "payload_exists": [],
        "contract_complete": [],
        "payload_no_downstream_fields": [],
        "payload_no_image_directing_terms": [],
        "payload_no_fixed_cut_count": [],
        "debug_prompt_source_exists": [],
        "contract_matches_outputs": [],
    }
    generation = as_dict(scene.get("scene_generation"))
    if not generation:
        issues["payload_exists"].append(f"scene{scene_id}:scene_generation")
        return {key: values for key, values in issues.items() if values}
    if str(generation.get("schema_version") or "").strip() != "scene_generation_v1":
        issues["payload_exists"].append(f"scene{scene_id}:scene_generation.schema_version")
    for block in SCENE_GENERATION_REQUIRED_BLOCKS:
        if not as_dict(generation.get(block)):
            target = "debug_prompt_source_exists" if block == "scene_debug_prompt_source" else "payload_exists"
            issues[target].append(f"scene{scene_id}:scene_generation.{block}")

    payload = as_dict(generation.get("scene_prompt_payload"))
    prompt = str(payload.get("prompt") or "")
    if not prompt.strip():
        issues["payload_exists"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.prompt")
    if not as_list(payload.get("input_refs")):
        issues["payload_exists"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.input_refs")
    payload_required_outputs = [str(item).strip() for item in as_list(payload.get("required_outputs")) if str(item).strip()]
    for output in SCENE_GENERATION_REQUIRED_OUTPUTS:
        if output not in payload_required_outputs:
            issues["contract_complete"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.required_outputs.{output}")
    prompt_paths = _iter_mapping_keys_recursive(payload)
    for forbidden in SCENE_PROMPT_PAYLOAD_FORBIDDEN_DOWNSTREAM_FIELDS:
        if any(path.rsplit(".", 1)[-1] == forbidden for path in prompt_paths) or forbidden in prompt:
            issues["payload_no_downstream_fields"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.{forbidden}")
    if SCENE_PROMPT_PAYLOAD_FORBIDDEN_DIRECTING_TERMS_RE.search(prompt):
        issues["payload_no_image_directing_terms"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.prompt")
    if SCENE_PROMPT_PAYLOAD_FIXED_CUT_COUNT_RE.search(prompt):
        issues["payload_no_fixed_cut_count"].append(f"scene{scene_id}:scene_generation.scene_prompt_payload.prompt")

    debug_source = as_dict(generation.get("scene_debug_prompt_source"))
    if not debug_source:
        issues["debug_prompt_source_exists"].append(f"scene{scene_id}:scene_generation.scene_debug_prompt_source")
    else:
        for key in ("source_story_beat_ids", "source_beats", "adaptation_choices", "excluded_from_payload"):
            if not as_list(debug_source.get(key)):
                issues["debug_prompt_source_exists"].append(f"scene{scene_id}:scene_generation.scene_debug_prompt_source.{key}")
        if debug_source.get("not_sent_to_agent") is not True:
            issues["debug_prompt_source_exists"].append(f"scene{scene_id}:scene_generation.scene_debug_prompt_source.not_sent_to_agent")

    contract = as_dict(generation.get("scene_generation_contract"))
    if not contract:
        issues["contract_complete"].append(f"scene{scene_id}:scene_generation.scene_generation_contract")
    else:
        contract_outputs = [str(item).strip() for item in as_list(contract.get("required_outputs")) if str(item).strip()]
        for output in SCENE_GENERATION_REQUIRED_OUTPUTS:
            if output not in contract_outputs:
                issues["contract_complete"].append(f"scene{scene_id}:scene_generation.scene_generation_contract.required_outputs.{output}")
        if str(contract.get("scene_event_schema_version") or "").strip() != "scene_event_v1":
            issues["contract_complete"].append(f"scene{scene_id}:scene_generation.scene_generation_contract.scene_event_schema_version")

    for output in SCENE_GENERATION_REQUIRED_OUTPUTS:
        if output == "forbidden_event_changes":
            scene_event = as_dict(scene.get("scene_event"))
            if "forbidden_event_changes" not in scene_event or not isinstance(scene_event.get("forbidden_event_changes"), list):
                issues["contract_matches_outputs"].append(f"scene{scene_id}:scene_event.forbidden_event_changes")
            continue
        if not as_dict(scene.get(output)):
            issues["contract_matches_outputs"].append(f"scene{scene_id}:{output}")
    return {key: values for key, values in issues.items() if values}


def _forbidden_reveal_ids_from_scene_intent(scene: dict[str, Any]) -> set[str]:
    intent = as_dict(scene.get("scene_intent"))
    forbidden: set[str] = set()
    delta = as_dict(intent.get("audience_knowledge_delta"))
    for item in as_list(delta.get("forbidden_early_reveals")):
        if isinstance(item, dict):
            for key in ("info_id", "reveal_id", "id"):
                value = str(item.get(key) or "").strip()
                if value:
                    forbidden.add(value)
        else:
            text = str(item).strip()
            if text and text.isascii() and " " not in text:
                forbidden.add(text)
    for constraint in as_list(intent.get("reveal_constraints")):
        if not isinstance(constraint, dict):
            text = str(constraint).strip()
            if text and text.isascii() and " " not in text:
                forbidden.add(text)
            continue
        for key in ("forbidden_info_ids", "forbidden_reveal_ids"):
            for value in as_list(constraint.get(key)):
                text = str(value).strip()
                if text:
                    forbidden.add(text)
    return forbidden


def _scene_event_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "exists": [],
        "sequence_complete": [],
        "visible_actions_complete": [],
        "story_grounding_complete": [],
        "concrete_story_function_complete": [],
        "specificity_budget_respected": [],
        "no_forbidden_directing_fields": [],
        "beat_ids_unique": [],
        "turning_event_ref_valid": [],
        "end_situation_ref_valid": [],
        "reveal_constraints_respected": [],
    }
    event = _scene_event(scene)
    if not event:
        issues["exists"].append(f"scene{scene_id}:scene_event")
        return {key: values for key, values in issues.items() if values}

    if str(event.get("schema_version") or "").strip() != "scene_event_v1":
        issues["exists"].append(f"scene{scene_id}:scene_event.schema_version")
    for key in ("event_logline", "start_situation", "turning_event", "end_situation"):
        if key not in event or not non_empty(event.get(key)):
            issues["exists"].append(f"scene{scene_id}:scene_event.{key}")
    for key in ("offscreen_context", "forbidden_event_changes"):
        if key not in event or not isinstance(event.get(key), list):
            issues["exists"].append(f"scene{scene_id}:scene_event.{key}")
    if not _scene_event_source_story_beat_refs(event):
        issues["exists"].append(f"scene{scene_id}:scene_event.source_story_beat_ids")
    specificity_layers = as_dict(event.get("story_specificity"))
    if not specificity_layers:
        issues["story_grounding_complete"].append(f"scene{scene_id}:scene_event.story_specificity")
    else:
        for layer_key in (
            "canonical_specificity",
            "character_specificity",
            "relationship_specificity",
            "object_specificity",
            "location_specificity",
            "rule_specificity",
            "visual_specificity",
        ):
            layer = as_dict(specificity_layers.get(layer_key))
            if not layer or not as_list(layer.get("required_elements")):
                issues["story_grounding_complete"].append(f"scene{scene_id}:scene_event.story_specificity.{layer_key}")
    scene_budget = as_dict(event.get("specificity_budget"))
    if not scene_budget:
        issues["specificity_budget_respected"].append(f"scene{scene_id}:scene_event.specificity_budget")
    elif scene_budget.get("reject_decorative_detail_without_story_function") is not True:
        issues["specificity_budget_respected"].append(f"scene{scene_id}:scene_event.specificity_budget.reject_decorative_detail_without_story_function")

    forbidden_fields = set(FORBIDDEN_SCENE_EVENT_DIRECTING_FIELDS)
    forbidden_paths = [
        path
        for path in _iter_mapping_keys_recursive(event)
        if path.rsplit(".", 1)[-1] in forbidden_fields or path.rsplit("[", 1)[-1].rstrip("]") in forbidden_fields
    ]
    if forbidden_paths:
        issues["no_forbidden_directing_fields"].extend(f"scene{scene_id}:scene_event.{path}" for path in forbidden_paths[:8])

    sequence = _scene_event_sequence(scene)
    if not sequence:
        issues["sequence_complete"].append(f"scene{scene_id}:scene_event.event_sequence")

    beat_ids: list[str] = []
    source_story_beat_ids = set(_scene_event_source_story_beat_refs(event))
    for index, beat in enumerate(sequence, start=1):
        beat_id = _scene_event_beat_id(beat)
        if not beat_id:
            issues["beat_ids_unique"].append(f"scene{scene_id}:scene_event.event_sequence[{index}].beat_id")
        else:
            beat_ids.append(beat_id)
        if not _scene_event_beat_function(beat):
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.beat_function")
        source_ids = [str(item).strip() for item in as_list(beat.get("source_story_beat_ids")) if str(item).strip()]
        if not source_ids:
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.source_story_beat_ids")
        elif source_story_beat_ids and any(source_id not in source_story_beat_ids for source_id in source_ids):
            issues["sequence_complete"].append(f"scene{scene_id}:{beat_id or index}.source_story_beat_ids.ref")
        for key in ("what_happens", "visible_action", "visible_reaction", "immediate_consequence", "emotional_pressure"):
            if not non_empty(beat.get(key)):
                issues["visible_actions_complete"].append(f"scene{scene_id}:{beat_id or index}.{key}")
        if not as_list(beat.get("required_visual_evidence")):
            issues["visible_actions_complete"].append(f"scene{scene_id}:{beat_id or index}.required_visual_evidence")
        abstract_function = as_dict(beat.get("abstract_function"))
        if not abstract_function:
            issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.abstract_function")
        else:
            for key in ("dramatic_job", "causal_role"):
                if not non_empty(abstract_function.get(key)):
                    issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.abstract_function.{key}")
        concrete_event = as_dict(beat.get("concrete_event"))
        if not concrete_event:
            issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.concrete_event")
        else:
            if not as_list(concrete_event.get("who")):
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.concrete_event.who")
            for key in ("where", "what_happens", "conflict_or_constraint", "visible_action", "visible_reaction"):
                if not non_empty(concrete_event.get(key)):
                    issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.concrete_event.{key}")
            if not as_list(concrete_event.get("required_visual_evidence")):
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.concrete_event.required_visual_evidence")
        grounding = as_dict(beat.get("story_grounding"))
        if not grounding:
            issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding")
        else:
            origin = str(grounding.get("source_origin") or "").strip()
            if origin not in STORY_GROUNDING_SOURCE_ORIGINS:
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.source_origin")
            grounding_refs = _story_grounding_source_refs(grounding)
            if not grounding_refs:
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.source_story_beat_ids")
            elif source_story_beat_ids and any(ref not in source_story_beat_ids for ref in grounding_refs):
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.source_story_beat_ids.ref")
            if not non_empty(grounding.get("source_text_or_summary")):
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.source_text_or_summary")
            if origin == "invented_candidate" and grounding.get("human_approval_required") is not True:
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.invented_candidate_without_approval")
            non_replaceable = [item for item in as_list(grounding.get("non_replaceable_elements")) if isinstance(item, dict)]
            if not non_replaceable:
                issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.non_replaceable_elements")
            for element_index, element in enumerate(non_replaceable, start=1):
                for key in ("element_id", "type", "value", "why_non_replaceable"):
                    if not non_empty(element.get(key)):
                        issues["story_grounding_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.non_replaceable_elements[{element_index}].{key}")
            concrete_elements = _concrete_story_elements(grounding)
            if not concrete_elements:
                issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.concrete_story_elements")
            for element_index, element in enumerate(concrete_elements, start=1):
                for key in ("element_id", "element_type", "concrete_description", "story_function", "visible_form"):
                    if not non_empty(element.get(key)):
                        issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.concrete_story_elements[{element_index}].{key}")
                function = str(element.get("story_function") or "").strip()
                if function and function not in CONCRETE_STORY_ELEMENT_FUNCTIONS:
                    issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.concrete_story_elements[{element_index}].story_function.enum")
                beat_refs = [str(item).strip() for item in as_list(element.get("appears_in_event_beat_ids")) if str(item).strip()]
                if beat_id and beat_refs and beat_id not in beat_refs:
                    issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.concrete_story_elements[{element_index}].appears_in_event_beat_ids")
            asset_usage = _asset_story_function_usage(grounding)
            if not asset_usage:
                issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.asset_story_function_usage")
            for usage_index, usage in enumerate(asset_usage, start=1):
                for key in ("asset_id", "asset_type", "story_function_in_scene", "visible_or_hidden"):
                    if not non_empty(usage.get(key)):
                        issues["concrete_story_function_complete"].append(f"scene{scene_id}:{beat_id or index}.story_grounding.asset_story_function_usage[{usage_index}].{key}")
        budget = as_dict(beat.get("specificity_budget"))
        if not budget:
            issues["specificity_budget_respected"].append(f"scene{scene_id}:{beat_id or index}.specificity_budget")
        else:
            max_primary = as_int(budget.get("max_primary_story_elements")) or 0
            max_secondary = as_int(budget.get("max_secondary_story_elements")) or 0
            if max_primary <= 0:
                issues["specificity_budget_respected"].append(f"scene{scene_id}:{beat_id or index}.specificity_budget.max_primary_story_elements")
            if budget.get("reject_decorative_detail_without_story_function") is not True:
                issues["specificity_budget_respected"].append(f"scene{scene_id}:{beat_id or index}.specificity_budget.reject_decorative_detail_without_story_function")
            concrete_count = len(_concrete_story_elements(as_dict(beat.get("story_grounding"))))
            if max_primary and max_secondary and concrete_count > max_primary + max_secondary:
                issues["specificity_budget_respected"].append(f"scene{scene_id}:{beat_id or index}.specificity_budget.overloaded:{concrete_count}>{max_primary + max_secondary}")

    duplicate_ids = sorted({beat_id for beat_id in beat_ids if beat_ids.count(beat_id) > 1})
    if duplicate_ids:
        issues["beat_ids_unique"].extend(f"scene{scene_id}:{beat_id}.duplicate" for beat_id in duplicate_ids)

    beat_id_set = set(beat_ids)
    turn_ids = {_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_function(beat) == "turn"}
    turning_event = as_dict(event.get("turning_event"))
    turning_ref = str(turning_event.get("source_event_beat_id") or turning_event.get("event_beat_id") or "").strip()
    if not turning_ref or turning_ref not in beat_id_set:
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.source_event_beat_id")
    elif turn_ids and turning_ref not in turn_ids:
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.source_event_beat_id.not_turn")
    if str(turning_event.get("causal_turn_ref") or "").strip() != "scene_intent.causal_turn":
        issues["turning_event_ref_valid"].append(f"scene{scene_id}:scene_event.turning_event.causal_turn_ref")

    end_situation = as_dict(event.get("end_situation"))
    if str(end_situation.get("value_shift_to_ref") or "").strip() != "scene_intent.value_shift.to":
        issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.value_shift_to_ref")
    for key in ("outcome", "character_position", "object_state", "relationship_state", "new_pressure"):
        if not non_empty(end_situation.get(key)):
            issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.{key}")
    visible_refs = [str(item).strip() for item in as_list(end_situation.get("visible_evidence_refs")) if str(item).strip()]
    if visible_refs and any(ref not in beat_id_set for ref in visible_refs):
        issues["end_situation_ref_valid"].append(f"scene{scene_id}:scene_event.end_situation.visible_evidence_refs")

    forbidden_reveals = _forbidden_reveal_ids_from_scene_intent(scene)
    if forbidden_reveals:
        for beat in sequence:
            beat_id = _scene_event_beat_id(beat) or "?"
            revealed = {str(item).strip() for item in as_list(beat.get("story_information_revealed_ids")) if str(item).strip()}
            if revealed & forbidden_reveals:
                issues["reveal_constraints_respected"].append(f"scene{scene_id}:{beat_id}.forbidden_reveal:{','.join(sorted(revealed & forbidden_reveals))}")

    return {key: values for key, values in issues.items() if values}


def _event_beats_blocked_after_cut(
    contract: dict[str, Any],
    refs: list[str],
    sequence_ids: list[str],
    beat_functions: dict[str, str],
) -> list[str]:
    cut_state_progression = as_dict(contract.get("cut_state_progression"))
    if str(cut_state_progression.get("progression_mode") or "").strip() == "sequential_state_progression":
        ref_indexes = [sequence_ids.index(ref) for ref in refs if ref in sequence_ids]
        max_ref_index = max(ref_indexes) if ref_indexes else -1
        return [
            beat_id
            for index, beat_id in enumerate(sequence_ids)
            if index > max_ref_index and beat_functions.get(beat_id) in {"turn", "payoff"}
        ]
    return [
        beat_id
        for beat_id in sequence_ids
        if beat_id not in refs and beat_functions.get(beat_id) in {"turn", "payoff"}
    ]


def _cut_event_ref_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    issues: dict[str, list[str]] = {
        "refs_valid": [],
        "reference_integrity": [],
        "source_event_preservation": [],
        "source_story_specificity_projection": [],
        "first_frame_alignment": [],
        "motion_boundary": [],
        "narration_boundary": [],
        "event_context_ready": [],
        "sequence_covered": [],
        "turn_payoff_have_cuts": [],
    }
    sequence = _scene_event_sequence(scene)
    beat_ids = {_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_id(beat)}
    if not beat_ids:
        issues["refs_valid"].append(f"scene{scene_id}:scene_event.event_sequence")
        return {key: values for key, values in issues.items() if values}

    beat_functions = {_scene_event_beat_id(beat): _scene_event_beat_function(beat) for beat in sequence if _scene_event_beat_id(beat)}
    beat_by_id = {_scene_event_beat_id(beat): beat for beat in sequence if _scene_event_beat_id(beat)}
    sequence_ids = [_scene_event_beat_id(beat) for beat in sequence if _scene_event_beat_id(beat)]
    forbidden_event_changes = {str(item).strip() for item in as_list(_scene_event(scene).get("forbidden_event_changes")) if str(item).strip()}
    covered: set[str] = set()
    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict) or str(cut.get("cut_status") or "").strip().lower() == "deleted":
            continue
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "?")
        contract = _node_cut_contract(cut, allow_legacy=False)
        if not contract:
            issues["refs_valid"].append(f"{selector}:cut_contract")
            continue
        source_contract = _cut_source_event_contract(contract)
        if not source_contract:
            issues["refs_valid"].append(f"{selector}:cut_contract.source_event_contract")
            continue
        primary = str(source_contract.get("primary_event_beat_id") or "").strip()
        refs = [str(item).strip() for item in as_list(source_contract.get("source_event_beat_ids")) if str(item).strip()]
        if not primary:
            issues["refs_valid"].append(f"{selector}:source_event_contract.primary_event_beat_id")
        elif primary not in beat_ids:
            issues["refs_valid"].append(f"{selector}:source_event_contract.primary_event_beat_id.ref")
        if not refs:
            issues["refs_valid"].append(f"{selector}:source_event_contract.source_event_beat_ids")
        elif any(ref not in beat_ids for ref in refs):
            issues["refs_valid"].append(f"{selector}:source_event_contract.source_event_beat_ids.ref")
        if primary and refs and primary not in refs:
            issues["reference_integrity"].append(f"{selector}:source_event_contract.primary_event_beat_id.not_in_source_event_beat_ids")
        declared_function = str(source_contract.get("event_beat_function") or "").strip()
        if primary and declared_function != beat_functions.get(primary):
            issues["reference_integrity"].append(f"{selector}:source_event_contract.event_beat_function")
        if str(source_contract.get("event_time_position") or "").strip() not in EVENT_TIME_POSITION_VALUES:
            issues["reference_integrity"].append(f"{selector}:source_event_contract.event_time_position")
        if not non_empty(source_contract.get("source_visible_reaction")) and not non_empty(source_contract.get("no_reaction_required_reason")):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_visible_reaction")
        for key in ("event_facts_to_preserve", "event_facts_not_to_invent", "allowed_reveal_info_ids", "forbidden_reveal_info_ids"):
            if key not in source_contract or not isinstance(source_contract.get(key), list):
                if key in {"event_facts_to_preserve", "event_facts_not_to_invent"}:
                    issues["refs_valid"].append(f"{selector}:source_event_contract.{key}")
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.{key}")
        source_concrete_events = [item for item in as_list(source_contract.get("source_concrete_events")) if isinstance(item, dict)]
        if not source_concrete_events:
            issues["source_story_specificity_projection"].append(f"{selector}:source_event_contract.source_concrete_events")
        source_story_grounding = [item for item in as_list(source_contract.get("source_story_grounding")) if isinstance(item, dict)]
        if not source_story_grounding:
            issues["source_story_specificity_projection"].append(f"{selector}:source_event_contract.source_story_grounding")
        source_non_replaceable = [item for item in as_list(source_contract.get("source_non_replaceable_elements")) if isinstance(item, dict)]
        if not source_non_replaceable:
            issues["source_story_specificity_projection"].append(f"{selector}:source_event_contract.source_non_replaceable_elements")
        ref_beats = [beat_by_id[ref] for ref in refs if ref in beat_by_id]
        primary_beat = beat_by_id.get(primary)
        expected_facts = {str(beat.get("what_happens") or "").strip() for beat in ref_beats if str(beat.get("what_happens") or "").strip()}
        canonical_preserve = source_contract.get("canonical_event_facts_to_preserve")
        declared_preserve = {
            str(item).strip()
            for item in as_list(
                canonical_preserve
                if isinstance(canonical_preserve, list)
                else source_contract.get("event_facts_to_preserve")
            )
            if str(item).strip()
        }
        if expected_facts and not expected_facts.issubset(declared_preserve):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.event_facts_to_preserve.mismatch")
        expected_not_invent = forbidden_event_changes
        declared_not_invent = {str(item).strip() for item in as_list(source_contract.get("event_facts_not_to_invent")) if str(item).strip()}
        if expected_not_invent and not expected_not_invent.issubset(declared_not_invent):
            issues["source_event_preservation"].append(f"{selector}:source_event_contract.event_facts_not_to_invent.mismatch")
        if primary_beat:
            expected_action = str(primary_beat.get("visible_action") or "").strip()
            declared_action = str(
                source_contract.get("canonical_source_visible_action")
                or source_contract.get("source_visible_action")
                or ""
            ).strip()
            if expected_action and declared_action != expected_action:
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_visible_action.mismatch")
            expected_evidence = {str(item).strip() for item in as_list(primary_beat.get("required_visual_evidence")) if str(item).strip()}
            canonical_evidence = source_contract.get("canonical_source_required_visual_evidence")
            declared_evidence = {
                str(item).strip()
                for item in as_list(
                    canonical_evidence
                    if isinstance(canonical_evidence, list)
                    else source_contract.get("source_required_visual_evidence")
                )
                if str(item).strip()
            }
            if expected_evidence and not expected_evidence.issubset(declared_evidence):
                issues["source_event_preservation"].append(f"{selector}:source_event_contract.source_required_visual_evidence.mismatch")
        first_frame = as_dict(contract.get("first_frame_contract"))
        if str(first_frame.get("source_event_beat_id") or "").strip() != primary:
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.source_event_beat_id")
        if str(first_frame.get("event_time_position") or "").strip() not in EVENT_TIME_POSITION_VALUES:
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.event_time_position")
        if not non_empty(first_frame.get("event_fact_visible_in_still")):
            issues["first_frame_alignment"].append(f"{selector}:first_frame_contract.event_fact_visible_in_still")
        motion = as_dict(contract.get("motion_contract"))
        if str(motion.get("source_event_beat_id") or "").strip() != primary:
            issues["motion_boundary"].append(f"{selector}:motion_contract.source_event_beat_id")
        if motion.get("starts_from_first_frame") is not True:
            issues["motion_boundary"].append(f"{selector}:motion_contract.starts_from_first_frame")
        if "must_not_advance_to_event_beat_ids" not in motion or not isinstance(motion.get("must_not_advance_to_event_beat_ids"), list):
            issues["motion_boundary"].append(f"{selector}:motion_contract.must_not_advance_to_event_beat_ids")
        expected_blocked = _event_beats_blocked_after_cut(contract, refs, sequence_ids, beat_functions)
        motion_blocked = {str(item).strip() for item in as_list(motion.get("must_not_advance_to_event_beat_ids")) if str(item).strip()}
        if expected_blocked and not set(expected_blocked).issubset(motion_blocked):
            issues["motion_boundary"].append(f"{selector}:motion_contract.must_not_advance_to_event_beat_ids.incomplete")
        narration = as_dict(contract.get("narration_contract"))
        narration_refs = [str(item).strip() for item in as_list(narration.get("source_event_beat_ids")) if str(item).strip()]
        if not narration_refs or any(ref not in refs for ref in narration_refs):
            issues["narration_boundary"].append(f"{selector}:narration_contract.source_event_beat_ids")
        if narration.get("must_not_explain_visible_action_as_caption") is not True:
            issues["narration_boundary"].append(f"{selector}:narration_contract.must_not_explain_visible_action_as_caption")
        if str(narration.get("narration_event_boundary") or "").strip() not in {"same_event_only", "may_bridge_previous", "may_bridge_next_without_reveal"}:
            issues["narration_boundary"].append(f"{selector}:narration_contract.narration_event_boundary")
        narration_blocked = {str(item).strip() for item in as_list(narration.get("must_not_advance_to_event_beat_ids")) if str(item).strip()}
        if expected_blocked and not set(expected_blocked).issubset(narration_blocked):
            issues["narration_boundary"].append(f"{selector}:narration_contract.must_not_advance_to_event_beat_ids.incomplete")
        event_context = as_dict(contract.get("event_context_for_cut"))
        context_primary = as_dict(event_context.get("primary_event_beat"))
        if not event_context:
            issues["event_context_ready"].append(f"{selector}:event_context_for_cut")
        else:
            derived_from = {str(item).strip() for item in as_list(event_context.get("derived_from")) if str(item).strip()}
            if not {"scene_event.event_sequence[]", "cut_contract.source_event_contract"}.issubset(derived_from):
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.derived_from")
            if event_context.get("editable") is not False:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.editable")
            if str(context_primary.get("beat_id") or "").strip() != primary:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.primary_event_beat.beat_id")
            context_source_ids = {
                str(as_dict(beat).get("beat_id") or "").strip()
                for beat in as_list(event_context.get("source_event_beats"))
                if str(as_dict(beat).get("beat_id") or "").strip()
            }
            if set(refs) != context_source_ids:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.source_event_beats")
            expected_neighbor_ids: set[str] = set()
            for ref in refs:
                if ref not in sequence_ids:
                    continue
                index = sequence_ids.index(ref)
                for neighbor_index in (index - 1, index + 1):
                    if 0 <= neighbor_index < len(sequence_ids):
                        neighbor_id = sequence_ids[neighbor_index]
                        if neighbor_id not in refs:
                            expected_neighbor_ids.add(neighbor_id)
            context_neighbor_ids = {
                str(as_dict(beat).get("beat_id") or "").strip()
                for beat in as_list(event_context.get("neighboring_event_beats"))
                if str(as_dict(beat).get("beat_id") or "").strip()
            }
            if expected_neighbor_ids != context_neighbor_ids:
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.neighboring_event_beats")
            context_forbidden = {str(item).strip() for item in as_list(event_context.get("forbidden_event_changes")) if str(item).strip()}
            if forbidden_event_changes and not forbidden_event_changes.issubset(context_forbidden):
                issues["event_context_ready"].append(f"{selector}:event_context_for_cut.forbidden_event_changes")
        covered.update(ref for ref in refs if ref in beat_ids)

    required_beats = _coverage_authored_event_beat_ids(_scene_cut_coverage_plan(scene))
    missing_required = sorted(required_beats - covered)
    if missing_required:
        issues["sequence_covered"].extend(f"scene{scene_id}:{beat_id}.uncovered" for beat_id in missing_required)
    missing_turn_payoff = sorted(beat_id for beat_id in missing_required if beat_functions.get(beat_id) in {"turn", "payoff"})
    if missing_turn_payoff:
        issues["turn_payoff_have_cuts"].extend(f"scene{scene_id}:{beat_id}.uncovered" for beat_id in missing_turn_payoff)

    return {key: values for key, values in issues.items() if values}


def _visible_behavior_complete(value: Any) -> bool:
    behavior = as_dict(value)
    return all(non_empty(behavior.get(field)) for field in VISIBLE_BEHAVIOR_FIELDS)


def _scene_expected_character_ids(scene: dict[str, Any]) -> set[str]:
    expected: set[str] = set()
    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict) or str(cut.get("cut_status") or "").strip().lower() == "deleted":
            continue
        contract = _node_cut_contract(cut, allow_legacy=False)
        asset_dependency = as_dict(contract.get("asset_dependency")) if contract else {}
        for value in as_list(asset_dependency.get("character_ids_required")):
            if non_empty(value):
                expected.add(str(value).strip())
        image_generation = as_dict(cut.get("image_generation"))
        for value in as_list(image_generation.get("character_ids")):
            if non_empty(value):
                expected.add(str(value).strip())
    return expected


def _scene_emotion_film_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    scene_id = _scene_id_for_issue(scene)
    beat_ids = set(_scene_event_beat_ids(scene))
    beat_functions = {
        _scene_event_beat_id(beat): _scene_event_beat_function(beat)
        for beat in _scene_event_sequence(scene)
        if _scene_event_beat_id(beat)
    }
    beat_has_reveal = {
        _scene_event_beat_id(beat): _scene_event_beat_function(beat) in {"reveal", "threshold_reveal", "reveal_hold"}
        for beat in _scene_event_sequence(scene)
        if _scene_event_beat_id(beat)
    }
    cut_selectors = {
        _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "?")
        for cut in as_list(scene.get("cuts"))
        if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
    }
    issues: dict[str, list[str]] = {
        "timeline_exists": [],
        "timeline_states_complete": [],
        "visible_proof_complete": [],
        "cut_emotion_exists": [],
        "cut_emotion_trigger_refs": [],
        "cut_emotion_visible_behavior": [],
        "no_emotion_jump": [],
        "reaction_required": [],
        "coverage_exists": [],
        "edit_motivation": [],
        "attention_continuity": [],
        "screen_direction": [],
        "prop_costume_body": [],
    }

    timeline = as_dict(scene.get("scene_character_state_timeline"))
    if not timeline:
        issues["timeline_exists"].append(f"scene{scene_id}:scene_character_state_timeline")
    else:
        if str(timeline.get("policy_version") or "").strip() != "character_emotion_continuity_v1":
            issues["timeline_exists"].append(f"scene{scene_id}:scene_character_state_timeline.policy_version")
        linked_ids = [str(value).strip() for value in as_list(timeline.get("linked_scene_event_beat_ids")) if str(value).strip()]
        if not linked_ids or any(beat_id not in beat_ids for beat_id in linked_ids) or (beat_ids and not beat_ids.issubset(set(linked_ids))):
            issues["timeline_states_complete"].append(f"scene{scene_id}:scene_character_state_timeline.linked_scene_event_beat_ids")
        characters = [character for character in as_list(timeline.get("characters")) if isinstance(character, dict)]
        if not characters:
            issues["timeline_states_complete"].append(f"scene{scene_id}:scene_character_state_timeline.characters")
        timeline_character_ids = {str(character.get("character_id") or "").strip() for character in characters if str(character.get("character_id") or "").strip()}
        expected_character_ids = _scene_expected_character_ids(scene)
        if expected_character_ids and not expected_character_ids.issubset(timeline_character_ids):
            missing = ",".join(sorted(expected_character_ids - timeline_character_ids))
            issues["timeline_states_complete"].append(f"scene{scene_id}:scene_character_state_timeline.missing_characters:{missing}")
        for char_index, character in enumerate(characters, start=1):
            for state_key in ("start_state", "midpoint_state", "end_state"):
                state = as_dict(character.get(state_key))
                if not state:
                    issues["timeline_states_complete"].append(f"scene{scene_id}:character[{char_index}].{state_key}")
                    continue
                if not non_empty(state.get("emotion")):
                    issues["timeline_states_complete"].append(f"scene{scene_id}:character[{char_index}].{state_key}.emotion")
                trigger = str(state.get("trigger_event_beat_id") or "").strip()
                if not trigger or (beat_ids and trigger not in beat_ids):
                    issues["timeline_states_complete"].append(f"scene{scene_id}:character[{char_index}].{state_key}.trigger_event_beat_id")
                visible_proof = as_dict(state.get("visible_proof"))
                if not _visible_behavior_complete(visible_proof):
                    issues["visible_proof_complete"].append(f"scene{scene_id}:character[{char_index}].{state_key}.visible_proof")
            no_return = as_dict(character.get("emotional_no_return_point"))
            no_return_ref = str(no_return.get("event_beat_id") or "").strip()
            if not no_return_ref or (beat_ids and no_return_ref not in beat_ids):
                issues["timeline_states_complete"].append(f"scene{scene_id}:character[{char_index}].emotional_no_return_point.event_beat_id")

    coverage = as_dict(scene.get("scene_film_coverage_plan"))
    if not coverage:
        issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan")
    else:
        if str(coverage.get("policy_version") or "").strip() != "scene_film_coverage_v1":
            issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.policy_version")
        shot_mix = as_dict(coverage.get("shot_mix"))
        if not shot_mix or not isinstance(shot_mix.get("required_coverage"), dict):
            issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.shot_mix")
        if "missing_coverage" not in coverage or not isinstance(coverage.get("missing_coverage"), list):
            issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.missing_coverage")
        if "action_reaction_pair" not in coverage or not isinstance(coverage.get("action_reaction_pair"), list):
            issues["reaction_required"].append(f"scene{scene_id}:scene_film_coverage_plan.action_reaction_pair")
        else:
            pairs_by_beat = {
                str(pair.get("source_event_beat_id") or "").strip(): pair
                for pair in as_list(coverage.get("action_reaction_pair"))
                if isinstance(pair, dict)
            }
            for beat_id, function in beat_functions.items():
                if function not in {"turn", "payoff"} and not beat_has_reveal.get(beat_id):
                    continue
                pair = as_dict(pairs_by_beat.get(beat_id))
                action_selector = str(pair.get("action_cut_selector") or "").strip()
                reaction_selector = str(pair.get("reaction_cut_selector") or "").strip()
                if not pair or action_selector not in cut_selectors or reaction_selector not in cut_selectors:
                    issues["reaction_required"].append(f"scene{scene_id}:scene_film_coverage_plan.action_reaction_pair.{beat_id}")
        required_coverage = as_dict(shot_mix.get("required_coverage"))
        object_required = False
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            contract = _node_cut_contract(cut, allow_legacy=False)
            asset_dependency = as_dict(contract.get("asset_dependency")) if contract else {}
            if as_list(asset_dependency.get("object_ids_required")):
                object_required = True
                break
        if object_required and not as_list(required_coverage.get("insert")):
            issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.shot_mix.required_coverage.insert")
        rules = as_dict(coverage.get("required_when_rules"))
        for rule_key in ("reaction", "insert", "eyeline", "silence"):
            if not non_empty(rules.get(rule_key)):
                issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.required_when_rules.{rule_key}")
        audience = as_dict(coverage.get("audience_emotion_target"))
        if audience.get("separate_from_character_emotion") is not True:
            issues["coverage_exists"].append(f"scene{scene_id}:scene_film_coverage_plan.audience_emotion_target")

    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict) or str(cut.get("cut_status") or "").strip().lower() == "deleted":
            continue
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "?")
        contract = _node_cut_contract(cut, allow_legacy=False)
        if not contract:
            issues["cut_emotion_exists"].append(f"{selector}:cut_contract")
            continue
        source_contract = _cut_source_event_contract(contract)
        primary = str(source_contract.get("primary_event_beat_id") or "").strip()
        emotion = as_dict(contract.get("cut_character_emotion_transition"))
        if not emotion:
            issues["cut_emotion_exists"].append(f"{selector}:cut_character_emotion_transition")
        else:
            if str(emotion.get("policy_version") or "").strip() != "cut_character_emotion_transition_v1":
                issues["cut_emotion_exists"].append(f"{selector}:cut_character_emotion_transition.policy_version")
            if not non_empty(emotion.get("transition_mode")):
                issues["no_emotion_jump"].append(f"{selector}:cut_character_emotion_transition.transition_mode")
            trigger = as_dict(emotion.get("transition_trigger"))
            trigger_ref = str(trigger.get("source_event_beat_id") or "").strip()
            if not trigger_ref or trigger_ref not in beat_ids or (primary and trigger_ref != primary):
                issues["cut_emotion_trigger_refs"].append(f"{selector}:cut_character_emotion_transition.transition_trigger.source_event_beat_id")
            for state_key in ("emotion_from", "emotion_to"):
                state = as_dict(emotion.get(state_key))
                if not _visible_behavior_complete(state.get("visible_behavior")):
                    issues["cut_emotion_visible_behavior"].append(f"{selector}:cut_character_emotion_transition.{state_key}.visible_behavior")
            transition_visible = as_dict(emotion.get("transition_visible_in_cut"))
            for key in ("face_change", "gaze_change", "posture_change", "hand_change", "foot_change", "distance_change"):
                if not non_empty(transition_visible.get(key)):
                    issues["cut_emotion_visible_behavior"].append(f"{selector}:cut_character_emotion_transition.transition_visible_in_cut.{key}")
            if emotion.get("must_not_jump_to_final_emotion") is not True:
                issues["no_emotion_jump"].append(f"{selector}:cut_character_emotion_transition.must_not_jump_to_final_emotion")

        film = as_dict(contract.get("cut_film_grammar_contract"))
        if not film:
            issues["edit_motivation"].append(f"{selector}:cut_film_grammar_contract")
            issues["attention_continuity"].append(f"{selector}:cut_film_grammar_contract")
            issues["screen_direction"].append(f"{selector}:cut_film_grammar_contract")
            issues["prop_costume_body"].append(f"{selector}:cut_film_grammar_contract")
            continue
        if str(film.get("policy_version") or "").strip() != "cut_film_grammar_v1":
            issues["edit_motivation"].append(f"{selector}:cut_film_grammar_contract.policy_version")
        required_modules = as_dict(film.get("required_modules"))
        conditional_modules = as_dict(film.get("conditional_modules"))
        if not required_modules:
            issues["edit_motivation"].append(f"{selector}:cut_film_grammar_contract.required_modules")
        if not conditional_modules:
            issues["prop_costume_body"].append(f"{selector}:cut_film_grammar_contract.conditional_modules")
        if not non_empty(as_dict(required_modules.get("edit_motivation")).get("why_current_cut_is_needed")):
            issues["edit_motivation"].append(f"{selector}:cut_film_grammar_contract.required_modules.edit_motivation")
        attention = as_dict(required_modules.get("attention_state"))
        eyeline = as_dict(required_modules.get("eyeline_continuity"))
        if not non_empty(attention.get("gaze_target")) or not non_empty(attention.get("viewer_attention_target")):
            issues["attention_continuity"].append(f"{selector}:cut_film_grammar_contract.required_modules.attention_state")
        if not non_empty(eyeline.get("gaze_target")):
            issues["attention_continuity"].append(f"{selector}:cut_film_grammar_contract.required_modules.eyeline_continuity")
        screen_direction = as_dict(required_modules.get("screen_direction_continuity"))
        if not non_empty(screen_direction.get("movement_direction")) or screen_direction.get("direction_change_motivated") is not True:
            issues["screen_direction"].append(f"{selector}:cut_film_grammar_contract.required_modules.screen_direction_continuity")
        audience = as_dict(required_modules.get("audience_emotion_target"))
        if audience.get("separate_from_character_emotion") is not True:
            issues["attention_continuity"].append(f"{selector}:cut_film_grammar_contract.required_modules.audience_emotion_target")
        function = beat_functions.get(primary)
        reaction = as_dict(conditional_modules.get("character_reaction_contract"))
        reveal_required = bool(beat_has_reveal.get(primary))
        if function in {"turn", "payoff"} or reveal_required:
            if reaction.get("required") is not True or str(reaction.get("reacts_to_event_beat_id") or "").strip() != primary:
                issues["reaction_required"].append(f"{selector}:cut_film_grammar_contract.conditional_modules.character_reaction_contract")
            silence = as_dict(conditional_modules.get("silence_and_pause_contract"))
            if silence.get("required") is not True or silence.get("silence_required") is not True:
                issues["reaction_required"].append(f"{selector}:cut_film_grammar_contract.conditional_modules.silence_and_pause_contract")
        prop = as_dict(conditional_modules.get("prop_state_progression"))
        costume = as_dict(conditional_modules.get("costume_and_body_continuity"))
        object_ids = as_list(as_dict(contract.get("asset_dependency")).get("object_ids_required"))
        if object_ids and prop.get("required") is not True:
            issues["prop_costume_body"].append(f"{selector}:cut_film_grammar_contract.conditional_modules.prop_state_progression")
        for key in ("costume_state", "hair_state", "posture_state"):
            if not non_empty(costume.get(key)):
                issues["prop_costume_body"].append(f"{selector}:cut_film_grammar_contract.conditional_modules.costume_and_body_continuity.{key}")

    return {key: values for key, values in issues.items() if values}


def _scene_requires_emotion_film_contract(scene: dict[str, Any]) -> bool:
    if isinstance(scene.get("scene_character_state_timeline"), dict) or isinstance(scene.get("scene_film_coverage_plan"), dict):
        return True
    event = as_dict(scene.get("scene_event"))
    if str(event.get("schema_version") or "").strip() == "scene_event_v1":
        return True
    for cut in as_list(scene.get("cuts")):
        if not isinstance(cut, dict):
            continue
        contract = as_dict(cut.get("cut_contract"))
        if contract.get("cut_character_emotion_transition") or contract.get("cut_film_grammar_contract"):
            return True
        image_generation = as_dict(cut.get("image_generation"))
        if _image_api_prompt_policy(image_generation) == IMAGE_API_PROMPT_POLICY_VERSION:
            return True
    return False


def _scene_event_readiness_issues(scenes: list[Any], *, prefix: str = "script") -> list[str]:
    issues: list[str] = []
    for scene in scenes:
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip() == "reference":
            continue
        for issue_key, values in _scene_event_issue_map(scene).items():
            if values:
                issues.append(f"{prefix}.scene_event.{issue_key}")
        for issue_key, values in _cut_event_ref_issue_map(scene).items():
            if values:
                issues.append(f"{prefix}.cut_event.{issue_key}")
        if _scene_requires_emotion_film_contract(scene):
            for issue_key, values in _scene_emotion_film_issue_map(scene).items():
                if values:
                    issues.append(f"{prefix}.emotion_film.{issue_key}")
    return list(dict.fromkeys(issues))


def _canonical_event_coverage_matrix_issues(data: dict[str, Any], scenes: list[Any]) -> list[str]:
    matrix = _scene_event_top_level_matrix(data)
    concrete_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    if not concrete_scenes:
        return []
    scene_ids = {str(scene.get("scene_id") or index + 1).strip() for index, scene in enumerate(concrete_scenes)}
    beat_ids_by_scene: dict[str, set[str]] = {}
    all_beat_ids: set[str] = set()
    for index, scene in enumerate(concrete_scenes):
        scene_id = str(scene.get("scene_id") or index + 1).strip()
        beat_ids = set(_scene_event_beat_ids(scene))
        beat_ids_by_scene[scene_id] = beat_ids
        all_beat_ids.update(beat_ids)
    issues: list[str] = []
    if not matrix:
        return ["canonical_event_coverage_matrix"]
    rows = [row for row in as_list(matrix.get("source_story_events")) if isinstance(row, dict)]
    if not rows:
        return ["canonical_event_coverage_matrix.source_story_events"]
    previous_index = -1
    for row_index, row in enumerate(rows, start=1):
        row_id = str(row.get("source_event_id") or row_index).strip()
        if not non_empty(row.get("source_event_summary")):
            issues.append(f"{row_id}:source_event_summary")
        canonical_order = as_int(row.get("canonical_order_index"))
        if canonical_order is None:
            issues.append(f"{row_id}:canonical_order_index")
        elif canonical_order < previous_index:
            issues.append(f"{row_id}:canonical_order_broken")
        else:
            previous_index = canonical_order
        required = row.get("required") is True or str(row.get("importance") or "").strip().lower() in {"high", "critical"}
        assigned_scene_ids = [str(item).strip() for item in as_list(row.get("assigned_scene_ids")) if str(item).strip()]
        assigned_beat_ids = [str(item).strip() for item in as_list(row.get("assigned_event_beat_ids")) if str(item).strip()]
        if required:
            if not assigned_scene_ids and not non_empty(row.get("omission_reason")):
                issues.append(f"{row_id}:assigned_scene_ids")
            if not assigned_beat_ids and not non_empty(row.get("omission_reason")):
                issues.append(f"{row_id}:assigned_event_beat_ids")
        for scene_id in assigned_scene_ids:
            if scene_id not in scene_ids:
                issues.append(f"{row_id}:assigned_scene_ids.ref:{scene_id}")
        for beat_id in assigned_beat_ids:
            if beat_id not in all_beat_ids:
                issues.append(f"{row_id}:assigned_event_beat_ids.ref:{beat_id}")
        if row.get("human_approval_required") is True and not non_empty(row.get("adaptation_change_reason") or row.get("omission_reason")):
            issues.append(f"{row_id}:human_approval_required.reason")
    return issues


def _cut_has_blueprint(cut: dict[str, Any]) -> bool:
    contract = _node_cut_contract(cut)
    if contract and _cut_contract_complete(contract):
        return True

    blueprint = cut.get("cut_blueprint")
    if not isinstance(blueprint, dict):
        return False
    required_keys = {
        "cut_role",
        "duration_intent",
        "target_beat",
        "must_show",
        "must_avoid",
        "done_when",
        "visual_beat",
        "narration_role",
        "asset_dependency_hint",
    }
    if not required_keys.issubset(set(blueprint)):
        return False
    return (
        non_empty(blueprint.get("cut_role"))
        and non_empty(blueprint.get("duration_intent"))
        and non_empty(blueprint.get("target_beat"))
        and non_empty(blueprint.get("visual_beat"))
        and non_empty(blueprint.get("narration_role"))
        and as_list(blueprint.get("must_show"))
        and as_list(blueprint.get("done_when"))
        and isinstance(blueprint.get("asset_dependency_hint"), dict)
    )


def _scene_importance(scene: dict[str, Any]) -> str:
    value = scene.get("importance")
    if not value and isinstance(scene.get("scene_intent"), dict):
        value = scene["scene_intent"].get("importance")
    return str(value or "").strip().lower()


def _scene_cut_coverage_plan(scene: dict[str, Any]) -> dict[str, Any]:
    return as_dict(scene.get("scene_cut_coverage_plan"))


def _coverage_identifier(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coverage_assignment_obligation_ids(assignment: dict[str, Any]) -> set[str]:
    obligation_ids = {
        identifier
        for value in as_list(assignment.get("obligation_ids"))
        if (identifier := _coverage_identifier(value))
        and not identifier.lower().startswith("duration_")
    }
    single_obligation_id = _coverage_identifier(assignment.get("obligation_id"))
    if single_obligation_id and not single_obligation_id.lower().startswith("duration_"):
        obligation_ids.add(single_obligation_id)
    return obligation_ids


def _coverage_assignment_event_beat_ids(assignment: dict[str, Any]) -> set[str]:
    event_assignment = as_dict(assignment.get("event_assignment"))
    source_event_contract = as_dict(event_assignment.get("source_event_contract"))
    event_beat_ids = {
        identifier
        for value in as_list(source_event_contract.get("source_event_beat_ids"))
        if (identifier := _coverage_identifier(value))
    }
    primary_event_beat_id = _coverage_identifier(
        source_event_contract.get("primary_event_beat_id")
    )
    if primary_event_beat_id:
        event_beat_ids.add(primary_event_beat_id)
    return event_beat_ids


def _coverage_authored_obligation_ids(plan: dict[str, Any]) -> set[str]:
    obligation_ids: set[str] = set()
    for assignment in as_list(plan.get("cut_assignments")):
        if isinstance(assignment, dict):
            obligation_ids.update(_coverage_assignment_obligation_ids(assignment))
    return obligation_ids


def _coverage_authored_event_beat_ids(plan: dict[str, Any]) -> set[str]:
    return {
        beat_id
        for event_beat in as_list(plan.get("event_beat_inventory"))
        if isinstance(event_beat, dict)
        and event_beat.get("must_be_seen") is not False
        and (beat_id := _coverage_identifier(event_beat.get("beat_id")))
    }


def _coverage_minimum_cut_count(plan: dict[str, Any]) -> int:
    if not isinstance(plan, dict):
        return 0
    # Declared/legacy counters are audit metadata only. Only concrete authored
    # IDs can create a floor, so stale duration-derived values cannot authorize
    # filler cuts and missing inventories cannot be hidden by a claimed count.
    return max(
        len(_coverage_authored_obligation_ids(plan)),
        len(_coverage_authored_event_beat_ids(plan)),
    )


def _cinematic_min_cuts_for_scene(scene: dict[str, Any]) -> int:
    """Return the authored semantic/event floor; duration is audited separately."""

    return _coverage_minimum_cut_count(_scene_cut_coverage_plan(scene))


def _coverage_plan_assignment_issues(
    assignments: list[Any],
    *,
    scene_id: str,
    actual_selectors: set[str],
    obligation_ids: set[str],
    obligation_declared_selectors: dict[str, set[str]],
    seen_event_beat_ids: set[str],
    event_declared_selectors: dict[str, set[str]],
) -> tuple[list[str], dict[str, set[str]], dict[str, set[str]]]:
    issues: list[str] = []
    if not assignments:
        issues.append(f"scene{scene_id}:cut_assignments")
    assignment_obligation_selectors: dict[str, set[str]] = {}
    assignment_event_selectors: dict[str, set[str]] = {}
    for index, assignment in enumerate(assignments, start=1):
        if not isinstance(assignment, dict):
            issues.append(f"scene{scene_id}:cut_assignments[{index}]")
            continue
        cut_selector_value = _coverage_identifier(assignment.get("cut_selector"))
        if cut_selector_value not in actual_selectors:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].cut_selector")

        raw_obligation_value = assignment.get("obligation_ids")
        raw_obligation_ids = list(as_list(raw_obligation_value))
        invalid_obligation_ids = (
            "obligation_ids" in assignment and not isinstance(raw_obligation_value, list)
        ) or any(not _coverage_identifier(value) for value in raw_obligation_ids)
        if "obligation_id" in assignment:
            single_raw_obligation_id = assignment.get("obligation_id")
            raw_obligation_ids.append(single_raw_obligation_id)
            invalid_obligation_ids = (
                invalid_obligation_ids or not _coverage_identifier(single_raw_obligation_id)
            )
        duration_only_ids = {
            identifier
            for value in raw_obligation_ids
            if (identifier := _coverage_identifier(value))
            and identifier.lower().startswith("duration_")
        }
        assignment_obligations = _coverage_assignment_obligation_ids(assignment)
        if duration_only_ids:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].duration_only_obligation_ids")
        if invalid_obligation_ids or not assignment_obligations:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].obligation_ids")
        elif assignment_obligations - obligation_ids:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].obligation_ids")
        for obligation_id in assignment_obligations:
            assignment_obligation_selectors.setdefault(obligation_id, set()).add(cut_selector_value)
            if cut_selector_value not in obligation_declared_selectors.get(obligation_id, set()):
                issues.append(f"scene{scene_id}:cut_assignments[{index}].obligation_ids")

        event_assignment = as_dict(assignment.get("event_assignment"))
        source_event_contract = as_dict(event_assignment.get("source_event_contract"))
        raw_source_event_ids = source_event_contract.get("source_event_beat_ids")
        invalid_event_ids = (
            "source_event_beat_ids" in source_event_contract
            and not isinstance(raw_source_event_ids, list)
        ) or any(
            not _coverage_identifier(value)
            for value in as_list(raw_source_event_ids)
        )
        if "primary_event_beat_id" in source_event_contract:
            invalid_event_ids = invalid_event_ids or not _coverage_identifier(
                source_event_contract.get("primary_event_beat_id")
            )
        event_ids = _coverage_assignment_event_beat_ids(assignment)
        if invalid_event_ids:
            issues.append(f"scene{scene_id}:cut_assignments[{index}].event_assignment")
        if not event_ids:
            issues.append(
                f"scene{scene_id}:cut_assignments[{index}].event_assignment.source_event_contract"
            )
        for beat_id in sorted(event_ids):
            assignment_event_selectors.setdefault(beat_id, set()).add(cut_selector_value)
            if beat_id not in seen_event_beat_ids:
                issues.append(
                    f"scene{scene_id}:cut_assignments[{index}].unknown_event_beat:{beat_id}"
                )
            elif cut_selector_value not in event_declared_selectors.get(beat_id, set()):
                issues.append(f"scene{scene_id}:cut_assignments[{index}].event_assignment")
    return issues, assignment_obligation_selectors, assignment_event_selectors


def _scene_cut_coverage_plan_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    plan = _scene_cut_coverage_plan(scene)
    if not plan:
        return [f"scene{scene_id}:scene_cut_coverage_plan"]

    actual_selectors = {_scene_cut_selector(scene_id, cut) for cut in cuts}
    actual_selectors = {selector for selector in actual_selectors if selector}
    selected_min = _coverage_minimum_cut_count(plan)
    actual_cut_count = len(cuts)
    if actual_cut_count < selected_min:
        issues.append(f"scene{scene_id}:cut_count_below_coverage_plan:{actual_cut_count}<{selected_min}")

    min_cut_count = as_dict(plan.get("min_cut_count"))
    declared_semantic_count = as_int(min_cut_count.get("by_distinct_semantic_obligations"))
    authored_semantic_count = len(_coverage_authored_obligation_ids(plan))
    if declared_semantic_count is None:
        issues.append(f"scene{scene_id}:coverage_plan_distinct_semantic_obligations_missing")
    elif declared_semantic_count < authored_semantic_count:
        issues.append(f"scene{scene_id}:coverage_plan_distinct_semantic_obligations_below_authored")
    elif declared_semantic_count > authored_semantic_count:
        issues.append(
            f"scene{scene_id}:coverage_plan_distinct_semantic_obligations_mismatch:"
            f"{declared_semantic_count}!={authored_semantic_count}"
        )
    declared_event_count = as_int(min_cut_count.get("by_event_beats"))
    authored_event_count = len(_coverage_authored_event_beat_ids(plan))
    if declared_event_count is None:
        issues.append(f"scene{scene_id}:coverage_plan_event_beats_missing")
    elif declared_event_count < authored_event_count:
        issues.append(f"scene{scene_id}:coverage_plan_event_beats_below_authored")
    elif declared_event_count > authored_event_count:
        issues.append(
            f"scene{scene_id}:coverage_plan_event_beats_mismatch:"
            f"{declared_event_count}!={authored_event_count}"
        )
    selected = as_int(min_cut_count.get("selected"))
    if selected is None:
        issues.append(f"scene{scene_id}:coverage_plan_selected_missing")
    elif selected < selected_min:
        issues.append(f"scene{scene_id}:coverage_plan_selected_below_floor")
        issues.append(f"scene{scene_id}:coverage_plan_selected_mismatch:{selected}!={selected_min}")
    elif selected > selected_min:
        issues.append(f"scene{scene_id}:coverage_plan_selected_mismatch:{selected}!={selected_min}")
    strategy = str(plan.get("coverage_strategy") or "").strip()
    if strategy and strategy != "reverse_from_scene_event":
        issues.append(f"scene{scene_id}:coverage_strategy")
    source_schema_version = str(plan.get("source_schema_version") or "").strip()
    if source_schema_version and source_schema_version != "scene_event_v1":
        issues.append(f"scene{scene_id}:source_schema_version")

    obligations = as_list(plan.get("scene_obligations"))
    if not obligations:
        issues.append(f"scene{scene_id}:scene_obligations")
    obligation_ids: set[str] = set()
    obligation_declared_selectors: dict[str, set[str]] = {}
    for index, obligation in enumerate(obligations, start=1):
        if not isinstance(obligation, dict):
            issues.append(f"scene{scene_id}:scene_obligations[{index}]")
            continue
        obligation_id = _coverage_identifier(obligation.get("obligation_id"))
        label = obligation_id or str(index)
        if not obligation_id:
            issues.append(f"scene{scene_id}:scene_obligations[{index}].obligation_id")
        elif obligation_id.lower().startswith("duration_"):
            issues.append(f"scene{scene_id}:scene_obligations[{obligation_id}].duration_only")
        elif obligation_id in obligation_ids:
            issues.append(f"scene{scene_id}:scene_obligations[{obligation_id}].duplicate")
        else:
            obligation_ids.add(obligation_id)
        raw_assigned_cut_ids = obligation.get("assigned_cut_ids")
        invalid_assigned_cut_ids = not isinstance(raw_assigned_cut_ids, list) or any(
            not _coverage_identifier(item) for item in as_list(raw_assigned_cut_ids)
        )
        assigned = {
            selector
            for item in as_list(raw_assigned_cut_ids)
            if (selector := _coverage_identifier(item))
        }
        if obligation_id:
            obligation_declared_selectors.setdefault(obligation_id, set()).update(assigned)
        if invalid_assigned_cut_ids or not assigned:
            issues.append(f"scene{scene_id}:scene_obligations[{label}].assigned_cut_ids")
        for selector in sorted(assigned - actual_selectors):
            issues.append(f"scene{scene_id}:scene_obligations[{label}].unknown_cut:{selector}")

    assignments = as_list(plan.get("cut_assignments"))
    assignment_event_ids = {
        beat_id
        for assignment in assignments
        if isinstance(assignment, dict)
        for beat_id in _coverage_assignment_event_beat_ids(assignment)
    }
    event_inventory = as_list(plan.get("event_beat_inventory"))
    if (
        declared_event_count
        or authored_event_count
        or assignment_event_ids
        or _scene_event_beat_ids(scene)
    ) and not event_inventory:
        issues.append(f"scene{scene_id}:event_beat_inventory")
    seen_event_beat_ids: set[str] = set()
    required_event_beat_ids: set[str] = set()
    event_declared_selectors: dict[str, set[str]] = {}
    for index, event_beat in enumerate(event_inventory, start=1):
        if not isinstance(event_beat, dict):
            issues.append(f"scene{scene_id}:event_beat_inventory[{index}]")
            continue
        beat_id = _coverage_identifier(event_beat.get("beat_id"))
        label = beat_id or str(index)
        if not beat_id:
            issues.append(f"scene{scene_id}:event_beat_inventory[{index}].beat_id")
        elif beat_id in seen_event_beat_ids:
            issues.append(f"scene{scene_id}:event_beat_inventory[{beat_id}].duplicate")
        else:
            seen_event_beat_ids.add(beat_id)
            if event_beat.get("must_be_seen") is not False:
                required_event_beat_ids.add(beat_id)
        raw_assigned_cut_ids = event_beat.get("assigned_cut_ids")
        invalid_assigned_cut_ids = not isinstance(raw_assigned_cut_ids, list) or any(
            not _coverage_identifier(item) for item in as_list(raw_assigned_cut_ids)
        )
        assigned = {
            selector
            for item in as_list(raw_assigned_cut_ids)
            if (selector := _coverage_identifier(item))
        }
        if beat_id:
            event_declared_selectors.setdefault(beat_id, set()).update(assigned)
        if invalid_assigned_cut_ids or (
            event_beat.get("must_be_seen") is not False and not assigned
        ):
            issues.append(f"scene{scene_id}:event_beat_inventory[{label}].assigned_cut_ids")
        for selector in sorted(assigned - actual_selectors):
            issues.append(f"scene{scene_id}:event_beat_inventory[{label}].unknown_cut:{selector}")
    for beat_id in sorted(set(_scene_event_beat_ids(scene)) - seen_event_beat_ids):
        issues.append(f"scene{scene_id}:event_beat_inventory[{beat_id}].missing")
    for beat_id in sorted(seen_event_beat_ids - set(_scene_event_beat_ids(scene))):
        issues.append(f"scene{scene_id}:event_beat_inventory[{beat_id}].unknown_scene_event")

    assignment_issues, assignment_obligation_selectors, assignment_event_selectors = (
        _coverage_plan_assignment_issues(
            assignments,
            scene_id=scene_id,
            actual_selectors=actual_selectors,
            obligation_ids=obligation_ids,
            obligation_declared_selectors=obligation_declared_selectors,
            seen_event_beat_ids=seen_event_beat_ids,
            event_declared_selectors=event_declared_selectors,
        )
    )
    issues.extend(assignment_issues)

    for obligation_id in sorted(obligation_ids):
        if assignment_obligation_selectors.get(obligation_id, set()) != obligation_declared_selectors.get(obligation_id, set()):
            issues.append(f"scene{scene_id}:scene_obligations[{obligation_id}].assignment_mismatch")
    for beat_id in sorted(required_event_beat_ids):
        if assignment_event_selectors.get(beat_id, set()) != event_declared_selectors.get(beat_id, set()):
            issues.append(f"scene{scene_id}:event_beat_inventory[{beat_id}].assignment_mismatch")

    if as_list(plan.get("unassigned_obligations")):
        issues.append(f"scene{scene_id}:unassigned_obligations")
    overloaded = as_list(plan.get("overloaded_cuts"))
    for index, item in enumerate(overloaded, start=1):
        if not isinstance(item, dict) or not non_empty(item.get("overload_exception_reason") or item.get("exception_reason")):
            issues.append(f"scene{scene_id}:overloaded_cuts[{index}]")
    duplicate_risks = as_list(plan.get("duplicate_meaning_risks"))
    for index, item in enumerate(duplicate_risks, start=1):
        if not isinstance(item, dict) or not non_empty(item.get("prompt_reinforcement_reason") or item.get("reinforcement_reason")):
            issues.append(f"scene{scene_id}:duplicate_meaning_risks[{index}]")
    return issues


def _canonical_redundancy_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _motion_end_state_signature(cut: dict[str, Any]) -> tuple[tuple[str, str], str] | None:
    contract = _node_cut_contract(cut, allow_legacy=False)
    motion_contract = as_dict(contract.get("motion_contract"))
    # `movable: false` is the cut-local contract for an intentional static hold.
    # Missing or non-boolean values do not authorize an exception.
    if motion_contract.get("movable") is False:
        return None
    subject_motion = _canonical_redundancy_text(motion_contract.get("subject_motion"))
    motion_brief = _canonical_redundancy_text(motion_contract.get("motion_brief"))
    end_state = _canonical_redundancy_text(motion_contract.get("end_state"))
    if not end_state or not (subject_motion or motion_brief):
        return None
    return (subject_motion, motion_brief), end_state


def _scene_cut_redundancy_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    plan = _scene_cut_coverage_plan(scene)
    allowed_duplicate_keys = {
        str(item.get("anti_redundancy_key") or item.get("meaning_key") or "").strip()
        for item in as_list(plan.get("duplicate_meaning_risks"))
        if isinstance(item, dict) and non_empty(item.get("prompt_reinforcement_reason") or item.get("reinforcement_reason"))
    }
    seen: dict[str, str] = {}
    active_cuts = [
        cut
        for cut in cuts
        if str(cut.get("cut_status") or "").strip().lower() != "deleted"
    ]
    for cut in active_cuts:
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "cut")
        contract = _node_cut_contract(cut, allow_legacy=False)
        key = _contract_string(contract, "viewer_contract.anti_redundancy_key", "anti_redundancy_key")
        if not key:
            issues.append(f"{selector}:anti_redundancy_key")
            continue
        if key in seen and key not in allowed_duplicate_keys:
            issues.append(f"{selector}:duplicate_anti_redundancy_key:{key}")
        seen.setdefault(key, selector)
    for previous_cut, cut in zip(active_cuts, active_cuts[1:]):
        previous_signature = _motion_end_state_signature(previous_cut)
        if previous_signature is None or previous_signature != _motion_end_state_signature(cut):
            continue
        previous_selector = _scene_cut_selector(scene_id, previous_cut) or str(
            previous_cut.get("cut_id") or "cut"
        )
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "cut")
        issues.append(
            f"{selector}:duplicate_adjacent_motion_end_state:{previous_selector}"
        )
    return issues


def _scene_cut_handoff_issues(scene: dict[str, Any], *, scene_id: str, cuts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    previous_outgoing: dict[str, Any] | None = None
    previous_selector = ""
    for index, cut in enumerate(cuts):
        selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or index + 1)
        contract = _node_cut_contract(cut, allow_legacy=False)
        handoff = as_dict(contract.get("cut_handoff"))
        incoming = as_dict(handoff.get("receives_from_previous"))
        outgoing = as_dict(handoff.get("delivers_to_next"))
        if not incoming:
            issues.append(f"{selector}:cut_handoff.receives_from_previous")
        if not outgoing:
            issues.append(f"{selector}:cut_handoff.delivers_to_next")
        if index == 0:
            incoming_type = str(incoming.get("anchor_type") or "").strip().lower()
            if incoming and incoming_type not in {"none", "question", "object", "sound", "gaze", "gesture", "movement", "light", "threat"}:
                issues.append(f"{selector}:cut_handoff.incoming.anchor_type")
        elif previous_outgoing:
            previous_anchor = str(previous_outgoing.get("anchor_id") or "").strip()
            incoming_anchor = str(incoming.get("anchor_id") or "").strip()
            if previous_anchor and previous_anchor != incoming_anchor:
                issues.append(f"{selector}:cut_handoff.anchor_mismatch:{previous_selector}->{selector}")
        if index < len(cuts) - 1:
            if not non_empty(outgoing.get("anchor_id")) or not non_empty(outgoing.get("visible_or_audible_form")):
                issues.append(f"{selector}:cut_handoff.outgoing")
        else:
            outgoing_type = str(outgoing.get("anchor_type") or "").strip().lower()
            if outgoing_type not in {"terminal", "question", "object", "sound", "gaze", "gesture", "movement", "light", "threat"}:
                issues.append(f"{selector}:cut_handoff.final_anchor_type")
        previous_outgoing = outgoing
        previous_selector = selector
    return issues


def _triangulation_review_issues(cut: dict[str, Any], *, selector: str) -> list[str]:
    review = as_dict(cut.get("review")).get("triangulation_review")
    if not isinstance(review, dict):
        image_review = as_dict(as_dict(cut.get("image_generation")).get("review"))
        review = image_review.get("triangulation_review")
    if not isinstance(review, dict):
        return [f"{selector}:triangulation_review"]
    status = str(review.get("status") or "").strip().lower()
    human_waived = str(review.get("waived_by") or "").strip().lower() in {"human", "user"} and non_empty(review.get("waiver_reason"))
    if status in {"waived", "approved"} and human_waived:
        return []
    issues = [f"{selector}:triangulation_review.status" if status and status not in {"passed", "approved"} else ""]
    for key in TRIANGULATION_REQUIRED_KEYS:
        if review.get(key) is not True:
            issues.append(f"{selector}:triangulation_review.{key}")
    return [issue for issue in issues if issue]


def _scene_readiness_issues(scenes: list[Any]) -> list[str]:
    issues: list[str] = []
    concrete_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    for index, scene in enumerate(concrete_scenes):
        scene_id = as_dotted_str(scene.get("scene_id")) or str(index + 1)
        scene_intent = as_dict(scene.get("scene_intent"))
        if "importance" in scene or "importance" in scene_intent:
            importance = _scene_importance(scene)
            if importance not in {"low", "medium", "high", "critical"}:
                issues.append(f"scene{scene_id}:importance")
        for key in ("target_duration_seconds", "estimated_duration_seconds"):
            if key not in scene and key not in scene_intent:
                continue
            value = scene.get(key)
            if (not isinstance(value, (int, float)) or isinstance(value, bool)) and key in scene_intent:
                value = scene_intent.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                issues.append(f"scene{scene_id}:{key}")
        if index < len(concrete_scenes) - 1:
            if not non_empty(scene.get("handoff_to_next_scene")):
                issues.append(f"scene{scene_id}:handoff_to_next_scene")
        elif not (non_empty(scene.get("terminal_resolution")) or non_empty(scene.get("handoff_to_next_scene"))):
            issues.append(f"scene{scene_id}:terminal_resolution")

        cuts = [
            cut
            for cut in as_list(scene.get("cuts"))
            if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
        ]
        min_cuts = _cinematic_min_cuts_for_scene(scene)
        if len(cuts) < min_cuts:
            issues.append(f"scene{scene_id}:cut_count_below_calculated_floor:{len(cuts)}<{min_cuts}")
        has_new_cut_contract = any(isinstance(cut.get("cut_contract"), dict) and cut.get("cut_contract") for cut in cuts)
        if _scene_cut_coverage_plan(scene) or has_new_cut_contract:
            issues.extend(_scene_cut_coverage_plan_issues(scene, scene_id=scene_id, cuts=cuts))
            issues.extend(_scene_cut_redundancy_issues(scene, scene_id=scene_id, cuts=cuts))
            issues.extend(_scene_cut_handoff_issues(scene, scene_id=scene_id, cuts=cuts))

        coverage = scene.get("coverage_review")
        if not isinstance(coverage, dict):
            issues.append(f"scene{scene_id}:coverage_review")
        else:
            for key in SCENE_COVERAGE_REVIEW_REQUIRED_KEYS:
                if coverage.get(key) is not True:
                    issues.append(f"scene{scene_id}:{key}")
    return issues


def _review_status(data: dict[str, Any], key: str) -> str:
    review = data.get(key)
    if isinstance(review, dict):
        return str(review.get("status") or "").strip().lower()
    nested = nested_get(data, ["script", key], {})
    if isinstance(nested, dict):
        return str(nested.get("status") or "").strip().lower()
    return ""


def _append_p400_event_and_film_checks(
    checks: list[dict[str, Any]], data: dict[str, Any], scenes: list[Any]
) -> None:
    scene_event_issues: dict[str, list[str]] = {
        "exists": [],
        "sequence_complete": [],
        "visible_actions_complete": [],
        "story_grounding_complete": [],
        "concrete_story_function_complete": [],
        "specificity_budget_respected": [],
        "no_forbidden_directing_fields": [],
        "beat_ids_unique": [],
        "turning_event_ref_valid": [],
        "end_situation_ref_valid": [],
        "reveal_constraints_respected": [],
    }
    cut_event_issues: dict[str, list[str]] = {
        "refs_valid": [],
        "reference_integrity": [],
        "source_event_preservation": [],
        "source_story_specificity_projection": [],
        "first_frame_alignment": [],
        "motion_boundary": [],
        "narration_boundary": [],
        "event_context_ready": [],
        "sequence_covered": [],
        "turn_payoff_have_cuts": [],
    }
    cut_context_packet_issues: dict[str, list[str]] = {key: [] for key in WARNING_KEY_BY_DIAGNOSTIC}
    emotion_film_issues: dict[str, list[str]] = {
        "timeline_exists": [],
        "timeline_states_complete": [],
        "visible_proof_complete": [],
        "cut_emotion_exists": [],
        "cut_emotion_trigger_refs": [],
        "cut_emotion_visible_behavior": [],
        "no_emotion_jump": [],
        "reaction_required": [],
        "coverage_exists": [],
        "edit_motivation": [],
        "attention_continuity": [],
        "screen_direction": [],
        "prop_costume_body": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for key, values in _scene_event_issue_map(scene).items():
            scene_event_issues.setdefault(key, []).extend(values)
        for key, values in _cut_event_ref_issue_map(scene).items():
            cut_event_issues.setdefault(key, []).extend(values)
        for key, values in cut_context_packet_issue_map(scene).items():
            cut_context_packet_issues.setdefault(key, []).extend(values)
        if _scene_requires_emotion_film_contract(scene):
            for key, values in _scene_emotion_film_issue_map(scene).items():
                emotion_film_issues.setdefault(key, []).extend(values)
    scene_event_checks = (
        ("script.scene_event_exists", "exists", "all scenes include canonical scene_event with scene_event_v1 fields"),
        ("script.scene_event_sequence_complete", "sequence_complete", "scene_event.event_sequence contains authored beats with source story refs; function labels are scene-specific"),
        ("script.scene_event_visible_actions_complete", "visible_actions_complete", "each scene_event beat declares what happens, visible action/reaction, consequence, pressure, and visual evidence"),
        ("script.scene_event_story_specific_grounding_complete", "story_grounding_complete", "each scene_event beat separates abstract_function, concrete_event, and source-grounded story_grounding with non-replaceable elements"),
        ("script.scene_event_concrete_story_function_complete", "concrete_story_function_complete", "concrete story elements and asset usage declare story functions instead of decorative detail"),
        ("script.scene_event_specificity_budget_respected", "specificity_budget_respected", "scene_event and beats include specificity budgets and do not overload concrete detail"),
        ("script.scene_event_no_forbidden_directing_fields", "no_forbidden_directing_fields", "scene_event contains story events only and no directing or prompt fields"),
        ("script.scene_event_beat_ids_unique", "beat_ids_unique", "scene_event beat_id values are present and unique per scene"),
        ("script.scene_event_turning_event_ref_valid", "turning_event_ref_valid", "scene_event.turning_event references the turn beat and scene_intent.causal_turn"),
        ("script.scene_event_end_situation_ref_valid", "end_situation_ref_valid", "scene_event.end_situation references scene_intent.value_shift.to and declared event evidence"),
        ("script.scene_event_reveal_constraints_respected", "reveal_constraints_respected", "scene_event does not fully reveal forbidden reveal IDs"),
    )
    for check_id, issue_key, message in scene_event_checks:
        issue_values = scene_event_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )
    canonical_matrix_issues = _canonical_event_coverage_matrix_issues(data, scenes)
    add_check(
        checks,
        "script.canonical_event_coverage_matrix_complete",
        not canonical_matrix_issues,
        "canonical source/user-input events are mapped to scene ids and scene_event beat ids"
        + (f" (issues: {', '.join(canonical_matrix_issues[:8])})" if canonical_matrix_issues else ""),
        kind="rubric",
    )
    cut_event_checks = (
        ("script.cut_event_beat_refs_valid", "refs_valid", "all cut_contract entries reference valid scene_event beat ids"),
        ("script.event_beat_reference_integrity", "reference_integrity", "cut_contract.source_event_contract matches the primary scene_event beat and enum policy"),
        ("script.source_event_preservation", "source_event_preservation", "cut_contract.source_event_contract preserves source event facts and reveal boundaries"),
        ("script.source_story_specificity_projection", "source_story_specificity_projection", "cut_contract.source_event_contract projects concrete_event, story_grounding, and non-replaceable elements from scene_event"),
        ("script.event_first_frame_alignment", "first_frame_alignment", "first_frame_contract aligns with the primary source event beat"),
        ("script.event_motion_boundary", "motion_boundary", "motion_contract starts from the first frame and does not cross forbidden event beat boundaries"),
        ("script.event_narration_boundary", "narration_boundary", "narration_contract stays within allowed event and reveal boundaries"),
        ("script.event_context_for_cut_ready", "event_context_ready", "event_context_for_cut is a non-editable derived projection matching source_event_contract"),
        ("script.cuts_cover_scene_event_sequence", "sequence_covered", "cuts cover every must-be-seen event_beat_inventory beat"),
        ("script.turn_and_payoff_event_beats_have_cuts", "turn_payoff_have_cuts", "turn and payoff event beats are assigned to at least one cut"),
    )
    for check_id, issue_key, message in cut_event_checks:
        issue_values = cut_event_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )
    cut_context_packet_checks = (
        ("script.cut_context_packet_exists", "missing_packet", "cut_context_packet is materialized or can be derived on read"),
        ("script.cut_context_packet_derived_from_valid", "invalid_derived_from", "cut_context_packet declares editable:false and expected derived_from sources"),
        ("script.cut_context_packet_event_beat_preserved", "missing_event_beat", "cut_context_packet preserves the primary source event beat"),
        ("script.cut_context_packet_required_roles_preserved", "missing_required_roles", "cut_context_packet preserves required role coverage"),
        ("script.cut_context_packet_visual_proof_preserved", "missing_visual_proof", "cut_context_packet preserves visual proof obligations"),
        ("script.cut_context_packet_reveal_boundary_preserved", "missing_reveal_boundary", "cut_context_packet preserves reveal and forbidden event boundaries"),
        ("script.cut_context_packet_previous_next_delta_present", "missing_previous_next_delta", "cut_context_packet carries previous/current/next state deltas where neighboring cuts exist"),
    )
    for check_id, issue_key, message in cut_context_packet_checks:
        issue_values = cut_context_packet_issues.get(issue_key, [])
        if not issue_values:
            continue
        add_check(
            checks,
            check_id,
            True,
            message + f" (warnings: {', '.join(issue_values[:8])})",
            kind="warning",
        )
    emotion_film_checks = (
        ("script.scene_character_state_timeline_exists", "timeline_exists", "all scenes include scene_character_state_timeline"),
        ("script.scene_character_state_timeline_start_mid_end_complete", "timeline_states_complete", "character timelines include start/mid/end states tied to scene event beats"),
        ("script.character_state_visible_proof_complete", "visible_proof_complete", "character states expose drawable face/gaze/posture/hands/feet/distance proof"),
        ("script.cut_character_emotion_transition_exists", "cut_emotion_exists", "all cuts include cut_character_emotion_transition"),
        ("script.cut_emotion_transition_trigger_refs_scene_event", "cut_emotion_trigger_refs", "cut emotion transition triggers reference the primary scene_event beat"),
        ("script.cut_emotion_transition_has_visible_behavior", "cut_emotion_visible_behavior", "cut emotion transitions are expressed as drawable behavior"),
        ("script.no_emotion_jump_without_trigger", "no_emotion_jump", "cuts do not jump to final emotion without transition_mode and trigger"),
        ("script.reaction_contract_required_for_turn_reveal_payoff", "reaction_required", "turn/reveal/payoff cuts include required reaction contracts"),
        ("script.scene_film_coverage_plan_exists", "coverage_exists", "all scenes include scene_film_coverage_plan with shot/action-reaction/missing coverage and required_when rules"),
        ("script.edit_motivation_exists", "edit_motivation", "all cuts declare why the edit exists"),
        ("script.eyeline_or_attention_continuity_complete", "attention_continuity", "all cuts declare viewer attention and eyeline continuity"),
        ("script.screen_direction_change_motivated", "screen_direction", "all screen-direction choices are motivated"),
        ("script.prop_costume_body_continuity_complete", "prop_costume_body", "prop, costume, and body continuity are declared where required"),
    )
    for check_id, issue_key, message in emotion_film_checks:
        issue_values = emotion_film_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )


def _append_p400_scene_cut_checks(checks: list[dict[str, Any]], data: dict[str, Any], scenes: list[Any]) -> None:
    if not scenes:
        return

    scene_set_status = _review_status(data, "scene_set_review")
    scene_detail_status = _review_status(data, "scene_detail_review")
    cut_blueprint_status = _review_status(data, "cut_blueprint_review")
    add_check(
        checks,
        "script.scene_set_review_approved",
        scene_set_status == "approved",
        f"p410 abstract scene-set review is approved before p420 (got {scene_set_status or 'missing'})",
        kind="rubric",
    )
    add_check(
        checks,
        "script.scene_detail_review_approved",
        scene_detail_status == "approved",
        f"p410 concrete per-scene review is approved before p420 (got {scene_detail_status or 'missing'})",
        kind="rubric",
    )
    add_check(
        checks,
        "script.cut_blueprint_review_approved",
        cut_blueprint_status == "approved",
        f"p420 cut blueprint review is approved before p430 (got {cut_blueprint_status or 'missing'})",
        kind="rubric",
    )
    scene_count = len([scene for scene in scenes if isinstance(scene, dict)])
    scenes_with_intent = sum(1 for scene in scenes if isinstance(scene, dict) and _scene_has_intent(scene))
    add_check(
        checks,
        "script.scene_intent_cards",
        scenes_with_intent == scene_count,
        f"all scenes include p410 scene_intent cards ({scenes_with_intent}/{scene_count})",
        kind="rubric",
    )
    scene_contract_issues: dict[str, list[str]] = {
        "dramatic_question": [],
        "value_shift": [],
        "causal_turn": [],
        "visual_thesis": [],
        "story_specificity": [],
        "conflict_engine": [],
        "handoff_chain": [],
        "coverage_review": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for key, values in _scene_intent_issue_map(scene).items():
            scene_contract_issues.setdefault(key, []).extend(values)
    scene_contract_checks = (
        ("script.scene_dramatic_question_complete", "dramatic_question", "all scenes declare dramatic_question, scene_spine, and audience knowledge delta"),
        ("script.scene_value_shift_complete", "value_shift", "all scenes declare value_shift.from/to and visible evidence"),
        ("script.scene_causal_turn_complete", "causal_turn", "all scenes declare an irreversible causal_turn"),
        ("script.scene_visual_thesis_complete", "visual_thesis", "all scenes declare a concrete visual thesis"),
        ("script.scene_story_specificity_complete", "story_specificity", "all scenes declare story_specificity and avoid generic template language"),
        ("script.scene_conflict_engine_complete", "conflict_engine", "all scenes declare desire, obstacle, stakes, escalation, no-return point, and visible pressure"),
        ("script.scene_handoff_chain_complete", "handoff_chain", "all scenes declare concrete incoming/outgoing handoff chains"),
        ("script.scene_coverage_review_complete", "coverage_review", "all scenes mark required coverage_review gates as true"),
    )
    for check_id, issue_key, message in scene_contract_checks:
        issue_values = scene_contract_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )

    scene_generation_issues: dict[str, list[str]] = {
        "payload_exists": [],
        "contract_complete": [],
        "payload_no_downstream_fields": [],
        "payload_no_image_directing_terms": [],
        "payload_no_fixed_cut_count": [],
        "debug_prompt_source_exists": [],
        "contract_matches_outputs": [],
    }
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for key, values in _scene_generation_issue_map(scene).items():
            scene_generation_issues.setdefault(key, []).extend(values)
    scene_generation_checks = (
        ("script.scene_generation_payload_exists", "payload_exists", "all scenes include scene_generation with scene_prompt_payload"),
        ("script.scene_generation_contract_complete", "contract_complete", "scene_generation declares the required output contract"),
        ("script.scene_prompt_payload_no_downstream_fields", "payload_no_downstream_fields", "scene prompt payload excludes downstream execution fields"),
        ("script.scene_prompt_payload_no_image_directing_terms", "payload_no_image_directing_terms", "scene prompt payload excludes image directing terms"),
        ("script.scene_prompt_payload_no_fixed_cut_count", "payload_no_fixed_cut_count", "scene prompt payload does not fix cut count"),
        ("script.scene_debug_prompt_source_exists", "debug_prompt_source_exists", "scene debug prompt source records source beats and adaptation choices"),
        ("script.scene_generation_contract_matches_outputs", "contract_matches_outputs", "scene_generation required outputs exist on the scene"),
    )
    for check_id, issue_key, message in scene_generation_checks:
        issue_values = scene_generation_issues.get(issue_key, [])
        add_check(
            checks,
            check_id,
            not issue_values,
            message + (f" (issues: {', '.join(issue_values[:8])})" if issue_values else ""),
            kind="rubric",
        )

    _append_p400_event_and_film_checks(checks, data, scenes)
    scenes_agent_passed = sum(
        1
        for scene in scenes
        if isinstance(scene, dict)
        and str(((scene.get("agent_review") or {}) if isinstance(scene.get("agent_review"), dict) else {}).get("status") or "").strip().lower() == "passed"
    )
    add_check(
        checks,
        "script.scene_agent_review_passed",
        scenes_agent_passed == scene_count,
        f"all scenes have agent_review.status=passed ({scenes_agent_passed}/{scene_count})",
        kind="rubric",
    )

    renderable_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    scenes_with_cuts = [scene for scene in renderable_scenes if as_list(scene.get("cuts"))]
    add_check(
        checks,
        "script.renderable_scenes_have_cuts",
        len(scenes_with_cuts) == len(renderable_scenes),
        f"all renderable scenes include cuts ({len(scenes_with_cuts)}/{len(renderable_scenes)})",
        kind="rubric",
    )

    cuts: list[dict[str, Any]] = []
    for scene in renderable_scenes:
        cuts.extend([cut for cut in as_list(scene.get("cuts")) if isinstance(cut, dict)])
    if not cuts:
        add_check(checks, "script.cut_blueprints", False, "renderable cuts include p420 cut_blueprint entries (0/0)", kind="rubric")
        return
    cuts_with_blueprint = sum(1 for cut in cuts if _cut_has_blueprint(cut))
    add_check(
        checks,
        "script.cut_blueprints",
        cuts_with_blueprint == len(cuts),
        f"all cuts include p420 cut_blueprint entries ({cuts_with_blueprint}/{len(cuts)})",
        kind="rubric",
    )
    readiness_issues = _scene_readiness_issues(scenes)
    add_check(
        checks,
        "script.scene_readiness_contract",
        not readiness_issues,
        "all scenes declare importance, target/estimated duration, handoff, coverage review, and authored semantic/event cut coverage"
        + (f" (issues: {', '.join(readiness_issues[:8])})" if readiness_issues else ""),
        kind="rubric",
    )


def check_script_single(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "script.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}

    add_check(checks, "script.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("script", path.name, checks), updates

    text, data = load_structured_document(path)
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    body_text = flatten_without_keys(data, excluded={"evaluation_contract"}) or text
    _script_text_quality_checks(checks, body_text, data, profile)
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    time_contract_declared, time_contract_valid = scene_time_of_day_contract_marker(
        data, artifact="script"
    )
    if time_contract_declared:
        add_check(
            checks,
            "script.scene_time_of_day_contract",
            time_contract_valid,
            "script_metadata.scene_time_of_day_contract is required_v1",
            kind="rubric",
        )
    missing_time_of_day = scene_time_of_day_contract_missing(data, artifact="script")
    if missing_time_of_day is not None:
        add_check(
            checks,
            "script.scene_time_of_day",
            not missing_time_of_day,
            "all newly authored script scenes include non-empty time_of_day"
            + (f" (missing: {', '.join(missing_time_of_day[:8])})" if missing_time_of_day else ""),
            kind="rubric",
        )
    basis_contract_declared, basis_contract_valid = (
        scene_time_of_day_visual_basis_contract_marker(data, artifact="script")
    )
    if basis_contract_declared:
        add_check(
            checks,
            "script.scene_time_of_day_visual_basis_contract",
            basis_contract_valid,
            "script_metadata.scene_time_of_day_visual_basis_contract is required_v1",
            kind="rubric",
        )
    basis_issues = scene_time_of_day_visual_basis_issues(data, artifact="script")
    if basis_issues is not None:
        add_check(
            checks,
            "script.scene_time_of_day_visual_basis",
            not basis_issues,
            "all newly authored script scenes define lighting evidence for 光源, 明るさ, 影, 色温度"
            + (f" (issues: {', '.join(basis_issues[:8])})" if basis_issues else ""),
            kind="rubric",
        )
    flattened = body_text
    _append_p400_scene_cut_checks(checks, data, scenes)
    if not contract:
        add_check(checks, "script.contract_missing", False, "evaluation_contract is missing for script stage.", kind="rubric")
    else:
        must_cover = contract_list(contract, "must_cover")
        must_avoid = contract_list(contract, "must_avoid")
        target_arc = [part.strip() for part in str(contract.get("target_arc") or "").split(",") if part.strip()]
        phases = {str(scene.get("phase") or "").strip() for scene in scenes if isinstance(scene, dict)}
        if must_cover and not all(term in flattened for term in must_cover):
            add_check(checks, "script.contract_must_cover_unmet", False, "script does not yet cover all required beats or anchors.", kind="rubric")
        if must_avoid and any(term in flattened for term in must_avoid):
            add_check(checks, "script.contract_must_avoid_violated", False, "script still includes a forbidden beat or phrase from the contract.", kind="rubric")
        if target_arc and not all(phase in phases for phase in target_arc):
            add_check(checks, "script.contract_target_arc_unmet", False, "script phases do not yet satisfy target_arc.", kind="rubric")
    rubric_scores = _script_rubric(body_text, data, scenes=scenes)
    _append_rubric_findings(checks=checks, stage="script", rubric_scores=rubric_scores)
    updates["eval.script.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("script", path.name, checks, rubric_scores=rubric_scores), updates


def check_script_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    script_paths = [scene_dir / "script.md" for scene_dir in scene_dirs]

    add_check(checks, "script.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "script.scene_files", all(path.exists() for path in script_paths), "each scene has script.md")
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")

    all_no_todo = True
    scene_event_issues: list[str] = []
    for path in script_paths:
        if not path.exists():
            all_no_todo = False
            continue
        text = path.read_text(encoding="utf-8")
        if profile == "standard" and has_todo(text):
            all_no_todo = False
        _scene_text, data = load_structured_document(path)
        scene_data = data.get("scene") if isinstance(data.get("scene"), dict) else data
        scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
        if not scenes and isinstance(scene_data, dict):
            scenes = [scene_data]
        scene_event_issues.extend(_scene_event_readiness_issues(scenes, prefix="script.scene_series"))
    if profile == "standard":
        add_check(checks, "script.scene_no_todo", all_no_todo, "scene scripts do not contain TODO/TBD markers", kind="rubric")
    add_check(
        checks,
        "script.scene_series_scene_event_contract",
        not scene_event_issues,
        "scene-series scripts satisfy scene_event v1 and cut event beat contracts"
        + (f" (issues: {', '.join(scene_event_issues[:8])})" if scene_event_issues else ""),
        kind="rubric",
    )

    updates = {"eval.script.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("script", "scenes/*/script.md", checks, details={"scene_count": len(scene_dirs)}), updates
