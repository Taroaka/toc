from __future__ import annotations

import asyncio
from copy import deepcopy
import json

import pytest

from toc.story_authoring import AUDIENCE_MEANING_INSTRUCTION, build_research_registry, validate_story_document
from toc.story_author_pipeline import (
    ARCHITECT_OUTPUT_SCHEMA,
    SCENE_AUTHOR_OUTPUT_SCHEMA,
    StoryAuthoringError,
    author_story_from_research,
)


def _research() -> dict:
    return {
        "story_materials": {
            "chronological_events": [
                {
                    "event_id": "E01",
                    "event": "工房で主人公が停止した時計を発見する。",
                    "involved_characters": ["C01"],
                    "place_ids": ["L01"],
                    "world_rule_ids": ["R01"],
                    "sources": ["P01"],
                },
                {
                    "event_id": "E02",
                    "event": "塔で時計を動かし、町の時間が戻る。",
                    "involved_characters": ["C01"],
                    "place_ids": ["L02"],
                    "world_rule_ids": ["R01"],
                    "sources": ["P02"],
                },
            ],
            "characters": [
                {"character_id": "C01", "name": "ミナ", "role": "protagonist"}
            ],
            "setting": {
                "places": [
                    {"place_id": "L01", "name": "閉鎖工房"},
                    {"place_id": "L02", "name": "時計塔"},
                ],
                "world_rules": [
                    {"rule_id": "R01", "rule": "時計の停止中は町の時間も止まる"}
                ],
            },
        },
        "source_passages": [
            {"passage_id": "P01", "passage": "工房の根拠本文"},
            {"passage_id": "P02", "passage": "時計塔の根拠本文"},
        ],
    }


def _scene(scene_id: str, event_id: str, start: str, end: str, previous, next_):
    registry = build_research_registry(_research())
    event = registry["events"][event_id]
    index = 1 if event_id == "E01" else 2
    return {
        "scene_id": scene_id,
        "title": event["event"],
        "phase": "opening" if index == 1 else "ending",
        "location": {"name": event["place_ids"][0], "sequence": [event["place_ids"][0]]},
        "time_of_day": "夜明け前" if index == 1 else "朝",
        "time_of_day_visual_basis": (
            "光源: 窓からの月光。明るさ: 暗い。影: 青く深い。色温度: 4200K。"
            if index == 1
            else "光源: 朝日。明るさ: 明るい。影: 短い。色温度: 5200K。"
        ),
        "purpose": event["event"],
        "conflict": "世界規則が主人公の行動を制約する",
        "turn": event["event"],
        "affect": {"label_hint": "curiosity", "audience_job": "hook"},
        "visualizable_action": event["event"],
        "grounding_note": "research eventを完全保持",
        "source_basis": {
            "event_ids": [event_id],
            "passage_ids": event["sources"],
            "character_ids": event["involved_characters"],
            "place_ids": event["place_ids"],
            "world_rule_ids": event["world_rule_ids"],
        },
        "scene_intent": {
            "story_purpose": event["event"],
            "dramatic_question": "主人公は状態を変えられるか",
            "value_shift": {"from": start, "to": end},
            "causal_turn": event["event"],
        },
        "start_state": {"state_id": start},
        "event_sequence": [
            {
                "beat_id": f"{scene_id}_beat_01",
                "beat_function": "source_event",
                "source_event_ids": [event_id],
                "source_refs": event["sources"],
                "participants": event["involved_characters"],
                "location_id": event["place_ids"][0],
                "what_happens": event["event"],
                "visible_action": event["event"],
                "required_visual_evidence": [event["event"]],
                "immediate_consequence": end,
            }
        ],
        "turning_event": {
            "beat_id": f"{scene_id}_beat_01",
            "irreversible_change": event["event"],
        },
        "end_state": {"state_id": end},
        "handoff_chain": {
            "incoming": {"producer_scene_id": previous, "state_id": start},
            "outgoing": {"consumer_scene_id": next_, "state_id": end},
        },
        "preservation": {"must_preserve": [event["event"]], "must_not_show": []},
    }


