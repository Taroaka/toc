"""Lossless scene projections for source-first p400; no synthetic plot defaults."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from toc.visual_planning_contract import VISUAL_PLANNING_CONTRACT, planning_marker


def source_first_profile(profile: dict) -> bool:
    visual = profile.get("visual_planning")
    if not isinstance(visual, dict):
        return False
    marker = planning_marker(visual, "visual_value_metadata")
    if marker != VISUAL_PLANNING_CONTRACT:
        raise ValueError("unsupported visual planning contract")
    return True


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def scene_notes(profile: dict, scene: dict) -> list[str]:
    rows = profile["visual_planning"].get("scene_visual_values", [])
    matches = [row for row in rows if str(row.get("scene_selector")) == str(scene.get("scene_id"))]
    if len(matches) != 1 or not isinstance(matches[0].get("notes"), list):
        raise ValueError("source scene visual notes missing or ambiguous")
    return deepcopy(matches[0]["notes"])


def source_blueprint(scene: dict) -> dict:
    if not scene:
        raise ValueError("source-first scene is missing")
    intent = _dict(scene.get("scene_intent"))
    beats = _list(scene.get("event_sequence"))
    facts = [b["what_happens"] for b in beats if isinstance(b, dict) and b.get("what_happens")]
    evidence = list(dict.fromkeys(e for b in beats for e in _list(b.get("required_visual_evidence"))))
    handoff = _dict(scene.get("handoff_chain"))
    outgoing = _dict(handoff.get("outgoing"))
    incoming = _dict(handoff.get("incoming"))
    shift = _dict(intent.get("value_shift"))
    start = _dict(scene.get("start_state"))
    end = _dict(scene.get("end_state"))
    conflict = _dict(intent.get("scene_conflict_engine"))
    result = {
        "source_events": facts,
        "research_refs": deepcopy(scene.get("research_refs", [])),
        "semantic_scene_responsibility_id": str(scene.get("semantic_scene_responsibility_id") or scene.get("scene_id")),
        "segment_beat_ids": [b["beat_id"] for b in beats],
        "segment_responsibility": scene.get("purpose", ""),
        "story_purpose": intent.get("story_purpose", scene.get("purpose", "")),
        "dramatic_question": intent.get("dramatic_question", ""),
        "scene_spine": intent.get("scene_spine", ""),
        "desire": conflict.get("desire", intent.get("desire", "")),
        "obstacle": conflict.get("obstacle", scene.get("conflict", "")),
        "stakes": conflict.get("stakes", ""),
        "escalation": conflict.get("escalation", ""),
        "no_return_point": conflict.get("no_return_point", ""),
        "visible_pressure": deepcopy(conflict.get("visible_pressure", [])),
        "pressure_source": conflict.get("pressure_source", ""),
        "pressure_source_visible_from": "",
        "turn_motion_target": "",
        "payoff_focus": "",
        "beat_overrides": {},
        "causal_turn": intent.get("causal_turn", scene.get("turn", "")),
        "payoff": intent.get("payoff", ""),
        "handoff_anchor": outgoing.get("visible_or_audible_form", ""),
        "incoming_trigger": incoming.get("visible_or_audible_form", ""),
        "outgoing_pressure": outgoing.get("required_next_scene_start_pressure", ""),
        "value_from": shift.get("from", start.get("description", "")),
        "value_to": shift.get("to", end.get("description", "")),
        "visible_evidence": evidence,
        "character_start": start.get("description", ""),
        "character_end": end.get("description", ""),
        "story_terms": [],
        "story_overview_visualizable_action": scene.get("visualizable_action", ""),
        "story_scene_id": str(scene.get("scene_id", "")),
    }
    return deepcopy(result)


def source_scene_intent(scene: dict, profile: dict, location: dict) -> dict:
    intent = deepcopy(_dict(scene.get("scene_intent")))
    blueprint = source_blueprint(scene)
    start, end = _dict(scene.get("start_state")), _dict(scene.get("end_state"))
    reveal = _dict(scene.get("reveal_contract"))
    defaults = {
        "story_purpose": blueprint["story_purpose"],
        "dramatic_question": "", "value_shift": {}, "causal_turn": scene.get("turn", ""),
        "done_when": [], "audience_information": [], "withheld_information": [], "reveal_constraints": [],
        "audience_knowledge_delta": {
            "before_scene": deepcopy(start.get("audience_knowledge", [])),
            "learned_during_scene": [b["audience_knowledge_delta"] for b in _list(scene.get("event_sequence")) if b.get("audience_knowledge_delta")],
            "still_unknown_after_scene": deepcopy(end.get("withheld_information", [])),
            "forbidden_early_reveals": deepcopy(reveal.get("must_not_show", [])),
        },
        "affect_transition": "", "character_state": {}, "production_risks": [],
        "scene_conflict_engine": {}, "story_specificity": {},
        "handoff_notes": {}, "visual_thesis": "",
        "spatial_plan": {"location_id": location.get("asset_id", ""), "screen_geography": "", "continuity_anchors": []},
        "handoff_to_next_scene": "", "terminal_resolution": "",
    }
    for key, value in defaults.items():
        intent.setdefault(key, value)
    intent.pop("scene_value_amplification", None)
    for key in ("start_state", "end_state", "handoff_chain", "preservation", "reveal_contract"):
        if key in scene:
            intent[key] = deepcopy(scene[key])
    intent["authored_scene_id"] = str(scene["scene_id"])
    intent["visual_notes"] = scene_notes(profile, scene)
    intent["story_overview_visualizable_action"] = scene.get("visualizable_action", "")
    return intent


def source_scene_event(scene: dict, *, runtime_scene_id: int, location_name: str) -> dict:
    beats = deepcopy(scene.get("event_sequence"))
    if not isinstance(beats, list) or not beats:
        raise ValueError("source-first event_sequence is missing")
    for beat in beats:
        if not isinstance(beat, dict) or not beat.get("beat_id") or not beat.get("what_happens"):
            raise ValueError("source-first event beat is invalid")
        beat.setdefault("visible_action", beat["what_happens"])
        beat.setdefault("visible_reaction", "")
        beat.setdefault("motion_brief", beat["visible_action"])
        beat.setdefault("motion_end_state", beat.get("immediate_consequence", ""))
        beat.setdefault("required_roles", deepcopy(beat.get("participants", beat.get("character_ids", []))))
        beat.setdefault("required_visual_evidence", [])
        beat.setdefault("must_be_seen", True)
        concrete = deepcopy(_dict(beat.get("concrete_event")))
        for key in ("what_happens", "visible_action", "visible_reaction", "immediate_consequence", "required_visual_evidence", "motion_brief", "motion_end_state"):
            concrete.setdefault(key, deepcopy(beat.get(key, "")))
        concrete.setdefault("who", deepcopy(beat["required_roles"]))
        concrete.setdefault("where", beat.get("location", location_name))
        beat["concrete_event"] = concrete
        grounding = deepcopy(_dict(beat.get("story_grounding")))
        grounding.setdefault("research_refs", deepcopy(beat.get("research_refs", scene.get("research_refs", []))))
        grounding.setdefault("source_text_or_summary", beat["what_happens"])
        grounding["source_event_ids"] = deepcopy(beat.get("source_event_ids", []))
        beat["story_grounding"] = grounding
    result = {"schema_version": "scene_event_v1", "scene_id": runtime_scene_id,
        "authored_scene_id": str(scene["scene_id"]), "event_logline": scene.get("purpose", ""),
        "event_sequence": beats, "research_refs": deepcopy(scene.get("research_refs", [])),
        "forbidden_event_changes": deepcopy(_dict(scene.get("preservation")).get("must_not_show", []))}
    for key in ("start_state", "end_state", "turning_event", "handoff_chain", "preservation", "reveal_contract"):
        result[key] = deepcopy(scene.get(key, {}))
    turn = result["turning_event"]
    if isinstance(turn, dict) and turn.get("beat_id"):
        turn.setdefault("source_event_beat_id", turn["beat_id"])
    return result
