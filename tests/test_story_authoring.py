from __future__ import annotations

from copy import deepcopy

import pytest

from toc.story_authoring import (
    build_research_registry,
    build_story_architect_prompt,
    validate_story_document,
)


def _research(prefix: str) -> dict:
    long_event = (
        f"{prefix}固有の出来事。人物が場所の規則に直面し、具体物を動かした結果、"
        "関係と観客の理解が不可逆に変化する。"
        + "この根拠本文を省略してはならない。" * 20
    )
    return {
        "story_materials": {
            "chronological_events": [
                {
                    "event_id": f"{prefix}-E01",
                    "event": long_event,
                    "involved_characters": [f"{prefix}-C01", f"{prefix}-C02"],
                    "place_ids": [f"{prefix}-L01"],
                    "world_rule_ids": [f"{prefix}-R01"],
                    "sources": [f"{prefix}-P01"],
                    "confidence": 0.91,
                },
                {
                    "event_id": f"{prefix}-E02",
                    "event": f"{prefix}の第二イベント。第一イベントの結果を受けて帰還する。",
                    "involved_characters": [f"{prefix}-C01"],
                    "place_ids": [f"{prefix}-L02"],
                    "world_rule_ids": [f"{prefix}-R01"],
                    "sources": [f"{prefix}-P02"],
                    "confidence": 0.87,
                },
            ],
            "characters": [
                {
                    "character_id": f"{prefix}-C01",
                    "name": f"{prefix}主人公",
                    "role": "protagonist",
                    "motivations": [f"{prefix}固有の長い動機を最後まで保持する"],
                    "relationships": [
                        {
                            "target": f"{prefix}-C02",
                            "relation": f"{prefix}固有の関係性",
                            "evidence_refs": [f"{prefix}-P01"],
                        }
                    ],
                },
                {
                    "character_id": f"{prefix}-C02",
                    "name": f"{prefix}同行者",
                    "role": "helper",
                },
            ],
            "setting": {
                "places": [
                    {
                        "place_id": f"{prefix}-L01",
                        "name": f"{prefix}開始地点",
                        "description": f"{prefix}にしか存在しない場所の具体的な状態",
                        "source_refs": [f"{prefix}-P01"],
                    },
                    {
                        "place_id": f"{prefix}-L02",
                        "name": f"{prefix}帰還地点",
                        "description": f"{prefix}の帰還後の場所",
                        "source_refs": [f"{prefix}-P02"],
                    },
                ],
                "world_rules": [
                    {
                        "rule_id": f"{prefix}-R01",
                        "rule": f"{prefix}固有の世界規則。破ると帰還条件が変化する。",
                        "evidence_refs": [f"{prefix}-P01"],
                    }
                ],
            },
            "symbols_and_themes": [
                {
                    "item_id": f"{prefix}-SYM01",
                    "item": f"{prefix}固有の象徴物",
                    "meaning": "選択の代償",
                    "evidence_refs": [f"{prefix}-P01"],
                }
            ],
        },
        "source_passages": [
            {
                "passage_id": f"{prefix}-P01",
                "source_id": f"{prefix}-S01",
                "passage": f"{prefix}の第一資料本文。省略禁止。" * 12,
                "evidence_note": "第一イベントを裏付ける",
                "confidence": 0.91,
            },
            {
                "passage_id": f"{prefix}-P02",
                "source_id": f"{prefix}-S01",
                "passage": f"{prefix}の帰還資料本文。",
                "evidence_note": "第二イベントを裏付ける",
                "confidence": 0.87,
            },
        ],
        "facts": {"items": [{"fact_id": f"{prefix}-F01", "claim": f"{prefix}固有事実"}]},
        "conflicts": [{"conflict_id": f"{prefix}-X01", "topic": f"{prefix}版差"}],
        "handoff_to_story": {"must_preserve": [f"{prefix}-E01", f"{prefix}-E02"]},
    }