def test_scene_author_schema_requires_rich_and_legacy_downstream_fields() -> None:
    required = set(SCENE_AUTHOR_OUTPUT_SCHEMA["required"])

    assert {
        "character_ids",
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
    } <= required
    beats = SCENE_AUTHOR_OUTPUT_SCHEMA["properties"]["event_sequence"]["items"]
    assert "participants" in beats["required"]
    assert beats["properties"]["participants"]["type"] == "array"


def test_architect_schema_requires_story_metadata_and_adaptation_root() -> None:
    assert {
        "story_metadata",
        "adaptation_source_contract",
        "selection",
        "scene_plan",
    } <= set(ARCHITECT_OUTPUT_SCHEMA["required"])


@pytest.mark.parametrize("character_id, substitutions", [
    ("CH1", {}),
    ("traveler_alpha", {"時計": "潮流", "工房": "船室", "塔": "海岸"}),
])
def test_published_story_binds_character_key_for_arbitrary_ids(tmp_path, character_id, substitutions):
    research = _research()
    research["story_materials"]["characters"][0]["character_id"] = character_id
    research["story_materials"]["characters"][0]["role"] = "時計を調べる旅人"
    for event in research["story_materials"]["chronological_events"]:
        event["involved_characters"] = [character_id]

    def transform(value):
        encoded = json.dumps(value, ensure_ascii=False).replace('"C01"', json.dumps(character_id))
        for old, new in substitutions.items():
            encoded = encoded.replace(old, new)
        return json.loads(encoded)

    research = transform(research)
    runner = FakeTurnRunner()

    async def renamed_runner(**kwargs):
        response = await runner(**kwargs)
        return transform(response)

    output = tmp_path / "story.md"
    result = asyncio.run(author_story_from_research(
        research, topic="時計の旅", target_duration_seconds=600,
        turn_runner=renamed_runner, output_path=output,
    ))
    assert result.story["story_metadata"]["scene_character_binding_contract"] == "scene_character_binding_v1"
    assert [s["character_ids"] for s in result.story["script"]["scenes"]] == [[character_id], [character_id]]
    import yaml
    saved = yaml.safe_load(output.read_text().split("```yaml\n", 1)[1].split("```", 1)[0])
    assert saved["script"]["scenes"][0]["character_ids"] == [character_id]


def test_character_key_includes_later_and_state_only_characters_without_rewriting_prose():
    from toc.story_author_pipeline import _ensure_scene_binding

    scene = _scene("scene_01", "E01", "state_before", "state_after", None, None)
    scene["start_state"]["characters"] = [{"character_id": "observer", "state": "窓辺で待つ"}]
    scene["event_sequence"][0]["participants"] = ["C01", "arrival", "C01"]
    scene["end_state"]["characters"] = ["arrival", {"character_id": "end_only"}]
    scene["character_ids"] = ["stale_model_guess"]
    before = deepcopy(scene)
    plan = {
        "scene_id": "scene_01", "source_event_ids": ["E01"],
        "incoming_state_id": "state_before", "outgoing_state_id": "state_after",
    }
    bound = _ensure_scene_binding(scene, plan)
    assert bound["character_ids"] == ["C01", "observer", "arrival", "end_only"]
    assert bound["event_sequence"] == before["event_sequence"]
    assert scene == before

    # The same boundary runs after scene regeneration/field repair: a
    # corrected lifecycle must not retain a stale downstream character index.
    bound["event_sequence"][0]["participants"] = ["C01", "replacement"]
    bound["end_state"]["characters"] = []
    rebound = _ensure_scene_binding(bound, plan)
    assert rebound["character_ids"] == ["C01", "observer", "replacement"]


