"""Derived cut context packets for cut authoring and semantic repair.

The packet is a generated view. It does not replace scene_event,
scene_cut_coverage_plan, or cut_contract as canonical authoring sources.
"""

from __future__ import annotations

from typing import Any


CUT_CONTEXT_PACKET_SCHEMA_VERSION = "cut_context_packet_v1"
CUT_CONTEXT_PACKET_DERIVED_FROM = [
    "scene_intent",
    "scene_event",
    "scene_cut_coverage_plan",
    "scene_character_state_timeline",
    "scene_film_coverage_plan",
    "cut_contract",
]

WARNING_KEY_BY_DIAGNOSTIC = {
    "missing_packet": "script.cut_context_packet_exists",
    "invalid_derived_from": "script.cut_context_packet_derived_from_valid",
    "missing_event_beat": "script.cut_context_packet_event_beat_preserved",
    "missing_required_roles": "script.cut_context_packet_required_roles_preserved",
    "missing_visual_proof": "script.cut_context_packet_visual_proof_preserved",
    "missing_reveal_boundary": "script.cut_context_packet_reveal_boundary_preserved",
    "missing_previous_next_delta": "script.cut_context_packet_previous_next_delta_present",
    "unrelated_scene_info_risk": "script.cut_context_packet_not_overloaded_with_unrelated_scene_info",
}


