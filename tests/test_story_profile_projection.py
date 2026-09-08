from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from toc.story_author_pipeline import author_story_from_research


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_frontend_run_module():
    """Load the legacy frontend profile adapter under a test-only module name."""

    module_name = "story_profile_projection_frontend_run"
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


def _research_fixture(
    *,
    topic: str,
    source_id: str,
    events: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    places: list[dict[str, Any]],
    world_rules: list[dict[str, Any]],
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the same rich research shape for unrelated story inputs."""

    return {
        "topic": topic,
        "story_materials": {
            "canonical_story_dump": (
                f"{topic}の全編資料。"
                "各eventの人物、場所、世界規則、結果を省略せず保持する。"
            ),
            "chronological_events": deepcopy(events),
            "characters": deepcopy(characters),
            "setting": {
                "places": deepcopy(places),
                "time_or_era": "物語内の固有時代",
                "world_rules": deepcopy(world_rules),
            },
        },
        "source_inventory": [
            {
                "source_id": source_id,
                "title": f"{topic}の一次資料",
                "url": f"fixture://{source_id}",
                "type": "primary",
                "reliability": "high",
                "accessed_at": "2026-09-01T00:00:00+09:00",
            }
        ],
        "source_passages": deepcopy(passages),
    }


STORY_FIXTURES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "urashima",
        "topic": "浦島太郎",
        "source": "海辺の伝承",
        "research": _research_fixture(
            topic="浦島太郎",
            source_id="U-S1",
            events=[
                {
                    "event_id": "U-E01",
                    "event": "潮の浜辺で浦島太郎が子どもたちから亀を救い、恩返しの約束が生まれる。",
                    "story_function": "setup",
                    "involved_characters": ["U-C-URASHIMA", "U-C-TURTLE"],
                    "place_ids": ["U-L-SHORE"],
                    "world_rule_ids": ["U-R-SEA-TIME"],
                    "sources": ["U-P01"],
                },
                {
                    "event_id": "U-E02",
                    "event": "亀が浦島太郎を竜宮城へ運び、海中の時間が地上と違うことを体験させる。",
                    "story_function": "threshold",
                    "involved_characters": ["U-C-URASHIMA", "U-C-TURTLE"],
                    "place_ids": ["U-L-SHORE", "U-L-PALACE"],
                    "world_rule_ids": ["U-R-SEA-TIME"],
                    "sources": ["U-P02"],
                },
                {
                    "event_id": "U-E03",
                    "event": "故郷へ戻った浦島太郎が玉手箱を開き、時間の断絶と禁忌の結果を受け取る。",
                    "story_function": "aftermath",
                    "involved_characters": ["U-C-URASHIMA", "U-C-OTOHIME"],
                    "place_ids": ["U-L-VILLAGE"],
                    "world_rule_ids": ["U-R-SEA-TIME", "U-R-BOX-TABOO"],
                    "sources": ["U-P03"],
                },
            ],
            characters=[
                {
                    "character_id": "U-C-URASHIMA",
                    "name": "浦島太郎",
                    "role": "主人公",
                    "motivations": ["救った相手を見捨てない", "故郷へ戻る"],
                    "relationships": [
                        {"target": "U-C-TURTLE", "relation": "浜辺で救った相手"}
                    ],
                },
                {
                    "character_id": "U-C-TURTLE",
                    "name": "亀",
                    "role": "導き手",
                    "motivations": ["受けた恩を返す"],
                    "relationships": [
                        {"target": "U-C-URASHIMA", "relation": "竜宮城へ導く"}
                    ],
                },
                {
                    "character_id": "U-C-OTOHIME",
                    "name": "乙姫",
                    "role": "別れを告げる人物",
                    "motivations": ["海中の別れを受け入れる"],
                    "relationships": [
                        {"target": "U-C-URASHIMA", "relation": "玉手箱を渡す"}
                    ],
                },
            ],
            places=[
                {
                    "place_id": "U-L-SHORE",
                    "name": "潮の浜辺",
                    "description": "濡れた砂、潮の匂い、子どもたちの足跡が残る浜辺。",
                    "source_refs": ["U-P01"],
                },
                {
                    "place_id": "U-L-PALACE",
                    "name": "竜宮城の珊瑚門",
                    "description": "海中の青い光と珊瑚の門が境界を示す宮殿。",
                    "source_refs": ["U-P02"],
                },
                {
                    "place_id": "U-L-VILLAGE",
                    "name": "時間の進んだ故郷の村",
                    "description": "知っている家が消え、見知らぬ世代が暮らす故郷。",
                    "source_refs": ["U-P03"],
                },
            ],
            world_rules=[
                {
                    "rule_id": "U-R-SEA-TIME",
                    "rule": "竜宮城の時間は地上の時間と異なり、帰還時には故郷の時間が大きく進んでいる。",
                    "evidence_refs": ["U-P02", "U-P03"],
                },
                {
                    "rule_id": "U-R-BOX-TABOO",
                    "rule": "玉手箱は開けてはならず、開けた瞬間に隠されていた時間が現れる。",
                    "evidence_refs": ["U-P03"],
                },
            ],
            passages=[
                {
                    "passage_id": "U-P01",
                    "source_id": "U-S1",
                    "passage": "浜辺で亀を救う場面と、救助が後の旅の原因になること。",
                },
                {
                    "passage_id": "U-P02",
                    "source_id": "U-S1",
                    "passage": "亀に導かれて海中の宮殿へ向かい、時間差を経験する場面。",
                },
                {
                    "passage_id": "U-P03",
                    "source_id": "U-S1",
                    "passage": "故郷の変化と玉手箱の禁忌が結末を決める場面。",
                },
            ],
        ),
        "scene_plan": [
            {
                "scene_id": "urashima_rescue",
                "semantic_scene_responsibility_id": "urashima_rescue",
                "title": "潮の浜辺で亀を救う",
                "source_event_ids": ["U-E01"],
                "character_ids": ["U-C-URASHIMA", "U-C-TURTLE"],
                "place_ids": ["U-L-SHORE"],
                "world_rule_ids": ["U-R-SEA-TIME"],
                "passage_ids": ["U-P01"],
                "location": {
                    "location_id": "U-L-SHORE",
                    "name": "潮の浜辺",
                    "mode": "single",
                    "sequence": ["潮の浜辺"],
                    "segments": [],
                },
                "time_of_day": "朝の満潮前",
                "time_of_day_visual_basis": "低い朝光、濡れた砂の反射、長く柔らかな影、少し暖かい色温度。",
                "target_duration_seconds": 84,
                "incoming_state_id": "u_state_start",
                "outgoing_state_id": "u_state_turtle_saved",
                "previous_scene_id": None,
                "next_scene_id": "urashima_palace",
            },
            {
                "scene_id": "urashima_palace",
                "semantic_scene_responsibility_id": "urashima_palace",
                "title": "珊瑚門を越えた竜宮城",
                "source_event_ids": ["U-E02"],
                "character_ids": ["U-C-URASHIMA", "U-C-TURTLE"],
                "place_ids": ["U-L-SHORE", "U-L-PALACE"],
                "world_rule_ids": ["U-R-SEA-TIME"],
                "passage_ids": ["U-P02"],
                "location": {
                    "location_id": "U-L-SHORE",
                    "name": "潮の浜辺",
                    "mode": "sequence",
                    "sequence": ["潮の浜辺", "竜宮城の珊瑚門"],
                    "segments": [],
                },
                "time_of_day": "海中の青い昼",
                "time_of_day_visual_basis": "海面からの拡散光、青い明るさ、珊瑚の細い影、冷たい色温度。",
                "target_duration_seconds": 126,
                "incoming_state_id": "u_state_turtle_saved",
                "outgoing_state_id": "u_state_time_shifted",
                "previous_scene_id": "urashima_rescue",
                "next_scene_id": "urashima_return",
            },
            {
                "scene_id": "urashima_return",
                "semantic_scene_responsibility_id": "urashima_return",
                "title": "時間の進んだ故郷と玉手箱",
                "source_event_ids": ["U-E03"],
                "character_ids": ["U-C-URASHIMA", "U-C-OTOHIME"],
                "place_ids": ["U-L-VILLAGE"],
                "world_rule_ids": ["U-R-SEA-TIME", "U-R-BOX-TABOO"],
                "passage_ids": ["U-P03"],
                "location": {
                    "location_id": "U-L-VILLAGE",
                    "name": "時間の進んだ故郷の村",
                    "mode": "single",
                    "sequence": ["時間の進んだ故郷の村"],
                    "segments": [],
                },
                "time_of_day": "夕暮れ",
                "time_of_day_visual_basis": "低い夕日、村の長い影、薄い赤金の明るさ、暖色から灰色へ移る色温度。",
                "target_duration_seconds": 90,
                "incoming_state_id": "u_state_time_shifted",
                "outgoing_state_id": "u_state_box_opened",
                "previous_scene_id": "urashima_palace",
                "next_scene_id": None,
            },
        ],
    },
    {
        "case_id": "blue_clock",
        "topic": "青い鳥の時計",
        "source": "時計師の町の創作伝承",
        "research": _research_fixture(
            topic="青い鳥の時計",
            source_id="B-S1",
            events=[
                {
                    "event_id": "B-E01",
                    "event": "閉鎖工房でミナが青い鳥時計を見つけ、止まった町の鐘の原因を探し始める。",
                    "story_function": "setup",
                    "involved_characters": ["B-C-MINA", "B-C-CLOCK"],
                    "place_ids": ["B-L-WORKSHOP"],
                    "world_rule_ids": ["B-R-REVERSE-TIME"],
                    "sources": ["B-P01"],
                },
                {
                    "event_id": "B-E02",
                    "event": "鐘楼の歯車室でミナが逆回転する針を見つけ、失われた時刻の仕組みを理解する。",
                    "story_function": "revelation",
                    "involved_characters": ["B-C-MINA", "B-C-CLOCK", "B-C-TOWN"],
                    "place_ids": ["B-L-TOWER"],
                    "world_rule_ids": ["B-R-REVERSE-TIME", "B-R-DAWN-LIMIT"],
                    "sources": ["B-P02"],
                },
                {
                    "event_id": "B-E03",
                    "event": "夜明け前の一度だけ、ミナが青い鳥時計のゼンマイを巻き、町の鐘を鳴らす。",
                    "story_function": "climax",
                    "involved_characters": ["B-C-MINA", "B-C-CLOCK", "B-C-TOWN"],
                    "place_ids": ["B-L-SQUARE"],
                    "world_rule_ids": ["B-R-DAWN-LIMIT"],
                    "sources": ["B-P03"],
                },
            ],
            characters=[
                {
                    "character_id": "B-C-MINA",
                    "name": "ミナ",
                    "role": "主人公",
                    "motivations": ["師匠の約束を守る", "町の鐘を取り戻す"],
                    "relationships": [
                        {"target": "B-C-TOWN", "relation": "町の鐘に責任を負う"}
                    ],
                },
                {
                    "character_id": "B-C-CLOCK",
                    "name": "青い鳥時計",
                    "role": "秘密を示す道具",
                    "motivations": ["失われた時刻を刻み直す"],
                    "relationships": [
                        {"target": "B-C-MINA", "relation": "機構の秘密を示す"}
                    ],
                },
                {
                    "character_id": "B-C-TOWN",
                    "name": "鐘守の町",
                    "role": "待つ共同体",
                    "motivations": ["止まった鐘を取り戻す"],
                    "relationships": [{"target": "B-C-MINA", "relation": "成果を待つ"}],
                },
            ],
            places=[
                {
                    "place_id": "B-L-WORKSHOP",
                    "name": "閉鎖工房",
                    "description": "油、木屑、止まった工具が残る閉鎖工房。",
                    "source_refs": ["B-P01"],
                },
                {
                    "place_id": "B-L-TOWER",
                    "name": "霧の鐘楼",
                    "description": "霧の中で巨大な歯車が止まり、鐘の空洞だけが残る鐘楼。",
                    "source_refs": ["B-P02"],
                },
                {
                    "place_id": "B-L-SQUARE",
                    "name": "鐘を待つ町の広場",
                    "description": "夜明けを待つ町人が空の鐘楼を見上げる広場。",
                    "source_refs": ["B-P03"],
                },
            ],
            world_rules=[
                {
                    "rule_id": "B-R-REVERSE-TIME",
                    "rule": "青い鳥時計の針が逆回転すると、町から失われた時刻が一瞬だけ現れる。",
                    "evidence_refs": ["B-P01", "B-P02"],
                },
                {
                    "rule_id": "B-R-DAWN-LIMIT",
                    "rule": "機構を動かせるのは夜明け前の一度だけで、その機会を逃すと鐘は一年鳴らない。",
                    "evidence_refs": ["B-P02", "B-P03"],
                },
            ],
            passages=[
                {
                    "passage_id": "B-P01",
                    "source_id": "B-S1",
                    "passage": "閉鎖工房で青い鳥時計を見つけ、止まった鐘の謎へ入る場面。",
                },
                {
                    "passage_id": "B-P02",
                    "source_id": "B-S1",
                    "passage": "逆回転する針と夜明け前の期限が、町の時間の仕組みを明らかにする場面。",
                },
                {
                    "passage_id": "B-P03",
                    "source_id": "B-S1",
                    "passage": "ミナが一度だけ機構を動かし、町の鐘を鳴らす結末の場面。",
                },
            ],
        ),
        "scene_plan": [
            {
                "scene_id": "blue_clock_workshop",
                "semantic_scene_responsibility_id": "blue_clock_workshop",
                "title": "閉鎖工房で青い鳥時計を見つける",
                "source_event_ids": ["B-E01"],
                "character_ids": ["B-C-MINA", "B-C-CLOCK"],
                "place_ids": ["B-L-WORKSHOP"],
                "world_rule_ids": ["B-R-REVERSE-TIME"],
                "passage_ids": ["B-P01"],
                "location": {
                    "location_id": "B-L-WORKSHOP",
                    "name": "閉鎖工房",
                    "mode": "single",
                    "sequence": ["閉鎖工房"],
                    "segments": [],
                },
                "time_of_day": "雨上がりの夕刻",
                "time_of_day_visual_basis": "工房の窓から差す低い夕光、油の反射、長い工具の影、やや暖かい色温度。",
                "target_duration_seconds": 75,
                "incoming_state_id": "b_state_start",
                "outgoing_state_id": "b_state_clock_found",
                "previous_scene_id": None,
                "next_scene_id": "blue_clock_tower",
            },
            {
                "scene_id": "blue_clock_tower",
                "semantic_scene_responsibility_id": "blue_clock_tower",
                "title": "霧の鐘楼で逆回転を読む",
                "source_event_ids": ["B-E02"],
                "character_ids": ["B-C-MINA", "B-C-CLOCK", "B-C-TOWN"],
                "place_ids": ["B-L-TOWER"],
                "world_rule_ids": ["B-R-REVERSE-TIME", "B-R-DAWN-LIMIT"],
                "passage_ids": ["B-P02"],
                "location": {
                    "location_id": "B-L-TOWER",
                    "name": "霧の鐘楼",
                    "mode": "sequence",
                    "sequence": ["霧の鐘楼", "鐘を待つ町の広場"],
                    "segments": [],
                },
                "time_of_day": "深夜の霧",
                "time_of_day_visual_basis": "歯車の小さな人工光、霧の暗い明るさ、硬い歯車の影、冷たい色温度。",
                "target_duration_seconds": 135,
                "incoming_state_id": "b_state_clock_found",
                "outgoing_state_id": "b_state_deadline_known",
                "previous_scene_id": "blue_clock_workshop",
                "next_scene_id": "blue_clock_square",
            },
            {
                "scene_id": "blue_clock_square",
                "semantic_scene_responsibility_id": "blue_clock_square",
                "title": "夜明け前の広場に鐘を戻す",
                "source_event_ids": ["B-E03"],
                "character_ids": ["B-C-MINA", "B-C-CLOCK", "B-C-TOWN"],
                "place_ids": ["B-L-SQUARE"],
                "world_rule_ids": ["B-R-DAWN-LIMIT"],
                "passage_ids": ["B-P03"],
                "location": {
                    "location_id": "B-L-SQUARE",
                    "name": "鐘を待つ町の広場",
                    "mode": "single",
                    "sequence": ["鐘を待つ町の広場"],
                    "segments": [],
                },
                "time_of_day": "夜明け直前",
                "time_of_day_visual_basis": "空が白み始める弱い自然光、鐘楼の長い影、低い明るさ、冷たい青から淡い金への色温度。",
                "target_duration_seconds": 90,
                "incoming_state_id": "b_state_deadline_known",
                "outgoing_state_id": "b_state_bell_ringing",
                "previous_scene_id": "blue_clock_tower",
                "next_scene_id": None,
            },
        ],
    },
)


def _event_map(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(event["event_id"]): event
        for event in case["research"]["story_materials"]["chronological_events"]
    }


def _authored_scene(case: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    event = _event_map(case)[plan["source_event_ids"][0]]
    beat_id = f"{plan['scene_id']}_event"
    research_refs = [
        f"research.story_materials.chronological_events[{event_id}]"
        for event_id in plan["source_event_ids"]
    ] + [
        f"research.source_passages[{passage_id}]" for passage_id in plan["passage_ids"]
    ]
    source_basis = {
        "event_ids": list(plan["source_event_ids"]),
        "passage_ids": list(plan["passage_ids"]),
        "character_ids": list(plan["character_ids"]),
        "place_ids": list(plan["place_ids"]),
        "world_rule_ids": list(plan["world_rule_ids"]),
    }
    return {
        "scene_id": plan["scene_id"],
        "semantic_scene_responsibility_id": plan["semantic_scene_responsibility_id"],
        "title": plan["title"],
        "phase": "opening" if plan["previous_scene_id"] is None else "development",
        "purpose": plan["title"],
        "conflict": "固有の世界規則が主人公の選択を制約する。",
        "turn": event["event"],
        "visualizable_action": event["event"],
        "grounding_note": "review済みresearchのsource eventをそのまま保持する。",
        "affect": {"label_hint": "curiosity", "audience_job": "bond"},
        "time_of_day": plan["time_of_day"],
        "time_of_day_visual_basis": (
            "光源は"
            + plan["time_of_day_visual_basis"]
            + " 明るさ、影、色温度もscene固有に保持する。"
        ),
        "target_duration_seconds": plan["target_duration_seconds"],
        "location": deepcopy(plan["location"]),
        "location_ids": list(plan["place_ids"]),
        "character_ids": list(plan["character_ids"]),
        "world_rule_ids": list(plan["world_rule_ids"]),
        "research_refs": research_refs,
        "source_basis": source_basis,
        "scene_intent": {
            "story_purpose": plan["title"],
            "dramatic_question": f"{plan['title']}で何が変わるか",
            "value_shift": {
                "from": plan["incoming_state_id"],
                "to": plan["outgoing_state_id"],
            },
            "causal_turn": event["event"],
        },
        "start_state": {
            "state_id": plan["incoming_state_id"],
            "location_id": plan["place_ids"][0],
            "time_of_day": plan["time_of_day"],
            "description": f"{plan['title']}の開始状態。{event['event']}",
        },
        "event_sequence": [
            {
                "beat_id": beat_id,
                "beat_function": event["story_function"],
                "source_event_ids": list(plan["source_event_ids"]),
                "source_refs": list(plan["passage_ids"]),
                "participants": list(plan["character_ids"]),
                "place_ids": list(plan["place_ids"]),
                "world_rule_ids": list(plan["world_rule_ids"]),
                "what_happens": event["event"],
                "visible_action": event["event"],
                "immediate_consequence": plan["outgoing_state_id"],
                "required_visual_evidence": [
                    plan["location"]["name"],
                    event["event"],
                ],
            }
        ],
        "turning_event": {
            "beat_id": beat_id,
            "irreversible_change": event["event"],
            "source_refs": list(plan["passage_ids"]),
        },
        "end_state": {
            "state_id": plan["outgoing_state_id"],
            "location_id": plan["place_ids"][-1],
            "time_of_day": plan["time_of_day"],
            "description": f"{plan['title']}の終了状態。{plan['outgoing_state_id']}へ移る。",
        },
        "handoff_chain": {
            "incoming": {
                "producer_scene_id": plan["previous_scene_id"],
                "state_id": plan["incoming_state_id"],
                "source_refs": list(plan["passage_ids"]),
            },
            "outgoing": {
                "consumer_scene_id": plan["next_scene_id"],
                "state_id": plan["outgoing_state_id"],
                "source_refs": list(plan["passage_ids"]),
            },
        },
        "preservation": {
            "must_preserve": [event["event"]],
            "must_not_show": [],
        },
    }


class _FixtureTurnRunner:
    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["role"] == "architect":
            return {
                "story_metadata": {
                    "pattern_used": "research_grounded",
                    "time": "物語内の固有時代",
                },
                "adaptation_source_contract": {
                    "schema_version": "adaptation_source_contract_v1",
                    "mode": "existing_story",
                    "source_story_promise": "researchの因果順を保つ。",
                    "core_values": [
                        {
                            "value_id": "value_source_causality",
                            "statement": "主体の選択と結果を保つ。",
                            "audience_effect": "出来事の連鎖を追える。",
                            "source_event_refs": [
                                event["event_id"]
                                for event in self.case["research"]["story_materials"][
                                    "chronological_events"
                                ]
                            ],
                        }
                    ],
                    "non_negotiable_events": [
                        event["event_id"]
                        for event in self.case["research"]["story_materials"][
                            "chronological_events"
                        ]
                    ],
                    "non_negotiable_meanings": ["researchの順序を変えない"],
                    "iconic_moments": ["source eventの不可逆な転換"],
                    "forbidden_value_distortions": ["generic montageに置換しない"],
                },
                "selection": {
                    "candidates": [
                        {"candidate_id": "A", "logline": "source eventを順に描く"},
                        {"candidate_id": "B", "logline": "世界規則の結果を描く"},
                    ],
                    "chosen_candidate_id": "A",
                    "rationale": "全source eventをsemantic sceneへ一度ずつ割り当てる",
                },
                "scene_plan": deepcopy(self.case["scene_plan"]),
            }
        if kwargs["role"] == "scene_author":
            return {
                "scenes": [
                    _authored_scene(self.case, plan)
                    for plan in kwargs["scene_plans"]
                ]
            }
        raise AssertionError(f"unexpected author role: {kwargs['role']}")


def _authored_story(
    case: dict[str, Any], target_duration_seconds: int | None = None
) -> dict[str, Any]:
    result = asyncio.run(
        author_story_from_research(
            case["research"],
            topic=case["topic"],
            target_duration_seconds=target_duration_seconds,
            turn_runner=_FixtureTurnRunner(case),
        )
    )
    return result.story


def _projected_profile(
    module: Any, case: dict[str, Any], story: dict[str, Any]
) -> dict[str, Any]:
    base_profile = module._story_profile(
        case["topic"],
        case["source"],
        variant_seed=f"rich-story-profile-{case['case_id']}",
    )
    return module._profile_from_reviewed_story(base_profile, story)


@pytest.mark.parametrize("case", STORY_FIXTURES, ids=lambda case: case["case_id"])
def test_profile_from_reviewed_story_projects_rich_scene_identity_location_time_and_duration(
    case: dict[str, Any],
) -> None:
    """A model-authored story must survive the legacy profile handoff losslessly."""

    story = _authored_story(case)
    module = _load_frontend_run_module()
    profile = _projected_profile(module, case, story)
    plans = case["scene_plan"]

    assert profile.get("scene_ids") == [plan["scene_id"] for plan in plans]
    assert profile.get("scene_semantic_responsibility_ids") == [
        plan["semantic_scene_responsibility_id"] for plan in plans
    ]
    assert profile.get("scene_location_ids") == [
        plan["location"]["location_id"] for plan in plans
    ]
    assert profile["scene_locations"] == [plan["location"]["name"] for plan in plans]
    assert profile["scene_location_sequences"] == [
        plan["location"]["sequence"] for plan in plans
    ]
    assert profile["scene_times_of_day"] == [plan["time_of_day"] for plan in plans]
    assert profile["scene_time_of_day_visual_bases"] == [
        scene["time_of_day_visual_basis"] for scene in story["script"]["scenes"]
    ]
    assert profile["scene_target_durations"] == [
        plan["target_duration_seconds"] for plan in plans
    ]


@pytest.mark.parametrize("case", STORY_FIXTURES, ids=lambda case: case["case_id"])
def test_semantic_scene_identity_and_count_do_not_expand_with_target_duration(
    case: dict[str, Any],
) -> None:
    """Target duration may change timing, but never creates cloned story scenes."""

    module = _load_frontend_run_module()
    expected_ids = [plan["scene_id"] for plan in case["scene_plan"]]
    expected_titles = [plan["title"] for plan in case["scene_plan"]]
    expected_locations = [plan["location"]["name"] for plan in case["scene_plan"]]
    projected_snapshots: dict[int, tuple[Any, ...]] = {}

    for target_duration_seconds in (300, 600, 900):
        story = _authored_story(case, target_duration_seconds)
        profile = _projected_profile(module, case, story)
        duration_profile = module._duration_aware_profile(
            profile,
            target_duration_seconds=target_duration_seconds,
        )

        assert len(duration_profile["scene_titles"]) == len(expected_ids)
        assert duration_profile["scene_titles"] == expected_titles
        assert duration_profile["scene_locations"] == expected_locations
        assert duration_profile.get("scene_ids") == expected_ids
        assert duration_profile.get("scene_semantic_responsibility_ids") == [
            plan["semantic_scene_responsibility_id"] for plan in case["scene_plan"]
        ]
        assert (
            sum(duration_profile["scene_target_durations"]) == target_duration_seconds
        )
        projected_snapshots[target_duration_seconds] = (
            tuple(duration_profile["scene_titles"]),
            tuple(duration_profile["scene_locations"]),
            tuple(duration_profile.get("scene_ids") or ()),
        )

    assert (
        projected_snapshots[300] == projected_snapshots[600] == projected_snapshots[900]
    )


@pytest.mark.parametrize("case", STORY_FIXTURES, ids=lambda case: case["case_id"])
def test_rich_story_multi_location_route_does_not_require_motion_segments(
    case: dict[str, Any],
) -> None:
    story = _authored_story(case, 300)
    module = _load_frontend_run_module()

    assert module._reviewed_story_time_of_day_contract_errors(story) == []
