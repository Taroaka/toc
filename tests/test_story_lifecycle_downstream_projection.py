"""RED coverage for projecting the authored story lifecycle into cut design.

The Story Author is allowed to choose the number and names of event beats.  A
downstream compiler may enrich those beats for image/cut work, but it must not
replace them with a fixed setup/pressure/turn/payoff ladder or invent a second
start/end/handoff state machine.
"""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_frontend_run_module() -> Any:
    module_name = "story_lifecycle_downstream_projection_frontend_run"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name,
        REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _authored_scene(
    *,
    scene_id: str,
    title: str,
    event_id: str,
    location_id: str,
    location_name: str,
    start_state_id: str,
    end_state_id: str,
    previous_scene_id: str,
    next_scene_id: str,
    beats: list[dict[str, Any]],
    turning_beat_id: str,
    turning_text: str,
) -> dict[str, Any]:
    start_state = {
        "state_id": start_state_id,
        "location_id": location_id,
        "description": f"開始時、{location_name}では{start_state_id}が成立している。",
        "characters": ["character_wanderer"],
        "relationships": ["関係はまだ確定していない"],
        "objects": ["object_token"],
        "audience_knowledge": ["観客は開始条件だけを知っている"],
    }
    end_state = {
        "state_id": end_state_id,
        "location_id": location_id,
        "description": f"終了時、{location_name}には{end_state_id}が残っている。",
        "characters": ["character_wanderer"],
        "relationships": ["次の場面へ原因が渡っている"],
        "objects": ["object_token"],
        "audience_knowledge": ["観客は転換後の条件を知っている"],
        "unresolved_threads": ["次の場所で結果を確かめる"],
    }
    handoff_chain = {
        "incoming": {
            "producer_scene_id": previous_scene_id,
            "state_id": start_state_id,
            "anchor_id": f"{scene_id}_incoming_anchor",
            "visible_or_audible_form": "前場面から届いた低い鐘の反響",
        },
        "outgoing": {
            "consumer_scene_id": next_scene_id,
            "state_id": end_state_id,
            "anchor_id": f"{scene_id}_outgoing_anchor",
            "visible_or_audible_form": "濡れた印と手渡された金属片",
            "required_next_scene_start_conditions": [end_state_id],
        },
    }
    return {
        "scene_id": scene_id,
        "canonical_scene_index": 1 if scene_id == "scene_alpha" else 2,
        "semantic_scene_responsibility_id": scene_id,
        "title": title,
        "phase": "opening" if scene_id == "scene_alpha" else "ending",
        "purpose": f"{title}だけが成立させる出来事。",
        "conflict": f"{location_name}の規則が、{title}の選択を狭める。",
        "turn": turning_text,
        "affect": {"label_hint": "tension", "audience_job": "follow_causality"},
        "visualizable_action": "複数の観測可能な出来事が順番に起きる。",
        "grounding_note": f"source event {event_id} を保持する。",
        "source_basis": {
            "event_ids": [event_id],
            "character_ids": ["character_wanderer"],
            "place_ids": [location_id],
        },
        "research_refs": [
            f"research.story_materials.chronological_events[{event_id}]"
        ],
        "location": {
            "location_id": location_id,
            "name": location_name,
            "mode": "single",
            "sequence": [location_name],
            "segments": [],
        },
        "time_of_day": "夜明け前" if scene_id == "scene_alpha" else "朝",
        "time_of_day_visual_basis": (
            "光源: 低い自然光; 明るさ: 控えめ; 影: 長い; 色温度: 冷たい。"
        ),
        "target_duration_seconds": 210,
        "narration_target_seconds": 140,
        "scene_intent": {
            "story_purpose": f"{title}だけが成立させる出来事。",
            "dramatic_question": f"{title}の選択は状態を変えるか。",
            "value_shift": {"from": start_state_id, "to": end_state_id},
            "causal_turn": turning_text,
            "start_state": deepcopy(start_state),
            "end_state": deepcopy(end_state),
            "handoff_chain": deepcopy(handoff_chain),
        },
        "start_state": start_state,
        "event_sequence": beats,
        "turning_event": {
            "beat_id": turning_beat_id,
            "irreversible_change": turning_text,
            "source_refs": [event_id],
        },
        "end_state": end_state,
        "handoff_chain": handoff_chain,
        "preservation": {
            "must_preserve": ["出来事の順序", "濡れた印", "金属片"],
            "must_not_change": ["source event の因果"],
            "must_not_show": ["まだ起きていない帰還"],
        },
    }


