from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_from_manifest", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from toc.review_loop import REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE


def _approve_video_request_entries(
    request_path: Path,
    entries: list[dict],
) -> None:
    pending = MODULE._video_prompt_pending_state_updates(
        request_path=request_path,
        entries=entries,
    )
    approved = dict(pending)
    for entry in entries:
        prefix = MODULE._video_prompt_approval_state_prefix(entry["selector"])
        approved[f"{prefix}.status"] = "approved"
        approved[f"{prefix}.approved_by"] = "test_reviewer"
        approved[f"{prefix}.approved_at"] = "2026-07-18T00:00:00+09:00"
    MODULE.append_state_snapshot(request_path.parent / "state.txt", approved)


def _scene_intent_dict(scene_id: int | str, *, topic: str = "request preview") -> dict:
    next_selector = f"scene{scene_id}_next"
    return {
        "story_purpose": f"{topic} の preview scene を映画的な出来事として成立させる",
        "dramatic_question": f"{topic} は画面上の圧力を受けて次の状態へ移れるか",
        "scene_spine": f"{topic} の静止状態から圧力が生まれ、行為の痕跡が残る",
        "value_shift": {
            "from": "未確定の preview 状態",
            "to": "次の生成へ渡せる状態",
            "visible_evidence": ["足跡", "手元の道具"],
        },
        "causal_turn": f"{topic} の被写体が手元の道具を握り、次の cut の圧力を作る",
        "audience_information": [f"{topic} の主対象"],
        "withheld_information": ["後続の結末"],
        "reveal_constraints": ["後続の結末を早出ししない"],
        "affect_transition": "確認前の静けさから生成可能な緊張へ移る",
        "character_state": {
            "start": "動き出す直前",
            "end": "次の行為へ向く",
            "visible_behavior": ["視線が前を向く", "手元の道具を握る"],
        },
        "visual_thesis": f"{topic} の主対象、足跡、道具が同じ画面で読める",
        "visual_value_source": "none",
        "production_risks": [],
        "scene_conflict_engine": {
            "desire": "次の生成へ渡せる画を得る",
            "obstacle": "preview 情報の不足",
            "stakes": "後段 prompt が曖昧になる",
            "escalation": "手元の道具と視線で圧力が増える",
            "no_return_point": "主対象が画面中央で行為を始める",
            "visible_pressure": ["視線", "足跡"],
        },
        "audience_knowledge_delta": {
            "before_scene": [f"{topic} を生成対象として見る"],
            "learned_during_scene": [f"{topic} の画面上の主対象と行為が分かる"],
            "still_unknown_after_scene": ["後続 cut の結末"],
            "forbidden_early_reveals": ["後続 cut の結末"],
        },
        "handoff_chain": {
            "incoming": {
                "anchor_id": f"scene{scene_id}_incoming_anchor",
                "anchor_type": "question",
                "visible_or_audible_form": "画面中央の主対象",
            },
            "outgoing": {
                "anchor_id": f"scene{scene_id}_outgoing_anchor",
                "anchor_type": "gesture",
                "next_scene_selector": next_selector,
                "required_next_scene_start_pressure": "手元の道具が次の cut の圧力になる",
            },
        },
        "object_arc": [
            {
                "object_id": "preview_tool",
                "first_meaning": "生成対象の手がかり",
                "current_scene_meaning": "行為の証拠",
                "later_meaning": "後段 prompt の anchor",
                "visible_state_in_this_scene": "手元に見える",
                "must_not_show_yet": ["結末"],
            }
        ],
        "story_specificity": {
            "non_compressible_beat": f"{topic} が生成可能な visual proof を得る",
            "scene_promotion_reason": "独立した問い、価値変化、因果 turn を持つ",
            "unique_scene_responsibility": "preview 対象を後段生成へ渡せる visual proof に変える",
            "actor_forces": {
                "protagonist": topic,
                "opposing": ["情報不足"],
                "helping": ["画面上の道具"],
                "observing": ["reviewer"],
                "pressure_method": "情報不足が画面上の証拠を要求する",
            },
            "meaning_ladder": {
                "protagonist_stage": "未確定から生成可能へ",
                "relationship_stage": "reviewer と生成対象の関係が明確になる",
                "object_or_setpiece_stage": "道具が visual proof になる",
            },
            "concrete_handoff": {
                "incoming_trigger": "preview 対象の不足情報",
                "outgoing_anchor": "手元の道具と足跡",
                "outgoing_pressure": "visual proof が次の cut を要求する",
            },
            "anti_template_language": {
                "banned_generic_phrases_absent": True,
                "story_specific_terms": [topic, "preview_tool", "足跡"],
                "specificity_note": "主対象、道具、行為を明示する",
            },
        },
        "handoff_notes": {
            "p500_asset": ["preview_tool"],
            "p600_image": ["主対象と足跡を見せる"],
            "p700_narration": ["説明過多にしない"],
            "p800_video": ["手元の道具を起点に動かす"],
        },
    }


def _scene_event_dict(scene_id: int | str, *, topic: str = "request preview") -> dict:
    return _with_story_specific_grounding({
        "schema_version": "scene_event_v1",
        "event_logline": f"{topic} が preview の圧力を受けて次の生成に渡る",
        "start_situation": f"{topic} は画面中央で未確定の状態にある",
        "source_story_beat_ids": [f"preview_scene{scene_id}_beat"],
        "event_sequence": [
            {
                "beat_id": f"scene{scene_id}_event_setup",
                "beat_function": "setup",
                "source_story_beat_ids": [f"preview_scene{scene_id}_beat"],
                "what_happens": f"{topic} の主対象と道具が同じ画面に現れる",
                "visible_action": "主対象が画面中央に立つ",
                "visible_reaction": "周囲の視線が主対象へ集まる",
                "immediate_consequence": "preview の問いが発生する",
                "emotional_pressure": "未確定さが残る",
                "required_visual_evidence": [topic, "道具", "足跡"],
                "story_information_revealed_ids": ["preview_setup"],
            },
            {
                "beat_id": f"scene{scene_id}_event_pressure",
                "beat_function": "pressure",
                "source_story_beat_ids": [f"preview_scene{scene_id}_beat"],
                "what_happens": f"{topic} が道具を握り、次の行為への圧力を受ける",
                "visible_action": "手元の道具が握られる",
                "visible_reaction": "主対象の視線が前へ向く",
                "immediate_consequence": "画面上の証拠が増える",
                "emotional_pressure": "生成可能な緊張が高まる",
                "required_visual_evidence": ["握られた道具", "視線", "足跡"],
                "story_information_revealed_ids": ["preview_pressure"],
            },
            {
                "beat_id": f"scene{scene_id}_event_turn",
                "beat_function": "turn",
                "source_story_beat_ids": [f"preview_scene{scene_id}_beat"],
                "what_happens": f"{topic} が次の cut に渡せる行為を始める",
                "visible_action": "主対象が一歩動く",
                "visible_reaction": "足跡が残る",
                "immediate_consequence": "後続生成の原因が確定する",
                "emotional_pressure": "未確定から生成可能へ変わる",
                "required_visual_evidence": ["一歩", "足跡", "道具"],
                "story_information_revealed_ids": ["preview_turn"],
            },
            {
                "beat_id": f"scene{scene_id}_event_payoff",
                "beat_function": "payoff",
                "source_story_beat_ids": [f"preview_scene{scene_id}_beat"],
                "what_happens": f"{topic} の足跡と道具が後続 prompt の根拠として残る",
                "visible_action": "主対象が次へ向く",
                "visible_reaction": "道具と足跡が画面に残る",
                "immediate_consequence": "次の cut の圧力が成立する",
                "emotional_pressure": "後続への期待が残る",
                "required_visual_evidence": ["足跡", "道具", "前を向く姿"],
                "story_information_revealed_ids": ["preview_payoff"],
            },
        ],
        "turning_event": {
            "source_event_beat_id": f"scene{scene_id}_event_turn",
            "causal_turn_ref": "scene_intent.causal_turn",
            "irreversible_change": f"{topic} が後続生成へ渡る",
        },
        "end_situation": {
            "value_shift_to_ref": "scene_intent.value_shift.to",
            "outcome": f"{topic} が次の生成へ渡せる状態になる",
            "character_position": "前方へ向く",
            "object_state": "道具が手元に残る",
            "relationship_state": "reviewer と生成対象の関係が明確になる",
            "new_pressure": "足跡が次の cut を要求する",
            "visible_evidence_refs": [f"scene{scene_id}_event_payoff"],
        },
        "offscreen_context": ["後続 cut の結末はまだ起きていない"],
        "forbidden_event_changes": ["後続 cut の結末をこのsceneで起こさない"],
    }, scene_id, topic=topic)


def _with_story_specific_grounding(event: dict, scene_id: int | str, *, topic: str) -> dict:
    source_beat_id = f"preview_scene{scene_id}_beat"
    event["story_specificity"] = {
        "canonical_specificity": {"description": "preview source", "required_elements": [topic]},
        "character_specificity": {"description": "preview subject", "required_elements": [topic]},
        "relationship_specificity": {"description": "preview relation", "required_elements": ["reviewer と生成対象"]},
        "object_specificity": {"description": "preview object", "required_elements": ["道具"]},
        "location_specificity": {"description": "preview location", "required_elements": ["画面中央"]},
        "rule_specificity": {"description": "preview rule", "required_elements": ["後続 cut の結末を先に見せない"]},
        "visual_specificity": {"description": "preview evidence", "required_elements": ["足跡", "道具"]},
    }
    event["specificity_budget"] = {
        "max_primary_story_elements": 3,
        "max_secondary_story_elements": 3,
        "required_element_types": ["character", "location", "conflict_or_constraint", "visual_evidence"],
        "optional_element_types": ["object"],
        "reject_if": ["decorative_detail_without_story_function"],
        "reject_decorative_detail_without_story_function": True,
    }
    for beat in event.get("event_sequence", []):
        if not isinstance(beat, dict):
            continue
        beat_id = str(beat.get("beat_id") or "")
        what = str(beat.get("what_happens") or "")
        evidence = beat.get("required_visual_evidence") if isinstance(beat.get("required_visual_evidence"), list) else []
        beat["abstract_function"] = {
            "dramatic_job": "preview の観客理解を進める",
            "value_shift_role": "未確定から生成可能へ",
            "emotional_pressure_role": str(beat.get("emotional_pressure") or ""),
            "causal_role": str(beat.get("immediate_consequence") or ""),
        }
        beat["concrete_event"] = {
            "who": [topic],
            "where": "preview frame",
            "what_happens": what,
            "conflict_or_constraint": "後続生成の境界を越えずに根拠だけを見せる",
            "object_or_trace": ["道具", "足跡"],
            "visible_action": str(beat.get("visible_action") or ""),
            "visible_reaction": str(beat.get("visible_reaction") or ""),
            "immediate_consequence": str(beat.get("immediate_consequence") or ""),
            "required_visual_evidence": evidence,
        }
        beat["story_grounding"] = {
            "source_origin": "script",
            "source_story_beat_ids": [source_beat_id],
            "source_confidence": "high",
            "source_text_or_summary": what,
            "adaptation_reason": "request preview の出来事を後続 prompt に渡せる具体証拠へ変換する",
            "human_approval_required": False,
            "non_replaceable_elements": [
                {"element_id": "preview_subject", "type": "character", "value": topic, "why_non_replaceable": "preview 対象"},
                {"element_id": "preview_tool", "type": "object", "value": "道具", "why_non_replaceable": "後続 prompt の証拠"},
            ],
            "replaceability_check": {
                "would_survive_character_swap": False,
                "would_survive_object_swap": False,
                "would_survive_location_swap": False,
                "note": "preview 対象と道具を置換すると request の意味が変わる",
            },
            "concrete_story_elements": [
                {"element_id": "preview_subject", "element_type": "character", "concrete_description": topic, "story_function": "status_marker", "appears_in_event_beat_ids": [beat_id], "visible_form": "主対象の姿勢", "must_not_be_generic": True},
                {"element_id": "preview_tool", "element_type": "object", "concrete_description": "道具", "story_function": "proof", "appears_in_event_beat_ids": [beat_id], "visible_form": "手元の道具", "must_not_be_generic": True},
            ],
            "asset_story_function_usage": [
                {"asset_id": "preview_subject", "asset_type": "character", "used_in_scene": True, "used_in_event_beat_ids": [beat_id], "story_function_in_scene": "status_marker", "visible_or_hidden": "visible", "reason_if_unused": ""},
            ],
            "confidence": "high",
        }
        beat["specificity_budget"] = dict(event["specificity_budget"])
    return event


def _scene_generation_dict(scene_id: int | str, *, topic: str = "request preview") -> dict:
    source_beat_id = f"preview_scene{scene_id}_beat"
    return {
        "schema_version": "scene_generation_v1",
        "scene_authoring_context": {
            "schema_version": "scene_authoring_context_v1",
            "topic": topic,
            "scene_id": scene_id,
            "scene_index": scene_id,
            "scene_title": f"{topic} preview",
            "story_scope": {"protagonist": topic, "artifact": "道具", "theme": "preview 境界"},
            "source_beats": [{"source_story_beat_id": source_beat_id, "summary": f"{topic} が後続生成へ渡る", "source_origin": "script"}],
            "canonical_event_policy": {
                "source_story_events": "top-level canonical_event_coverage_matrix を参照",
                "scene_specificity": "source beat を具体出来事へ接地する",
            },
            "scene_count_policy": {
                "maximize_meaningful_scene_count": True,
                "do_not_fix_cut_count_in_prompt": True,
                "cut_count_is_derived_by": "scene_cut_coverage_plan",
            },
        },
        "scene_prompt_payload": {
            "schema_version": "scene_prompt_payload_v1",
            "prompt": (
                f"物語『{topic}』の preview scene{scene_id} を設計する。"
                "この scene が物語内で何を成立させるかを正本化し、"
                "scene_intent, scene_event, scene_character_state_timeline, scene_film_coverage_plan, "
                "scene_cut_coverage_plan, forbidden_event_changes を出力する。"
                "後段の画像・音声・動画実行情報は含めない。"
            ),
            "input_refs": ["story.md", "video_manifest.md", "canonical_event_coverage_matrix"],
            "required_outputs": [
                "scene_intent",
                "scene_event",
                "scene_character_state_timeline",
                "scene_film_coverage_plan",
                "scene_cut_coverage_plan",
                "forbidden_event_changes",
            ],
            "constraints": ["scene 正本生成だけに使う", "後段の画像・音声・動画実行情報を含めない", "scene_event は物語事実に限定する"],
        },
        "scene_debug_prompt_source": {
            "schema_version": "scene_debug_prompt_source_v1",
            "not_sent_to_agent": True,
            "source_story_beat_ids": [source_beat_id],
            "source_beats": [f"{topic} が後続生成へ渡る"],
            "source_origin": "script",
            "adaptation_choices": ["preview source beat を setup / pressure / turn / payoff の可視出来事へ分解する"],
            "excluded_from_payload": ["後段の画像生成詳細", "後段の動画生成詳細", "後段の音声生成詳細"],
            "forbidden_event_changes_source": "scene_event.forbidden_event_changes",
        },
        "scene_generation_contract": {
            "schema_version": "scene_generation_contract_v1",
            "required_outputs": [
                "scene_intent",
                "scene_event",
                "scene_character_state_timeline",
                "scene_film_coverage_plan",
                "scene_cut_coverage_plan",
                "forbidden_event_changes",
            ],
            "scene_event_schema_version": "scene_event_v1",
            "payload_boundary": "scene_prompt_payload は scene 正本生成だけに使う",
        },
    }


def _preview_source_projection_for_event(scene_id: int | str, event_record: dict, *, label: str) -> tuple[dict, dict, list[dict]]:
    beat_id = str(event_record.get("beat_id") or "")
    source_beat_id = f"preview_scene{scene_id}_beat"
    concrete_event = {
        "who": [label],
        "where": "preview frame",
        "what_happens": str(event_record.get("what_happens") or ""),
        "conflict_or_constraint": "後続生成の境界を越えずに根拠だけを見せる",
        "object_or_trace": ["道具", "足跡"],
        "visible_action": str(event_record.get("visible_action") or ""),
        "visible_reaction": str(event_record.get("visible_reaction") or ""),
        "required_visual_evidence": list(event_record.get("required_visual_evidence") or []),
    }
    non_replaceable = [
        {
            "element_id": "preview_subject",
            "type": "character",
            "value": label,
            "why_non_replaceable": "preview 対象",
        },
        {
            "element_id": "preview_tool",
            "type": "object",
            "value": "道具",
            "why_non_replaceable": "後続 prompt の証拠",
        },
    ]
    story_grounding = {
        "source_origin": "script",
        "source_story_beat_ids": [source_beat_id],
        "source_confidence": "high",
        "source_text_or_summary": str(event_record.get("what_happens") or ""),
        "adaptation_reason": "request preview の出来事を後続 prompt に渡せる具体証拠へ変換する",
        "human_approval_required": False,
        "non_replaceable_elements": non_replaceable,
        "replaceability_check": {
            "would_survive_character_swap": False,
            "would_survive_object_swap": False,
            "would_survive_location_swap": False,
            "note": "preview 対象と道具を置換すると request の意味が変わる",
        },
        "concrete_story_elements": [
            {
                "element_id": "preview_subject",
                "element_type": "character",
                "concrete_description": label,
                "story_function": "status_marker",
                "appears_in_event_beat_ids": [beat_id],
                "visible_form": "主対象の姿勢",
                "must_not_be_generic": True,
            },
            {
                "element_id": "preview_tool",
                "element_type": "object",
                "concrete_description": "道具",
                "story_function": "proof",
                "appears_in_event_beat_ids": [beat_id],
                "visible_form": "手元の道具",
                "must_not_be_generic": True,
            },
        ],
        "asset_story_function_usage": [
            {
                "asset_id": "preview_subject",
                "asset_type": "character",
                "used_in_scene": True,
                "used_in_event_beat_ids": [beat_id],
                "story_function_in_scene": "status_marker",
                "visible_or_hidden": "visible",
                "reason_if_unused": "",
            },
        ],
        "confidence": "high",
    }
    return concrete_event, story_grounding, non_replaceable


def _preview_canonical_event_coverage_matrix(scene_ids: list[int | str]) -> dict:
    rows = []
    for order, scene_id in enumerate(scene_ids, start=1):
        scene_id_text = str(scene_id)
        rows.append(
            {
                "source_event_id": f"preview_scene{scene_id_text}_source_event",
                "source_event_summary": f"scene{scene_id_text} の preview 出来事が setup から payoff まで成立する",
                "importance": "high",
                "required": True,
                "must_appear_as": "scene",
                "canonical_order_index": order,
                "assigned_scene_ids": [scene_id_text],
                "assigned_event_beat_ids": [
                    f"scene{scene_id_text}_event_setup",
                    f"scene{scene_id_text}_event_pressure",
                    f"scene{scene_id_text}_event_turn",
                    f"scene{scene_id_text}_event_payoff",
                ],
                "omission_reason": "",
                "adaptation_change_reason": "",
                "human_approval_required": False,
            }
        )
    return {
        "policy_version": "canonical_event_coverage_matrix_v1",
        "source": ["script", "manifest", "request_preview"],
        "source_story_events": rows,
    }


def _scene_emotion_film_dicts(
    scene_id: int | str,
    *,
    topic: str = "request preview",
    selectors: list[str] | None = None,
    character_ids: list[str] | None = None,
) -> tuple[dict, dict]:
    selectors = selectors or [f"scene{scene_id}_cut{index}" for index in range(1, 5)]
    timeline_character_ids = list(dict.fromkeys([character_id for character_id in (character_ids or ["preview_subject"]) if str(character_id).strip()]))
    timeline = {
        "policy_version": "character_emotion_continuity_v1",
        "source_schema_version": "scene_event_v1",
        "scene_id": scene_id,
        "linked_scene_event_beat_ids": [
            f"scene{scene_id}_event_setup",
            f"scene{scene_id}_event_pressure",
            f"scene{scene_id}_event_turn",
            f"scene{scene_id}_event_payoff",
        ],
        "characters": [
            {
                "character_id": character_id,
                "character_name": topic if character_id == timeline_character_ids[0] else character_id,
                "scene_role": "protagonist",
                "objective_in_scene": "次の生成に渡る",
                "emotional_arc_summary": "未確定から生成可能へ",
                "start_state": {
                    "trigger_event_beat_id": f"scene{scene_id}_event_setup",
                    "emotion": "未確定",
                    "desire": "次へ渡る",
                    "fear_or_pressure": "preview の圧力",
                    "belief": "まだ未確定",
                    "relationship_to_others": "周囲の視線を受ける",
                    "body_state": "立つ",
                    "gaze_target": "前方",
                    "visible_proof": {"face": "緊張した表情", "gaze": "前方を見る", "posture": "立つ", "hands": "道具を握る", "feet": "足元が止まる", "distance": "道具との距離が読める", "visible_proof": "主対象と道具"},
                },
                "midpoint_state": {
                    "trigger_event_beat_id": f"scene{scene_id}_event_turn",
                    "emotion": "生成可能",
                    "desire_shift": "次へ進む",
                    "fear_or_pressure_shift": "後戻りできない",
                    "belief_shift": "次へ渡せる",
                    "relationship_shift": "画面上の証拠が増える",
                    "body_state": "一歩動く",
                    "gaze_target": "次のcut",
                    "visible_proof": {"face": "息を止めた表情", "gaze": "次を見る", "posture": "前傾", "hands": "道具を握る", "feet": "一歩出る", "distance": "前方へ距離が開く", "visible_proof": "一歩と足跡"},
                },
                "end_state": {
                    "trigger_event_beat_id": f"scene{scene_id}_event_payoff",
                    "emotion": "後続への期待",
                    "new_desire": "次cutへ渡る",
                    "unresolved_pressure": "結末はまだ",
                    "belief_after_scene": "生成可能",
                    "relationship_after_scene": "主対象と証拠が結びつく",
                    "body_state": "次へ向く",
                    "gaze_target": "次の導線",
                    "visible_proof": {"face": "静かな決意", "gaze": "次を見る", "posture": "次へ向く", "hands": "道具を持つ", "feet": "足跡を残す", "distance": "次へ距離が開く", "visible_proof": "足跡と道具"},
                },
                "emotional_no_return_point": {"event_beat_id": f"scene{scene_id}_event_turn", "description": "次へ渡る", "visible_behavior": "一歩動く"},
            }
            for character_id in timeline_character_ids
        ],
    }
    coverage = {
        "policy_version": "scene_film_coverage_v1",
        "source": ["scene_event", "scene_character_state_timeline", "scene_cut_coverage_plan"],
        "scene_id": scene_id,
        "shot_mix": {
            "required_coverage": {
                "establishing": selectors[:1],
                "action": selectors[1:3],
                "insert": [],
                "reaction": selectors[-1:],
                "handoff": selectors[-1:],
            },
            "actual_shots": [],
            "missing_coverage": [],
        },
        "action_reaction_pair": [
            {
                "source_event_beat_id": f"scene{scene_id}_event_turn",
                "action_cut_selector": selectors[min(2, len(selectors) - 1)] if selectors else "",
                "reaction_cut_selector": selectors[-1] if selectors else "",
                "meaning_created_by_pair": "行為の意味が反応で読める",
            },
            {
                "source_event_beat_id": f"scene{scene_id}_event_payoff",
                "action_cut_selector": selectors[-1] if selectors else "",
                "reaction_cut_selector": selectors[-1] if selectors else "",
                "meaning_created_by_pair": "結果の意味が反応で読める",
            }
        ],
        "missing_coverage": [],
        "required_when_rules": {
            "reaction": "turn / reveal / payoff の event beat では required",
            "insert": "重要小道具があれば required",
            "eyeline": "認識やhandoffでは required",
            "silence": "感情転換では required",
        },
        "audience_emotion_target": {
            "separate_from_character_emotion": True,
            "intended_audience_feeling": "次へ渡る圧力を感じる",
            "achieved_by": ["character_reaction", "shot_scale", "silence"],
        },
    }
    return timeline, coverage