@pytest.mark.parametrize("corruption", ["missing", "mismatch", "bad_type", "unknown", "malformed_state"])
def test_character_key_contract_rejects_missing_or_inconsistent_refs(corruption):
    from toc.story_author_pipeline import _assemble_story, _ensure_scene_binding

    scene = _scene("scene_01", "E01", "state_before", "state_after", None, "scene_02")
    plan = {"scene_id": "scene_01", "source_event_ids": ["E01"],
            "incoming_state_id": "state_before", "outgoing_state_id": "state_after"}
    scene = _ensure_scene_binding(scene, plan)
    story = _assemble_story({}, [scene], topic="test", target_duration_seconds=None,
                            source_digest="test", source_research="research.md")
    canonical = story["script"]["scenes"][0]
    if corruption == "missing":
        del canonical["character_ids"]
    elif corruption == "mismatch":
        canonical["character_ids"] = []
    elif corruption == "bad_type":
        canonical["character_ids"] = "C01"
    elif corruption == "unknown":
        canonical["start_state"]["characters"] = [{"character_id": "missing_person"}]
        canonical["character_ids"].append("missing_person")
    else:
        canonical["start_state"]["characters"] = [{"state": "no identity"}]
    errors = validate_story_document(story, build_research_registry(_research()))
    expected = {"missing": "story.scene_character_ids_missing",
                "mismatch": "story.scene_character_ids_mismatch",
                "bad_type": "story.scene_character_ids_invalid",
                "unknown": "story.scene_unknown_id",
                "malformed_state": "story.scene_character_refs_invalid"}
    assert expected[corruption] in errors


def test_characterless_scene_preserves_explicit_empty_participants():
    from toc.story_author_pipeline import _assemble_story, _ensure_scene_binding

    research = _research()
    for event in research["story_materials"]["chronological_events"]:
        event["involved_characters"] = []
    scene = _scene("scene_01", "E01", "state_before", "state_after", None, None)
    scene["source_basis"]["character_ids"] = []
    scene["event_sequence"][0]["participants"] = []
    plan = {"scene_id": "scene_01", "source_event_ids": ["E01"],
            "incoming_state_id": "state_before", "outgoing_state_id": "state_after"}
    bound = _ensure_scene_binding(scene, plan)
    assert bound["character_ids"] == []
    assert bound["event_sequence"][0]["participants"] == []
    story = _assemble_story({}, [bound], topic="test", target_duration_seconds=None,
                            source_digest="test", source_research="research.md")
    errors = validate_story_document(story, build_research_registry(research))
    assert "story.scene_event_beat_grounding_missing" not in errors
    assert not any("character" in error for error in errors)

    # Source references can mention a character without that character acting
    # in every beat. Explicit [] must not be filled with all scene characters.
    scene["source_basis"]["character_ids"] = ["C01"]
    bound = _ensure_scene_binding(scene, plan)
    assert bound["character_ids"] == ["C01"]
    assert bound["event_sequence"][0]["participants"] == []


@pytest.mark.parametrize("invalid_refs", [[{"state": "waiting"}], [{"character_id": "unregistered"}]])
def test_invalid_lifecycle_character_reference_never_publishes(tmp_path, invalid_refs):
    runner = FakeTurnRunner()

    async def invalid_runner(**kwargs):
        response = await runner(**kwargs)
        if kwargs["role"] == "scene_author":
            for scene in response["scenes"]:
                scene["start_state"]["characters"] = deepcopy(invalid_refs)
        return response

    output = tmp_path / "story.md"
    with pytest.raises(StoryAuthoringError) as exc:
        asyncio.run(author_story_from_research(_research(), topic="test", turn_runner=invalid_runner, output_path=output))
    assert any(error in exc.value.validation_errors for error in (
        "story.scene_character_refs_invalid", "story.scene_unknown_id"))
    assert not output.exists()