def _rich_story() -> dict[str, Any]:
    first_beats = [
        {
            "beat_id": "alpha_observe_mark",
            "beat_function": "observe_trace",
            "source_event_ids": ["event_alpha"],
            "what_happens": "主人公が濡れた印を見つける。",
            "visible_action": "指先が印の輪郭で止まる。",
            "immediate_consequence": "印が誰かの到着を示す。",
            "required_visual_evidence": ["濡れた印"],
        },
        {
            "beat_id": "alpha_hear_echo",
            "beat_function": "hear_echo",
            "source_event_ids": ["event_alpha"],
            "what_happens": "閉じた門の内側から鐘の反響が返る。",
            "visible_action": "門の鎖だけが微かに揺れる。",
            "immediate_consequence": "内側に応答する存在がいる。",
            "required_visual_evidence": ["揺れる鎖", "鐘の反響"],
        },
        {
            "beat_id": "alpha_name_cost",
            "beat_function": "name_cost",
            "source_event_ids": ["event_alpha"],
            "what_happens": "門番が通過の代償を告げる。",
            "visible_action": "門番が金属片を境界線へ置く。",
            "immediate_consequence": "選択の代償が目に見える。",
            "required_visual_evidence": ["金属片", "境界線"],
        },
        {
            "beat_id": "alpha_accept_cost",
            "beat_function": "accept_cost",
            "source_event_ids": ["event_alpha"],
            "what_happens": "主人公が代償を引き受ける言葉を選ぶ。",
            "visible_action": "主人公が金属片を印の隣へ置く。",
            "immediate_consequence": "主人公の選択が撤回できなくなる。",
            "required_visual_evidence": ["金属片", "主人公の手"],
        },
        {
            "beat_id": "alpha_cross_threshold",
            "beat_function": "cross_threshold",
            "source_event_ids": ["event_alpha"],
            "what_happens": "門が開き、主人公は次の場所へ入る。",
            "visible_action": "片足が境界を越え、印と金属片が残る。",
            "immediate_consequence": "次の場面は残された印から始まる。",
            "required_visual_evidence": ["開いた門", "残された印"],
        },
    ]
    second_beats = [
        {
            "beat_id": "beta_receive_token",
            "beat_function": "receive_token",
            "source_event_ids": ["event_beta"],
            "what_happens": "次の場所で金属片が受け取られる。",
            "visible_action": "手から手へ金属片が渡る。",
            "immediate_consequence": "門での選択が別の関係へ届く。",
            "required_visual_evidence": ["金属片", "二人の手"],
        },
        {
            "beat_id": "beta_reveal_pattern",
            "beat_function": "read_pattern",
            "source_event_ids": ["event_beta"],
            "what_happens": "金属片の刻印が地図の一部だと分かる。",
            "visible_action": "刻印と壁面の線が重なる。",
            "immediate_consequence": "さらに先の場所が必要になる。",
            "required_visual_evidence": ["刻印", "壁面の線"],
        },
    ]
    return {
        "story_metadata": {
            "scene_authoring_contract": "story_scene_contract_v1",
            "topic": "The Tidal Archive",
            "time": "架空の沿岸都市",
            "target_duration_seconds": 420,
            "scene_time_of_day_contract": "required_v1",
            "scene_time_of_day_visual_basis_contract": "required_v1",
        },
        "script": {
            "scenes": [
                _authored_scene(
                    scene_id="scene_alpha",
                    title="The Gate Listens",
                    event_id="event_alpha",
                    location_id="place_gate",
                    location_name="North Gate",
                    start_state_id="state_unheard",
                    end_state_id="state_named",
                    previous_scene_id="",
                    next_scene_id="scene_beta",
                    beats=first_beats,
                    turning_beat_id="alpha_accept_cost",
                    turning_text="主人公が代償を公に引き受ける。",
                ),
                _authored_scene(
                    scene_id="scene_beta",
                    title="The Archive Receives",
                    event_id="event_beta",
                    location_id="place_archive",
                    location_name="Tidal Archive",
                    start_state_id="state_named",
                    end_state_id="state_mapped",
                    previous_scene_id="scene_alpha",
                    next_scene_id="",
                    beats=second_beats,
                    turning_beat_id="beta_reveal_pattern",
                    turning_text="刻印が次の場所を示す地図として認識される。",
                ),
            ]
        },
    }