def _preview_triangulation_review() -> dict:
    return {
        "status": "passed",
        "same_target_beat": True,
        "image_supports_motion_start": True,
        "motion_reaches_declared_end_state": True,
        "narration_not_captioning_image": True,
        "reveal_constraints_preserved": True,
        "continuity_preserved": True,
        "handoff_visible_or_audible": True,
    }


def _preview_cut_contract(
    scene_id: int | str,
    cut_id: int | str,
    *,
    label: str = "request preview",
    sequence_index: int | None = None,
    total_cuts: int = 4,
    previous_selector: str = "",
    next_selector: str = "",
) -> dict:
    selector = f"scene{scene_id}_cut{cut_id}"
    sequence_index = sequence_index or int(cut_id)
    if sequence_index > 1 and not previous_selector:
        previous_selector = f"scene{scene_id}_cut{int(cut_id) - 1}"
    if sequence_index < total_cuts and not next_selector:
        next_selector = f"scene{scene_id}_cut{int(cut_id) + 1}"
    previous_selector = previous_selector if sequence_index > 1 else ""
    next_selector = next_selector if sequence_index < total_cuts else ""
    incoming_anchor = f"{previous_selector}_to_{selector}" if previous_selector else f"scene{scene_id}_incoming"
    outgoing_anchor = f"{selector}_to_{next_selector}" if next_selector else f"scene{scene_id}_to_next"
    event_records = [
        {
            "beat_id": f"scene{scene_id}_event_setup",
            "beat_function": "setup",
            "what_happens": f"{label} の主対象と道具が同じ画面に現れる",
            "visible_action": "主対象が画面中央に立つ",
            "visible_reaction": "周囲の視線が主対象へ集まる",
            "required_visual_evidence": [label, "道具", "足跡"],
        },
        {
            "beat_id": f"scene{scene_id}_event_pressure",
            "beat_function": "pressure",
            "what_happens": f"{label} が道具を握り、次の行為への圧力を受ける",
            "visible_action": "手元の道具が握られる",
            "visible_reaction": "主対象の視線が前へ向く",
            "required_visual_evidence": ["握られた道具", "視線", "足跡"],
        },
        {
            "beat_id": f"scene{scene_id}_event_turn",
            "beat_function": "turn",
            "what_happens": f"{label} が次の cut に渡せる行為を始める",
            "visible_action": "主対象が一歩動く",
            "visible_reaction": "足跡が残る",
            "required_visual_evidence": ["一歩", "足跡", "道具"],
        },
        {
            "beat_id": f"scene{scene_id}_event_payoff",
            "beat_function": "payoff",
            "what_happens": f"{label} の足跡と道具が後続 prompt の根拠として残る",
            "visible_action": "主対象が次へ向く",
            "visible_reaction": "道具と足跡が画面に残る",
            "required_visual_evidence": ["足跡", "道具", "前を向く姿"],
        },
    ]
    event_index = min(sequence_index - 1, len(event_records) - 1)
    event_record = event_records[event_index]
    event_function = str(event_record["beat_function"])
    event_beat_id = str(event_record["beat_id"])
    source_event_beat_ids = [event_beat_id]
    blocked_future_event_beat_ids = [
        str(record["beat_id"])
        for record in event_records
        if record["beat_id"] not in source_event_beat_ids and record["beat_function"] in {"turn", "payoff"}
    ]
    neighboring_event_beats = []
    for neighbor_index in (event_index - 1, event_index + 1):
        if 0 <= neighbor_index < len(event_records):
            neighboring_event_beats.append(event_records[neighbor_index])
    forbidden_event_changes = ["後続 cut の結末をこのsceneで起こさない"]
    concrete_event, story_grounding, non_replaceable_elements = _preview_source_projection_for_event(
        scene_id,
        event_record,
        label=label,
    )
    visible_behavior = {
        "face": "緊張した表情",
        "gaze": "前方を見る",
        "posture": event_record["visible_action"],
        "hands": "道具を握る",
        "feet": "次へ進める足元",
        "distance": "主対象と道具の距離が読める",
        "visible_proof": event_record["visible_action"],
    }
    return {
        "schema_version": "3.0",
        "source_event_contract": {
            "primary_event_beat_id": event_beat_id,
            "source_event_beat_ids": source_event_beat_ids,
            "event_beat_function": event_function,
            "event_time_position": "before_trigger",
            "source_event_summary": event_record["what_happens"],
            "source_concrete_events": [concrete_event],
            "source_story_grounding": [story_grounding],
            "source_non_replaceable_elements": non_replaceable_elements,
            "source_visible_action": event_record["visible_action"],
            "source_visible_reaction": event_record["visible_reaction"],
            "source_required_visual_evidence": event_record["required_visual_evidence"],
            "event_facts_to_preserve": [event_record["what_happens"]],
            "event_facts_not_to_invent": forbidden_event_changes,
            "allowed_reveal_info_ids": [],
            "forbidden_reveal_info_ids": ["後続 cut の結末"],
        },
        "cut_character_emotion_transition": {
            "policy_version": "cut_character_emotion_transition_v1",
            "focal_character_id": "preview_subject",
            "supporting_character_ids": [],
            "transition_mode": "triggered_shift",
            "emotion_from": {"label": "未確定", "visible_behavior": visible_behavior},
            "emotion_to": {"label": "次へ渡る", "visible_behavior": visible_behavior},
            "transition_trigger": {
                "source_event_beat_id": event_beat_id,
                "what_causes_shift": event_record["what_happens"],
                "visible_cause": event_record["visible_action"],
            },
            "transition_visible_in_cut": {
                "face_change": "表情が締まる",
                "gaze_change": "前方を見る",
                "posture_change": event_record["visible_action"],
                "hand_change": "道具を握る",
                "foot_change": "足元が次へ向く",
                "distance_change": "主対象と道具の距離が読める",
                "silence_or_pause": "一拍の沈黙",
            },
            "emotional_delta_visible_in_first_frame": "視線と手足に変化の始まりが見える",
            "emotional_delta_completed_by_motion": "動画で一段だけ進む",
            "must_not_jump_to_final_emotion": True,
        },
        "cut_film_grammar_contract": {
            "policy_version": "cut_film_grammar_v1",
            "required_modules": {
                "character_objective_and_tactic": {
                    "character_id": "preview_subject",
                    "objective": "次の生成に渡る",
                    "tactic": event_record["visible_action"],
                    "obstacle": "未確定さ",
                    "tactic_shift_after_event": "次へ進む",
                    "visible_action": event_record["visible_action"],
                },
                "attention_state": {
                    "character_id": "preview_subject",
                    "gaze_target": "前方",
                    "attention_type": "recognizing",
                    "viewer_attention_target": event_record["visible_action"],
                    "eyeline_match_to_next_cut": next_selector,
                },
                "eyeline_continuity": {
                    "cut_selector": selector,
                    "character_id": "preview_subject",
                    "gaze_target": "前方",
                    "next_cut_should_show_target": bool(next_selector),
                    "previous_cut_gaze_source": previous_selector,
                    "eyeline_match_valid": True,
                },
                "screen_direction_continuity": {
                    "movement_direction": "left_to_right",
                    "previous_direction": "left_to_right",
                    "direction_change_motivated": True,
                    "motivation": "次の生成に渡るため",
                },
                "edit_motivation": {
                    "cut_selector": selector,
                    "cut_reason": "new_information",
                    "why_previous_cut_is_complete": "前cutの証拠が読めた",
                    "why_current_cut_is_needed": event_record["visible_action"],
                    "viewer_attention_shift": "前方",
                },
                "audience_emotion_target": {
                    "cut_selector": selector,
                    "separate_from_character_emotion": True,
                    "intended_audience_feeling": "次へ渡る圧力を感じる",
                    "achieved_by": ["character_reaction", "shot_scale", "silence"],
                },
            },
            "conditional_modules": {
                "character_reaction_contract": {
                    "required": event_function in {"turn", "payoff"},
                    "required_when": "turn / reveal / payoff の event beat を担当するcut",
                    "reacts_to_event_beat_id": event_beat_id,
                    "reacting_character_id": "preview_subject",
                    "reaction_type": "recognition",
                    "visible_reaction": {
                        "eyes": "前方を見る",
                        "mouth": "閉じる",
                        "head": "前へ向く",
                        "shoulders": "硬い",
                        "hands": "道具を握る",
                        "body_distance": "距離が読める",
                    },
                    "reaction_duration_intent": "held",
                    "should_be_silent": True,
                    "narration_should_not_explain": True,
                },
                "relationship_state_delta": {
                    "required": True,
                    "relationship_id": "preview_subject_world",
                    "characters": ["preview_subject", "world"],
                    "from_state": "未確定",
                    "to_state": "生成可能",
                    "trigger_event_beat_id": event_beat_id,
                    "visible_evidence": {
                        "distance": "距離が読める",
                        "gaze": "前方",
                        "body_orientation": event_record["visible_action"],
                        "touch_or_non_touch": "道具を握る",
                        "hierarchy_in_frame": "主対象が中景",
                    },
                    "must_not_resolve_yet": [],
                },
                "prop_state_progression": {
                    "required": False,
                    "object_id": "",
                    "source_event_beat_ids": [event_beat_id],
                    "state_by_cut": [],
                },
                "costume_and_body_continuity": {
                    "required": True,
                    "character_id": "preview_subject",
                    "costume_state": "同じ衣装",
                    "hair_state": "同じ髪",
                    "dirt_or_damage_state": "急変なし",
                    "posture_state": event_record["visible_action"],
                    "allowed_changes_in_this_cut": ["視線", "手", "足"],
                    "forbidden_changes_in_this_cut": ["別人物化"],
                },
                "silence_and_pause_contract": {
                    "required": event_function in {"turn", "payoff"},
                    "cut_selector": selector,
                    "silence_required": event_function in {"turn", "payoff"},
                    "pause_reason": "感情転換を説明しない",
                    "emotion_to_read_in_silence": "視線と手足",
                    "narration_must_not_explain": True,
                },
            },
            "required_when_rules": {
                "reaction": "turn / reveal / payoff の event beat では required",
                "insert": "重要小道具があれば required",
                "eyeline": "認識やhandoffでは required",
                "silence": "感情転換では required",
            },
        },
        "cut_function": "setup",
        "intent_budget": {
            "primary_intent": label,
            "secondary_intents_allowed": [],
            "forbidden_combined_intents": ["new_location_establishing + major_reveal + next_scene_handoff"],
            "assigned_obligation_ids": [f"obligation_{cut_id}"],
            "overload_exception_reason": "",
        },
        "viewer_contract": {
            "target_beat": label,
            "screen_question": f"{label} は何を見せるか",
            "dramatic_job": "sceneの意味を一つ進める",
            "audience_knowledge_delta": f"観客は {label} の画面上の役割を理解する",
            "causal_proof": f"{label} が人物・場所・道具の関係で読める",
            "visual_evidence": [label],
            "required_roles": ["protagonist"],
            "anti_redundancy_key": f"scene{scene_id}:cut{cut_id}:{label}",
            "visual_proof": f"{label} が見える",
            "must_show": [label],
            "must_avoid": [],
            "done_when": [f"{label} is visible"],
        },
        "cinematic_contract": {
            "camera_intent": f"{label} へ視線を導く",
            "subject_priority": {"primary": label, "secondary": "道具", "background": "場所"},
            "screen_geography": {"foreground": "足元", "midground": label, "background": "奥行き", "screen_direction": "left_to_right"},
        },
        "continuity_contract": {
            "start_state": {"character_state": "開始前", "prop_state": "道具が見える", "spatial_state": "場所", "time_state": "現在"},
            "end_state": {"character_state": "次へ向く", "prop_state": "道具が残る", "spatial_state": "場所", "time_state": "cut後"},
            "carry_forward_to_next_cut": [label],
        },
        "cut_handoff": {
            "receives_from_previous": {
                "anchor_id": incoming_anchor,
                "anchor_type": "none" if not previous_selector else "gesture",
                "visible_or_audible_form": "前cutから残る視線",
                "expected_previous_cut_selector": previous_selector,
            },
            "delivers_to_next": {
                "anchor_id": outgoing_anchor,
                "anchor_type": "gesture",
                "visible_or_audible_form": "次へ残る視線",
                "expected_next_cut_selector": next_selector,
            },
        },
        "first_frame_contract": {
            "imageable": True,
            "source_event_beat_id": event_beat_id,
            "event_time_position": "before_trigger",
            "event_fact_visible_in_still": event_record["visible_action"],
            "not_yet_happened_in_still": ["後続 cut の結末"],
            "first_frame_brief": event_record["visible_action"],
            "visible_start_state": {"character_state": "開始前", "prop_state": "道具が見える", "spatial_state": "場所", "emotional_state": "緊張", "gaze_or_attention": "前方"},
            "motion_start_affordance": {"movable_subject": label, "movement_vector": "left_to_right", "camera_start_reason": "奥行きがある"},
            "action_completion_state": "pre_action",
            "static_first_frame_rule": f"{label} の意味が静止画で読める",
            "must_be_static_evidence_not_motion": True,
        },
        "motion_contract": {
            "movable": True,
            "source_event_beat_id": event_beat_id,
            "starts_from_first_frame": True,
            "must_not_advance_to_event_beat_ids": blocked_future_event_beat_ids,
            "motion_brief": f"{label} がゆっくり動く",
            "start_from_visible_state": "first_frame_contract.visible_start_state",
            "end_state": f"{label} が次へ向く",
            "end_frame_brief": f"{label} が次へ向く",
            "must_not_add": ["新しい人物"],
        },
        "narration_contract": {
            "source_event_beat_ids": [event_beat_id],
            "allowed_info_ids": [],
            "forbidden_info_ids": ["後続 cut の結末"],
            "must_not_advance_to_event_beat_ids": blocked_future_event_beat_ids,
            "must_not_explain_visible_action_as_caption": True,
            "narration_event_boundary": "same_event_only",
            "role": "emotion",
            "target_function": "絵を説明せず補う",
            "must_avoid": ["映像のキャプション化"],
            "silence_reason": "",
        },
        "rhythm_contract": {
            "expected_duration_seconds": 12,
            "pacing": "standard",
            "comprehension_moment": f"{label} が見えた瞬間",
            "cut_out_reason": "次への視線が残る",
            "audio_visual_sync_point": "視線の後に声が入る",
            "duration_exception": {"allowed": False, "reason": ""},
        },
        "asset_dependency": {
            "character_ids_required": [],
            "object_ids_required": [],
            "location_ids_required": [],
            "variant_ids_required": [],
            "new_asset_requests": [],
            "reusable_anchor_ids": [],
        },
        "downstream_handoff": {
            "p500_asset": {"required_asset_ids": [], "asset_candidates": [], "continuity_anchor_needed": False, "new_asset_needed": False, "reuse_allowed": True},
            "p600_image": {"prompt_requirements": [label], "reference_requirements": [], "first_frame_must_include": [label], "first_frame_must_avoid": []},
            "p700_narration": {"narration_requirements": ["補う"], "role": "emotion", "must_not_caption_visible_content": True},
            "p800_video": {"motion_requirements": [f"{label} がゆっくり動く"], "start_state": "開始前", "last_frame_or_end_state": f"{label} が次へ向く", "must_not_add": ["新しい人物"]},
            "carries_to_next_cut": [label],
            "carries_to_next_scene": [],
        },
        "event_context_for_cut": {
            "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
            "editable": False,
            "primary_event_beat": {
                "beat_id": event_beat_id,
                "beat_function": event_function,
                "what_happens": event_record["what_happens"],
                "visible_action": event_record["visible_action"],
                "visible_reaction": event_record["visible_reaction"],
                "required_visual_evidence": event_record["required_visual_evidence"],
                "concrete_event": concrete_event,
                "story_grounding": story_grounding,
            },
            "source_event_beats": [event_record],
            "neighboring_event_beats": neighboring_event_beats,
            "forbidden_event_changes": forbidden_event_changes,
            "reveal_constraints_for_this_cut": [],
        },
    }


def _preview_scene_cut_coverage_plan(scene_id: int | str, cut_count: int, *, label: str = "request preview", selectors: list[str] | None = None) -> dict:
    selectors = selectors or [f"scene{scene_id}_cut{index}" for index in range(1, cut_count + 1)]
    return {
        "coverage_strategy": "reverse_from_scene_event",
        "source_schema_version": "scene_event_v1",
        "min_cut_count": {"by_importance": 3, "by_duration": min(4, max(3, cut_count)), "by_event_beats": min(4, max(3, cut_count)), "selected": min(4, max(3, cut_count)), "exception_reason": ""},
        "scene_obligations": [
            {"obligation_id": "dramatic_question_01", "source": "dramatic_question", "evidence": label, "assigned_cut_ids": selectors[:1]},
            {"obligation_id": "value_shift_01", "source": "value_shift.visible_evidence", "evidence": [label], "assigned_cut_ids": selectors[1:2] or selectors[:1]},
            {"obligation_id": "causal_turn_01", "source": "causal_turn", "evidence": label, "assigned_cut_ids": selectors[2:3] or selectors[:1]},
            {"obligation_id": "handoff_01", "source": "handoff_to_next_scene", "evidence": label, "assigned_cut_ids": selectors[-1:]},
        ],
        "cut_assignments": [
            {
                "cut_index": index,
                "cut_selector": selector,
                "obligation_ids": ["dramatic_question_01"] if index == 1 else ["value_shift_01"] if index == 2 else ["causal_turn_01"] if index == 3 else ["handoff_01"],
                "cut_function": "setup",
                "event_assignment": {
                    "source_event_contract": {
                        "primary_event_beat_id": f"scene{scene_id}_event_{['setup', 'pressure', 'turn', 'payoff'][min(index - 1, 3)]}",
                        "source_event_beat_ids": [f"scene{scene_id}_event_{['setup', 'pressure', 'turn', 'payoff'][min(index - 1, 3)]}"],
                    }
                },
                "target_beat": label,
                "visual_proof": f"{label} が見える",
                "audience_knowledge_delta": f"{label} を理解する",
                "causal_proof": f"{label} が画面で証明される",
                "required_roles": ["protagonist"],
                "anti_redundancy_key": f"scene{scene_id}:cut{index}:{label}",
            }
            for index, selector in enumerate(selectors, start=1)
        ],
        "unassigned_obligations": [],
        "overloaded_cuts": [],
        "duplicate_meaning_risks": [],
    }