class FakeTurnRunner:
    def __init__(
        self,
        *,
        break_handoff: bool = False,
        break_visual_basis: bool = False,
        break_turning_event: bool = False,
        split_first_event: bool = False,
    ) -> None:
        self.calls: list[dict] = []
        self.break_handoff = break_handoff
        self.break_visual_basis = break_visual_basis
        self.break_turning_event = break_turning_event
        self.split_first_event = split_first_event

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['role'] == 'field_repair':
            from toc.story_field_repair import scene_digest
            correct = _scene('scene_02', 'E02', 'state_clock_found', 'state_time_restored', 'scene_01', None)
            operations = []
            for issue in kwargs['field_issues']:
                value = correct
                for part in issue['path'].strip('/').split('/'):
                    value = value[int(part)] if isinstance(value, list) else value[part]
                if issue['expected_type'] == 'object':
                    value = json.dumps(value, ensure_ascii=False)
                operations.append({'path': issue['path'], 'value': value})
            return {'scene_id': kwargs['scene_id'], 'base_digest': scene_digest(kwargs['scene']), 'operations': operations}
        if kwargs["role"] == "repair":
            return {
                "scene_id": "scene_02",
                "replacement_scene": _scene(
                    "scene_02",
                    "E02",
                    "state_clock_found",
                    "state_time_restored",
                    "scene_01",
                    None,
                ),
                "addressed_errors": list(kwargs["validation_errors"]),
            }
        if kwargs["role"] == "architect":
            return {
                "story_metadata": {"pattern_used": "mystery", "time": "架空の近代"},
                "adaptation_source_contract": {
                    "schema_version": "adaptation_source_contract_v1",
                    "mode": "existing_story",
                    "source_story_promise": "止まった時間をミナの選択で動かす。",
                    "core_values": [
                        {
                            "value_id": "value_restore_time",
                            "statement": "自ら時計を動かし町の時間を取り戻す。",
                            "audience_effect": "止まった世界が再び動く解放感。",
                            "source_event_refs": ["E01", "E02"],
                        }
                    ],
                    "non_negotiable_events": ["E01", "E02"],
                    "non_negotiable_meanings": ["ミナ自身の選択で時計を動かす"],
                    "iconic_moments": ["時計塔で針が動く"],
                    "forbidden_value_distortions": ["偶然だけで解決しない"],
                },
                "selection": {
                    "candidates": [
                        {"candidate_id": "A", "logline": "時計を動かす"},
                        {"candidate_id": "B", "logline": "時間を待つ"},
                    ],
                    "chosen_candidate_id": "A",
                    "rationale": "全eventを因果順に保持する",
                },
                "scene_plan": [
                    {
                        "scene_id": "scene_01",
                        "title": "停止した時計",
                        "phase": "opening",
                        "source_event_ids": ["E01"],
                        "incoming_state_id": "state_start",
                        "outgoing_state_id": "state_clock_found",
                        "previous_scene_id": None,
                        "next_scene_id": "scene_02",
                    },
                    {
                        "scene_id": "scene_02",
                        "title": "時計塔",
                        "phase": "ending",
                        "source_event_ids": ["E02"],
                        "incoming_state_id": "state_clock_found",
                        "outgoing_state_id": "state_time_restored",
                        "previous_scene_id": "scene_01",
                        "next_scene_id": None,
                    },
                ],
            }
        scenes = []
        for plan in kwargs["scene_plans"]:
            if plan["scene_id"] == "scene_01":
                scene = _scene(
                    "scene_01", "E01", "state_start", "state_clock_found", None, "scene_02"
                )
                if self.split_first_event:
                    first = deepcopy(scene["event_sequence"][0])
                    first["beat_id"] = "scene_01_beat_00"
                    first["what_happens"] = "工房の扉を開け、止まった時計の存在を見つける。"
                    first["immediate_consequence"] = "state_clock_seen"
                    scene["event_sequence"].insert(0, first)
                scenes.append(scene)
                continue
            start = "wrong_state" if self.break_handoff else "state_clock_found"
            second = _scene(
                    "scene_02", "E02", start, "state_time_restored", "scene_01", None
            )
            if self.break_visual_basis:
                second["time_of_day_visual_basis"] = "朝の光"
            if self.break_turning_event:
                second["turning_event"]["beat_id"] = "unknown_beat"
            scenes.append(second)
        return {"scenes": scenes}