def _project_scene_design(module: Any, story: dict[str, Any], index: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base_profile = module._story_profile(
        "The Tidal Archive",
        "neutral fixture source",
        variant_seed="lifecycle-downstream-projection",
    )
    profile = module._profile_from_story(base_profile, story)
    title = profile["scene_titles"][index - 1]
    location = module._location_spec_for_scene(profile, index)
    intent = module._scene_intent_for_cut_design(
        title=title,
        idx=index,
        location_spec=location,
        profile=profile,
        include_artifact=False,
    )
    event = module._scene_event_for_cut_design(
        title=title,
        idx=index,
        scene_intent=intent,
        location_name=str(location["name"]),
        location_id=str(location["asset_id"]),
        profile=profile,
        include_artifact=False,
    )
    return profile, intent, event


def test_rich_scene_lifecycle_is_projected_into_scene_intent_without_reconstruction() -> None:
    module = _load_frontend_run_module()
    story = _rich_story()
    authored = story["script"]["scenes"][0]

    profile, intent, _event = _project_scene_design(module, story, 1)

    # The profile handoff and the scene-intent handoff must retain the
    # author-owned state machine.  Rebuilding a fresh state from profile
    # titles/locations loses the causal boundary before cut design begins.
    assert profile["story_scenes"][0]["start_state"] == authored["start_state"]
    assert profile["story_scenes"][0]["end_state"] == authored["end_state"]
    assert profile["story_scenes"][0]["handoff_chain"] == authored["handoff_chain"]
    assert intent.get("start_state") == authored["start_state"]
    assert intent.get("end_state") == authored["end_state"]
    assert intent.get("handoff_chain") == authored["handoff_chain"]


def test_authored_event_sequence_turn_and_handoff_survive_scene_event_projection() -> None:
    module = _load_frontend_run_module()
    story = _rich_story()
    authored = story["script"]["scenes"][0]

    _profile, _intent, event = _project_scene_design(module, story, 1)

    authored_beats = authored["event_sequence"]
    projected_beats = event.get("event_sequence")
    assert isinstance(projected_beats, list)
    assert [beat.get("beat_id") for beat in projected_beats] == [
        beat["beat_id"] for beat in authored_beats
    ]
    assert [beat.get("beat_function") for beat in projected_beats] == [
        beat["beat_function"] for beat in authored_beats
    ]
    assert [beat.get("what_happens") for beat in projected_beats] == [
        beat["what_happens"] for beat in authored_beats
    ]
    assert len(projected_beats) > 4

    turning = event.get("turning_event")
    assert isinstance(turning, dict)
    assert turning.get("source_event_beat_id") == authored["turning_event"]["beat_id"]
    assert turning.get("irreversible_change") == authored["turning_event"]["irreversible_change"]

    # Keep the explicit state objects and handoff as an extension of the
    # scene_event contract so downstream compilers can bind to authored IDs,
    # not only to prose strings such as ``start_situation``.
    assert event.get("start_state") == authored["start_state"]
    assert event.get("end_state") == authored["end_state"]
    assert event.get("handoff_chain") == authored["handoff_chain"]


@pytest.mark.parametrize("index", [1, 2])
def test_each_authored_scene_keeps_its_own_turning_beat_and_neighbor_state(index: int) -> None:
    module = _load_frontend_run_module()
    story = _rich_story()
    authored = story["script"]["scenes"][index - 1]

    _profile, intent, event = _project_scene_design(module, story, index)

    turning = event["turning_event"]
    assert turning["source_event_beat_id"] == authored["turning_event"]["beat_id"]
    assert turning["irreversible_change"] == authored["turning_event"]["irreversible_change"]
    assert intent["handoff_chain"] == authored["handoff_chain"]
    assert event["start_state"]["state_id"] == authored["start_state"]["state_id"]
    assert event["end_state"]["state_id"] == authored["end_state"]["state_id"]


@pytest.mark.parametrize("delta", [None, "", "  ", "同じ行為に複数の解釈が残る。"])
def test_event_obligation_prefers_authored_understanding_with_legacy_fallback(delta) -> None:
    module = _load_frontend_run_module()
    beat = {
        "beat_id": "beat_source",
        "what_happens": "行為が終わる。",
        "audience_knowledge_delta": delta,
        "immediate_consequence": "周囲の状況が変わる。",
    }
    scene_event = {"event_sequence": [beat]}
    original = deepcopy(scene_event)

    obligations = module._story_event_obligations_from_scene_event(scene_event)

    expected = (delta or "").strip() or beat["immediate_consequence"]
    assert obligations[0]["audience_knowledge_delta"] == expected
    assert scene_event == original


def test_cut_coverage_preserves_the_primary_beats_authored_understanding() -> None:
    module = _load_frontend_run_module()
    story = _rich_story()
    authored = story["script"]["scenes"][0]
    for index, beat in enumerate(authored["event_sequence"]):
        beat["audience_knowledge_delta"] = f"根拠{index}を知っても、解釈は未確定のまま残る。"
    profile, intent, event = _project_scene_design(module, story, 1)
    location = module._location_spec_for_scene(profile, 1)
    event_before = deepcopy(event)

    result = module._scene_cut_coverage_plan(
        title=profile["scene_titles"][0],
        idx=1,
        scene_intent=intent,
        scene_event=event,
        location_name=str(location["name"]),
        profile=profile,
        include_artifact=False,
    )

    deltas = {beat["beat_id"]: beat["audience_knowledge_delta"] for beat in authored["event_sequence"]}
    assert result["coverage_plan"]["cut_assignments"]
    for assignment in result["coverage_plan"]["cut_assignments"]:
        primary_id = assignment["event_assignment"]["source_event_contract"]["primary_event_beat_id"]
        assert assignment["audience_knowledge_delta"] == deltas[primary_id]
    assert event == event_before