def _make_p400_ready_for_request_preview(run_dir: Path) -> None:
    manifest_path = run_dir / "video_manifest.md"
    data = MODULE.yaml.safe_load(MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8"))) if MODULE.yaml is not None else {}
    if not isinstance(data, dict):
        data = {}
    initial_metadata = data.get("video_metadata") if isinstance(data.get("video_metadata"), dict) else {}
    if str(initial_metadata.get("experience") or "").strip().lower().startswith("asset_stage"):
        with (run_dir / "state.txt").open("a", encoding="utf-8") as f:
            f.write("eval.p400_readiness.status=approved\n---\n")
        return
    existing_script = {}
    existing_script_path = run_dir / "script.md"
    if existing_script_path.exists():
        existing_script = MODULE.yaml.safe_load(MODULE.extract_yaml_block(existing_script_path.read_text(encoding="utf-8"))) if MODULE.yaml is not None else {}
        if not isinstance(existing_script, dict):
            existing_script = {}
    existing_cut_lookup = {}
    existing_scenes = existing_script.get("scenes")
    if not existing_scenes and isinstance(existing_script.get("script"), dict):
        existing_scenes = existing_script["script"].get("scenes")
    for existing_scene in existing_scenes if isinstance(existing_scenes, list) else []:
        if not isinstance(existing_scene, dict):
            continue
        for existing_cut in existing_scene.get("cuts", []) if isinstance(existing_scene.get("cuts"), list) else []:
            if isinstance(existing_cut, dict):
                existing_cut_lookup[(str(existing_scene.get("scene_id")), str(existing_cut.get("cut_id")))] = existing_cut
    data["manifest_phase"] = "production"
    metadata = data.setdefault("video_metadata", {})
    if isinstance(metadata, dict):
        metadata.setdefault("topic", "request preview")
        metadata.setdefault("experience", "cinematic_story")
        metadata["target_duration_seconds"] = 300
    scenes = data.setdefault("scenes", [])
    if not isinstance(scenes, list):
        scenes = []
        data["scenes"] = scenes
    if not scenes:
        scenes.append({"scene_id": 1, "cuts": []})

    total_duration = 0
    script_scenes: list[dict] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id", scene_index)
        if str(scene.get("kind") or "").strip().lower() in {"reference", "character_reference"}:
            continue
        cuts = scene.setdefault("cuts", [])
        if not isinstance(cuts, list):
            cuts = []
            scene["cuts"] = cuts
        while len([cut for cut in cuts if isinstance(cut, dict) and str(cut.get("cut_status") or "").lower() != "deleted"]) < 4:
            filler_cut_id = len(cuts) + 1
            cuts.append(
                {
                    "cut_id": filler_cut_id,
                    "cut_contract": _preview_cut_contract(scene_id, filler_cut_id, label="request preview"),
                    "scene_contract": {"target_beat": "request preview", "must_show": ["request preview"], "must_avoid": [], "done_when": ["request preview cut is present"]},
                    "image_generation": {
                        "tool": "codex_builtin_image",
                        "prompt": "画面内テキストなし。実写映画風の村道、人物、道具、背景、光、足元、空気感が具体的に見える。",
                        "character_ids": [],
                        "object_ids": [],
                        "output": f"assets/scenes/scene{scene_id}_p400_filler_{filler_cut_id}.png",
                        "review": {"triangulation_review": _preview_triangulation_review()},
                    },
                    "video_generation": {
                        "tool": "kling_3_0",
                        "duration_seconds": 15,
                        "motion_prompt": "人物がゆっくり前へ進む。",
                        "output": f"assets/videos/scene{scene_id}_p400_filler_{filler_cut_id}.mp4",
                    },
                    "audio": {"narration": {"tool": "elevenlabs", "text": "場面が続く。", "output": f"assets/audio/scene{scene_id}_p400_filler_{filler_cut_id}.mp3"}},
                    "review": {"triangulation_review": _preview_triangulation_review()},
                }
            )
        render_units = scene.get("render_units")
        if isinstance(render_units, list) and render_units:
            active_cut_ids = [
                str(cut.get("cut_id", index))
                for index, cut in enumerate(cuts, start=1)
                if isinstance(cut, dict) and str(cut.get("cut_status") or "").lower() != "deleted"
            ]
            assigned_cut_ids = {
                str(cut_id)
                for unit in render_units
                if isinstance(unit, dict)
                for cut_id in (unit.get("source_cut_ids") if isinstance(unit.get("source_cut_ids"), list) else [])
            }
            missing_cut_ids = [cut_id for cut_id in active_cut_ids if cut_id not in assigned_cut_ids]
            if missing_cut_ids and isinstance(render_units[-1], dict):
                existing_source_ids = render_units[-1].get("source_cut_ids")
                if not isinstance(existing_source_ids, list):
                    existing_source_ids = []
                render_units[-1]["source_cut_ids"] = [*existing_source_ids, *missing_cut_ids]
        active_cuts = [
            cut
            for cut in cuts
            if isinstance(cut, dict) and str(cut.get("cut_status") or "").lower() != "deleted"
        ]
        active_meta: dict[int, tuple[int, int, str, str]] = {}
        active_selectors = [
            str(cut.get("selector") or f"scene{scene_id}_cut{cut.get('cut_id', index)}")
            for index, cut in enumerate(active_cuts, start=1)
        ]
        active_character_ids: list[str] = []
        for active_cut in active_cuts:
            active_image_generation = active_cut.get("image_generation") if isinstance(active_cut.get("image_generation"), dict) else {}
            active_character_ids.extend(str(item) for item in active_image_generation.get("character_ids", []) if str(item).strip())
        for active_index, active_cut in enumerate(active_cuts, start=1):
            previous_selector = active_selectors[active_index - 2] if active_index > 1 else ""
            next_selector = active_selectors[active_index] if active_index < len(active_selectors) else ""
            active_meta[id(active_cut)] = (active_index, len(active_selectors), previous_selector, next_selector)
        script_cuts = []
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict) or str(cut.get("cut_status") or "").lower() == "deleted":
                continue
            cut_id = cut.get("cut_id", cut_index)
            video_generation = cut.setdefault("video_generation", {})
            if isinstance(video_generation, dict):
                preview_duration = (
                    12
                    if "seedance"
                    in str(video_generation.get("tool") or "").strip().lower()
                    else 15
                )
                video_generation["duration_seconds"] = preview_duration
                video_generation.setdefault("motion_prompt", "人物がゆっくり前へ進む。")
                total_duration += preview_duration
            image_generation = cut.setdefault("image_generation", {})
            if isinstance(image_generation, dict):
                image_generation.setdefault("prompt", "画面内テキストなし。実写映画風の具体的な人物、場所、道具、光が見える。")
                image_generation.setdefault("character_ids", [])
                image_generation.setdefault("object_ids", [])
            cut.setdefault(
                "scene_contract",
                {
                    "target_beat": "request preview",
                    "must_show": ["request preview"],
                    "must_avoid": [],
                    "done_when": ["request preview cut is present"],
                },
            )
            scene_contract_for_label = cut.get("scene_contract") if isinstance(cut.get("scene_contract"), dict) else {}
            active_index, active_total, previous_selector, next_selector = active_meta.get(
                id(cut),
                (int(cut_id), 4, "", ""),
            )
            cut["cut_contract"] = _preview_cut_contract(
                scene_id,
                cut_id,
                label=str(scene_contract_for_label.get("target_beat") or "request preview"),
                sequence_index=active_index,
                total_cuts=active_total,
                previous_selector=previous_selector,
                next_selector=next_selector,
            )
            cut.setdefault("review", {})["triangulation_review"] = _preview_triangulation_review()
            contract = cut.get("scene_contract") if isinstance(cut.get("scene_contract"), dict) else {}
            prompt_terms = [str(contract.get("target_beat") or "request preview")]
            prompt_terms.extend(str(item) for item in contract.get("must_show", []) if str(item).strip())
            if isinstance(image_generation, dict):
                current_prompt = str(image_generation.get("prompt") or "")
                image_generation["prompt"] = (
                    current_prompt
                    + " 画面内テキストなし。"
                    + "、".join(prompt_terms)
                    + "、人物、場所、道具、背景、光、足元、空気感、衣装の布目、地面の質感、前景の小物、中景の人物、背景の奥行き、自然な影、実写映画のレンズ感が具体的に見える。"
                )
                image_generation.setdefault("review", {})["triangulation_review"] = _preview_triangulation_review()
            cut.setdefault("audio", {"narration": {"tool": "elevenlabs", "text": "場面が続く。"}})
            narration = cut.get("audio", {}).get("narration") if isinstance(cut.get("audio"), dict) else None
            request_ids = []
            if isinstance(image_generation, dict):
                request_ids.extend(str(item) for item in image_generation.get("applied_request_ids", []) if str(item).strip())
            if isinstance(video_generation, dict):
                request_ids.extend(str(item) for item in video_generation.get("applied_request_ids", []) if str(item).strip())
            trace = cut.get("implementation_trace") if isinstance(cut.get("implementation_trace"), dict) else {}
            request_ids.extend(str(item) for item in trace.get("source_request_ids", []) if str(item).strip())
            request_ids = list(dict.fromkeys(request_ids))
            if isinstance(narration, dict) and request_ids:
                narration.setdefault("applied_request_ids", request_ids)
            existing_cut = existing_cut_lookup.get((str(scene_id), str(cut_id)), {})
            script_cut = {
                key: value
                for key, value in existing_cut.items()
                if key not in {"cut_blueprint"}
            } if isinstance(existing_cut, dict) else {}
            script_cut.update(
                {
                    "cut_id": cut_id,
                    "selector": cut.get("selector") or f"scene{scene_id}_cut{cut_id}",
                    "cut_contract": cut["cut_contract"],
                    "scene_contract": cut.get("scene_contract"),
                    "cut_blueprint": {
                        "cut_role": "main",
                        "duration_intent": "standard",
                        "target_beat": "request preview",
                        "must_show": ["request preview"],
                        "must_avoid": [],
                        "done_when": ["request preview cut is present"],
                        "visual_beat": "request preview",
                        "narration_role": "setup",
                        "asset_dependency_hint": {"character_ids": [], "object_ids": [], "location_ids": [], "reusable_still_candidates": []},
                    },
                }
            )
            script_cuts.append(
                script_cut
            )
        scene_character_state_timeline, scene_film_coverage_plan = _scene_emotion_film_dicts(
            scene_id,
            selectors=[str(item) for item in active_selectors],
            character_ids=active_character_ids or None,
        )
        script_scenes.append(
            {
                "scene_id": scene_id,
                "phase": "development",
                "importance": "medium",
                "summary": "request preview 用の p400 readiness scene。",
                "target_duration_seconds": max(32, len(script_cuts) * 8),
                "estimated_duration_seconds": max(32, len(script_cuts) * 8),
                "handoff_to_next_scene": "次へつながる",
                "terminal_resolution": "preview 完了",
                "coverage_review": {
                    "audience_information_covered": True,
                    "visualizable_action_covered": True,
                    "value_shift_visible": True,
                    "causal_turn_visible": True,
                    "scene_specificity_gate_passed": True,
                    "next_scene_connection_checked": True,
                },
                "scene_intent": _scene_intent_dict(scene_id),
                "scene_generation": _scene_generation_dict(scene_id),
                "scene_event": _scene_event_dict(scene_id),
                "scene_character_state_timeline": scene_character_state_timeline,
                "scene_film_coverage_plan": scene_film_coverage_plan,
                "scene_cut_coverage_plan": _preview_scene_cut_coverage_plan(scene_id, len(script_cuts), selectors=[str(item) for item in active_selectors]),
                "agent_review": {"status": "passed"},
                "cuts": script_cuts,
            }
        )
        scene["importance"] = "medium"
        scene["target_duration_seconds"] = max(32, len(script_cuts) * 8)
        scene["estimated_duration_seconds"] = max(32, len(script_cuts) * 8)
        scene["scene_intent"] = _scene_intent_dict(scene_id)
        scene["scene_generation"] = _scene_generation_dict(scene_id)
        scene["scene_event"] = _scene_event_dict(scene_id)
        scene["scene_character_state_timeline"] = scene_character_state_timeline
        scene["scene_film_coverage_plan"] = scene_film_coverage_plan
        scene["scene_cut_coverage_plan"] = _preview_scene_cut_coverage_plan(scene_id, len(script_cuts), selectors=[str(item) for item in active_selectors])
        scene["scene_composite_review"] = {"status": "passed", "scene_obligation_covered_by_cut_group": True, "no_duplicate_story_fact_without_new_evidence": True, "scene_meaning_visualized_across_cuts": True, "blocking_reason_keys": []}

    filler_scene_id = 900
    while total_duration < 300:
        filler_cuts = []
        manifest_cuts = []
        for cut_id in (1, 2, 3, 4):
            total_duration += 15
            manifest_cuts.append(
                {
                    "cut_id": cut_id,
                    "cut_contract": _preview_cut_contract(filler_scene_id, cut_id, label="filler preview"),
                    "scene_contract": {"target_beat": "filler preview", "must_show": ["filler preview"], "must_avoid": [], "done_when": ["filler preview is visible"]},
                    "image_generation": {
                        "tool": "codex_builtin_image",
                        "prompt": "画面内テキストなし。filler preview が見える。実写映画風の道、人物、背景、光、空気感、足元の動き、衣装の布目、地面の質感、前景の小物、中景の人物、背景の奥行き、自然な影が具体的に見える。",
                        "character_ids": [],
                        "object_ids": [],
                        "output": f"assets/scenes/scene{filler_scene_id}_cut{cut_id}.png",
                        "review": {"triangulation_review": _preview_triangulation_review()},
                    },
                    "video_generation": {"tool": "kling_3_0", "duration_seconds": 15, "motion_prompt": "人物が進む。", "output": f"assets/videos/scene{filler_scene_id}_cut{cut_id}.mp4"},
                    "audio": {"narration": {"tool": "elevenlabs", "text": "場面が続く。", "output": f"assets/audio/scene{filler_scene_id}_cut{cut_id}.mp3"}},
                    "review": {"triangulation_review": _preview_triangulation_review()},
                }
            )
            filler_cuts.append(
                {
                    "cut_id": cut_id,
                    "selector": f"scene{filler_scene_id}_cut{cut_id}",
                    "cut_contract": _preview_cut_contract(filler_scene_id, cut_id, label="filler preview"),
                    "scene_contract": {"target_beat": "filler preview", "must_show": ["filler preview"], "must_avoid": [], "done_when": ["filler preview is visible"]},
                    "cut_blueprint": {
                        "cut_role": "main",
                        "duration_intent": "standard",
                        "target_beat": "filler preview",
                        "must_show": ["filler preview"],
                        "must_avoid": [],
                        "done_when": ["filler preview is visible"],
                        "visual_beat": "filler preview",
                        "narration_role": "setup",
                        "asset_dependency_hint": {"character_ids": [], "object_ids": [], "location_ids": [], "reusable_still_candidates": []},
                    },
                }
            )
        filler_selectors = [f"scene{filler_scene_id}_cut{cut_id}" for cut_id in (1, 2, 3, 4)]
        filler_timeline, filler_film_coverage = _scene_emotion_film_dicts(
            filler_scene_id,
            topic="filler preview",
            selectors=filler_selectors,
        )
        scenes.append({"scene_id": filler_scene_id, "scene_intent": _scene_intent_dict(filler_scene_id, topic="filler preview"), "scene_generation": _scene_generation_dict(filler_scene_id, topic="filler preview"), "scene_event": _scene_event_dict(filler_scene_id, topic="filler preview"), "scene_character_state_timeline": filler_timeline, "scene_film_coverage_plan": filler_film_coverage, "cuts": manifest_cuts})
        script_scenes.append(
            {
                "scene_id": filler_scene_id,
                "phase": "development",
                "importance": "medium",
                "summary": "尺を満たす filler scene。",
                "target_duration_seconds": 32,
                "estimated_duration_seconds": 32,
                "handoff_to_next_scene": "次へつながる",
                "terminal_resolution": "preview 完了",
                "coverage_review": {
                    "audience_information_covered": True,
                    "visualizable_action_covered": True,
                    "value_shift_visible": True,
                    "causal_turn_visible": True,
                    "scene_specificity_gate_passed": True,
                    "next_scene_connection_checked": True,
                },
                "scene_intent": _scene_intent_dict(filler_scene_id, topic="filler preview"),
                "scene_generation": _scene_generation_dict(filler_scene_id, topic="filler preview"),
                "scene_event": _scene_event_dict(filler_scene_id, topic="filler preview"),
                "scene_character_state_timeline": filler_timeline,
                "scene_film_coverage_plan": filler_film_coverage,
                "scene_cut_coverage_plan": _preview_scene_cut_coverage_plan(filler_scene_id, len(filler_cuts), label="filler preview"),
                "agent_review": {"status": "passed"},
                "cuts": filler_cuts,
            }
        )
        scenes[-1]["importance"] = "medium"
        scenes[-1]["target_duration_seconds"] = 32
        scenes[-1]["estimated_duration_seconds"] = 32
        scenes[-1]["scene_intent"] = _scene_intent_dict(filler_scene_id, topic="filler preview")
        scenes[-1]["scene_generation"] = _scene_generation_dict(filler_scene_id, topic="filler preview")
        scenes[-1]["scene_event"] = _scene_event_dict(filler_scene_id, topic="filler preview")
        scenes[-1]["scene_character_state_timeline"] = filler_timeline
        scenes[-1]["scene_film_coverage_plan"] = filler_film_coverage
        scenes[-1]["scene_cut_coverage_plan"] = _preview_scene_cut_coverage_plan(filler_scene_id, len(manifest_cuts), label="filler preview")
        scenes[-1]["scene_composite_review"] = {"status": "passed", "scene_obligation_covered_by_cut_group": True, "no_duplicate_story_fact_without_new_evidence": True, "scene_meaning_visualized_across_cuts": True, "blocking_reason_keys": []}
        filler_scene_id += 1

    canonical_event_coverage_matrix = _preview_canonical_event_coverage_matrix(
        [scene.get("scene_id", index + 1) for index, scene in enumerate(script_scenes) if isinstance(scene, dict)]
    )
    data["canonical_event_coverage_matrix"] = canonical_event_coverage_matrix
    manifest_path.write_text("```yaml\n" + MODULE.yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "```\n", encoding="utf-8")
    (run_dir / "script.md").write_text(
        "```yaml\n"
        + MODULE.yaml.safe_dump(
            {
                "evaluation_contract": {"target_arc": "development", "must_cover": ["request preview"], "must_avoid": []},
                "canonical_event_coverage_matrix": canonical_event_coverage_matrix,
                "scene_set_review": {"status": "approved"},
                "scene_detail_review": {"status": "approved"},
                "cut_blueprint_review": {"status": "approved"},
                "scenes": script_scenes,
                "script": {
                    "canonical_event_coverage_matrix": canonical_event_coverage_matrix,
                    "scenes": script_scenes,
                },
            },
            allow_unicode=True,
            sort_keys=False,
        )
        + "```\n",
        encoding="utf-8",
    )
    for name in ("scene_set_review.md", "scene_detail_review.md", "cut_blueprint_review.md", "script_review.md"):
        (run_dir / name).write_text("status: passed\n\nreview passed\n", encoding="utf-8")
    (run_dir / "production_readiness_review.md").write_text("status: passed\n\nStructure: ok\nDuration: ok\nQuality: ok\nDesign Owner Patch Brief: ok\n", encoding="utf-8")
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness"):
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        round_dir.mkdir(parents=True, exist_ok=True)
        prompt_dir = round_dir / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        stage_focus = REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE.get(stage, {})
        for index in range(1, 6):
            focus_name = stage_focus.get(index, ("", ""))[0]
            focus_line = f"critic_focus: {focus_name}\n" if focus_name else ""
            (round_dir / f"critic_{index}.md").write_text(f"{focus_line}status: passed\n\ncritic passed\n", encoding="utf-8")
            (prompt_dir / f"critic_{index}.prompt.md").write_text(
                f"Critic focus for this prompt:\n- role: {focus_name}\n" if focus_name else "generic critic\n",
                encoding="utf-8",
            )
        patch = "## Design Owner Patch Brief" if stage == "production_readiness" else "## Generator Patch Brief"
        scene_count_gate = ""
        if stage == "scene_set":
            scene_count_gate = (
                "## Scene Count Gate\n"
                "- maximal_meaningful_stop_condition: no additional independent scene remains\n"
                "- next_scene_candidate: no additional independent scene candidate remains\n"
                "- cut_thickening_reason: additional material repeats the same scene turn\n"
                "- critic_1_scene_count_coverage_resolution: scene_count_coverage passed\n"
                "## Scene Specificity Gate\n"
                "- non_compressible_beat_inventory: approved story beats are inventoried\n"
                "- scene_promotion_rule: every promoted scene has its own question, value shift, and causal turn\n"
                "- unique_scene_responsibility: each scene owns a distinct story obligation\n"
                "- actor_force_coverage: protagonist, opposing/helper, and witness forces are covered where story-relevant\n"
                "- object_meaning_ladder: story objects and setpieces have staged meaning\n"
                "- concrete_handoff_chain: handoff is visible or audible, not narration-only\n"
                "- anti_template_language: banned generic placeholders are absent\n"
                "## Reveal Order Gate\n"
                "- reveal_order_preserved: approved reveal order is preserved\n"
                "- withheld_information_preserved: future-only information remains withheld\n"
                "- early_reveal_risk_resolved: no payoff evidence leaks early\n"
                "## Handoff Chain Gate\n"
                "- handoff_chain_coverage: each scene ending causes the next scene\n"
                "- incoming_outgoing_anchor_ids: concrete anchor ids are present\n"
                "- terminal_resolution_checked: final scene uses terminal_resolution\n"
            )
        elif stage == "scene_detail":
            scene_count_gate = (
                "## Scene Detail Gate\n"
                "- scene_necessity: each scene owns a non-compressible beat\n"
                "- internal_pressure: pressure escalates before the turn\n"
                "- value_shift_visibility: value shift is visible\n"
                "- causal_turn_visibility: causal turn is visible\n"
                "- scene_event_sequence: setup, pressure, turn, and payoff are present\n"
                "- scene_generation_prompt_separation: scene prompt payload excludes downstream execution details\n"
                "- scene_generation_debug_source: source beats and adaptation choices are recorded\n"
                "- scene_generation_contract: required scene outputs are declared\n"
                "- scene_character_state_timeline: start/mid/end visible behavior is present\n"
                "- scene_film_coverage_plan: shot/action-reaction/missing coverage and required_when rules are present\n"
                "- turning_event_alignment: turning_event matches scene_intent.causal_turn\n"
                "- end_situation_alignment: end_situation matches scene_intent.value_shift.to\n"
                "- neighbor_handoff: neighboring handoffs are checked\n"
            )
        elif stage_focus:
            scene_count_gate = (
                "## Cut Blueprint Gate\n"
                "- cut_intent_isolation: passed\n"
                "- scene_event_coverage: passed\n"
                "- event_beat_reference_integrity: passed\n"
                "- first_frame_motion_readiness: passed\n"
                "- event_first_frame_alignment: passed\n"
                "- multimodal_event_boundary_coverage: passed\n"
                "- source_event_preservation: passed\n"
                "- no_unapproved_event_invention: passed\n"
                "- event_motion_boundary: passed\n"
                "- event_narration_boundary: passed\n"
                "- event_context_for_cut_ready: passed\n"
                "- causal_proof_coverage: passed\n"
                "- role_coverage: passed\n"
                "- audience_knowledge_delta_coverage: passed\n"
                "- anti_redundancy_gate: passed\n"
                "- duration_density_and_handoff: passed\n"
                "- coverage_plan_complete: passed\n"
                "- continuity_contract_complete: passed\n"
                "- character_emotion_continuity_complete: passed\n"
                "- film_grammar_contract_complete: passed\n"
                "- action_reaction_and_eyeline_complete: passed\n"
                "- narration_contract_complete: passed\n"
                "- downstream_handoff_complete: passed\n"
                "- triangulation_review_ready: passed\n"
            )
        (round_dir / "aggregated_review.md").write_text(
            "status: passed\n\n## Blocking Findings\nnone\n## Recommended Changes\nnone\n## Rejected Suggestions\nnone\n"
            + scene_count_gate
            + patch
            + "\nnone\n## Round Summary\npassed\n",
            encoding="utf-8",
        )
    with (run_dir / "state.txt").open("a", encoding="utf-8") as f:
        f.write("eval.p400_readiness.status=approved\n---\n")