def test_story_pipeline_runs_architect_then_scene_authors_and_validates() -> None:
    runner = FakeTurnRunner()

    result = asyncio.run(
        author_story_from_research(
            _research(),
            topic="青い時計",
            target_duration_seconds=600,
            turn_runner=runner,
        )
    )

    assert result.validation_errors == ()
    assert result.story["story_metadata"]["scene_authoring_contract"] == "story_scene_contract_v1"
    assert [call["role"] for call in runner.calls] == [
        "architect",
        "scene_author",
        "scene_author",
    ]
    assert [scene["scene_id"] for scene in result.story["script"]["scenes"]] == [
        "scene_01",
        "scene_02",
    ]
    assert [
        scene["target_duration_seconds"]
        for scene in result.story["script"]["scenes"]
    ] == [300, 300]
    assert sum(
        scene["narration_target_seconds"]
        for scene in result.story["script"]["scenes"]
    ) >= 420
    assert result.story["story_metadata"]["duration_binding"] == {
        "schema_version": "story_duration_binding_v1",
        "target_seconds": 600,
        "scene_ids": ["scene_01", "scene_02"],
        "scene_allocations": [
            {"scene_id": "scene_01", "seconds": 300},
            {"scene_id": "scene_02", "seconds": 300},
        ],
        "sum_seconds": 600,
        "minimum_narration_seconds": 420,
        "source": "request",
        "semantic_scene_ids_unchanged": True,
    }


def test_story_pipeline_keeps_semantic_scene_identity_across_target_durations() -> None:
    authored = {}
    for duration in (300, 600, 900):
        result = asyncio.run(
            author_story_from_research(
                _research(),
                topic="青い時計",
                target_duration_seconds=duration,
                turn_runner=FakeTurnRunner(),
            )
        )
        scenes = result.story["script"]["scenes"]
        authored[duration] = [scene["scene_id"] for scene in scenes]
        assert sum(scene["target_duration_seconds"] for scene in scenes) == duration

    assert authored[300] == authored[600] == authored[900] == [
        "scene_01",
        "scene_02",
    ]


def test_story_pipeline_allows_one_source_event_to_expand_into_multiple_beats() -> None:
    result = asyncio.run(
        author_story_from_research(
            _research(),
            topic="青い時計",
            target_duration_seconds=300,
            turn_runner=FakeTurnRunner(split_first_event=True),
        )
    )

    assert [
        beat["source_event_ids"]
        for beat in result.story["script"]["scenes"][0]["event_sequence"]
    ] == [["E01"], ["E01"]]


def test_story_pipeline_reconciles_only_frozen_handoff_keys() -> None:
    runner = FakeTurnRunner(break_handoff=True)

    result = asyncio.run(
        author_story_from_research(
            _research(),
            topic="青い時計",
            target_duration_seconds=600,
            turn_runner=runner,
            max_repair_rounds=0,
        )
    )

    second = result.story["script"]["scenes"][1]
    assert second["start_state"]["state_id"] == "state_clock_found"
    assert second["handoff_chain"]["incoming"]["state_id"] == "state_clock_found"


def test_story_pipeline_repairs_only_failing_field_then_revalidates() -> None:
    runner = FakeTurnRunner(break_turning_event=True)

    result = asyncio.run(
        author_story_from_research(
            _research(),
            topic="青い時計",
            target_duration_seconds=600,
            turn_runner=runner,
            max_repair_rounds=1,
        )
    )

    assert result.validation_errors == ()
    assert result.repair_count == 1
    assert [call["role"] for call in runner.calls] == [
        "architect",
        "scene_author",
        "scene_author",
        "field_repair",
    ]
    for call in runner.calls:
        assert AUDIENCE_MEANING_INSTRUCTION in json.loads(call["prompt"])["instructions"]
    assert result.story["script"]["scenes"][1]["start_state"]["state_id"] == "state_clock_found"


def test_architect_is_repaired_with_previous_output_and_error():
    base = FakeTurnRunner()
    attempts = []
    async def turn(**kwargs):
        if kwargs['role'] == 'architect':
            attempts.append(kwargs)
            if len(attempts) == 1:
                return {'scene_plan': 'invalid'}
        return await base(**kwargs)
    result = asyncio.run(author_story_from_research(_research(), topic='時計', target_duration_seconds=600,
        turn_runner=turn, max_repair_rounds=2))
    assert not result.validation_errors
    context = json.loads(attempts[1]['prompt'])['repair_context']
    assert context['previous_output'] == {'scene_plan': 'invalid'}
    assert 'scene_plan' in context['errors'][0]