def _story(prefix: str, registry: dict) -> dict:
    events = list(registry["events"])
    scenes = []
    for index, event_id in enumerate(events, start=1):
        event = registry["events"][event_id]
        next_scene_id = f"scene_{index + 1:02d}" if index < len(events) else None
        previous_scene_id = f"scene_{index - 1:02d}" if index > 1 else None
        incoming_state = f"state_{index:02d}_start"
        outgoing_state = f"state_{index:02d}_end"
        scenes.append(
            {
                "scene_id": f"scene_{index:02d}",
                "title": event["event"],
                "phase": "development",
                "purpose": event["event"],
                "conflict": f"{event_id}の世界規則が行動を制約する",
                "turn": event["event"],
                "affect": {"label_hint": "tension"},
                "visualizable_action": event["event"],
                "grounding_note": f"research event {event_id}",
                "location": {
                    "name": event["place_ids"][0],
                    "sequence": [event["place_ids"][0]],
                },
                "time_of_day": "夕方",
                "time_of_day_visual_basis": (
                    "光源: 西日。明るさ: 中間調。"
                    "影: 長く伸びる。色温度: 4300K。"
                ),
                "source_basis": {
                    "event_ids": [event_id],
                    "passage_ids": list(event["sources"]),
                    "character_ids": list(event["involved_characters"]),
                    "place_ids": list(event["place_ids"]),
                    "world_rule_ids": list(event["world_rule_ids"]),
                },
                "scene_intent": {
                    "story_purpose": event["event"],
                    "dramatic_question": f"{event_id}はどう変化するか",
                    "value_shift": {"from": incoming_state, "to": outgoing_state},
                    "causal_turn": event["event"],
                },
                "start_state": {"state_id": incoming_state, "incoming_from": previous_scene_id},
                "event_sequence": [
                    {
                        "beat_id": f"scene_{index:02d}_beat_01",
                        "beat_function": "source_event",
                        "source_event_ids": [event_id],
                        "source_refs": list(event["sources"]),
                        "participants": list(event["involved_characters"]),
                        "location_id": event["place_ids"][0],
                        "what_happens": event["event"],
                        "visible_action": event["event"],
                        "required_visual_evidence": [event["event"]],
                        "immediate_consequence": outgoing_state,
                    }
                ],
                "turning_event": {
                    "beat_id": f"scene_{index:02d}_beat_01",
                    "irreversible_change": event["event"],
                },
                "end_state": {"state_id": outgoing_state},
                "handoff_chain": {
                    "incoming": {
                        "producer_scene_id": previous_scene_id,
                        "state_id": incoming_state,
                    },
                    "outgoing": {
                        "consumer_scene_id": next_scene_id,
                        "state_id": outgoing_state,
                    },
                },
                "preservation": {"must_preserve": [event["event"]], "must_not_show": []},
            }
        )
    for previous, current in zip(scenes, scenes[1:]):
        current["start_state"]["state_id"] = previous["end_state"]["state_id"]
        current["handoff_chain"]["incoming"]["state_id"] = previous["end_state"]["state_id"]
    return {
        "story_metadata": {"scene_authoring_contract": "story_scene_contract_v1"},
        "script": {"scenes": scenes},
    }


@pytest.mark.parametrize("prefix", ["SEA", "CLOCK"])
def test_research_registry_and_architect_prompt_are_lossless(prefix: str) -> None:
    research = _research(prefix)
    registry = build_research_registry(research)
    prompt = build_story_architect_prompt(
        registry,
        topic=f"{prefix}物語",
        target_duration_seconds=600,
    )

    assert research["story_materials"]["chronological_events"][0]["event"] in prompt
    assert research["story_materials"]["characters"][0]["motivations"][0] in prompt
    assert research["story_materials"]["characters"][0]["relationships"][0]["relation"] in prompt
    assert research["story_materials"]["setting"]["places"][0]["description"] in prompt
    assert research["story_materials"]["setting"]["world_rules"][0]["rule"] in prompt
    assert research["source_passages"][0]["passage"] in prompt
    assert f"{prefix}-SYM01" in prompt
    assert f"{prefix}-F01" in prompt
    assert f"{prefix}-X01" in prompt


@pytest.mark.parametrize("prefix", ["SEA", "CLOCK"])
def test_rich_story_validator_accepts_complete_research_grounded_lifecycle(prefix: str) -> None:
    registry = build_research_registry(_research(prefix))
    story = _story(prefix, registry)

    assert validate_story_document(story, registry) == []


def test_rich_story_validator_rejects_event_gap_and_handoff_mismatch() -> None:
    registry = build_research_registry(_research("SEA"))
    story = _story("SEA", registry)
    broken = deepcopy(story)
    broken["script"]["scenes"][0]["source_basis"]["event_ids"] = []
    broken["script"]["scenes"][1]["start_state"]["state_id"] = "wrong_state"

    errors = validate_story_document(broken, registry)

    assert "story.scene_source_event_coverage" in errors
    assert "story.scene_handoff_state_mismatch" in errors