class TestRequestPreviewPrompt(unittest.TestCase):
    def test_cli_provider_dispatch_gate_rejects_blocking_video_quality_issues(self) -> None:
        payload = {
            "quality_issues": [
                {
                    "code": "video_motion_generated_fallback",
                    "blocking": True,
                }
            ],
            "video_prompt_ir": {
                "quality_issues": [
                    {
                        "code": "video_motion_generated_fallback",
                        "blocking": True,
                    },
                    {
                        "code": "video_motion_unresolved_alternative",
                        "blocking": True,
                    },
                    {
                        "code": "   ",
                        "blocking": True,
                    },
                ]
            },
        }

        self.assertEqual(
            MODULE._blocking_video_prompt_quality_issue_codes(payload),
            [
                "video_motion_generated_fallback",
                "video_motion_unresolved_alternative",
                "video_motion_blocking_quality_issue",
            ],
        )

        with self.assertRaisesRegex(
            RuntimeError,
            r"scene2_unit1.*video_motion_generated_fallback.*video_motion_unresolved_alternative.*video_motion_blocking_quality_issue",
        ):
            MODULE._assert_video_prompt_quality_allows_provider_execution(
                selector="scene2_unit1",
                payload=payload,
            )

        with self.assertRaisesRegex(
            RuntimeError,
            r"scene2_unit1.*video_motion_generated_fallback.*video_motion_unresolved_alternative.*video_motion_blocking_quality_issue",
        ):
            MODULE._dispatch_reviewed_video_provider_call(
                selector="scene2_unit1",
                tool="kling_3_0",
                api_prompt_payload=payload,
                prompt="",
                negative_prompt="",
                input_image=None,
                last_frame_image=None,
                reference_images=[],
                out_path=Path("unused.mp4"),
                log_dir=Path("unused-logs"),
                poll_every=0.1,
                timeout_seconds=1.0,
                force=False,
                dry_run=True,
                gemini_client=None,
                kling_client=None,
                evolink_client=None,
                seedance_client=None,
            )

    def test_cli_materialization_keeps_blocking_video_quality_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: blocking quality evidence
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        video_generation:
          tool: kling_3_0
          motion_prompt: sceneの変化点を見せる
          output: assets/videos/scene1_cut1.mp4
```
""",
                encoding="utf-8",
            )
            _make_p400_ready_for_request_preview(run_dir)
            ready_text = manifest_path.read_text(encoding="utf-8")
            ready_manifest = MODULE.yaml.safe_load(
                MODULE.extract_yaml_block(ready_text)
            )
            ready_manifest["scenes"][0]["cuts"][0]["cut_contract"][
                "motion_contract"
            ]["motion_brief"] = "sceneの変化点を見せる"
            MODULE._write_manifest_yaml_atomic(
                manifest_path=manifest_path,
                original_text=ready_text,
                manifest=ready_manifest,
            )
            common_argv = [
                str(SCRIPT_PATH),
                "--manifest",
                str(manifest_path),
                "--skip-images",
                "--skip-audio",
                "--skip-image-prompt-review",
                "--dry-run",
                "--kling-api-key",
                "test-api-key",
            ]

            with patch.object(MODULE, "load_env_files"), patch.object(
                sys,
                "argv",
                [*common_argv, "--materialize-request-files-only"],
            ):
                MODULE.main()

            manifest = MODULE.yaml.safe_load(
                MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8"))
            )
            payload = manifest["scenes"][0]["cuts"][0]["video_generation"][
                "api_prompt_payload"
            ]
            self.assertIn(
                "video_motion_abstract_primary",
                MODULE._blocking_video_prompt_quality_issue_codes(payload),
            )
            request_path = run_dir / "video_generation_requests.md"
            _approve_video_request_entries(
                request_path,
                [{"selector": "scene1_cut1", "api_prompt_payload": payload}],
            )

            with patch.object(MODULE, "load_env_files"), patch.object(
                MODULE,
                "_dispatch_reviewed_video_provider_call",
            ) as dispatch, patch.object(sys, "argv", common_argv):
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"scene1_cut1.*video_motion_abstract_primary",
                ):
                    MODULE.main()

            dispatch.assert_not_called()

    def test_image_tool_aliases_normalize_to_codex_builtin_image(self) -> None:
        for tool in [
            "google_nanobanana_2",
            "nanobanana_2",
            "gemini_3_1_flash_image",
            "seadream",
            "seedream_4_5",
            "codex_app_server",
            "gpt-image-2",
        ]:
            with self.subTest(tool=tool):
                self.assertEqual(MODULE.normalize_tool_name(tool), "codex_builtin_image")

    def test_generation_requires_p400_readiness_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: production
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "画面内テキストなし。竹林の朝、光る竹、人物、足元の霧が見える。"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())

    def test_p400_readiness_override_is_read_only_diagnostic_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: production
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "画面内テキストなし。竹林の朝、光る竹、人物、足元の霧が見える。"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--ignore-p400-readiness-gate",
                    "--dry-run",
                    "--skip-images",
                    "--skip-videos",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("readiness override diagnostic only", result.stdout)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "asset_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

            materialize_result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--ignore-p400-readiness-gate",
                    "--dry-run",
                    "--skip-images",
                    "--skip-videos",
                    "--skip-audio",
                    "--materialize-request-files-only",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(materialize_result.returncode, 0)
            self.assertIn("read-only diagnostics", materialize_result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

    def test_skeleton_manifest_does_not_materialize_scene_or_video_request_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
          generation_status: planned
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 4
          output: "assets/videos/scene01_1.mp4"
        audio:
          narration:
            tool: "silent"
            text: ""
            tts_text: ""
            silence_contract:
              intentional: true
              kind: "visual_value_hold"
              confirmed_by_human: true
              reason: "draft"
            output: "assets/audio/scene01_1.mp3"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--skip-images",
                    "--skip-videos",
                    "--dry-run",
                    "--skip-image-prompt-review",
                    "--skip-narration-review",
                ],
                check=False,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr)
            self.assertFalse((tmp_path / "image_generation_requests.md").exists())
            self.assertFalse((tmp_path / "video_generation_requests.md").exists())
            self.assertFalse((tmp_path / "generation_exclusion_report.md").exists())

    def test_skeleton_manifest_fails_before_scene_review_can_mutate_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            original_manifest = """# Manifest

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "かぐや姫"
scenes:
  - scene_id: 1
    image_generation:
      tool: "codex_builtin_image"
      prompt: "かぐや姫"
      output: "assets/scenes/scene01.png"
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 4
      output: "assets/videos/scene01.mp4"
    audio:
      narration:
        tool: "silent"
        text: ""
        tts_text: ""
        silence_contract:
          intentional: true
          kind: "visual_value_hold"
          confirmed_by_human: true
          reason: "draft"
        output: "assets/audio/scene01.mp3"
```
"""
            manifest_path.write_text(original_manifest, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--skip-videos",
                    "--dry-run",
                    "--image-prompt-review-fix-character-ids",
                    "--skip-narration-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("p400 readiness gate is not approved", result.stderr + result.stdout)
            self.assertEqual(manifest_path.read_text(encoding="utf-8"), original_manifest)

    def test_rewrites_stateful_character_asset_wording(self) -> None:
        prompt = """[登場人物]
浦島太郎の参照画像（以後のsceneで一貫性を保つため）。

[小道具 / 舞台装置]
参照画像のため背景小道具は置かない。

[連続性]
後続sceneでも顔立ち、髪型、衣装の形、体格比率を変えないための基準画像にする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/characters/urashima.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertIn("浦島太郎のキャラクター基準画像。", rewritten)
        self.assertIn("基準画像のため背景小道具は置かない。", rewritten)
        self.assertIn("顔立ち、髪型、衣装の形、体格比率を読み取れる基準画像にする。", rewritten)
        self.assertNotIn("物語「浦島太郎」", rewritten)
        self.assertNotIn("後続scene", rewritten)
        self.assertNotIn("以後のscene", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_rewrites_reference_usage_for_cut_requests(self) -> None:
        prompt = """[登場人物]
参照画像と完全一致（顔、髪型、衣装、甲羅パターン）。

[小道具 / 舞台装置]
連続性アンカー: 海亀の甲羅の模様、朝の光の方向、波の質感。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene01_cut01.png",
            references=["assets/characters/urashima.png", "assets/characters/turtle.png"],
            topic="浦島太郎",
        )
        self.assertIn("参照画像に写っている顔、髪型、衣装、甲羅パターンをこの場面でも維持する。", rewritten)
        self.assertIn("参照画像に写っている海亀の甲羅の模様、朝の光の方向、波の質感を、この場面の画面内でも維持する。", rewritten)
        self.assertNotIn("この画像は物語", rewritten)
        self.assertNotIn("物語「浦島太郎」", rewritten)
        self.assertNotIn("連続性アンカー", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_removes_nonvisual_story_scene_metadata_from_request_prompt(self) -> None:
        prompt = """[全体 / 不変条件]
物語「シンデレラ」の scene10。実写映画風、横長16:9。

[シーン]
灰の残る古い台所で、シンデレラが暖炉の灰を掃いている。

[連続性]
scene10 の灰の台所と同じ床。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene10_ash_kitchen.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("灰の残る古い台所", rewritten)
        self.assertIn("シンデレラが暖炉の灰を掃いている", rewritten)
        self.assertNotIn("物語「シンデレラ」", rewritten)
        self.assertNotIn("scene10", rewritten)
        self.assertNotIn("[物語の文脈]", rewritten)

    def test_removes_short_story_context_sentence_from_request_prompt(self) -> None:
        prompt = """[物語の文脈]
この画像は物語「シンデレラ」の一場面。

[シーン]
灰の残る古い台所で、シンデレラが暖炉の灰を掃いている。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene10_ash_kitchen.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("灰の残る古い台所", rewritten)
        self.assertNotIn("この画像は物語", rewritten)
        self.assertNotIn("[物語の文脈]", rewritten)

    def test_removes_first_frame_authoring_metadata_from_request_prompt(self) -> None:
        prompt = """[シーン]
この画像は動画の最初の1フレームとして使う。王宮階段の手前にガラスの靴があり、奥で王子が手を伸ばす直前。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene50_cut01.png",
            references=[],
            topic="シンデレラ",
        )
        self.assertIn("王宮階段の手前にガラスの靴", rewritten)
        self.assertNotIn("最初の1フレーム", rewritten)
        self.assertNotIn("1フレーム目", rewritten)

    def test_removes_stateful_next_cut_language_from_request(self) -> None:
        prompt = """[連続性]
この cut 単体で、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。次の cut で太郎が帰りたいと言い出しても不自然にならない感情の橋渡しにする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene08_cut01.png",
            references=["assets/characters/urashima.png"],
            topic="浦島太郎",
        )
        self.assertIn("この画像だけで、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。", rewritten)
        self.assertNotIn("次の cut", rewritten)
        self.assertNotIn("感情の橋渡し", rewritten)

    def test_drops_reference_section_when_references_are_empty(self) -> None:
        prompt = """[シーン]
海底神殿の奥に、まだ動いていない巨大な砂時計がある。

[参照画像の使い方]
参照画像は使わない。

[禁止]
文字なし。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene03_7_cut01.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertNotIn("[参照画像の使い方]", rewritten)
        self.assertNotIn("参照画像は使わない。", rewritten)

    def test_relabels_reference_paths_in_prompt_body(self) -> None:
        prompt = """[参照画像の使い方]
`assets/characters/urashima.png` は顔立ちの基準として使う。`assets/characters/urashima_refstrip.png` は側面確認に使う。`assets/locations/banquet_hall_main.png` は空間構成の基準として使う。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene07_cut01.png",
            references=[
                "assets/characters/urashima.png",
                "assets/characters/urashima_refstrip.png",
                "assets/locations/banquet_hall_main.png",
            ],
            topic="浦島太郎",
        )
        self.assertIn("人物参照画像1", rewritten)
        self.assertIn("人物参照画像2", rewritten)
        self.assertIn("場所参照画像1", rewritten)
        self.assertNotIn("assets/characters/urashima.png", rewritten)
        self.assertNotIn("assets/locations/banquet_hall_main.png", rewritten)

    def test_materialized_requests_include_reuse_and_bridge_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
      - cut_id: 2
        still_image_plan:
          mode: reuse_anchor
          generation_status: recreate
          source: "scene01_cut01"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene01_2.png"
      - cut_id: 3
        still_image_plan:
          mode: no_dedicated_still
          source: "motion chain: scene01_cut01 -> scene02_cut01"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p3"
          output: "assets/scenes/scene01_3.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertTrue((tmp_path / "p000_index.md").exists())
            self.assertIn("## scene1_cut2", request_text)
            self.assertIn("- authoring_role: `video_first_frame_candidate`", request_text)
            self.assertIn("prompt本文には「最初の1フレーム」等を書かず", request_text)
            self.assertIn("- prompt_policy_version: `image_api_prompt_v2`", request_text)
            self.assertTrue((tmp_path / "image_generation_request_snapshot.json").is_file())
            self.assertIn("```debug_prompt_source", request_text)
            self.assertIn("```api_prompt", request_text)
            self.assertNotIn("```text\n[参照画像の使い方]", request_text)
            self.assertIn("- still_mode: `reuse_anchor`", request_text)
            self.assertIn("- generation_status: `recreate`", request_text)
            self.assertIn("- plan_source: `scene01_cut01`", request_text)
            self.assertIn("## scene1_cut3", request_text)
            self.assertIn("- still_mode: `no_dedicated_still`", request_text)
            self.assertIn("motion chain: scene01_cut01 -> scene02_cut01", request_text)

    def test_cut_contract_feeds_image_and_video_prompts_without_motion_leak(self) -> None:
        manifest_yaml = """
video_metadata:
  topic: "シンデレラ"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        cut_contract:
          cut_function: "threshold"
          viewer_contract:
            target_beat: "階段に残された靴へ王子の注意が集まる"
            screen_question: "王子は消えた相手の証拠に気づくのか"
            visual_proof: "前景のガラスの靴と、奥で止まる王子の手"
            must_show: ["ガラスの靴"]
            must_avoid: ["馬車"]
          cinematic_contract:
            subject_priority:
              primary: "ガラスの靴"
              secondary: "王子の手"
            screen_geography:
              foreground: "階段の端の靴"
              midground: "手を伸ばす王子"
              background: "空になった階段"
          first_frame_contract:
            first_frame_brief: "動画が動き出す直前に見えている初期状態。王子の手はまだ靴に触れていない"
          motion_contract:
            motion_brief: "王子の手が靴へゆっくり近づく"
            end_state: "手が靴に触れる直前で止まる"
            must_not_add: ["新しい人物"]
        image_generation:
          tool: "codex_builtin_image"
          prompt: "灰色の城階段。自然な映画照明。"
          output: "assets/scenes/scene01_cut01.png"
        video_generation:
          tool: "kling"
          motion_prompt: "低い位置からゆっくり寄る。"
          output: "assets/videos/scene01_cut01.mp4"
"""
        _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)
        scene = scenes[0]

        image_prompt = MODULE._compose_final_image_prompt(scene, prefix="", suffix="")
        self.assertIn("[このcutの開始状態]", image_prompt)
        self.assertIn("event_time_position:", image_prompt)
        self.assertIn("not_yet_happened_in_still:", image_prompt)
        self.assertIn("[単一瞬間ルール]", image_prompt)
        self.assertIn("[構図]", image_prompt)
        self.assertIn("[動画化のための開始余地]", image_prompt)
        self.assertIn("primary_visual_anchor:", image_prompt)
        self.assertIn("action_completion_state:", image_prompt)
        self.assertIn("motion_ceiling:", image_prompt)
        self.assertIn("ガラスの靴", image_prompt)
        self.assertIn("王子の手はまだ靴に触れていない", image_prompt)
        self.assertIn("灰色の城階段", image_prompt)
        self.assertNotIn("first_frame_visual_plan", image_prompt)
        self.assertNotIn("[cut契約からの可視要件]", image_prompt)
        self.assertNotIn("観客理解の増分:", image_prompt)
        self.assertNotIn("因果の証明:", image_prompt)
        self.assertNotIn("motion_brief", image_prompt)
        self.assertNotIn("王子の手が靴へゆっくり近づく", image_prompt)
        self.assertNotIn("最初の1フレーム", image_prompt)

        api_payload = MODULE._image_api_prompt_payload_for_scene(scene)
        api_prompt = api_payload["prompt"]
        self.assertEqual(api_payload["policy_version"], "image_api_prompt_v2")
        self.assertEqual(api_payload["compiler_version"], "conditional_drawable_prompt_compiler_v3")
        self.assertIn("[シーン]", api_prompt)
        self.assertIn("[場所と構図]", api_prompt)
        self.assertNotIn("[登場人物]", api_prompt)
        self.assertNotIn("[小道具 / 舞台装置]", api_prompt)
        self.assertNotIn("shot_role:", api_prompt)
        self.assertNotIn("shot_scale:", api_prompt)
        self.assertTrue(api_payload["shot_design_contract"]["shot_role"])
        self.assertTrue(api_payload["shot_design_contract"]["shot_scale"])
        if api_payload["shot_design_contract"]["shot_role"] in {"insert", "object_proof"}:
            self.assertTrue(api_payload["shot_design_contract"]["should_show_object_detail"])
        self.assertNotIn("should_show_object_detail:", api_prompt)
        self.assertNotIn("location_zone:", api_prompt)
        self.assertNotIn("this_cut_delta:", api_prompt)
        self.assertNotIn("hand_position:", api_prompt)
        self.assertNotIn("foot_position:", api_prompt)
        self.assertNotIn("object_contact_state:", api_prompt)
        self.assertNotIn("movement_vector_visible_as_static_pose:", api_prompt)
        self.assertNotIn("手元に緊張が読める", api_prompt)
        self.assertNotIn("足先と重心が次の動きに向く", api_prompt)
        self.assertIn("場所", api_prompt)
        self.assertNotIn("source_event_beat_id", api_prompt)
        self.assertNotIn("event_time_position", api_prompt)
        self.assertNotIn("what_happens", api_prompt)
        self.assertNotIn("visible_action", api_prompt)
        self.assertNotIn("first_frame_visual_plan", api_prompt)
        self.assertNotIn("cut_contract", api_prompt)
        self.assertNotIn("scene_event", api_prompt)
        self.assertNotIn("validation_gates", api_prompt)
        self.assertNotIn("追加の具体描写", api_prompt)
        self.assertNotIn("motion_brief", api_prompt)
        self.assertNotIn("王子の手が靴へゆっくり近づく", api_prompt)
        self.assertIn("drawable_prompt_ir", api_payload)

        video_prompt = MODULE._compose_final_video_prompt(scene, prefix="", suffix="")
        self.assertIn("王子の手が靴へゆっくり近づく", video_prompt)
        self.assertIn("手が靴に触れる直前で止まる", video_prompt)
        self.assertIn("低い位置からゆっくり寄る。", video_prompt)
        self.assertIn("単一の連続ショット", video_prompt)
        self.assertNotIn("cut_contract", video_prompt)
        self.assertNotIn("cut_function:", video_prompt)
        self.assertNotIn("target_beat:", video_prompt)
        self.assertNotIn("motion_brief:", video_prompt)
        self.assertNotIn("end_state:", video_prompt)

        video_payload = MODULE._video_api_prompt_payload_for_scene(scene, prefix="", suffix="")
        self.assertEqual(video_payload["policy_version"], "video_api_prompt_v1")
        self.assertEqual(video_payload["compiler_version"], "conditional_video_prompt_compiler_v3")
        self.assertEqual(video_payload["prompt"], video_prompt)
        self.assertEqual(len(video_payload["sha256"]), 64)
        self.assertIn("video_prompt_ir", video_payload)

    def test_sequential_cut_state_progression_shapes_api_prompt_without_internal_fields(self) -> None:
        manifest_yaml = """
video_metadata:
  topic: "シンデレラ"
scenes:
  - scene_id: 40
    scene_state_progression_plan:
      policy_version: scene_state_progression_v1
      progression_mode: sequential_state_progression
      mode_reason: 乗車から出発までscene内で状態が前進する
      cut_progression_map:
        - cut_selector: scene40_cut04
          progression_position: departure_progress
          first_frame_temporal_role: progressed_state_after_previous_cut
          state_after_previous_cut: シンデレラは馬車の扉に片足をかけている
          state_visible_in_this_cut: 馬車が門前を離れ始め、車輪と月光の道が見える
          must_not_revert_to: 馬車へ乗る前の門前待機へ戻らない
          must_not_advance_beyond: 宮殿到着までは見せない
    cuts:
      - cut_id: 04
        selector: scene40_cut04
        cut_contract:
          cut_function: "spatial_transition"
          cut_state_progression:
            policy_version: cut_state_progression_v1
            progression_mode: sequential_state_progression
            cut_selector: scene40_cut04
            progression_position: departure_progress
            first_frame_temporal_role: progressed_state_after_previous_cut
            state_after_previous_cut: シンデレラは馬車の扉に片足をかけている
            state_visible_in_first_frame: 馬車が門前を離れ始め、車輪と月光の道が見える
            visible_state_delta_from_previous_cut: 乗る前の門前待機ではなく、車輪が道へ向いている
            must_not_revert_to: 馬車へ乗る前の門前待機へ戻らない
            must_not_advance_beyond: 宮殿到着までは見せない
            done_when: [馬車が出発状態へ進んだことが静止画で読める]
          viewer_contract:
            target_beat: "馬車が門前を離れる"
            visual_proof: "車輪と月光の道"
            must_show: ["馬車"]
            must_avoid: ["宮殿到着"]
          cinematic_contract:
            subject_priority:
              primary: "馬車"
              secondary: "月光の道"
            screen_geography:
              foreground: "車輪"
              midground: "馬車の側面"
              background: "門前から続く道"
              screen_direction: "left_to_right"
          first_frame_contract:
            first_frame_brief: "馬車が門前を離れ始め、車輪と月光の道が見える"
            visible_start_state:
              character_state: "馬車に乗った後、出発が始まった状態"
              prop_state: "車輪が道へ向く"
              spatial_state: "門前から宮殿へ続く道"
              emotional_state: "出発の緊張"
              gaze_or_attention: "道の先"
            action_completion_state: "progressed_state"
          motion_contract:
            motion_brief: "馬車がゆっくり走り出す"
            must_not_advance_to_event_beat_ids: []
        image_generation:
          tool: "codex_builtin_image"
          output: "assets/scenes/scene40_cut04.png"
          references: ["assets/characters/cinderella.png", "assets/objects/pumpkin_carriage.png", "assets/locations/gate_road.png"]
          character_ids: ["cinderella_transformed_fullbody"]
          object_ids: ["pumpkin_carriage"]
          location_ids: ["gate_road"]
          prompt: "旧prompt。"
        video_generation:
          tool: "kling"
          motion_prompt: "馬車が道へ出る。"