def compile_cut_context_packet(
    scene: dict[str, Any],
    cut: dict[str, Any],
    *,
    previous_cut: dict[str, Any] | None = None,
    next_cut: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile a scene-level design into a single cut's derived context packet."""

    packet = _compile_packet(scene, cut, previous_cut=previous_cut, next_cut=next_cut)
    diagnostics = diagnose_cut_context_packet(
        scene,
        cut,
        packet,
        previous_cut=previous_cut,
        next_cut=next_cut,
        packet_was_missing=False,
    )
    packet["diagnostics"] = _packet_diagnostics_payload(diagnostics)
    return packet, diagnostics


def cut_context_packet_for_review(
    scene: dict[str, Any],
    cut: dict[str, Any],
    *,
    previous_cut: dict[str, Any] | None = None,
    next_cut: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the saved packet if present, otherwise derive an on-read view."""

    stored = _stored_packet(cut)
    if stored:
        diagnostics = diagnose_cut_context_packet(
            scene,
            cut,
            stored,
            previous_cut=previous_cut,
            next_cut=next_cut,
            packet_was_missing=False,
        )
        packet = dict(stored)
        packet["diagnostics"] = _packet_diagnostics_payload(diagnostics)
        return packet, diagnostics

    packet, diagnostics = compile_cut_context_packet(scene, cut, previous_cut=previous_cut, next_cut=next_cut)
    diagnostics = dict(diagnostics)
    diagnostics["missing_packet"] = [_selector(scene, cut)]
    diagnostics["warning_keys"] = _warning_keys(diagnostics)
    packet["diagnostics"] = _packet_diagnostics_payload(diagnostics)
    return packet, diagnostics


def cut_context_packet_issue_map(scene: dict[str, Any]) -> dict[str, list[str]]:
    """Return nonblocking warning diagnostics for all cuts in a scene."""

    issues: dict[str, list[str]] = {key: [] for key in WARNING_KEY_BY_DIAGNOSTIC}
    cuts = [cut for cut in _as_list(scene.get("cuts")) if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"]
    for index, cut in enumerate(cuts):
        previous_cut = cuts[index - 1] if index > 0 else None
        next_cut = cuts[index + 1] if index + 1 < len(cuts) else None
        _packet, diagnostics = cut_context_packet_for_review(scene, cut, previous_cut=previous_cut, next_cut=next_cut)
        for key in issues:
            values = [str(item) for item in _as_list(diagnostics.get(key)) if str(item).strip()]
            issues[key].extend(values)
    return {key: values for key, values in issues.items() if values}


def materialize_cut_context_packet(
    scene: dict[str, Any],
    cut: dict[str, Any],
    *,
    previous_cut: dict[str, Any] | None = None,
    next_cut: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compile and store the packet on cut_contract."""

    packet, diagnostics = compile_cut_context_packet(scene, cut, previous_cut=previous_cut, next_cut=next_cut)
    contract = _as_dict(cut.get("cut_contract"))
    if contract:
        contract["cut_context_packet"] = packet
        cut["cut_contract"] = contract
    else:
        cut["cut_context_packet"] = packet
    return packet, diagnostics


def _compile_packet(
    scene: dict[str, Any],
    cut: dict[str, Any],
    *,
    previous_cut: dict[str, Any] | None,
    next_cut: dict[str, Any] | None,
) -> dict[str, Any]:
    scene_event = _as_dict(scene.get("scene_event"))
    cut_contract = _as_dict(cut.get("cut_contract"))
    source_contract = _as_dict(cut_contract.get("source_event_contract"))
    viewer_contract = _as_dict(cut_contract.get("viewer_contract"))
    continuity = _as_dict(cut_contract.get("continuity_contract"))
    asset_dependency = _as_dict(cut_contract.get("asset_dependency"))
    cinematic = _as_dict(cut_contract.get("cinematic_contract"))
    screen_geography = _as_dict(cinematic.get("screen_geography"))
    primary_id = _text(source_contract.get("primary_event_beat_id"))
    source_ids = [_text(item) for item in _as_list(source_contract.get("source_event_beat_ids")) if _text(item)]
    if primary_id and primary_id not in source_ids:
        source_ids = [primary_id, *source_ids]
    event_sequence = [beat for beat in _as_list(scene_event.get("event_sequence")) if isinstance(beat, dict)]
    beat_by_id = {_text(beat.get("beat_id")): beat for beat in event_sequence if _text(beat.get("beat_id"))}
    source_beats = [beat_by_id[beat_id] for beat_id in source_ids if beat_id in beat_by_id]
    cut_assignment = _cut_assignment(scene, _selector(scene, cut))
    return _without_empty(
        {
            "schema_version": CUT_CONTEXT_PACKET_SCHEMA_VERSION,
            "derived_from": list(CUT_CONTEXT_PACKET_DERIVED_FROM),
            "editable": False,
            "cut_selector": _selector(scene, cut),
            "source_event": _without_empty(
                {
                    "primary_event_beat_id": primary_id,
                    "source_event_beat_ids": source_ids,
                    "primary_event_beat": beat_by_id.get(primary_id) or {},
                    "source_event_beats": source_beats,
                    "event_beat_function": source_contract.get("event_beat_function"),
                    "event_time_position": source_contract.get("event_time_position"),
                    "source_visible_action": source_contract.get("source_visible_action"),
                    "source_visible_reaction": source_contract.get("source_visible_reaction"),
                    "source_required_visual_evidence": _as_str_list(source_contract.get("source_required_visual_evidence")),
                    "event_facts_to_preserve": _as_str_list(source_contract.get("event_facts_to_preserve")),
                }
            ),
            "scene_obligations": _scene_obligations_for_cut(scene, cut_assignment, viewer_contract),
            "previous_next_delta": _without_empty(
                {
                    "previous_cut_selector": _selector(scene, previous_cut) if previous_cut else "",
                    "previous_end_state": _cut_end_state(previous_cut) if previous_cut else "",
                    "current_start_state": continuity.get("start_state") or _as_dict(cut_contract.get("first_frame_contract")).get("visible_start_state"),
                    "current_end_state": continuity.get("end_state") or _as_dict(cut_contract.get("motion_contract")).get("end_state"),
                    "next_cut_selector": _selector(scene, next_cut) if next_cut else "",
                    "next_start_requirement": _cut_start_state(next_cut) if next_cut else "",
                    "handoff": _as_dict(cut_contract.get("cut_handoff")),
                }
            ),
            "character_state": _without_empty(
                {
                    "scene_character_state_timeline_summary": scene.get("scene_character_state_timeline"),
                    "cut_character_emotion_transition": cut_contract.get("cut_character_emotion_transition"),
                }
            ),
            "film_grammar": _film_grammar(scene, cut, cut_contract),
            "location_use": _without_empty(
                {
                    "location_ids": _as_str_list(continuity.get("location_ids")) or _as_str_list(asset_dependency.get("location_ids_required")),
                    "screen_geography": screen_geography,
                    "foreground": screen_geography.get("foreground"),
                    "midground": screen_geography.get("midground"),
                    "background": screen_geography.get("background"),
                    "screen_direction": screen_geography.get("screen_direction"),
                }
            ),
            "object_reference_use": _without_empty(
                {
                    "required_character_ids": _as_str_list(asset_dependency.get("character_ids_required")) or _as_str_list(continuity.get("character_ids")),
                    "required_object_ids": _as_str_list(asset_dependency.get("object_ids_required")) or _as_str_list(continuity.get("object_ids")),
                    "required_location_ids": _as_str_list(asset_dependency.get("location_ids_required")) or _as_str_list(continuity.get("location_ids")),
                    "must_show": _as_str_list(viewer_contract.get("must_show")),
                    "object_visibility": _as_str_list(viewer_contract.get("visual_evidence")),
                }
            ),
            "boundary": _without_empty(
                {
                    "allowed_info_ids": _as_str_list(source_contract.get("allowed_reveal_info_ids")),
                    "forbidden_info_ids": _as_str_list(source_contract.get("forbidden_reveal_info_ids")),
                    "forbidden_event_changes": _as_str_list(scene_event.get("forbidden_event_changes")),
                    "event_facts_not_to_invent": _as_str_list(source_contract.get("event_facts_not_to_invent")),
                    "reveal_constraints": _reveal_constraints(scene, viewer_contract),
                }
            ),
            "output_requirements": {
                "must_output": ["cut_contract_patch", "first_frame_brief", "motion_boundary", "api_prompt_payload_seed"],
                "must_not_output": ["full_scene_summary", "debug_reasoning", "unrelated_assets", "future_reveals"],
            },
        }
    )


def diagnose_cut_context_packet(
    scene: dict[str, Any],
    cut: dict[str, Any],
    packet: dict[str, Any],
    *,
    previous_cut: dict[str, Any] | None,
    next_cut: dict[str, Any] | None,
    packet_was_missing: bool,
) -> dict[str, Any]:
    selector = _selector(scene, cut)
    diagnostics: dict[str, list[str]] = {key: [] for key in WARNING_KEY_BY_DIAGNOSTIC}
    if packet_was_missing:
        diagnostics["missing_packet"].append(selector)
    if not packet:
        diagnostics["missing_packet"].append(selector)
        diagnostics["warning_keys"] = _warning_keys(diagnostics)
        return diagnostics

    derived_from = {str(item) for item in _as_list(packet.get("derived_from"))}
    if (
        str(packet.get("schema_version") or "").strip() != CUT_CONTEXT_PACKET_SCHEMA_VERSION
        or not set(CUT_CONTEXT_PACKET_DERIVED_FROM).issubset(derived_from)
        or packet.get("editable") is not False
    ):
        diagnostics["invalid_derived_from"].append(selector)

    source_contract = _as_dict(_as_dict(cut.get("cut_contract")).get("source_event_contract"))
    primary_id = _text(source_contract.get("primary_event_beat_id"))
    packet_source = _as_dict(packet.get("source_event"))
    packet_primary = _as_dict(packet_source.get("primary_event_beat"))
    if primary_id and _text(packet_primary.get("beat_id")) != primary_id:
        diagnostics["missing_event_beat"].append(f"{selector}:{primary_id}")

    expected_roles = _expected_required_roles(scene, cut)
    packet_roles = _packet_required_roles(packet)
    missing_roles = sorted(role for role in expected_roles if role not in packet_roles)
    if missing_roles:
        diagnostics["missing_required_roles"].extend(f"{selector}:{role}" for role in missing_roles)

    expected_visual_terms = _expected_visual_proof_terms(scene, cut)
    packet_text = _flatten_text(packet)
    missing_visual_terms = sorted(term for term in expected_visual_terms if term and term not in packet_text)
    if missing_visual_terms:
        diagnostics["missing_visual_proof"].extend(f"{selector}:{term}" for term in missing_visual_terms[:8])

    expected_boundary = _expected_boundary_terms(scene, cut)
    packet_boundary_text = _flatten_text(_as_dict(packet.get("boundary")))
    missing_boundary = sorted(term for term in expected_boundary if term and term not in packet_boundary_text)
    if missing_boundary:
        diagnostics["missing_reveal_boundary"].extend(f"{selector}:{term}" for term in missing_boundary[:8])

    delta = _as_dict(packet.get("previous_next_delta"))
    has_cut_neighbor = previous_cut is not None or next_cut is not None
    has_delta = bool(delta.get("current_start_state")) and bool(delta.get("current_end_state"))
    if has_cut_neighbor and not has_delta:
        diagnostics["missing_previous_next_delta"].append(selector)

    if "scene_event" in packet or "all_assets" in packet or "all_scenes" in packet:
        diagnostics["unrelated_scene_info_risk"].append(selector)

    compact = {key: values for key, values in diagnostics.items() if values}
    compact["warning_keys"] = _warning_keys(compact)
    return compact


def _packet_diagnostics_payload(diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        "warning_keys": _as_str_list(diagnostics.get("warning_keys")),
        "missing_required_roles": _diagnostic_values(diagnostics, "missing_required_roles"),
        "missing_visual_proof": _diagnostic_values(diagnostics, "missing_visual_proof"),
        "missing_event_beat": _diagnostic_values(diagnostics, "missing_event_beat"),
        "missing_reveal_boundary": _diagnostic_values(diagnostics, "missing_reveal_boundary"),
        "missing_previous_next_delta": _diagnostic_values(diagnostics, "missing_previous_next_delta"),
        "unrelated_scene_info_risk": _diagnostic_values(diagnostics, "unrelated_scene_info_risk"),
    }


def _diagnostic_values(diagnostics: dict[str, Any], key: str) -> list[str]:
    values: list[str] = []
    for item in _as_list(diagnostics.get(key)):
        text = str(item)
        values.append(text.split(":", 1)[1] if ":" in text else text)
    return _unique(values)


def _warning_keys(diagnostics: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for key, warning_key in WARNING_KEY_BY_DIAGNOSTIC.items():
        if _as_list(diagnostics.get(key)):
            keys.append(warning_key)
    return keys


def _stored_packet(cut: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(cut.get("cut_context_packet"))
    if direct:
        return direct
    return _as_dict(_as_dict(cut.get("cut_contract")).get("cut_context_packet"))


def _scene_obligations_for_cut(scene: dict[str, Any], assignment: dict[str, Any], viewer_contract: dict[str, Any]) -> list[dict[str, Any]]:
    selector = _text(assignment.get("cut_selector"))
    assigned_ids = {_text(item) for item in _as_list(assignment.get("obligation_ids")) if _text(item)}
    if _text(assignment.get("obligation_id")):
        assigned_ids.add(_text(assignment.get("obligation_id")))
    obligations: list[dict[str, Any]] = []
    for obligation in _as_list(_as_dict(scene.get("scene_cut_coverage_plan")).get("scene_obligations")):
        if not isinstance(obligation, dict):
            continue
        assigned_cut_ids = {_text(item) for item in _as_list(obligation.get("assigned_cut_ids")) if _text(item)}
        obligation_id = _text(obligation.get("obligation_id"))
        if selector and selector not in assigned_cut_ids and obligation_id not in assigned_ids:
            continue
        obligations.append(
            _without_empty(
                {
                    "obligation_id": obligation_id,
                    "source": obligation.get("source"),
                    "evidence": obligation.get("evidence"),
                    "assigned_cut_ids": _as_str_list(obligation.get("assigned_cut_ids")),
                    "required_roles": _as_str_list(assignment.get("required_roles")) or _as_str_list(viewer_contract.get("required_roles")),
                    "visual_proof": assignment.get("visual_proof") or viewer_contract.get("visual_proof"),
                    "audience_knowledge_delta": assignment.get("audience_knowledge_delta") or viewer_contract.get("audience_knowledge_delta"),
                    "causal_proof": assignment.get("causal_proof") or viewer_contract.get("causal_proof"),
                }
            )
        )
    if not obligations:
        obligations.append(
            _without_empty(
                {
                    "obligation_id": assignment.get("obligation_id") or "",
                    "source": assignment.get("source") or "",
                    "required_roles": _as_str_list(assignment.get("required_roles")) or _as_str_list(viewer_contract.get("required_roles")),
                    "visual_proof": assignment.get("visual_proof") or viewer_contract.get("visual_proof"),
                }
            )
        )
    return [item for item in obligations if item]


def _film_grammar(scene: dict[str, Any], cut: dict[str, Any], cut_contract: dict[str, Any]) -> dict[str, Any]:
    selector = _selector(scene, cut)
    shot: dict[str, Any] = {}
    film_plan = _as_dict(scene.get("scene_film_coverage_plan"))
    for candidate in _as_list(_as_dict(film_plan.get("shot_mix")).get("actual_shots")):
        if isinstance(candidate, dict) and _text(candidate.get("selector")) == selector:
            shot = candidate
            break
    grammar = _as_dict(cut_contract.get("cut_film_grammar_contract"))
    required_modules = _as_dict(grammar.get("required_modules"))
    return _without_empty(
        {
            "shot_role": shot.get("shot_role"),
            "shot_scale": shot.get("shot_scale"),
            "shot_mix_record": shot,
            "edit_motivation": _as_dict(required_modules.get("edit_motivation")),
            "attention_state": _as_dict(required_modules.get("attention_state")),
            "cut_film_grammar_contract": grammar,
        }
    )


def _cut_assignment(scene: dict[str, Any], selector: str) -> dict[str, Any]:
    plan = _as_dict(scene.get("scene_cut_coverage_plan"))
    for assignment in _as_list(plan.get("cut_assignments")):
        if isinstance(assignment, dict) and _text(assignment.get("cut_selector")) == selector:
            return dict(assignment)
    return {}


def _expected_required_roles(scene: dict[str, Any], cut: dict[str, Any]) -> set[str]:
    contract = _as_dict(cut.get("cut_contract"))
    viewer = _as_dict(contract.get("viewer_contract"))
    assignment = _cut_assignment(scene, _selector(scene, cut))
    return {
        item
        for item in [
            *_as_str_list(viewer.get("required_roles")),
            *_as_str_list(assignment.get("required_roles")),
        ]
        if item
    }


def _packet_required_roles(packet: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for obligation in _as_list(packet.get("scene_obligations")):
        if isinstance(obligation, dict):
            roles.update(_as_str_list(obligation.get("required_roles")))
    roles.update(_as_str_list(_as_dict(packet.get("object_reference_use")).get("required_character_ids")))
    return roles


def _expected_visual_proof_terms(scene: dict[str, Any], cut: dict[str, Any]) -> set[str]:
    contract = _as_dict(cut.get("cut_contract"))
    viewer = _as_dict(contract.get("viewer_contract"))
    source = _as_dict(contract.get("source_event_contract"))
    assignment = _cut_assignment(scene, _selector(scene, cut))
    values = [
        *_as_str_list(viewer.get("visual_evidence")),
        *_as_str_list(source.get("source_required_visual_evidence")),
        _text(viewer.get("visual_proof")),
        _text(assignment.get("visual_proof")),
    ]
    return {value for value in values if value}


def _expected_boundary_terms(scene: dict[str, Any], cut: dict[str, Any]) -> set[str]:
    contract = _as_dict(cut.get("cut_contract"))
    source = _as_dict(contract.get("source_event_contract"))
    scene_event = _as_dict(scene.get("scene_event"))
    intent = _as_dict(scene.get("scene_intent"))
    return {
        value
        for value in [
            *_as_str_list(source.get("event_facts_not_to_invent")),
            *_as_str_list(source.get("forbidden_reveal_info_ids")),
            *_as_str_list(scene_event.get("forbidden_event_changes")),
            *_as_str_list(intent.get("reveal_constraints")),
        ]
        if value
    }


def _cut_start_state(cut: dict[str, Any] | None) -> Any:
    contract = _as_dict((cut or {}).get("cut_contract"))
    return _as_dict(contract.get("continuity_contract")).get("start_state") or _as_dict(contract.get("first_frame_contract")).get("visible_start_state")


def _cut_end_state(cut: dict[str, Any] | None) -> Any:
    contract = _as_dict((cut or {}).get("cut_contract"))
    return _as_dict(contract.get("continuity_contract")).get("end_state") or _as_dict(contract.get("motion_contract")).get("end_state")


def _reveal_constraints(scene: dict[str, Any], viewer_contract: dict[str, Any]) -> Any:
    reveal = viewer_contract.get("reveal_constraints")
    if reveal not in (None, "", [], {}):
        return reveal
    return _as_dict(scene.get("scene_intent")).get("reveal_constraints")


def _selector(scene: dict[str, Any], cut: dict[str, Any] | None) -> str:
    if not isinstance(cut, dict):
        return ""
    raw = _text(cut.get("selector"))
    if raw:
        return raw
    scene_id = _text(scene.get("scene_id"), "unknown")
    cut_id = _text(cut.get("cut_id"), "01")
    if cut_id.isdigit():
        cut_id = f"{int(cut_id):02d}"
    return f"scene{scene_id}_cut{cut_id}"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_str_list(value: Any) -> list[str]:
    return _unique(str(item).strip() for item in _as_list(value) if str(item).strip())


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value or "")


def _without_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}