"""
        _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)
        api_prompt = MODULE._image_api_prompt_payload_for_scene(scenes[0])["prompt"]

        self.assertIn("馬車が門前を離れ始め", api_prompt)
        self.assertIn("車輪", api_prompt)
        self.assertIn("月光の道", api_prompt)
        self.assertIn("[現在の状態差分]", api_prompt)
        self.assertIn("現在の画面では", api_prompt)
        self.assertNotIn("progressed_state", api_prompt)
        self.assertNotIn("must_not_repeat", api_prompt)
        self.assertNotIn("馬車へ乗る前の門前待機へ戻らない", api_prompt)
        self.assertNotIn("scene_state_progression_plan", api_prompt)
        self.assertNotIn("cut_state_progression", api_prompt)
        self.assertNotIn("first_frame_visual_plan", api_prompt)
        self.assertNotIn("motion_brief", api_prompt)
        self.assertNotIn("still_must_not_show: 行為完了後、後続reveal、次sceneの結果。", api_prompt)

    def test_recreate_archives_existing_image_to_test_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "assets" / "scenes" / "scene01_1.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"old-image")

            MODULE._archive_existing_image_for_recreate(
                out_path=image_path,
                base_dir=tmp_path,
                test_image_dir="assets/test",
            )

            self.assertFalse(image_path.exists())
            archived = list((tmp_path / "assets" / "test").glob("scene01_1__recreate_backup_*.png"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), b"old-image")

    def test_resolve_image_reference_paths_uses_archived_self_reference_when_output_was_moved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archived_path = tmp_path / "assets" / "test" / "scene01_cut01__recreate_backup.png"
            archived_path.parent.mkdir(parents=True, exist_ok=True)
            archived_path.write_bytes(b"old-image")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=archived_path,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [archived_path])

    def test_resolve_image_reference_paths_finds_latest_backup_for_missing_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_dir = tmp_path / "assets" / "test"
            archive_dir.mkdir(parents=True, exist_ok=True)
            older = archive_dir / "scene01_cut01__recreate_backup_20260412_100000.png"
            newer = archive_dir / "scene01_cut01__recreate_backup_20260412_110000.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=None,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [newer])

    def test_materialized_requests_include_resolved_asset_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "locations").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/characters/urashima.png",
                "assets/objects/tamatebako.png",
                "assets/locations/banquet_hall_main.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  character_bible:
    - character_id: urashima
      reference_images: ["assets/characters/urashima.png"]
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
  location_bible:
    - location_id: banquet_hall_main
      reference_images: ["assets/locations/banquet_hall_main.png"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          character_ids: ["urashima"]
          object_ids: ["tamatebako"]
          location_ids: ["banquet_hall_main"]
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertTrue((tmp_path / "p000_index.md").exists())
            self.assertIn("`人物参照画像1`: `assets/characters/urashima.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)
            self.assertIn("`場所参照画像1`: `assets/locations/banquet_hall_main.png`", request_text)

    def test_asset_generation_requests_include_bootstrap_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
  experience: "asset_stage"
scenes:
  - scene_id: 0
    still_assets:
      - asset_id: "urashima_seed"
        asset_type: "character_reference"
        source_script_selectors: ["scene1_cut1"]
        output: "assets/characters/urashima_seed.png"
        creation_status: "planned"
        generation_plan:
          required_views: ["front", "side", "back"]
        review:
          status: "pending"
        image_generation:
          tool: "codex_builtin_image"
          execution_lane: "bootstrap_builtin"
          bootstrap_allowed: true
          bootstrap_reason: "no_reference_seed"
          prompt: "浦島太郎の seed"
          output: "assets/characters/urashima_seed.png"
          references: []
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("- tool: `codex_builtin_image`", request_text)
            self.assertNotIn("google_nanobanana_2", request_text)
            self.assertIn("- asset_id: `urashima_seed`", request_text)
            self.assertIn("- asset_type: `character_reference`", request_text)
            self.assertIn("- execution_lane: `bootstrap_builtin`", request_text)
            self.assertIn("- reference_count: `0`", request_text)
            self.assertIn("- review_status: `pending`", request_text)
            self.assertIn("- creation_status: `planned`", request_text)
            self.assertIn("- authoring_role: `reusable_asset_candidate`", request_text)
            self.assertIn("prompt本文には物語タイトルやscene idを書かず", request_text)
            self.assertIn("- prompt_policy_version: `image_api_prompt_v1`", request_text)
            self.assertIn("```api_prompt", request_text)
            self.assertNotIn("```text", request_text)
            self.assertNotIn("```debug_prompt_source", request_text)
            self.assertNotIn("first_frame_visual_plan", request_text)
            self.assertNotIn("source_event_beat_id", request_text)
            self.assertNotIn("このcut", request_text)
            self.assertNotIn("video_first_frame_candidate", request_text)
            self.assertNotIn("最初の1フレーム", request_text)
            self.assertIn("浦島太郎の seed", request_text)
            self.assertIn("- bootstrap_allowed: `true`", request_text)
            self.assertIn("- bootstrap_reason: `no_reference_seed`", request_text)
            self.assertIn("- source_script_selectors:", request_text)
            self.assertIn("  - `scene1_cut1`", request_text)
            self.assertIn("- required_views:", request_text)
            self.assertIn("  - `front`", request_text)
            self.assertIn("  - `side`", request_text)
            self.assertIn("  - `back`", request_text)
            self.assertIn("- output: `assets/characters/urashima_seed.png`", request_text)

    def test_asset_stage_manifest_can_use_noncanonical_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "asset_stage_manifest.md"
            manifest_path.write_text(
                """# Asset Stage Manifest

```yaml
video_metadata:
  topic: "Asset Stage"
  experience: "asset_stage"
scenes:
  - scene_id: 1
    still_assets:
      - asset_id: "seed_asset"
        asset_type: "object_reference"
        output: "assets/objects/seed_asset.png"
        creation_status: "planned"
        image_generation:
          tool: "codex_builtin_image"
          execution_lane: "bootstrap_builtin"
          bootstrap_allowed: true
          prompt: "seed object"
          output: "assets/objects/seed_asset.png"
          references: []
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-videos",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("- asset_id: `seed_asset`", request_text)
            self.assertIn("- authoring_role: `reusable_asset_candidate`", request_text)
            self.assertIn("- prompt_policy_version: `image_api_prompt_v1`", request_text)
            self.assertIn("```api_prompt", request_text)
            self.assertNotIn("```debug_prompt_source", request_text)
            self.assertNotIn("first_frame_visual_plan", request_text)

    def test_reference_asset_generation_uses_compiled_api_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_yaml = """
video_metadata:
  topic: "シンデレラ"
  experience: "asset_stage"
scenes:
  - scene_id: 1
    still_assets:
      - asset_id: "cinderella_seed"
        asset_type: "character_reference"
        output: "assets/characters/cinderella_seed.png"
        image_generation:
          tool: "codex_builtin_image"
          execution_lane: "bootstrap_builtin"
          prompt: "シンデレラの全身参照。後続 scene でも同じ顔を保つ。source_event_beat_id: scene01_event_setup"
          output: "assets/characters/cinderella_seed.png"
          references: []
"""
            _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)
            calls: list[dict] = []
            original_generate = MODULE.generate_codex_builtin_image
            try:
                MODULE.generate_codex_builtin_image = lambda **kwargs: calls.append(kwargs)
                args = type(
                    "Args",
                    (),
                    {
                        "force": True,
                        "dry_run": False,
                        "test_image_dir": "assets/test",
                        "image_size": "1K",
                        "image_prompt_prefix": "",
                        "image_prompt_suffix": "",
                        "character_reference_strip": False,
                        "character_reference_strip_suffix": "_refstrip",
                        "log_prompts": False,
                        "test_image_variants": 0,
                    },
                )()
                MODULE._generate_single_image_scene(
                    scene=scenes[0],
                    base_dir=tmp_path,
                    aspect_ratio="16:9",
                    args=args,
                    char_views=set(),
                    log_dir=tmp_path / "logs",
                    gemini_client=None,
                    seadream_client=None,
                )
            finally:
                MODULE.generate_codex_builtin_image = original_generate

            self.assertEqual(len(calls), 1)
            prompt = calls[0]["prompt"]
            self.assertEqual(calls[0]["prompt_policy_version"], "image_api_prompt_v1")
            self.assertIn("シンデレラの全身参照", prompt)
            self.assertIn("後続画像でも同じ顔を保つ", prompt)
            self.assertNotIn("後続 scene", prompt)
            self.assertNotIn("source_event_beat_id", prompt)

    def test_direct_v2_generation_is_snapshot_bound_and_reuses_only_exact_provenance(self) -> None:
        from server.codex_app_server import ImageGenerationResult
        from toc.image_request_snapshot import (
            materialize_request_snapshot,
            write_request_snapshot_atomic,
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "image_generation_requests.md"
            request_path.write_text("# requests\n", encoding="utf-8")
            prompt = "実写映画調。灰の床と閉じた扉が同じ画面に見える。"
            destination = run_dir / "assets/scenes/scene1_cut1.png"
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                source_artifact=request_path.name,
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "kind": "scene",
                        "destination": "assets/scenes/scene1_cut1.png",
                        "prompt": prompt,
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "conditional_drawable_prompt_compiler_v1",
                        "source_digest": hashlib.sha256(b"source").hexdigest(),
                        "references": [],
                    }
                ],
            )
            write_request_snapshot_atomic(
                run_dir / "image_generation_request_snapshot.json",
                snapshot,
                run_dir=run_dir,
            )
            saved = run_dir / "saved.png"
            saved.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            calls: list[dict] = []

            class FakeClient:
                async def start(self) -> None:
                    return None

                async def stop(self) -> None:
                    return None

                async def generate_image(self, **kwargs):
                    calls.append(kwargs)
                    return ImageGenerationResult(
                        saved_path=saved,
                        revised_prompt=None,
                        status="completed",
                        transcript=[],
                        source="app_server",
                        generation_job_id=kwargs["generation_job_id"],
                        item_id=kwargs["item_id"],
                        turn_id="turn-1",
                        prompt_sha256=hashlib.sha256(kwargs["prompt"].encode("utf-8")).hexdigest(),
                        reference_sha256s=[],
                        image_generation_item_id="image-item-1",
                        image_generation_item_count=1,
                        destination=str(kwargs["output_path"]),
                        provenance_authoritative=True,
                        provenance_policy=kwargs["provenance_policy"],
                    )

            with (
                patch.object(MODULE, "app_server_disabled", return_value=False),
                patch.object(MODULE, "create_codex_app_server_client", return_value=FakeClient()),
                patch.dict(
                    MODULE.os.environ,
                    {"TOC_IMAGE_GEN_GLOBAL_LOCK_DIR": str(run_dir / "locks")},
                    clear=False,
                ),
            ):
                MODULE.generate_codex_builtin_image(
                    prompt=prompt,
                    reference_images=[],
                    out_path=destination,
                    force=False,
                    log_path=None,
                    dry_run=False,
                    run_dir=run_dir,
                    item_id="scene1_cut1",
                    aspect_ratio="16:9",
                    image_size="1K",
                    prompt_policy_version="image_api_prompt_v2",
                    debug_prompt_source={},
                )
                MODULE.generate_codex_builtin_image(
                    prompt=prompt,
                    reference_images=[],
                    out_path=destination,
                    force=False,
                    log_path=None,
                    dry_run=False,
                    run_dir=run_dir,
                    item_id="scene1_cut1",
                    aspect_ratio="16:9",
                    image_size="1K",
                    prompt_policy_version="image_api_prompt_v2",
                    debug_prompt_source={},
                )

            self.assertEqual(len(calls), 1)
            self.assertFalse(calls[0]["allow_generated_images_fallback"])
            self.assertEqual(calls[0]["provenance_policy"], "request_bound_v2")
            log = json.loads(
                sorted((run_dir / "logs/app_server/image_gen").glob("*.json"))[-1].read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(log["requestRevision"], snapshot.request_revision)
            self.assertEqual(log["requestDigest"], snapshot.item("scene1_cut1").request_digest)
            self.assertEqual(log["outputSha256"], hashlib.sha256(saved.read_bytes()).hexdigest())

    def test_direct_v2_generation_fails_before_provider_without_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with (
                patch.object(MODULE, "app_server_disabled", return_value=False),
                patch.object(MODULE, "create_codex_app_server_client") as create_client,
            ):
                with self.assertRaisesRegex(SystemExit, "requires an immutable request snapshot"):
                    MODULE.generate_codex_builtin_image(
                        prompt="実写映画調の灰の台所。",
                        reference_images=[],
                        out_path=run_dir / "assets/scenes/scene1_cut1.png",
                        force=False,
                        log_path=None,
                        dry_run=False,
                        run_dir=run_dir,
                        item_id="scene1_cut1",
                        aspect_ratio="16:9",
                        image_size="1K",
                        prompt_policy_version="image_api_prompt_v2",
                        debug_prompt_source={},
                    )

            create_client.assert_not_called()

    def test_v2_materializer_preserves_manifest_first_frame_visual_plan(self) -> None:
        manifest_yaml = """
video_metadata:
  topic: "plan identity"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan: {mode: generate_still}
        image_generation:
          tool: codex_builtin_image
          output: assets/scenes/scene1_cut1.png
          first_frame_visual_plan:
            schema_version: first_frame_visual_plan_v1
            source_grounding:
              source_event_beat_id: scene01_event_setup
            visual_translation:
              concrete_visible_evidence:
                - source_field: viewer_contract.must_show
                  must_be_drawn_as: half-open coral gate
          api_prompt_payload:
            policy_version: image_api_prompt_v2
            prompt: half-open coral gate under moving water light
"""
        _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)

        plan = MODULE._build_first_frame_visual_plan(scenes[0])

        self.assertEqual(plan, scenes[0].image_first_frame_visual_plan)
        self.assertEqual(
            plan["visual_translation"]["concrete_visible_evidence"][0]["must_be_drawn_as"],
            "half-open coral gate",
        )

    def test_v2_materializer_rejects_frozen_payload_prompt_hash_drift(self) -> None:
        manifest_yaml = """
video_metadata: {topic: hash drift}
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          output: assets/scenes/scene1_cut1.png
          api_prompt_payload:
            policy_version: image_api_prompt_v2
            prompt: drawable prompt changed after compilation
            sha256: deadbeef
"""
        _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)

        with self.assertRaisesRegex(SystemExit, "sha256 does not match prompt"):
            MODULE._image_api_prompt_payload_for_scene(scenes[0])

    def test_v2_materializer_rejects_plan_or_dependency_drift_against_frozen_payload(self) -> None:
        old_plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "閉じた扉の前に朝日が差している"
            },
            "subject_binding": {"primary_subject": {"name": "閉じた扉"}},
            "spatial_composition": {
                "foreground": "石の床",
                "midground": "閉じた扉",
                "background": "暗い部屋",
            },
        }
        payload = MODULE.compile_image_api_prompt_v2(
            first_frame_visual_plan=old_plan,
            location_ids=["old_room"],
        )
        manifest_yaml = """
video_metadata: {topic: frozen payload drift}
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          output: assets/scenes/scene1_cut1.png
          location_ids: [old_room]
"""
        _, _, scenes = MODULE.parse_manifest_yaml_full(manifest_yaml)
        scene = scenes[0]
        scene.image_first_frame_visual_plan = old_plan
        scene.image_api_prompt_payload = payload

        scene.image_first_frame_visual_plan = {
            **old_plan,
            "temporal_boundary": {
                "event_fact_visible_in_still": "開いた扉の奥に人物が立っている"
            },
        }
        with self.assertRaisesRegex(SystemExit, "frozen v2 payload does not match"):
            MODULE._image_api_prompt_payload_for_scene(scene)

        scene.image_first_frame_visual_plan = old_plan
        scene.image_location_ids = ["new_room"]
        with self.assertRaisesRegex(SystemExit, "frozen v2 payload does not match"):
            MODULE._image_api_prompt_payload_for_scene(scene)

    def test_image_generation_requests_include_lane_and_reference_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "characters" / "urashima.png").write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: "generate_still"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浜辺の establishing shot"
          references: []
          output: "assets/scenes/scene1_cut1.png"
      - cut_id: 2
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浦島太郎の中景"
          references:
            - "assets/characters/urashima.png"
          output: "assets/scenes/scene1_cut2.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("## scene1_cut1", request_text)
            self.assertIn("## scene1_cut2", request_text)
            self.assertIn("- tool: `codex_builtin_image`", request_text)
            self.assertNotIn("google_nanobanana_2", request_text)
            self.assertIn("- execution_lane: `bootstrap_builtin`", request_text)
            self.assertIn("- reference_count: `0`", request_text)
            self.assertIn("- execution_lane: `standard`", request_text)
            self.assertIn("- reference_count: `1`", request_text)

    def test_generation_keeps_no_reference_requests_on_bootstrap_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: "generate_still"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "浜辺の establishing shot"
          references: []
          output: "assets/scenes/scene1_cut1.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--dry-run",
                    "--skip-audio",
                    "--skip-videos",
                    "--skip-image-prompt-review",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            self.assertIn("codex_builtin_image", completed.stdout)
            self.assertIn("refs=0", completed.stdout)

    def test_materialized_requests_preserve_explicit_scene_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/scenes/scene01_cut01.png",
                "assets/objects/tamatebako.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          object_ids: ["tamatebako"]
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "参照画像1の構図を維持し、玉手箱だけを直す。"
          output: "assets/scenes/scene01_cut01.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("`参照画像1`: `assets/scenes/scene01_cut01.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)

    def test_request_snapshot_binding_accepts_frozen_self_reference_archive(self) -> None:
        from toc.image_request_snapshot import (
            materialize_request_snapshot,
            write_request_snapshot_atomic,
        )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            destination = run_dir / "assets" / "scenes" / "scene01_cut01.png"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"existing-image")
            prompt = "既存画像を参照して小道具だけを修正する。"
            snapshot = materialize_request_snapshot(
                run_dir,
                kind="scene",
                items=[
                    {
                        "item_id": "scene1_cut1",
                        "kind": "scene",
                        "destination": "assets/scenes/scene01_cut01.png",
                        "prompt": prompt,
                        "prompt_policy_version": "image_api_prompt_v2",
                        "compiler_version": "conditional_drawable_prompt_compiler_v1",
                        "source_digest": hashlib.sha256(b"source").hexdigest(),
                        "references": ["assets/scenes/scene01_cut01.png"],
                    }
                ],
            )
            write_request_snapshot_atomic(
                run_dir / "image_generation_request_snapshot.json",
                snapshot,
                run_dir=run_dir,
            )
            archive = run_dir / "assets" / "test" / "scene01_cut01__recreate_backup.png"
            archive.parent.mkdir(parents=True)
            destination.replace(archive)

            binding = MODULE._direct_request_snapshot_binding(
                run_dir=run_dir,
                item_id="scene1_cut1",
                prompt=prompt,
                destination=destination,
                references=[archive],
                prompt_policy_version="image_api_prompt_v2",
            )

            self.assertIsNotNone(binding)
            self.assertEqual(binding[2], [hashlib.sha256(b"existing-image").hexdigest()])

    def test_build_image_scene_dependencies_tracks_inter_scene_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p2"
          output: "assets/scenes/scene01_cut02.png"
      - cut_id: 3
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          references: []
          prompt: "p3"
          output: "assets/scenes/scene01_cut03.png"
```
""",
                encoding="utf-8",
            )

            metadata, guides, scenes = MODULE.parse_manifest_yaml_full(MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8")))
            deps = MODULE._build_image_scene_dependencies(scenes)

            self.assertEqual(deps["scene1_cut1"], set())
            self.assertEqual(deps["scene1_cut2"], {"scene1_cut1"})
            self.assertEqual(deps["scene1_cut3"], set())

    def test_materialized_requests_include_source_requests_for_image_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 の玉手箱を asset に合わせて直す。"
    resolution_notes: "箱の見た目を黒漆と金意匠に統一"
  - request_id: "hr-002"
    status: verified
    raw_request: "scene1_cut1 の人物を老いた浦島太郎に直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        implementation_trace:
          source_request_ids: ["hr-001", "hr-002"]
          status: implemented
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
          applied_request_ids: ["hr-002", "hr-001"]
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
          applied_request_ids: ["hr-001", "hr-002"]
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertIn("- source_requests:", image_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", image_request_text)
            self.assertIn(
                "`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。 (resolution_notes: 箱の見た目を黒漆と金意匠に統一)",
                image_request_text,
            )
            self.assertLess(image_request_text.index("`hr-002`"), image_request_text.index("`hr-001`"))

            self.assertIn("- source_requests:", video_request_text)
            self.assertIn("`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。", video_request_text)
            self.assertRegex(video_request_text, r"- duration_seconds: `\d+`")
            self.assertIn("- aspect_ratio: `9:16`", video_request_text)
            self.assertIn("- resolution: `1080p`", video_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", video_request_text)
            self.assertLess(video_request_text.index("`hr-001`"), video_request_text.index("`hr-002`"))

    def test_materialized_requests_omit_source_requests_without_applied_request_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 を直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertNotIn("- source_requests:", image_request_text)
            self.assertNotIn("- source_requests:", video_request_text)

    def test_materialized_video_requests_support_render_units_with_source_cuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene03_cut01.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene03_cut01.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n1"
            tts_text: "n1"
            output: "assets/audio/scene03_cut01_narration.mp3"
      - cut_id: 2
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene03_cut02.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m2"
          output: "assets/videos/scene03_cut02.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n2"
            tts_text: "n2"
            output: "assets/audio/scene03_cut02_narration.mp3"
      - cut_id: 3
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p3"
          output: "assets/scenes/scene03_cut03.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m3"
          output: "assets/videos/scene03_cut03.mp4"
        audio:
          narration:
            tool: "elevenlabs"
            text: "n3"
            tts_text: "n3"
            output: "assets/audio/scene03_cut03_narration.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          tool: "kling_3_0_omni"
          duration_seconds: 15
          first_frame: "assets/scenes/scene03_cut01.png"
          motion_prompt: "unit1"
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2, 3]
        video_generation:
          tool: "kling_3_0_omni"
          duration_seconds: 45
          first_frame: "assets/scenes/scene03_cut02.png"
          motion_prompt: "unit2"
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertIn("## scene3_unit1", video_request_text)
            self.assertIn("## scene3_unit2", video_request_text)
            self.assertIn("- source_cuts:", video_request_text)
            self.assertIn("`scene3_cut2`", video_request_text)
            self.assertIn("`scene3_cut3`", video_request_text)
            self.assertNotIn("## scene3_cut3", video_request_text)

    def test_video_request_materialization_binds_frames_refs_and_negative_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            for rel, content in {
                "assets/scenes/scene01_cut01.png": b"first-frame-v1",
                "assets/scenes/scene01_cut01_end.png": b"last-frame-v1",
                "assets/characters/hero.png": b"hero-v1",
                "assets/characters/hero_refstrip.png": b"hero-strip-v1",
                "assets/locations/home.png": b"home-v1",
            }.items():
                path = tmp_path / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        video_generation:
          tool: "seedance"
          quality: "720p"
          aspect_ratio: "4:3"
          references:
            - "assets/characters/hero.png"
            - "assets/characters/hero_refstrip.png"
            - "assets/locations/home.png"
          prompt_authoring_source: "主人公が扉へ一歩進む"
          motion_prompt: "[主動作] 旧コンパイル済み本文"
          output: "assets/videos/scene01_cut01.mp4"
      - cut_id: 2
        image_generation:
          output: "assets/scenes/scene01_cut02.png"
        video_generation:
          tool: "kling_3_0"
          first_frame: "assets/scenes/scene01_cut02.png"
          last_frame: "assets/scenes/scene01_cut02_end.png"
          prompt_authoring_source: "主人公が光へ顔を向ける"
          motion_prompt: "[主動作] 旧コンパイル済み本文2"
          output: "assets/videos/scene01_cut02.mp4"
```
""",
                encoding="utf-8",
            )
            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                    "--dry-run",
                    "--enable-last-frame",
                    "--video-negative-prompt",
                    "霧を追加しない",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "video_generation_requests.md").read_text(
                encoding="utf-8"
            )
            reviewed = MODULE._parse_video_request_artifact(request_text)
            state = MODULE.parse_state_file(tmp_path / "state.txt")
            persisted_manifest = MODULE.yaml.safe_load(
                MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8"))
            )
            persisted_payload = persisted_manifest["scenes"][0]["cuts"][0][
                "video_generation"
            ]["api_prompt_payload"]
            MODULE.append_state_snapshot(
                tmp_path / "state.txt",
                {
                    f"{MODULE._video_prompt_approval_state_prefix(selector)}.status": "approved"
                    for selector in reviewed
                },
            )
            runtime_completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--dry-run",
                    "--skip-images",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                    "--enable-last-frame",
                    "--video-negative-prompt",
                    "霧を追加しない",
                ],
                check=False,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            reviewed["scene1_cut2"]["first_frame"],
            "assets/scenes/scene01_cut02.png",
        )
        self.assertEqual(
            reviewed["scene1_cut2"]["last_frame"],
            "assets/scenes/scene01_cut02_end.png",
        )
        self.assertNotIn("旧コンパイル済み本文", reviewed["scene1_cut1"]["prompt"])
        self.assertIn("霧を追加しない", reviewed["scene1_cut1"]["prompt"])
        self.assertEqual(reviewed["scene1_cut1"]["negative_prompt"], "")
        self.assertIn("霧を追加しない", reviewed["scene1_cut2"]["negative_prompt"])
        self.assertIn("assets/characters/hero_refstrip.png", request_text)
        self.assertIn("assets/locations/home.png", request_text)
        self.assertNotIn("- `人物参照画像1`: `assets/characters/hero.png`", request_text)
        self.assertEqual(reviewed["scene1_cut1"]["quality"], "720p")
        self.assertEqual(reviewed["scene1_cut1"]["resolution"], "720p")
        self.assertEqual(reviewed["scene1_cut1"]["aspect_ratio"], "4:3")
        self.assertEqual(persisted_payload["prompt"], reviewed["scene1_cut1"]["prompt"])
        content_hashes = persisted_payload["provider_request_binding"][
            "execution_options"
        ]["reference_content_sha256"]
        self.assertEqual(
            content_hashes["assets/characters/hero_refstrip.png"],
            hashlib.sha256(b"hero-strip-v1").hexdigest(),
        )
        prefix = MODULE._video_prompt_approval_state_prefix("scene1_cut1")
        self.assertEqual(state[f"{prefix}.status"], "pending")
        self.assertEqual(
            state[f"{prefix}.request_section_sha256"],
            reviewed["scene1_cut1"]["request_section_sha256"],
        )
        self.assertEqual(state[f"{prefix}.prompt_sha256"], persisted_payload["sha256"])
        self.assertEqual(
            runtime_completed.returncode,
            0,
            msg=runtime_completed.stderr,
        )

    def test_dynamic_chain_frame_flag_is_rejected_before_materialization_or_provider_dispatch(self) -> None:
        for extra_args in ([], ["--materialize-request-files-only"]):
            with self.subTest(materializing=bool(extra_args)), patch.object(
                MODULE,
                "load_env_files",
            ), patch.object(
                MODULE,
                "_dispatch_reviewed_video_provider_call",
            ) as dispatch, patch.object(
                sys,
                "argv",
                [
                    str(SCRIPT_PATH),
                    "--manifest",
                    "does-not-need-to-exist.md",
                    "--chain-first-frame-from-prev-video",
                    *extra_args,
                ],
            ):
                with self.assertRaisesRegex(
                    SystemExit,
                    "deprecated and unsupported.*rematerialize and approve",
                ):
                    MODULE.main()
                dispatch.assert_not_called()

    def test_video_request_materialization_omits_last_frame_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          output: "assets/scenes/scene01_cut01.png"
        video_generation:
          tool: "kling_3_0"
          first_frame: "assets/scenes/scene01_cut01.png"
          last_frame: "assets/scenes/scene01_cut01_end.png"
          motion_prompt: "主人公が扉へ一歩進む"
          output: "assets/videos/scene01_cut01.mp4"
```
""",
                encoding="utf-8",
            )
            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )
            reviewed = MODULE._parse_video_request_artifact(
                (tmp_path / "video_generation_requests.md").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(reviewed["scene1_cut1"]["last_frame"], "")

    def test_evolink_extra_payload_cannot_override_reviewed_video_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "protected reviewed fields"):
            MODULE._validate_evolink_video_extra_payload(
                {"prompt": "unreviewed", "sound": True}
            )

    def test_video_request_artifact_round_trips_the_exact_reviewed_provider_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "video_generation_requests.md"
            prompt = "[主動作]\n主人公が扉へ一歩進む。\n\n[禁止]\n単一の連続ショット。"
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            entry = {
                "selector": "scene3_cut1",
                "tool": "kling_3_0",
                "output": "assets/videos/scene3_cut1.mp4",
                "duration_seconds": 8,
                "aspect_ratio": "16:9",
                "resolution": "1080p",
                "first_frame": "assets/scenes/scene3_cut1.png",
                "last_frame": "",
                "references": [],
                "api_prompt_payload": {
                    "policy_version": "video_api_prompt_v1",
                    "compiler_version": "conditional_video_prompt_compiler_v1",
                    "source_digest": "a" * 64,
                    "sha256": prompt_sha256,
                    "prompt": prompt,
                },
                "prompt": prompt,
            }

            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[entry],
            )
            MODULE.append_state_snapshot(
                request_path.parent / "state.txt",
                MODULE._video_prompt_pending_state_updates(
                    request_path=request_path,
                    entries=[entry],
                ),
            )
            with self.assertRaisesRegex(SystemExit, "approval_status"):
                MODULE._validated_video_prompts_from_review_artifact(
                    request_path=request_path,
                    entries=[entry],
                )
            _approve_video_request_entries(request_path, [entry])
            reviewed = MODULE._validated_video_prompts_from_review_artifact(
                request_path=request_path,
                entries=[entry],
            )
            request_text = request_path.read_text(encoding="utf-8")

        self.assertEqual(reviewed, {"scene3_cut1": prompt})
        self.assertIn("```video_prompt", request_text)
        self.assertIn("- compiler_version: `conditional_video_prompt_compiler_v1`", request_text)
        self.assertIn("- source_digest: `" + "a" * 64 + "`", request_text)
        self.assertIn(f"- prompt_sha256: `{prompt_sha256}`", request_text)

    def test_video_request_artifact_rejects_source_drift_without_rewriting_reviewed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "video_generation_requests.md"
            prompt = "[主動作]\n主人公が扉へ一歩進む。"
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            entry = {
                "selector": "scene3_cut1",
                "tool": "kling_3_0",
                "output": "assets/videos/scene3_cut1.mp4",
                "duration_seconds": 8,
                "aspect_ratio": "16:9",
                "resolution": "1080p",
                "first_frame": "assets/scenes/scene3_cut1.png",
                "last_frame": "",
                "references": [],
                "api_prompt_payload": {
                    "policy_version": "video_api_prompt_v1",
                    "compiler_version": "conditional_video_prompt_compiler_v1",
                    "source_digest": "a" * 64,
                    "sha256": prompt_sha256,
                    "prompt": prompt,
                },
                "prompt": prompt,
            }
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[entry],
            )
            _approve_video_request_entries(request_path, [entry])
            reviewed_text = request_path.read_text(encoding="utf-8")
            stale_entry = json.loads(json.dumps(entry, ensure_ascii=False))
            stale_entry["api_prompt_payload"]["source_digest"] = "b" * 64

            with self.assertRaises(SystemExit) as ctx:
                MODULE._validated_video_prompts_from_review_artifact(
                    request_path=request_path,
                    entries=[stale_entry],
                )

            self.assertIn("stale", str(ctx.exception))
            self.assertEqual(request_path.read_text(encoding="utf-8"), reviewed_text)

    def test_video_request_artifact_rejects_reference_or_negative_prompt_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "video_generation_requests.md"
            prompt = "[主動作]\n主人公が扉へ一歩進む。"
            negative_prompt = "新しい人物を追加しない。"
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            entry = {
                "selector": "scene3_cut1",
                "tool": "kling_3_0",
                "output": "assets/videos/scene3_cut1.mp4",
                "duration_seconds": 8,
                "aspect_ratio": "16:9",
                "resolution": "1080p",
                "first_frame": "assets/scenes/scene3_cut1.png",
                "last_frame": "",
                "references": ["assets/characters/hero.png"],
                "api_prompt_payload": {
                    "policy_version": "video_api_prompt_v1",
                    "compiler_version": "conditional_video_prompt_compiler_v1",
                    "source_digest": "a" * 64,
                    "sha256": prompt_sha256,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                },
                "prompt": prompt,
            }
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[entry],
            )
            _approve_video_request_entries(request_path, [entry])
            reviewed_text = request_path.read_text(encoding="utf-8")

            stale_references = json.loads(json.dumps(entry, ensure_ascii=False))
            stale_references["references"] = ["assets/characters/hero_alt.png"]
            with self.assertRaises(SystemExit):
                MODULE._validated_video_prompts_from_review_artifact(
                    request_path=request_path,
                    entries=[stale_references],
                )

            request_path.write_text(
                reviewed_text.replace(negative_prompt, "別のnegative prompt。"),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                MODULE._validated_video_prompts_from_review_artifact(
                    request_path=request_path,
                    entries=[entry],
                )

    def test_video_reference_content_binding_rejects_same_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            reference = base_dir / "assets" / "characters" / "hero.png"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_bytes(b"approved-reference-bytes")
            bound = MODULE._video_execution_options_with_reference_content(
                options={"resolution": "1080p"},
                base_dir=base_dir,
                bindings=["assets/characters/hero.png"],
                stored_payload=None,
                materializing=True,
            )
            stored_payload = {
                "provider_request_binding": {"execution_options": bound}
            }
            reference.write_bytes(b"replaced-at-the-same-path")

            with self.assertRaisesRegex(SystemExit, "reference content changed"):
                MODULE._video_execution_options_with_reference_content(
                    options={"resolution": "1080p"},
                    base_dir=base_dir,
                    bindings=["assets/characters/hero.png"],
                    stored_payload=stored_payload,
                    materializing=False,
                )

    def test_video_provider_input_snapshot_freezes_approved_bytes_and_rejects_pre_copy_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            binding = "assets/characters/hero.png"
            reference = base_dir / binding
            reference.parent.mkdir(parents=True, exist_ok=True)
            approved_bytes = b"approved-reference-bytes"
            reference.write_bytes(approved_bytes)
            payload = {
                "provider_request_binding": {
                    "first_frame": "",
                    "last_frame": "",
                    "references": [binding],
                    "execution_options": {
                        "reference_content_sha256": {
                            binding: hashlib.sha256(approved_bytes).hexdigest()
                        }
                    },
                }
            }

            snapshot_dir, input_image, last_image, references = (
                MODULE._snapshot_reviewed_video_reference_inputs(
                    base_dir=base_dir,
                    selector="scene1_cut1",
                    api_prompt_payload=payload,
                    input_image=None,
                    last_frame_image=None,
                    reference_images=[reference],
                )
            )
            self.assertIsNotNone(snapshot_dir)
            self.assertIsNone(input_image)
            self.assertIsNone(last_image)
            self.assertNotEqual(references[0], reference)
            self.assertEqual(references[0].read_bytes(), approved_bytes)

            reference.write_bytes(b"swapped-after-validation")
            self.assertEqual(references[0].read_bytes(), approved_bytes)
            MODULE.shutil.rmtree(snapshot_dir, ignore_errors=True)

            with self.assertRaisesRegex(
                SystemExit,
                "reference content changed before provider submission",
            ):
                MODULE._snapshot_reviewed_video_reference_inputs(
                    base_dir=base_dir,
                    selector="scene1_cut1",
                    api_prompt_payload=payload,
                    input_image=None,
                    last_frame_image=None,
                    reference_images=[reference],
                )

    def test_main_dispatch_receives_private_approved_reference_bytes_and_cleans_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            manifest_path = run_dir / "video_manifest.md"
            reference_binding = "assets/characters/hero.png"
            reference = run_dir / reference_binding
            reference.parent.mkdir(parents=True, exist_ok=True)
            approved_bytes = b"approved-main-dispatch-reference"
            reference.write_bytes(approved_bytes)
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: snapshot test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        video_generation:
          tool: seedance
          references:
            - assets/characters/hero.png
          motion_prompt: 主人公が一歩進む
          output: assets/videos/scene1_cut1.mp4
```
""",
                encoding="utf-8",
            )
            _make_p400_ready_for_request_preview(run_dir)
            common_args = [
                "--manifest",
                str(manifest_path),
                "--scene-ids",
                "scene1_cut1",
                "--skip-images",
                "--skip-audio",
                "--skip-image-prompt-review",
                "--ark-seedance-i2v-model",
                "seedance-1-0-lite-i2v-250428",
            ]
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    *common_args,
                    "--materialize-request-files-only",
                    "--dry-run",
                ],
                check=True,
                cwd=REPO_ROOT,
            )
            request_path = run_dir / "video_generation_requests.md"
            persisted_manifest = MODULE.yaml.safe_load(
                MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8"))
            )
            payload = persisted_manifest["scenes"][0]["cuts"][0][
                "video_generation"
            ]["api_prompt_payload"]
            _approve_video_request_entries(
                request_path,
                [{"selector": "scene1_cut1", "api_prompt_payload": payload}],
            )

            captured_paths: list[Path] = []

            def fake_dispatch(**kwargs) -> None:
                provider_references = kwargs["reference_images"]
                self.assertEqual(len(provider_references), 1)
                provider_reference = provider_references[0]
                captured_paths.append(provider_reference)
                self.assertNotEqual(provider_reference, reference)
                self.assertTrue(provider_reference.is_file())
                reference.write_bytes(b"swapped-inside-provider-boundary")
                self.assertEqual(provider_reference.read_bytes(), approved_bytes)

            with patch.object(MODULE, "load_env_files"), patch.object(
                MODULE,
                "_dispatch_reviewed_video_provider_call",
                side_effect=fake_dispatch,
            ) as dispatch, patch.object(
                sys,
                "argv",
                [
                    str(SCRIPT_PATH),
                    *common_args,
                    "--ark-api-key",
                    "test-api-key",
                ],
            ):
                MODULE.main()

            dispatch.assert_called_once()
            self.assertEqual(len(captured_paths), 1)
            self.assertFalse(captured_paths[0].exists())

    def test_video_parser_preserves_canonical_motion_and_per_item_settings(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        video_generation:
          tool: seedance
          quality: 720p
          aspect_ratio: "4:3"
          motion_contract:
            motion_intent: 主人公が窓へ一歩近づく
            camera_motion: カメラはゆっくり寄る
          output: assets/videos/scene01_cut01.mp4
"""
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(
            manifest=MODULE.yaml.safe_load(yaml_text),
            scenes=scenes,
        )

        self.assertTrue(MODULE._video_target_has_prompt_source(targets[0]))
        self.assertEqual(targets[0].video_quality, "720p")
        self.assertEqual(targets[0].video_aspect_ratio, "4:3")
        payload = MODULE._video_api_prompt_payload_for_target(
            targets[0],
            prefix="",
            suffix="",
        )
        self.assertIn("主人公が窓へ一歩近づく", payload["prompt"])
        self.assertIn("カメラはゆっくり寄る", payload["prompt"])
        self.assertEqual(payload["provider_request_binding"]["quality"], "720p")
        self.assertEqual(payload["provider_request_binding"]["aspect_ratio"], "4:3")

    def test_render_unit_explicit_contract_overlays_composed_source_boundaries(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        cut_contract:
          first_frame_contract:
            first_frame_brief: 主人公が扉の前で立ち止まっている
          motion_contract:
            motion_brief: 主人公が扉へ手を伸ばす
            must_not_add: [新しい人物]
          continuity_contract:
            carry_forward_to_next_cut: [主人公の青い外套を変えない]
        video_generation:
          tool: seedance
          duration_seconds: 4
          motion_prompt: 主人公が扉へ手を伸ばす
          output: assets/videos/scene03_cut01.mp4
      - cut_id: 2
        cut_contract:
          motion_contract:
            motion_brief: 主人公が扉を開ける
            end_state: 扉が半分開き、主人公が中を見ている
            must_not_add: [別の場所]
          continuity_contract:
            carry_forward_to_next_cut: [扉の木目を変えない]
        video_generation:
          tool: seedance
          duration_seconds: 4
          motion_prompt: 主人公が扉を開ける
          output: assets/videos/scene03_cut02.mp4
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        cut_contract:
          motion_contract:
            motion_brief: 主人公がためらいを越えて扉を開く
            camera_motion: カメラは胸の高さで固定する
        video_generation:
          tool: seedance
          duration_seconds: 8
          prompt_authoring_source: 主人公がためらいを越えて扉を開く
          output: assets/videos/scene03_unit01.mp4
"""
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(
            manifest=MODULE.yaml.safe_load(yaml_text),
            scenes=scenes,
        )

        contract = MODULE._video_contract_for_target(targets[0])

        self.assertEqual(
            contract["first_frame_contract"]["first_frame_brief"],
            "主人公が扉の前で立ち止まっている",
        )
        self.assertEqual(
            contract["motion_contract"]["motion_brief"],
            "主人公がためらいを越えて扉を開く",
        )
        self.assertEqual(
            contract["motion_contract"]["camera_motion"],
            "カメラは胸の高さで固定する",
        )
        self.assertEqual(
            contract["motion_contract"]["end_state"],
            "扉が半分開き、主人公が中を見ている",
        )
        self.assertEqual(
            contract["motion_contract"]["must_not_add"],
            ["新しい人物", "別の場所"],
        )
        self.assertEqual(
            contract["continuity_contract"]["carry_forward_to_next_cut"],
            ["主人公の青い外套を変えない", "扉の木目を変えない"],
        )

    def test_cut_video_duration_prefers_approved_render_then_generation_then_legacy(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        duration_seconds: 6
        render:
          video_duration_seconds: 12
        video_generation:
          tool: seedance
          duration_seconds: 9
          motion_prompt: 主人公が進む
          output: assets/videos/scene01_cut01.mp4
      - cut_id: 2
        duration_seconds: 6
        video_generation:
          tool: seedance
          duration_seconds: 9
          motion_prompt: 主人公が止まる
          output: assets/videos/scene01_cut02.mp4
      - cut_id: 3
        duration_seconds: 6
        video_generation:
          tool: seedance
          motion_prompt: 主人公が振り返る
          output: assets/videos/scene01_cut03.mp4
"""
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(
            manifest=MODULE.yaml.safe_load(yaml_text),
            scenes=scenes,
        )

        self.assertEqual([scene.duration_seconds for scene in scenes], [12, 9, 6])
        self.assertEqual([target.duration_seconds for target in targets], [12, 9, 6])

    def test_render_unit_duration_is_inferred_from_approved_source_cut_total(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        render: {video_duration_seconds: 4}
        video_generation: {tool: seedance, motion_prompt: one, output: one.mp4}
      - cut_id: 2
        render: {video_duration_seconds: 6}
        video_generation: {tool: seedance, motion_prompt: two, output: two.mp4}
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        video_generation:
          tool: seedance
          prompt_authoring_source: one motion
          output: unit.mp4
"""
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(
            manifest=MODULE.yaml.safe_load(yaml_text),
            scenes=scenes,
        )

        self.assertEqual(targets[0].duration_seconds, 10)

    def test_render_unit_duration_rejects_source_total_mismatch_and_provider_overflow(self) -> None:
        def manifest_for(*, first: int, second: int, unit: int) -> str:
            return f"""
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        render: {{video_duration_seconds: {first}}}
        video_generation: {{tool: seedance, motion_prompt: one, output: one.mp4}}
      - cut_id: 2
        render: {{video_duration_seconds: {second}}}
        video_generation: {{tool: seedance, motion_prompt: two, output: two.mp4}}
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        video_generation:
          tool: seedance
          duration_seconds: {unit}
          prompt_authoring_source: one motion
          output: unit.mp4
"""

        mismatch = manifest_for(first=4, second=6, unit=9)
        _metadata, _guides, mismatch_scenes = MODULE.parse_manifest_yaml_full(mismatch)
        with self.assertRaisesRegex(SystemExit, "must equal source-cut total 10s"):
            MODULE._build_video_render_targets(
                manifest=MODULE.yaml.safe_load(mismatch),
                scenes=mismatch_scenes,
            )

        overflow = manifest_for(first=31, second=30, unit=61)
        _metadata, _guides, overflow_scenes = MODULE.parse_manifest_yaml_full(overflow)
        with self.assertRaisesRegex(SystemExit, "61s exceeds the 60s provider limit"):
            MODULE._build_video_render_targets(
                manifest=MODULE.yaml.safe_load(overflow),
                scenes=overflow_scenes,
            )

    def test_seedance_reference_render_unit_enforces_duration_and_reference_limits(self) -> None:
        def manifest_for(*, duration: int) -> dict:
            first_reference = "assets/scenes/scene1_cut1.png"
            storyboard_reference = "assets/storyboards/scene1_storyboard.png"
            references = [first_reference, storyboard_reference]
            return {
                "video_metadata": {"topic": "test"},
                "scenes": [
                    {
                        "scene_id": 1,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "render": {"video_duration_seconds": duration},
                                "image_generation": {"output": first_reference},
                                "video_generation": {
                                    "tool": "seedance",
                                    "motion_prompt": "source motion",
                                    "output": "assets/videos/source.mp4",
                                },
                            }
                        ],
                        "render_units": [
                            {
                                "unit_id": 1,
                                "source_cut_ids": [1],
                                "storyboard_image": storyboard_reference,
                                "video_input_contract": {
                                    "schema_version": "render_unit_video_input_v1",
                                    "input_mode": "reference_images",
                                    "required_references": references,
                                    "reference_roles": [
                                        {"image_index": 1, "role": "start_state_visual_anchor"},
                                        {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                                    ],
                                },
                                "video_generation": {
                                    "tool": "seedance",
                                    "duration_seconds": duration,
                                    "references": references,
                                    "prompt_authoring_source": "reference motion",
                                    "output": "assets/videos/unit.mp4",
                                    "api_prompt_payload": {
                                        "provider_request_binding": {
                                            "execution_options": {
                                                "model": "seedance-1-0-lite-i2v-250428"
                                            }
                                        }
                                    },
                                },
                            }
                        ],
                    }
                ],
            }

        valid = manifest_for(duration=12)
        valid_text = MODULE.yaml.safe_dump(valid, allow_unicode=True, sort_keys=False)
        _metadata, _guides, valid_scenes = MODULE.parse_manifest_yaml_full(valid_text)
        targets = MODULE._build_video_render_targets(
            manifest=valid,
            scenes=valid_scenes,
        )
        self.assertEqual(targets[0].duration_seconds, 12)

        for duration in (1, 13):
            with self.subTest(duration=duration):
                invalid = manifest_for(duration=duration)
                invalid_text = MODULE.yaml.safe_dump(
                    invalid,
                    allow_unicode=True,
                    sort_keys=False,
                )
                _metadata, _guides, invalid_scenes = MODULE.parse_manifest_yaml_full(
                    invalid_text
                )
                with self.assertRaisesRegex(SystemExit, "outside.*2-12"):
                    MODULE._build_video_render_targets(
                        manifest=invalid,
                        scenes=invalid_scenes,
                    )

        for reference_count in (0, 5):
            with self.subTest(reference_count=reference_count):
                issues = MODULE._video_provider_capability_issues(
                    label="scene1_unit1",
                    tool="seedance",
                    model="seedance-1-0-lite-i2v-250428",
                    input_mode="reference_images",
                    duration_seconds=12,
                    reference_count=reference_count,
                )
                self.assertEqual(len(issues), 1)
                self.assertRegex(
                    issues[0],
                    "reference image count.*outside.*1-4",
                )

    def test_seedance_cut_capabilities_cover_text_image_reference_and_unknown_model(self) -> None:
        def manifest_for(*, mode: str, duration: int, model: str = "") -> dict:
            generation = {
                "tool": "seedance",
                "duration_seconds": duration,
                "motion_prompt": "主人公が一歩進む",
                "output": "assets/videos/scene1_cut1.mp4",
            }
            if mode == "image_to_video":
                generation["first_frame"] = "assets/scenes/scene1_cut1.png"
            elif mode == "reference_images":
                generation["references"] = ["assets/references/hero.png"]
            if model:
                generation["api_prompt_payload"] = {
                    "provider_request_binding": {
                        "execution_options": {"model": model}
                    }
                }
            return {
                "video_metadata": {"topic": "test"},
                "scenes": [
                    {
                        "scene_id": 1,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "render": {"video_duration_seconds": duration},
                                "video_generation": generation,
                            }
                        ],
                    }
                ],
            }

        for mode in ("text_to_video", "image_to_video", "reference_images"):
            for duration in (2, 12):
                with self.subTest(mode=mode, valid_duration=duration):
                    valid = manifest_for(mode=mode, duration=duration)
                    valid_text = MODULE.yaml.safe_dump(
                        valid,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                    _metadata, _guides, valid_scenes = MODULE.parse_manifest_yaml_full(
                        valid_text
                    )
                    self.assertEqual(
                        len(
                            MODULE._build_video_render_targets(
                                manifest=valid,
                                scenes=valid_scenes,
                            )
                        ),
                        1,
                    )
            for duration in (1, 13):
                with self.subTest(mode=mode, invalid_duration=duration):
                    invalid = manifest_for(mode=mode, duration=duration)
                    invalid_text = MODULE.yaml.safe_dump(
                        invalid,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                    _metadata, _guides, invalid_scenes = MODULE.parse_manifest_yaml_full(
                        invalid_text
                    )
                    with self.assertRaisesRegex(SystemExit, "outside.*2-12"):
                        MODULE._build_video_render_targets(
                            manifest=invalid,
                            scenes=invalid_scenes,
                        )

        unknown = manifest_for(
            mode="reference_images",
            duration=8,
            model="seedance-2-experimental",
        )
        unknown_text = MODULE.yaml.safe_dump(
            unknown,
            allow_unicode=True,
            sort_keys=False,
        )
        _metadata, _guides, unknown_scenes = MODULE.parse_manifest_yaml_full(
            unknown_text
        )
        with self.assertRaisesRegex(SystemExit, "no reviewed capability contract"):
            MODULE._build_video_render_targets(
                manifest=unknown,
                scenes=unknown_scenes,
            )

        effective = manifest_for(mode="reference_images", duration=8)
        effective_text = MODULE.yaml.safe_dump(
            effective,
            allow_unicode=True,
            sort_keys=False,
        )
        _metadata, _guides, effective_scenes = MODULE.parse_manifest_yaml_full(
            effective_text
        )
        target = MODULE._build_video_render_targets(
            manifest=effective,
            scenes=effective_scenes,
        )[0]
        MODULE._validate_effective_video_provider_capabilities(
            target=target,
            duration_seconds=8,
            has_first_frame=False,
            has_last_frame=False,
            reference_count=1,
            execution_options={
                "backend": "ark",
                "model": "seedance-1-0-lite-i2v-250428",
            },
        )
        with self.assertRaisesRegex(SystemExit, "no reviewed capability contract"):
            MODULE._validate_effective_video_provider_capabilities(
                target=target,
                duration_seconds=8,
                has_first_frame=False,
                has_last_frame=False,
                reference_count=1,
                execution_options={
                    "backend": "ark",
                    "model": "seedance-2-experimental",
                },
            )
        with self.assertRaisesRegex(SystemExit, "outside.*2-12"):
            MODULE._validate_effective_video_provider_capabilities(
                target=target,
                duration_seconds=13,
                has_first_frame=False,
                has_last_frame=False,
                reference_count=1,
                execution_options={
                    "backend": "ark",
                    "model": "seedance-1-0-lite-i2v-250428",
                },
            )

    def test_cli_render_unit_video_input_contract_matches_server_fail_closed_validation(self) -> None:
        from server import image_gen_app

        first_reference = "assets/scenes/scene1_cut1.png"
        storyboard_reference = "assets/storyboards/scene1_storyboard.png"
        base_manifest = {
            "video_metadata": {"topic": "test"},
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "render": {"video_duration_seconds": 8},
                            "image_generation": {"output": first_reference},
                            "video_generation": {
                                "tool": "seedance",
                                "motion_prompt": "source motion",
                                "output": "assets/videos/source.mp4",
                            },
                        }
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1],
                            "storyboard_image": storyboard_reference,
                            "video_input_contract": {
                                "schema_version": "render_unit_video_input_v1",
                                "input_mode": "reference_images",
                                "required_references": [
                                    first_reference,
                                    storyboard_reference,
                                ],
                                "reference_roles": [
                                    {"image_index": 1, "role": "start_state_visual_anchor"},
                                    {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
                                ],
                            },
                            "video_generation": {
                                "tool": "seedance",
                                "duration_seconds": 8,
                                "references": [
                                    first_reference,
                                    storyboard_reference,
                                ],
                                "prompt_authoring_source": "reference motion",
                                "output": "assets/videos/unit.mp4",
                            },
                        }
                    ],
                }
            ],
        }

        def clone_manifest() -> dict:
            return json.loads(json.dumps(base_manifest))

        valid = clone_manifest()
        valid_text = MODULE.yaml.safe_dump(valid, allow_unicode=True, sort_keys=False)
        _metadata, _guides, valid_scenes = MODULE.parse_manifest_yaml_full(valid_text)
        valid_targets = MODULE._build_video_render_targets(
            manifest=valid,
            scenes=valid_scenes,
        )
        self.assertEqual(len(valid_targets), 1)
        compiled = MODULE._video_api_prompt_payload_for_target(
            valid_targets[0],
            prefix="",
            suffix="",
        )
        self.assertEqual(
            compiled["provider_request_binding"]["reference_roles"],
            base_manifest["scenes"][0]["render_units"][0][
                "video_input_contract"
            ]["reference_roles"],
        )
        self.assertIn("参照画像1は開始状態の基準", compiled["prompt"])
        self.assertNotIn(first_reference, compiled["prompt"])

        invalid_cases: list[tuple[str, str, object]] = []

        wrong_schema = clone_manifest()
        wrong_schema["scenes"][0]["render_units"][0]["video_input_contract"][
            "schema_version"
        ] = "render_unit_video_input_v0"
        invalid_cases.append(("wrong_schema", "unsupported.*schema_version", wrong_schema))

        wrong_mode = clone_manifest()
        wrong_mode["scenes"][0]["render_units"][0]["video_input_contract"][
            "input_mode"
        ] = "first_frame"
        invalid_cases.append(("wrong_mode", "input_mode must be reference_images", wrong_mode))

        missing_roles = clone_manifest()
        missing_roles["scenes"][0]["render_units"][0][
            "video_input_contract"
        ].pop("reference_roles")
        invalid_cases.append(
            ("missing_roles", "reference_roles count must equal", missing_roles)
        )

        duplicate_role_index = clone_manifest()
        duplicate_role_index["scenes"][0]["render_units"][0][
            "video_input_contract"
        ]["reference_roles"][1]["image_index"] = 1
        invalid_cases.append(
            (
                "duplicate_role_index",
                "image_index must be 1-based, consecutive, unique",
                duplicate_role_index,
            )
        )

        unknown_role = clone_manifest()
        unknown_role["scenes"][0]["render_units"][0][
            "video_input_contract"
        ]["reference_roles"][1]["role"] = "unknown_role"
        invalid_cases.append(
            ("unknown_role", "unsupported video reference role", unknown_role)
        )

        reversed_references = clone_manifest()
        reversed_references["scenes"][0]["render_units"][0]["video_generation"][
            "references"
        ] = [storyboard_reference, first_reference]
        invalid_cases.append(
            ("reversed_references", "exactly preserve the ordered", reversed_references)
        )

        mixed_frame_mode = clone_manifest()
        mixed_frame_mode["scenes"][0]["render_units"][0]["video_generation"][
            "first_frame"
        ] = first_reference
        invalid_cases.append(("mixed_frame_mode", "must not combine", mixed_frame_mode))

        missing_storyboard = clone_manifest()
        missing_storyboard_unit = missing_storyboard["scenes"][0]["render_units"][0]
        missing_storyboard_unit["video_input_contract"]["required_references"] = [
            first_reference
        ]
        missing_storyboard_unit["video_generation"]["references"] = [first_reference]
        invalid_cases.append(
            ("missing_storyboard", "storyboard_image must remain", missing_storyboard)
        )

        jointly_tampered_references = clone_manifest()
        jointly_tampered_unit = jointly_tampered_references["scenes"][0][
            "render_units"
        ][0]
        jointly_tampered_pair = [storyboard_reference, first_reference]
        jointly_tampered_unit["video_input_contract"][
            "required_references"
        ] = jointly_tampered_pair
        jointly_tampered_unit["video_generation"][
            "references"
        ] = jointly_tampered_pair
        invalid_cases.append(
            (
                "jointly_tampered_references",
                "canonical ordered first-source/storyboard pair",
                jointly_tampered_references,
            )
        )

        missing_first_source_output = clone_manifest()
        missing_first_source_output["scenes"][0]["cuts"][0].pop(
            "image_generation"
        )
        invalid_cases.append(
            (
                "missing_first_source_output",
                "requires the first source cut image_generation.output",
                missing_first_source_output,
            )
        )

        missing_storyboard_field = clone_manifest()
        missing_storyboard_field["scenes"][0]["render_units"][0].pop(
            "storyboard_image"
        )
        invalid_cases.append(
            (
                "missing_storyboard_field",
                "requires storyboard_image",
                missing_storyboard_field,
            )
        )

        for label, expected_error, invalid in invalid_cases:
            with self.subTest(case=label):
                unit = invalid["scenes"][0]["render_units"][0]
                self.assertEqual(
                    MODULE._render_unit_video_input_issues(
                        selector="scene1_unit1",
                        node=unit,
                    ),
                    image_gen_app._render_unit_video_input_issues(
                        selector="scene1_unit1",
                        node=unit,
                    ),
                )
                invalid_text = MODULE.yaml.safe_dump(
                    invalid,
                    allow_unicode=True,
                    sort_keys=False,
                )
                _metadata, _guides, invalid_scenes = MODULE.parse_manifest_yaml_full(
                    invalid_text
                )
                with self.assertRaisesRegex(SystemExit, expected_error):
                    MODULE._build_video_render_targets(
                        manifest=invalid,
                        scenes=invalid_scenes,
                    )

    def test_reviewed_video_provider_dispatch_uses_bound_per_item_settings(self) -> None:
        common = {
            "prompt": "承認済みの動画プロンプト",
            "negative_prompt": "新しい人物を追加しない",
            "input_image": None,
            "last_frame_image": None,
            "reference_images": [],
            "out_path": Path("assets/videos/test.mp4"),
            "log_dir": Path("logs/providers"),
            "poll_every": 0.1,
            "timeout_seconds": 1.0,
            "force": False,
            "dry_run": True,
            "gemini_client": None,
            "kling_client": None,
            "evolink_client": None,
            "seedance_client": None,
        }

        def payload(
            *,
            backend: str,
            model: str,
            extra_payload: dict | None = None,
            generate_audio: bool = False,
        ) -> dict:
            return {
                "provider_request_binding": {
                    "duration_seconds": 8,
                    "quality": "720p",
                    "aspect_ratio": "4:3",
                    "first_frame": "",
                    "last_frame": "",
                    "references": [],
                    "execution_options": {
                        "backend": backend,
                        "model": model,
                        "extra_payload": extra_payload or {},
                        "generate_audio": generate_audio,
                        "watermark": False,
                    },
                }
            }

        with patch.object(MODULE, "generate_kling_video") as generate:
            MODULE._dispatch_reviewed_video_provider_call(
                selector="scene1_cut1",
                tool="kling_3_0",
                api_prompt_payload=payload(
                    backend="kling",
                    model="reviewed-kling-model",
                    extra_payload={"cfg_scale": 0.4},
                ),
                **common,
            )
            kwargs = generate.call_args.kwargs
            self.assertEqual(kwargs["duration_seconds"], 8)
            self.assertEqual(kwargs["aspect_ratio"], "4:3")
            self.assertEqual(kwargs["resolution"], "720p")
            self.assertEqual(kwargs["model"], "reviewed-kling-model")
            self.assertEqual(kwargs["extra_payload"], {"cfg_scale": 0.4})

        with patch.object(MODULE, "generate_evolink_video") as generate:
            MODULE._dispatch_reviewed_video_provider_call(
                selector="scene2_cut1",
                tool="kling_3_0_omni",
                api_prompt_payload=payload(
                    backend="evolink",
                    model="reviewed-evolink-model",
                    extra_payload={"sound": False},
                ),
                **common,
            )
            kwargs = generate.call_args.kwargs
            self.assertEqual(kwargs["aspect_ratio"], "4:3")
            self.assertEqual(kwargs["resolution"], "720p")
            self.assertEqual(kwargs["model"], "reviewed-evolink-model")
            self.assertEqual(kwargs["extra_payload"], {"sound": False})

        with patch.object(MODULE, "generate_seedance_video") as generate:
            MODULE._dispatch_reviewed_video_provider_call(
                selector="scene3_cut1",
                tool="seedance",
                api_prompt_payload=payload(
                    backend="ark",
                    model="reviewed-seedance-model",
                    extra_payload={"camera_fixed": True},
                    generate_audio=True,
                ),
                **common,
            )
            kwargs = generate.call_args.kwargs
            self.assertEqual(kwargs["aspect_ratio"], "4:3")
            self.assertEqual(kwargs["resolution"], "720p")
            self.assertEqual(kwargs["model"], "reviewed-seedance-model")
            self.assertEqual(kwargs["extra_payload"], {"camera_fixed": True})
            self.assertTrue(kwargs["generate_audio"])
            self.assertFalse(kwargs["watermark"])

        with patch.object(MODULE, "generate_veo_video") as generate:
            MODULE._dispatch_reviewed_video_provider_call(
                selector="scene4_cut1",
                tool="google_veo_3_1",
                api_prompt_payload=payload(
                    backend="gemini",
                    model="reviewed-veo-model",
                ),
                **common,
            )
            kwargs = generate.call_args.kwargs
            self.assertEqual(kwargs["aspect_ratio"], "4:3")
            self.assertEqual(kwargs["resolution"], "720p")
            self.assertEqual(kwargs["model"], "reviewed-veo-model")

    def test_reviewed_kling_video_reuse_requires_exact_request_and_output_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            out_path = run_dir / "assets/videos/scene1_cut1.mp4"
            log_dir = run_dir / "logs/providers"
            calls: list[dict] = []

            def generate(**kwargs) -> None:
                calls.append(kwargs)
                kwargs["out_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["out_path"].write_bytes(b"approved-kling-video")
                kwargs["log_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["log_path"].write_text(
                    json.dumps(
                        {
                            "submit": {"data": {"task_id": "kling-task-1"}},
                            "operation": {"data": {"task_status": "succeed"}},
                        }
                    ),
                    encoding="utf-8",
                )

            payload = {
                "policy_version": MODULE.VIDEO_API_PROMPT_POLICY_VERSION,
                "compiler_version": "test-compiler-v1",
                "source_digest": hashlib.sha256(b"source-a").hexdigest(),
                "provider_request_binding": {
                    "duration_seconds": 8,
                    "quality": "720p",
                    "aspect_ratio": "16:9",
                    "first_frame": "",
                    "last_frame": "",
                    "references": [],
                    "execution_options": {
                        "backend": "kling",
                        "model": "kling-3.0",
                        "extra_payload": {},
                    },
                },
            }
            common = {
                "selector": "scene1_cut1",
                "tool": "kling_3_0",
                "api_prompt_payload": payload,
                "prompt": "承認済みプロンプトA",
                "negative_prompt": "余計な人物を出さない",
                "input_image": None,
                "last_frame_image": None,
                "reference_images": [],
                "out_path": out_path,
                "log_dir": log_dir,
                "poll_every": 0.1,
                "timeout_seconds": 1.0,
                "force": False,
                "dry_run": False,
                "gemini_client": None,
                "kling_client": None,
                "evolink_client": None,
                "seedance_client": None,
            }

            with patch.object(MODULE, "generate_kling_video", side_effect=generate):
                MODULE._dispatch_reviewed_video_provider_call(**common)
                MODULE._dispatch_reviewed_video_provider_call(**common)
                sidecar_path = out_path.with_name(out_path.name + ".provenance.json")
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                with self.assertRaisesRegex(
                    SystemExit,
                    "existing video output provenance does not match the approved request",
                ):
                    MODULE._dispatch_reviewed_video_provider_call(
                        **{**common, "prompt": "承認済みプロンプトB"}
                    )
                sidecar_path.unlink()
                with self.assertRaisesRegex(
                    SystemExit,
                    "existing video output provenance does not match the approved request",
                ):
                    MODULE._dispatch_reviewed_video_provider_call(**common)

            self.assertEqual(len(calls), 1)
            self.assertEqual(sidecar["schema_version"], "video_output_provenance_v1")
            self.assertEqual(
                sidecar["output_sha256"], hashlib.sha256(out_path.read_bytes()).hexdigest()
            )
            self.assertEqual(sidecar["provider_job"]["job_id"], "kling-task-1")

    def test_reviewed_seedance_video_reuse_rejects_changed_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            out_path = run_dir / "assets/videos/scene2_cut1.mp4"
            log_dir = run_dir / "logs/providers"
            calls: list[dict] = []

            def generate(**kwargs) -> None:
                calls.append(kwargs)
                kwargs["out_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["out_path"].write_bytes(b"approved-seedance-video")
                kwargs["log_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["log_path"].write_text(
                    json.dumps(
                        {
                            "submit": {"id": "seedance-task-1"},
                            "task": {"id": "seedance-task-1", "status": "succeeded"},
                        }
                    ),
                    encoding="utf-8",
                )

            payload = {
                "policy_version": MODULE.VIDEO_API_PROMPT_POLICY_VERSION,
                "compiler_version": "test-compiler-v1",
                "source_digest": hashlib.sha256(b"source-b").hexdigest(),
                "provider_request_binding": {
                    "duration_seconds": 8,
                    "quality": "720p",
                    "aspect_ratio": "16:9",
                    "first_frame": "",
                    "last_frame": "",
                    "references": [],
                    "execution_options": {
                        "backend": "ark",
                        "model": "seedance-1-0-pro-250528",
                        "extra_payload": {},
                        "generate_audio": False,
                        "watermark": False,
                    },
                },
            }
            common = {
                "selector": "scene2_cut1",
                "tool": "seedance",
                "api_prompt_payload": payload,
                "prompt": "承認済みSeedanceプロンプト",
                "negative_prompt": "",
                "input_image": None,
                "last_frame_image": None,
                "reference_images": [],
                "out_path": out_path,
                "log_dir": log_dir,
                "poll_every": 0.1,
                "timeout_seconds": 1.0,
                "force": False,
                "dry_run": False,
                "gemini_client": None,
                "kling_client": None,
                "evolink_client": None,
                "seedance_client": None,
            }

            with patch.object(MODULE, "generate_seedance_video", side_effect=generate):
                MODULE._dispatch_reviewed_video_provider_call(**common)
                MODULE._dispatch_reviewed_video_provider_call(**common)
                out_path.write_bytes(b"tampered-video")
                with self.assertRaisesRegex(
                    SystemExit,
                    "existing video output provenance does not match the approved request",
                ):
                    MODULE._dispatch_reviewed_video_provider_call(**common)

            self.assertEqual(len(calls), 1)

    def test_video_generation_paths_must_resolve_inside_the_run_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            run_dir = Path(tmp)
            external_dir = Path(external)
            legitimate = run_dir / "assets/scenes/frame.png"
            legitimate.parent.mkdir(parents=True)
            legitimate.write_bytes(b"frame")
            external_frame = external_dir / "outside.png"
            external_frame.write_bytes(b"outside")
            symlink_dir = run_dir / "assets/escape"
            symlink_dir.parent.mkdir(parents=True, exist_ok=True)
            symlink_dir.symlink_to(external_dir, target_is_directory=True)

            self.assertEqual(
                MODULE._resolve_run_confined_video_path(
                    base_dir=run_dir,
                    maybe_path="assets/scenes/frame.png",
                    selector="scene1_cut1",
                    role="first frame",
                ),
                legitimate,
            )
            invalid_paths = (
                str(external_frame),
                "../outside.png",
                "assets/escape/outside.png",
            )
            for invalid_path in invalid_paths:
                with self.subTest(path=invalid_path), self.assertRaisesRegex(
                    SystemExit,
                    "must be a run-relative path confined to the manifest directory",
                ):
                    MODULE._resolve_run_confined_video_path(
                        base_dir=run_dir,
                        maybe_path=invalid_path,
                        selector="scene1_cut1",
                        role="reference image",
                    )

            payload = {
                "provider_request_binding": {
                    "first_frame": "",
                    "last_frame": "",
                    "references": ["assets/escape/outside.png"],
                    "execution_options": {
                        "reference_content_sha256": {
                            "assets/escape/outside.png": hashlib.sha256(b"outside").hexdigest()
                        }
                    },
                }
            }
            with patch.object(MODULE, "sha256_file") as hash_file, self.assertRaisesRegex(
                SystemExit,
                "must be a run-relative path confined to the manifest directory",
            ):
                MODULE._snapshot_reviewed_video_reference_inputs(
                    base_dir=run_dir,
                    selector="scene1_cut1",
                    api_prompt_payload=payload,
                    input_image=None,
                    last_frame_image=None,
                    reference_images=[symlink_dir / "outside.png"],
                )
            hash_file.assert_not_called()

    def test_seedance_provider_log_redacts_signed_media_url_query_and_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            out_path = run_dir / "scene.mp4"
            log_path = run_dir / "provider.json"
            signed_url = (
                "https://cdn.example.test/video/scene.mp4"
                "?X-Amz-Credential=secret&X-Amz-Signature=top-secret#private"
            )

            class FakeSeedanceClient:
                def build_video_payload(self, **_kwargs):
                    return {"model": "seedance-test"}

                def create_task(self, *, payload):
                    return {"id": "task-1", "upload_url": signed_url, "payload": payload}

                def extract_task_id(self, _submit):
                    return "task-1"

                def poll_task(self, **_kwargs):
                    return {
                        "id": "task-1",
                        "status": "succeeded",
                        "content": {"video_url": signed_url},
                    }

                def is_failed_task(self, _task):
                    return False

                def extract_video_url(self, _task):
                    return signed_url

                def download_to_file(self, *, url, out_path):
                    self.downloaded_url = url
                    out_path.write_bytes(b"video")

            MODULE.generate_seedance_video(
                client=FakeSeedanceClient(),
                model="seedance-test",
                prompt="reviewed prompt",
                duration_seconds=4,
                aspect_ratio="16:9",
                resolution="720p",
                input_image=None,
                last_frame_image=None,
                reference_images=[],
                generate_audio=False,
                watermark=False,
                extra_payload=None,
                out_path=out_path,
                poll_every=0.1,
                timeout_seconds=1.0,
                force=True,
                log_path=log_path,
                dry_run=False,
            )

            persisted = log_path.read_text(encoding="utf-8")
            self.assertIn("https://cdn.example.test/video/scene.mp4", persisted)
            self.assertNotIn("X-Amz-Credential", persisted)
            self.assertNotIn("X-Amz-Signature", persisted)
            self.assertNotIn("top-secret", persisted)
            self.assertNotIn("#private", persisted)

    def test_cli_execution_options_match_server_for_direct_kling_and_seedance(self) -> None:
        from server import image_gen_app

        def target_for(tool: str) -> MODULE.VideoRenderTargetSpec:
            return MODULE.VideoRenderTargetSpec(
                selector="scene1_cut1",
                manifest_scene_id="1",
                unit_id=None,
                source_cut_ids=["1"],
                source_selectors=["scene1_cut1"],
                source_scenes=[],
                video_tool=tool,
                video_input_image="assets/scenes/scene1_cut1.png",
                video_first_frame="assets/scenes/scene1_cut1.png",
                video_last_frame=None,
                video_motion_prompt="主人公が一歩進む",
                video_output="assets/videos/scene1_cut1.mp4",
                video_applied_request_ids=[],
                duration_seconds=8,
                timestamp=None,
            )

        args = MODULE.argparse.Namespace(
            kling_video_model="kling-3.0",
            kling_omni_video_model="kling-3.0-omni",
            evolink_kling_v3_i2v_model="kling-v3-image-to-video",
            evolink_kling_v3_t2v_model="kling-v3-text-to-video",
            evolink_kling_o3_i2v_model="kling-v3-image-to-video",
            evolink_kling_o3_t2v_model="kling-o3-text-to-video",
            ark_seedance_i2v_model="seedance-1-0-lite-i2v-250428",
            ark_seedance_t2v_model="seedance-1-0-pro-250528",
            ark_generate_audio=False,
        )
        with patch.object(image_gen_app, "load_env_files"), patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            for tool in ("kling_3_0", "kling_3_0_omni", "seedance"):
                with self.subTest(tool=tool):
                    actual = MODULE._video_execution_options(
                        target=target_for(tool),
                        args=args,
                        has_first_frame=True,
                        has_reference_images=False,
                        evolink_enabled=False,
                        kling_extra_payload=None,
                        kling_omni_extra_payload=None,
                        ark_extra_payload=None,
                    )
                    expected = image_gen_app._server_video_execution_options(
                        tool=tool,
                        has_first_frame=True,
                    )
                    self.assertEqual(actual, expected)

    def test_cli_seedance_reference_only_request_uses_visual_input_model(self) -> None:
        from server import image_gen_app

        target = MODULE.VideoRenderTargetSpec(
            selector="scene1_cut1",
            manifest_scene_id="1",
            unit_id=None,
            source_cut_ids=["1"],
            source_selectors=["scene1_cut1"],
            source_scenes=[],
            video_tool="seedance",
            video_input_image=None,
            video_first_frame=None,
            video_last_frame=None,
            video_motion_prompt="主人公が一歩進む",
            video_output="assets/videos/scene1_cut1.mp4",
            video_applied_request_ids=[],
            duration_seconds=8,
            timestamp=None,
            video_references=["assets/characters/hero.png"],
        )
        args = MODULE.argparse.Namespace(
            ark_seedance_i2v_model="reviewed-reference-model",
            ark_seedance_t2v_model="text-only-model",
            ark_generate_audio=False,
        )
        with patch.object(image_gen_app, "load_env_files"), patch.dict(
            os.environ,
            {
                "ARK_SEEDANCE_I2V_MODEL": "reviewed-reference-model",
                "ARK_SEEDANCE_T2V_MODEL": "text-only-model",
            },
            clear=True,
        ):
            actual = MODULE._video_execution_options(
                target=target,
                args=args,
                has_first_frame=False,
                has_reference_images=True,
                evolink_enabled=False,
                kling_extra_payload=None,
                kling_omni_extra_payload=None,
                ark_extra_payload=None,
            )
            expected = image_gen_app._server_video_execution_options(
                tool="seedance",
                has_first_frame=False,
                has_reference_images=True,
            )

        self.assertEqual(actual, expected)
        self.assertEqual(actual["model"], "reviewed-reference-model")

    def test_cli_materializes_server_reference_only_render_unit_without_frame_fallback(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        render: {video_duration_seconds: 4}
        image_generation: {output: assets/scenes/scene1_cut1.png}
        video_generation:
          tool: seedance
          duration_seconds: 4
          motion_prompt: 前の場面が動く
          output: assets/videos/scene1_cut1.mp4
  - scene_id: 2
    cuts:
      - cut_id: 1
        render: {video_duration_seconds: 4}
        image_generation: {output: assets/scenes/scene2_cut1.png}
        video_generation:
          tool: seedance
          duration_seconds: 4
          motion_prompt: 主人公が扉へ近づく
          output: assets/videos/scene2_cut1.mp4
      - cut_id: 2
        render: {video_duration_seconds: 4}
        image_generation: {output: assets/scenes/scene2_cut2.png}
        video_generation:
          tool: seedance
          duration_seconds: 4
          motion_prompt: 主人公が扉を開く
          output: assets/videos/scene2_cut2.mp4
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        storyboard_image: assets/storyboards/scene2_storyboard.png
        video_input_contract:
          schema_version: render_unit_video_input_v1
          input_mode: reference_images
          required_references:
            - assets/scenes/scene2_cut1.png
            - assets/storyboards/scene2_storyboard.png
          reference_roles:
            - image_index: 1
              role: start_state_visual_anchor
            - image_index: 2
              role: ordered_storyboard_sequence_guide
        video_generation:
          tool: seedance
          duration_seconds: 8
          references:
            - assets/scenes/scene2_cut1.png
            - assets/storyboards/scene2_storyboard.png
          prompt_authoring_source: 主人公がためらいを越えて扉を開く
          output: assets/videos/scene2_unit1.mp4
"""
        manifest = MODULE.yaml.safe_load(yaml_text)
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(manifest=manifest, scenes=scenes)
        unit = targets[1]

        first_frame, last_frame = MODULE._effective_video_target_frame_paths(
            Path("/tmp/reference-only-run"),
            targets,
            1,
            chain_first_frame_from_prev_video=True,
            enable_last_frame=True,
        )
        execution_options = MODULE._video_execution_options(
            target=unit,
            args=MODULE.argparse.Namespace(
                ark_seedance_i2v_model="seedance-reference-model",
                ark_seedance_t2v_model="seedance-text-model",
                ark_generate_audio=False,
            ),
            has_first_frame=False,
            has_reference_images=True,
            evolink_enabled=False,
            kling_extra_payload=None,
            kling_omni_extra_payload=None,
            ark_extra_payload=None,
        )
        payload = MODULE._video_api_prompt_payload_for_target(
            unit,
            prefix="",
            suffix="",
            first_frame_override=MODULE._video_binding_path(
                Path("/tmp/reference-only-run"), first_frame
            ),
            last_frame_override=MODULE._video_binding_path(
                Path("/tmp/reference-only-run"), last_frame
            ),
            references_override=unit.video_references,
            quality="1080p",
            aspect_ratio="16:9",
            execution_options=execution_options,
        )

        self.assertEqual(unit.video_input_mode, "reference_images")
        self.assertIsNone(first_frame)
        self.assertIsNone(last_frame)
        self.assertEqual(payload["mode"], "reference_to_video")
        self.assertEqual(payload["provider_request_binding"]["first_frame"], "")
        self.assertEqual(
            payload["provider_request_binding"]["references"],
            [
                "assets/scenes/scene2_cut1.png",
                "assets/storyboards/scene2_storyboard.png",
            ],
        )
        self.assertEqual(
            payload["provider_request_binding"]["execution_options"]["model"],
            "seedance-reference-model",
        )

    def test_kling_video_materialization_rejects_auxiliary_references(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        video_generation:
          tool: kling_3_0
          motion_prompt: 主人公が窓へ一歩近づく
          references: [assets/characters/hero.png]
          output: assets/videos/scene01_cut01.mp4
"""
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        with self.assertRaisesRegex(
            SystemExit,
            "reference image count 1.*0-0",
        ):
            MODULE._build_video_render_targets(
                manifest=MODULE.yaml.safe_load(yaml_text),
                scenes=scenes,
            )

    def test_kling_first_frame_does_not_inherit_image_prompt_references(self) -> None:
        yaml_text = """
video_metadata:
  topic: test
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        render:
          video_duration_seconds: 8
        image_generation:
          references:
            - assets/characters/hero.png
            - assets/locations/kitchen.png
          output: assets/scenes/scene1_cut1.png
        video_generation:
          tool: kling_3_0_omni
          first_frame: assets/scenes/scene1_cut1.png
          motion_prompt: 主人公が窓へ一歩近づく
          output: assets/videos/scene1_cut1.mp4
"""
        manifest = MODULE.yaml.safe_load(yaml_text)
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(
            manifest=manifest,
            scenes=scenes,
        )

        self.assertEqual(
            targets[0].source_scenes[0].image_references,
            ["assets/characters/hero.png", "assets/locations/kitchen.png"],
        )
        self.assertEqual(MODULE._video_target_reference_strings(targets[0]), [])
        self.assertEqual(
            MODULE._effective_video_target_reference_strings(
                targets[0],
                prefer_character_refstrips=False,
                character_reference_strip_suffix="_strip.png",
            ),
            [],
        )

    def test_filtered_video_request_materialization_preserves_other_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "video_generation_requests.md"
            original = {
                "selector": "scene1_cut1",
                "tool": "seedance",
                "output": "assets/videos/scene1_cut1.mp4",
                "references": [],
                "prompt": "original prompt",
            }
            replacement = {
                "selector": "scene2_cut1",
                "tool": "seedance",
                "output": "assets/videos/scene2_cut1.mp4",
                "references": [],
                "prompt": "replacement prompt",
            }
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[original],
            )
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[replacement],
                merge_existing_sections=True,
            )
            merged = request_path.read_text(encoding="utf-8")

        self.assertEqual(merged.count("## scene1_cut1"), 1)
        self.assertEqual(merged.count("## scene2_cut1"), 1)
        self.assertIn("original prompt", merged)
        self.assertIn("replacement prompt", merged)

    def test_filtered_render_unit_migration_removes_obsolete_cut_sections_and_revokes_state(self) -> None:
        yaml_text = """
video_metadata: {topic: test}
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        render: {video_duration_seconds: 4}
        video_generation: {tool: seedance, motion_prompt: one, output: one.mp4}
      - cut_id: 2
        render: {video_duration_seconds: 4}
        video_generation: {tool: seedance, motion_prompt: two, output: two.mp4}
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        video_generation:
          tool: seedance
          duration_seconds: 8
          prompt_authoring_source: one motion
          output: unit.mp4
  - scene_id: 2
    cuts:
      - cut_id: 1
        render: {video_duration_seconds: 4}
        video_generation: {tool: seedance, motion_prompt: other, output: other.mp4}
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          tool: seedance
          duration_seconds: 4
          prompt_authoring_source: other motion
          output: other-unit.mp4
"""
        manifest = MODULE.yaml.safe_load(yaml_text)
        _metadata, _guides, scenes = MODULE.parse_manifest_yaml_full(yaml_text)
        targets = MODULE._build_video_render_targets(manifest=manifest, scenes=scenes)
        scene2_target = next(
            target for target in targets if target.selector == "scene2_unit1"
        )
        self.assertFalse(MODULE._video_target_matches_filter(scene2_target, {"1"}))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            request_path = run_dir / "video_generation_requests.md"
            old_entries = [
                {
                    "selector": selector,
                    "tool": "seedance",
                    "output": f"{selector}.mp4",
                    "references": [],
                    "prompt": f"old {selector}",
                }
                for selector in ("scene1_cut1", "scene1_cut2", "scene2_cut1")
            ]
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=old_entries,
            )
            approved_state = {}
            for selector in ("scene1_cut1", "scene1_cut2", "scene2_cut1"):
                prefix = MODULE._video_prompt_approval_state_prefix(selector)
                approved_state.update(
                    {
                        f"{prefix}.status": "approved",
                        f"{prefix}.request_section_sha256": "old-section",
                        f"{prefix}.prompt_sha256": "old-prompt",
                        f"{prefix}.source_digest": "old-source",
                        f"{prefix}.approved_by": "reviewer",
                        f"{prefix}.approved_at": "2026-07-18T00:00:00+09:00",
                    }
                )
            MODULE.append_state_snapshot(run_dir / "state.txt", approved_state)

            obsolete = MODULE._obsolete_video_request_selectors_for_selected_scenes(
                existing_text=request_path.read_text(encoding="utf-8"),
                targets=targets,
                scene_filter={"1"},
            )
            MODULE._write_request_preview_md(
                out_path=request_path,
                title="Video Generation Requests",
                entries=[
                    {
                        "selector": "scene1_unit1",
                        "tool": "seedance",
                        "output": "unit.mp4",
                        "references": [],
                        "prompt": "new unit prompt",
                    }
                ],
                merge_existing_sections=True,
                drop_existing_sections=obsolete,
            )
            MODULE.append_state_snapshot(
                run_dir / "state.txt",
                MODULE._obsolete_video_prompt_state_updates(obsolete),
            )
            merged = request_path.read_text(encoding="utf-8")
            state = MODULE.parse_state_file(run_dir / "state.txt")

        self.assertEqual(obsolete, {"scene1_cut1", "scene1_cut2"})
        self.assertNotIn("## scene1_cut1", merged)
        self.assertNotIn("## scene1_cut2", merged)
        self.assertIn("## scene1_unit1", merged)
        self.assertIn("## scene2_cut1", merged)
        for selector in obsolete:
            prefix = MODULE._video_prompt_approval_state_prefix(selector)
            self.assertEqual(state[f"{prefix}.status"], "revoked")
            self.assertEqual(state[f"{prefix}.request_section_sha256"], "")
            self.assertEqual(state[f"{prefix}.prompt_sha256"], "")
            self.assertEqual(state[f"{prefix}.source_digest"], "")
        scene2_prefix = MODULE._video_prompt_approval_state_prefix("scene2_cut1")
        self.assertEqual(state[f"{scene2_prefix}.status"], "approved")

    def test_validate_human_change_requests_rejects_unknown_applied_request_ids(self) -> None:
        manifest = {
            "human_change_requests": [
                {
                    "request_id": "hr-001",
                    "status": "verified",
                    "raw_request": "scene1_cut1 を直す。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "1",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "implementation_trace": {
                                "source_request_ids": ["hr-001"],
                                "status": "implemented",
                            },
                            "image_generation": {
                                "tool": "codex_builtin_image",
                                "prompt": "p1",
                                "output": "assets/scenes/scene01_cut01.png",
                                "applied_request_ids": ["hr-999"],
                            },
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(SystemExit) as ctx:
            MODULE.validate_human_change_requests(manifest=manifest, scene_filter=None)

        self.assertIn("unknown human_change_request id(s) in image_generation", str(ctx.exception))

    def test_validate_human_change_requests_rejects_unknown_render_unit_request_ids(self) -> None:
        manifest = {
            "human_change_requests": [
                {
                    "request_id": "hr-001",
                    "status": "verified",
                    "raw_request": "scene3_unit2 を直す。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "3",
                    "cuts": [
                        {"cut_id": "1"},
                        {"cut_id": "2"},
                    ],
                    "render_units": [
                        {
                            "unit_id": "2",
                            "source_cut_ids": ["1", "2"],
                            "video_generation": {
                                "tool": "kling_3_0_omni",
                                "motion_prompt": "m",
                                "output": "assets/videos/scene03_cut02.mp4",
                                "applied_request_ids": ["hr-999"],
                            },
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(SystemExit) as ctx:
            MODULE.validate_human_change_requests(manifest=manifest, scene_filter=None)

        self.assertIn("render_units.video_generation", str(ctx.exception))

    def test_scene7_onward_request_prefers_script_visual_beat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            script_path = tmp_path / "script.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "codex_builtin_image"
          prompt: "既存の prompt"
          output: "assets/scenes/scene07_cut01.png"
```
""",
                encoding="utf-8",
            )
            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        visual_beat: "宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
        human_review:
          approved_visual_beat: "竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("```api_prompt", request_text)
            self.assertIn("[シーン]", request_text)
            self.assertNotIn("[この1枚に写る瞬間]", request_text)
            api_prompt = request_text.split("```api_prompt\n", 1)[1].split("\n```", 1)[0]
            self.assertNotIn("hand_position:", api_prompt)
            self.assertIn("hand_position:", request_text)
            self.assertNotIn("[場面の核]", request_text)
            self.assertIn("竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎", request_text)
            self.assertNotIn("既存の prompt", request_text)

    def test_deleted_cuts_are_excluded_from_requests_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 6
    cuts:
      - cut_id: 1
        cut_status: deleted
        deletion_reason: "story removal"
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p1"
          output: "assets/scenes/scene06_cut01.png"
        audio:
          narration:
            tool: "silent"
            text: ""
            output: "assets/audio/scene06_cut01_narration.mp3"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene06_cut01.mp4"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "codex_builtin_image"
          prompt: "p2"
          output: "assets/scenes/scene06_cut02.png"
```
""",
                encoding="utf-8",
            )

            _make_p400_ready_for_request_preview(tmp_path)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("scene6_cut1", request_text)
            self.assertIn("scene6_cut2", request_text)
            self.assertTrue((tmp_path / "p000_index.md").exists())

            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("scene6_cut1", video_request_text)
            self.assertNotIn("scene06_cut01.mp4", video_request_text)

            exclusion_text = (tmp_path / "generation_exclusion_report.md").read_text(encoding="utf-8")
            self.assertIn("scene6_cut1", exclusion_text)
            self.assertIn("story removal", exclusion_text)
            self.assertIn("assets/videos/scene06_cut01.mp4", exclusion_text)
            self.assertIn("assets/audio/scene06_cut01_narration.mp3", exclusion_text)


if __name__ == "__main__":
    unittest.main()
