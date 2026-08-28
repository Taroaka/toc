from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from server import image_gen_app
from toc.semantic_repair_reconciliation import (
    SemanticRepairReconciliationError,
    reconcile_semantic_repair_documents,
)


def _event(beat_id: str, *, action: str, evidence: list[str]) -> dict:
    return {
        "beat_id": beat_id,
        "beat_function": "turn",
        "what_happens": action,
        "visible_action": action,
        "visible_reaction": "主人公が結果を見る",
        "required_visual_evidence": evidence,
        "motion_brief": "主人公が門へ一歩進む",
        "motion_end_state": "主人公が門を越えて止まる",
        "concrete_event": {
            "what_happens": action,
            "visible_action": action,
            "visible_reaction": "主人公が結果を見る",
            "required_visual_evidence": evidence,
        },
        "story_grounding": {
            "source_origin": "canonical_reference",
            "source_story_beat_ids": ["story-beat-1"],
            "source_text_or_summary": action,
            "non_replaceable_elements": [
                {
                    "element_id": "hero",
                    "type": "character",
                    "value": "主人公",
                    "why_non_replaceable": "主人公の選択だから",
                }
            ],
        },
    }


def _cut(selector: str, beat_id: str, *, character_id: str) -> dict:
    source = {
        "primary_event_beat_id": beat_id,
        "source_event_beat_ids": [beat_id],
        "event_beat_function": "turn",
        "event_time_position": "early_action",
        "canonical_source_visible_action": "古い行動",
        "source_visible_action": "古い行動",
        "source_visible_reaction": "古い反応",
        "canonical_source_required_visual_evidence": ["古い証拠"],
        "source_required_visual_evidence": ["古い証拠"],
        "event_facts_to_preserve": ["古い事実"],
        "event_facts_not_to_invent": [],
        "allowed_reveal_info_ids": [],
        "forbidden_reveal_info_ids": [],
        "source_concrete_events": [{"what_happens": "古い事実"}],
        "source_story_grounding": [{"source_origin": "canonical_reference"}],
        "source_non_replaceable_elements": [],
    }
    contract = {
        "source_event_contract": source,
        "event_context_for_cut": {
            "derived_from": [
                "scene_event.event_sequence[]",
                "cut_contract.source_event_contract",
            ],
            "editable": False,
            "primary_event_beat": {"beat_id": beat_id, "visible_action": "古い行動"},
            "source_event_beats": [
                {"beat_id": beat_id, "visible_action": "古い行動"}
            ],
            "neighboring_event_beats": [],
            "forbidden_event_changes": [],
        },
        "asset_dependency": {
            "character_ids_required": [character_id],
            "object_ids_required": [],
            "location_ids_required": ["location-garden"],
            "reusable_anchor_ids": [character_id, "location-garden"],
        },
    }
    return {
        "cut_id": "01",
        "selector": selector,
        "cut_contract": deepcopy(contract),
        "scene_contract": deepcopy(contract),
        "image_generation": {
            "character_ids": [character_id],
            "object_ids": [],
            "location_ids": ["location-garden"],
            "references": [f"assets/characters/{character_id}.png"],
            "first_frame_visual_plan": {
                "schema_version": "first_frame_visual_plan_v1",
                "reference_binding": {
                    "character_references": [
                        {
                            "path": f"assets/characters/{character_id}.png",
                            "target_character_id": character_id,
                            "target_character_name": "主人公",
                        }
                    ]
                },
                "source_grounding": {
                    "visible_action": "古い行動",
                    "visible_reaction": "古い反応",
                },
                "visual_translation": {
                    "concrete_visible_evidence": [
                        {
                            "must_be_drawn_as": "古い証拠",
                            "visible_substitute": "古い証拠",
                        }
                    ]
                },
            },
            "api_prompt_payload": {
                "policy_version": "image_api_prompt_v2",
                "prompt": "古いcompiled prompt",
            },
        },
    }


def _scene(*, character_id: str) -> dict:
    event = _event(
        "scene10-turn",
        action="主人公が月を見て自分で門へ進む",
        evidence=["月", "開いた門", "主人公"],
    )
    return {
        "scene_id": 10,
        "scene_event": {
            "event_sequence": [event],
            "forbidden_event_changes": [],
        },
        "scene_character_state_timeline": {
            "policy_version": "character_emotion_continuity_v1",
            "linked_scene_event_beat_ids": ["scene10-turn"],
            "characters": [
                {
                    "character_id": character_id,
                    "character_name": "主人公",
                    "appearance_asset_ids": [character_id],
                    "start_state": {
                        "emotion": "迷い",
                        "trigger_event_beat_id": "scene10-turn",
                        "visible_proof": {
                            "face": "迷い",
                            "gaze": "月",
                            "posture": "停止",
                            "hands": "胸元",
                            "feet": "門前",
                            "distance": "門まで一歩",
                        },
                    },
                    "midpoint_state": {
                        "emotion": "決意",
                        "trigger_event_beat_id": "scene10-turn",
                        "visible_proof": {
                            "face": "決意",
                            "gaze": "門",
                            "posture": "前傾",
                            "hands": "門へ",
                            "feet": "一歩前",
                            "distance": "門へ近づく",
                        },
                    },
                    "end_state": {
                        "emotion": "選択後",
                        "trigger_event_beat_id": "scene10-turn",
                        "visible_proof": {
                            "face": "選択後",
                            "gaze": "道",
                            "posture": "直立",
                            "hands": "下ろす",
                            "feet": "門内",
                            "distance": "門を越える",
                        },
                    },
                    "emotional_no_return_point": {
                        "event_beat_id": "scene10-turn",
                        "description": "門を越える",
                        "visible_behavior": "一歩進む",
                    },
                }
            ],
        },
        "cuts": [_cut("scene10_cut01", "scene10-turn", character_id=character_id)],
    }


class SemanticRepairReconciliationTests(unittest.TestCase):
    def test_semantic_repair_rejects_invalid_yaml_before_import(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "invalid YAML"):
            image_gen_app._validate_semantic_repair_structured_output(
                relative=Path("video_manifest.md"),
                original_text="# Manifest\n\n```yaml\nrun_variant: {label: test}\n```\n",
                repaired_text="# Manifest\n\n```yaml\nrun_variant: *missing\n```\n",
            )

        image_gen_app._validate_semantic_repair_structured_output(
            relative=Path("video_manifest.md"),
            original_text="# Manifest\n\n```yaml\nrun_variant: {label: test}\n```\n",
            repaired_text=(
                "# Manifest\n\n```yaml\n"
                "run_variant: &variant {label: test}\n"
                "scene_variant: *variant\n"
                "```\n"
            ),
        )

    def test_scene_scope_accepts_its_own_cut_failure_selector(self) -> None:
        self.assertEqual(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene10_cut01",
                scope_entry_ids=["scene:10"],
            ),
            "scene:10",
        )
        self.assertEqual(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene10_cut01.cut_contract.source_event_contract",
                scope_entry_ids=["scene:10"],
            ),
            "scene:10",
        )
        self.assertEqual(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene10.scene_character_state_timeline.characters[主人公]",
                scope_entry_ids=["scene:10"],
            ),
            "scene:10",
        )
        self.assertEqual(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene10.scene_event.event_sequence[*].story_grounding.non_replaceable_elements",
                scope_entry_ids=["scene:10"],
            ),
            "scene:10",
        )
        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene20_cut01",
                scope_entry_ids=["scene:10"],
            )
        )
        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene20.scene_character_state_timeline.characters[主人公]",
                scope_entry_ids=["scene:10"],
            )
        )
        self.assertEqual(
            image_gen_app._semantic_failure_selector_scope_key(
                "story.md:script.scenes[scene_id=3].location.segments[location=閉ざされた扉の前].responsibility",
                scope_entry_ids=["story:foundation"],
                source_artifacts=["story.md"],
            ),
            "story:foundation",
        )
        for malformed in (
            "scene10_cut01/../../scene20",
            "scene10_cut01.scene20.secret",
            "scene10_cut01.scene20_cut01.cut_contract",
            "scene10_cut01.scene20_cut01[location=主人公].responsibility",
            "scene10_cut01[location=主人公]x",
            "scene20.scene_event.event_sequence[*].story_grounding",
            "scene10.scene_event.event_sequence[*]../../scene20",
        ):
            self.assertIsNone(
                image_gen_app._semantic_failure_selector_scope_key(
                    malformed,
                    scope_entry_ids=["scene:10"],
                )
            )

    def test_reconciles_repaired_event_into_script_and_manifest_cuts(self) -> None:
        script = {"scenes": [_scene(character_id="hero-base")]}
        manifest = {"scenes": [deepcopy(script["scenes"][0])]}

        result = reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            cut = document["scenes"][0]["cuts"][0]
            for contract_name in ("cut_contract", "scene_contract"):
                contract = cut[contract_name]
                source = contract["source_event_contract"]
                self.assertEqual(
                    source["canonical_source_visible_action"],
                    "主人公が月を見て自分で門へ進む",
                )
                self.assertEqual(
                    source["canonical_source_required_visual_evidence"],
                    ["月", "開いた門", "主人公"],
                )
                self.assertEqual(
                    contract["event_context_for_cut"]["primary_event_beat"][
                        "visible_action"
                    ],
                    "主人公が月を見て自分で門へ進む",
                )
                self.assertEqual(
                    contract["first_frame_contract"]["event_fact_visible_in_still"],
                    "主人公が月を見て自分で門へ進む",
                )
                self.assertEqual(
                    contract["motion_contract"]["motion_brief"],
                    "主人公が門へ一歩進む",
                )
                self.assertEqual(
                    contract["motion_contract"]["end_state"],
                    "主人公が門を越えて止まる",
                )
            plan = cut["image_generation"]["first_frame_visual_plan"]
            self.assertEqual(
                plan["source_grounding"]["visible_action"],
                "主人公が月を見て自分で門へ進む",
            )
            self.assertEqual(
                [
                    item["must_be_drawn_as"]
                    for item in plan["visual_translation"][
                        "concrete_visible_evidence"
                    ]
                ],
                ["月", "開いた門", "主人公"],
            )
            self.assertNotIn("api_prompt_payload", cut["image_generation"])

        self.assertIn("scene10_cut01", result.changed_cut_selectors)

        before = deepcopy((script, manifest))
        second = reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )
        self.assertEqual((script, manifest), before)
        self.assertEqual(second.changed_cut_selectors, ())

    def test_repairs_deterministic_p400_scene_contracts_from_grounded_sources(self) -> None:
        scene = _scene(character_id="hero-base")
        beat = scene["scene_event"]["event_sequence"][0]
        beat["story_grounding"]["concrete_story_elements"] = [
            {
                "element_id": "gate",
                "element_type": "object",
                "concrete_description": "開いた門",
                "story_function": "causal_bridge",
                "visible_form": "月下の門",
                "appears_in_event_beat_ids": ["scene10-turn"],
            }
        ]
        beat["story_grounding"]["asset_story_function_usage"] = [
            {
                "asset_id": "location-garden",
                "asset_type": "location_reference",
                "story_function_in_scene": "主人公が越える境界",
                "visible_or_hidden": "visible",
            }
        ]
        scene["scene_event"]["turning_event"] = {
            "source_event_beat_id": "stale-payoff",
            "causal_turn_ref": "old.ref",
        }
        scene["scene_intent"] = {"causal_turn": "変化前後の差"}
        character = scene["scene_character_state_timeline"]["characters"][0]
        for state_key in ("start_state", "midpoint_state", "end_state"):
            character[state_key]["visible_proof"] = "主人公が門へ向く"
        character["start_state"]["visible_proof"] = {
            "face": {"emotion": "入れ子の不正値"}
        }
        for contract_name in ("cut_contract", "scene_contract"):
            scene["cuts"][0][contract_name]["viewer_contract"] = {
                "must_show": ["古い物証"]
            }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            projected = document["scenes"][0]
            self.assertEqual(
                projected["scene_event"]["turning_event"]["source_event_beat_id"],
                "scene10-turn",
            )
            self.assertEqual(
                projected["scene_event"]["turning_event"]["causal_turn_ref"],
                "scene_intent.causal_turn",
            )
            self.assertEqual(
                projected["scene_event"]["turning_event"]["irreversible_change"],
                "主人公が月を見て自分で門へ進む",
            )
            self.assertEqual(
                projected["scene_intent"]["causal_turn"],
                "主人公が月を見て自分で門へ進む",
            )
            element = projected["scene_event"]["event_sequence"][0][
                "story_grounding"
            ]["concrete_story_elements"][0]
            self.assertEqual(element["story_function"], "proof")
            for state_key in ("start_state", "midpoint_state", "end_state"):
                proof = projected["scene_character_state_timeline"]["characters"][0][
                    state_key
                ]["visible_proof"]
                self.assertTrue(
                    all(
                        proof.get(field)
                        for field in ("face", "gaze", "posture", "hands", "feet", "distance")
                    )
                )
                self.assertEqual(len(set(proof.values())), 6)
                self.assertTrue(proof["face"].startswith("表情: "))
                self.assertTrue(proof["gaze"].startswith("視線: "))
                self.assertTrue(proof["hands"].startswith("手元: "))
            for contract_name in ("cut_contract", "scene_contract"):
                self.assertEqual(
                    projected["cuts"][0][contract_name]["viewer_contract"][
                        "must_show"
                    ],
                    ["月", "開いた門", "主人公"],
                )

    def test_rebuilds_temporal_and_future_reveal_boundaries(self) -> None:
        scene = _scene(character_id="hero-base")
        pressure = _event(
            "scene10-pressure",
            action="主人公が門の前で立ち止まる",
            evidence=["閉じた門"],
        )
        pressure["beat_function"] = "pressure"
        pressure["story_information_hinted_ids"] = ["門の向こうの光"]
        turn = scene["scene_event"]["event_sequence"][0]
        turn["story_information_revealed_ids"] = ["主人公の決意"]
        payoff = _event(
            "scene10-payoff",
            action="主人公が門を越えて朝日を見る",
            evidence=["朝日"],
        )
        payoff["beat_function"] = "custom_future"
        payoff["story_information_revealed_ids"] = ["門の先の自由"]
        scene["scene_event"]["event_sequence"] = [pressure, turn, payoff]
        cut = scene["cuts"][0]
        cut["image_generation"]["first_frame_visual_plan"][
            "temporal_boundary"
        ] = {
            "not_yet_happened_in_still": ["古い禁止情報"],
            "forbidden_future_event_beat_ids": [],
            "forbidden_future_outcomes": ["古い禁止情報"],
        }
        cut["image_generation"]["first_frame_visual_plan"][
            "motion_affordance"
        ] = {
            "must_not_resolve_in_image": ["古い禁止情報"],
            "motion_ceiling": {
                "must_stop_before_event_beat_ids": [],
                "must_not_complete_outcomes": ["古い禁止情報"],
            },
        }
        for contract_name in ("cut_contract", "scene_contract"):
            contract = cut[contract_name]
            contract["cut_state_progression"] = {
                "progression_mode": "sequential_state_progression",
                "action_completion_state": "progressed_state",
            }
            source = contract["source_event_contract"]
            source["event_beat_function"] = "setup"
            source["event_time_position"] = "before_trigger"
            source["allowed_reveal_info_ids"] = ["古い許可情報"]
            source["forbidden_reveal_info_ids"] = ["古い禁止情報"]
            contract["first_frame_contract"] = {
                "event_time_position": "before_trigger",
                "action_completion_state": "pre_action",
            }
            contract["motion_contract"] = {
                "starts_from_first_frame": True,
                "must_not_advance_to_event_beat_ids": [],
            }
            contract["narration_contract"] = {
                "must_not_explain_visible_action_as_caption": True,
                "narration_event_boundary": "same_event_only",
                "must_not_advance_to_event_beat_ids": [],
            }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            for contract_name in ("cut_contract", "scene_contract"):
                contract = document["scenes"][0]["cuts"][0][contract_name]
                source = contract["source_event_contract"]
                self.assertEqual(source["event_beat_function"], "turn")
                self.assertEqual(source["event_time_position"], "mid_action")
                self.assertEqual(
                    source["allowed_reveal_info_ids"], ["主人公の決意"]
                )
                self.assertEqual(
                    source["forbidden_reveal_info_ids"], ["門の先の自由"]
                )
                self.assertEqual(
                    contract["first_frame_contract"]["event_time_position"],
                    "mid_action",
                )
                self.assertEqual(
                    contract["first_frame_contract"]["action_completion_state"],
                    "progressed_state",
                )
                self.assertEqual(
                    contract["motion_contract"][
                        "must_not_advance_to_event_beat_ids"
                    ],
                    ["scene10-payoff"],
                )
                self.assertEqual(
                    contract["narration_contract"][
                        "must_not_advance_to_event_beat_ids"
                    ],
                    ["scene10-payoff"],
                )
            plan = document["scenes"][0]["cuts"][0]["image_generation"][
                "first_frame_visual_plan"
            ]
            self.assertEqual(
                plan["source_grounding"]["allowed_reveal_info_ids"],
                ["主人公の決意"],
            )
            self.assertEqual(
                plan["source_grounding"]["forbidden_reveal_info_ids"],
                ["門の先の自由"],
            )
            self.assertEqual(
                plan["temporal_boundary"]["forbidden_future_event_beat_ids"],
                ["scene10-payoff"],
            )
            self.assertEqual(
                plan["temporal_boundary"]["not_yet_happened_in_still"],
                ["門の先の自由"],
            )
            self.assertEqual(
                plan["motion_affordance"]["motion_ceiling"][
                    "must_stop_before_event_beat_ids"
                ],
                ["scene10-payoff"],
            )

    def test_primary_beat_is_normalized_into_source_ids(self) -> None:
        scene = _scene(character_id="hero-base")
        for contract_name in ("cut_contract", "scene_contract"):
            scene["cuts"][0][contract_name]["source_event_contract"][
                "source_event_beat_ids"
            ] = []
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            source = document["scenes"][0]["cuts"][0]["cut_contract"][
                "source_event_contract"
            ]
            self.assertEqual(source["source_event_beat_ids"], ["scene10-turn"])

    def test_cut_blueprint_preserves_distinct_motion_for_shared_event_beat(self) -> None:
        scene = _scene(character_id="hero-base")
        first = scene["cuts"][0]
        second = deepcopy(first)
        second["cut_id"] = "02"
        second["selector"] = "scene10_cut02"
        first["cut_blueprint"] = {
            "motion_brief": "主人公が月へ顔を向ける",
            "motion_end_state": "主人公の顔が月を向いて止まる",
            "first_frame_brief": "門前で主人公が月を見上げる静止状態",
            "must_show": ["月光"],
        }
        second["cut_blueprint"] = {
            "motion_brief": "主人公が門へ重心を移す",
            "motion_end_state": "主人公の足先が門を向いて止まる",
            "first_frame_brief": "門前で主人公の足先が前を向く静止状態",
            "must_show": ["門の敷居"],
        }
        scene["cuts"] = [first, second]
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            cuts = document["scenes"][0]["cuts"]
            self.assertEqual(
                [
                    cut["cut_contract"]["motion_contract"]["motion_brief"]
                    for cut in cuts
                ],
                ["主人公が月へ顔を向ける", "主人公が門へ重心を移す"],
            )
            self.assertEqual(
                cuts[0]["cut_contract"]["first_frame_contract"][
                    "first_frame_brief"
                ],
                "門前で主人公が月を見上げる静止状態",
            )
            evidence = cuts[1]["image_generation"][
                "first_frame_visual_plan"
            ]["visual_translation"]["concrete_visible_evidence"]
            self.assertIn(
                "門の敷居", [item["must_be_drawn_as"] for item in evidence]
            )

    def test_promotes_concrete_event_and_refreshes_scene_intent_projections(self) -> None:
        scene = _scene(character_id="hero-base")
        beat = scene["scene_event"]["event_sequence"][0]
        beat["what_happens"] = "古い抽象的な出来事"
        beat["visible_action"] = "古い行動"
        beat["visible_reaction"] = "古い反応"
        beat["required_visual_evidence"] = ["古い証拠"]
        beat["concrete_event"].update(
            {
                "who": ["hero", "gatekeeper"],
                "primary_subject": "hero",
                "where": "moon-gate",
                "what_happens": "主人公が月を見て門を選ぶ",
                "conflict_or_constraint": "門が閉まりかけている",
                "visible_action": "主人公が自分の足で門へ進む",
                "visible_reaction": "門番が道を開ける",
                "immediate_consequence": "主人公の選択が確定する",
                "required_visual_evidence": ["月", "開いた門"],
            }
        )
        scene["scene_event"]["turning_event"] = {
            "source_event_beat_id": "scene10-turn",
            "irreversible_change": "主人公が門を選ぶ",
        }
        scene["scene_intent"] = {
            "story_event_obligations": [
                {
                    "event_id": "scene10-turn",
                    "source_event_beat_id": "scene10-turn",
                    "source_events": ["古い出来事"],
                    "causal_proof": "古い証明",
                    "visual_evidence": ["古い証拠"],
                }
            ],
            "audience_knowledge_delta": {
                "learned_during_scene": [
                    "主人公は自分で進路を選べる",
                    "主人公が門を選んだ後に秘密の鍵が現れたと理解する"
                ],
                "still_unknown_after_scene": ["秘密の鍵"],
                "forbidden_early_reveals": [],
            },
            "audience_knowledge_plan": [
                "秘密の鍵が現れたと理解する",
                "秘密の鍵は主人公の前にあると理解する",
            ],
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            projected_scene = document["scenes"][0]
            projected_beat = projected_scene["scene_event"]["event_sequence"][0]
            self.assertEqual(
                projected_beat["visible_action"],
                "主人公が自分の足で門へ進む",
            )
            self.assertEqual(projected_beat["who"], ["hero", "gatekeeper"])
            self.assertEqual(
                projected_beat["required_roles"], ["hero", "gatekeeper"]
            )
            self.assertEqual(projected_beat["where"], "moon-gate")
            obligation = projected_scene["scene_intent"][
                "story_event_obligations"
            ][0]
            self.assertEqual(
                obligation["visual_evidence"], ["月", "開いた門"]
            )
            self.assertEqual(
                obligation["causal_proof"], "主人公が自分の足で門へ進む"
            )
            learned = projected_scene["scene_intent"][
                "audience_knowledge_delta"
            ]["learned_during_scene"]
            self.assertEqual(learned[0], "主人公は自分で進路を選べる")
            self.assertNotIn("秘密の鍵", learned[1])
            self.assertEqual(
                projected_scene["scene_intent"]["audience_knowledge_plan"],
                [learned[1]],
            )

    def test_reconciles_incoming_handoff_from_previous_scene_boundary(self) -> None:
        first = _scene(character_id="hero-base")
        first["handoff_to_next_scene"] = (
            "閉じた門の外から近づく足音だけを残し、最初のノックは次のsceneに留保する"
        )
        first["scene_intent"] = {
            "handoff_chain": {
                "outgoing": {
                    "visible_or_audible_form": "古い送り出し",
                }
            }
        }

        second = _scene(character_id="hero-base")
        second["scene_id"] = 20
        second["cuts"][0]["selector"] = "scene20_cut01"
        second["scene_intent"] = {
            "story_specificity": {
                "concrete_handoff": {
                    "incoming_trigger": "前sceneですでにノックが鳴った",
                }
            },
            "handoff_notes": {
                "incoming": "前sceneですでにノックが鳴った",
            },
            "handoff_chain": {
                "incoming": {
                    "visible_or_audible_form": "前sceneですでにノックが鳴った",
                }
            },
        }
        expected = (
            "scene10から渡る物理的原因: "
            "閉じた門の外から近づく足音だけを残し、最初のノックは次のsceneに留保する"
        )
        script = {"scenes": [first, second]}
        manifest = {"scenes": [deepcopy(first), deepcopy(second)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            projected = document["scenes"][1]["scene_intent"]
            self.assertEqual(
                projected["story_specificity"]["concrete_handoff"]
                ["incoming_trigger"],
                expected,
            )
            self.assertEqual(projected["handoff_notes"]["incoming"], expected)
            self.assertEqual(
                projected["handoff_chain"]["incoming"]
                ["visible_or_audible_form"],
                expected,
            )
            self.assertEqual(
                document["scenes"][0]["scene_intent"]["handoff_chain"]
                ["outgoing"]["visible_or_audible_form"],
                first["handoff_to_next_scene"],
            )

    def test_preserves_explicit_character_state_and_attention_target(self) -> None:
        scene = _scene(character_id="hero-base")
        beat = scene["scene_event"]["event_sequence"][0]
        beat["concrete_event"].update(
            {
                "visible_action": "主人公が門へ進む",
                "visible_reaction": "門番が振り返る",
                "visible_character_state": {
                    "posture": "片足を門内へ踏み込んだ前傾姿勢",
                    "gaze": "門の先の月明かり",
                },
                "motion_attention_target": "門の敷居",
                "obligation_overrides": {
                    "spatial_transition": {
                        "motion_attention_target": "古い視線対象"
                    }
                },
            }
        )
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            projected = document["scenes"][0]["scene_event"]["event_sequence"][0]
            self.assertEqual(
                projected["visible_character_state"],
                {
                    "posture": "片足を門内へ踏み込んだ前傾姿勢",
                    "gaze": "門の先の月明かり",
                },
            )
            self.assertEqual(projected["motion_attention_target"], "門の敷居")
            self.assertEqual(
                projected["obligation_overrides"]["spatial_transition"]
                ["motion_attention_target"],
                "門の敷居",
            )

    def test_attention_target_prefers_existing_or_primary_before_reaction(self) -> None:
        primary_scene = _scene(character_id="hero-base")
        primary_beat = primary_scene["scene_event"]["event_sequence"][0]
        primary_beat["concrete_event"]["primary_subject"] = "開いた門"
        primary_beat["concrete_event"]["visible_reaction"] = "主人公が結果を見る"
        existing_scene = _scene(character_id="hero-base")
        existing_scene["scene_id"] = 20
        existing_scene["cuts"][0]["selector"] = "scene20_cut01"
        existing_beat = existing_scene["scene_event"]["event_sequence"][0]
        existing_beat["beat_id"] = "scene20-turn"
        existing_beat["motion_attention_target"] = "既存の視線対象"
        for character in existing_scene["scene_character_state_timeline"]["characters"]:
            for state_key in ("start_state", "midpoint_state", "end_state"):
                character[state_key]["trigger_event_beat_id"] = "scene20-turn"
            character["emotional_no_return_point"]["event_beat_id"] = "scene20-turn"
        existing_scene["scene_character_state_timeline"][
            "linked_scene_event_beat_ids"
        ] = ["scene20-turn"]
        for contract_name in ("cut_contract", "scene_contract"):
            source = existing_scene["cuts"][0][contract_name][
                "source_event_contract"
            ]
            source["primary_event_beat_id"] = "scene20-turn"
            source["source_event_beat_ids"] = ["scene20-turn"]
        script = {"scenes": [primary_scene, existing_scene]}
        manifest = {"scenes": deepcopy(script["scenes"])}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            first = document["scenes"][0]["scene_event"]["event_sequence"][0]
            second = document["scenes"][1]["scene_event"]["event_sequence"][0]
            self.assertEqual(first["motion_attention_target"], "開いた門")
            self.assertEqual(second["motion_attention_target"], "既存の視線対象")

    def test_refreshes_symbolic_proof_on_first_event_beat(self) -> None:
        scene = _scene(character_id="hero-base")
        beat = scene["scene_event"]["event_sequence"][0]
        beat["concrete_event"]["primary_subject"] = "hero"
        beat["concrete_event"]["who"] = ["hero", "gatekeeper"]
        beat["concrete_event"]["obligation_overrides"] = {
            "symbolic_proof": {
                "visible_action": "古い行動",
                "visible_reaction": "古い反応",
                "required_visual_evidence": ["古い証拠"],
                "primary_subject": "old-subject",
                "required_roles": ["old-role"],
            }
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            symbolic = document["scenes"][0]["scene_event"]["event_sequence"][0][
                "obligation_overrides"
            ]["symbolic_proof"]
            self.assertEqual(symbolic["visible_action"], "主人公が月を見て自分で門へ進む")
            self.assertEqual(symbolic["visible_reaction"], "主人公が結果を見る")
            self.assertEqual(symbolic["required_visual_evidence"], ["月", "開いた門", "主人公"])
            self.assertEqual(symbolic["primary_subject"], "hero")
            self.assertEqual(symbolic["required_roles"], ["hero", "gatekeeper"])

    def test_removes_only_exact_ungrounded_filler_fields(self) -> None:
        scene = _scene(character_id="hero-base")
        scene["scene_event"]["story_specificity"] = {
            "visual_specificity": {
                "required_elements": ["月", "床や道具に残る痕跡"]
            }
        }
        scene["scene_intent"] = {
            "fallback_evidence": "床や道具に残る痕跡",
            "scene_conflict_engine": {
                "escalation": "主人公が進むが、人物の手元, 床や道具に残る痕跡によって選択へ狭まる"
            }
        }
        scene["semantic_contract"] = {
            "required_visual_evidence": ["門", "助力の発生源", "変化前後の差"]
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            projected = document["scenes"][0]
            self.assertEqual(
                projected["scene_event"]["story_specificity"]
                ["visual_specificity"]["required_elements"],
                ["月"],
            )
            self.assertEqual(projected["scene_intent"]["fallback_evidence"], "")
            self.assertEqual(
                projected["scene_intent"]["scene_conflict_engine"]["escalation"],
                "主人公が進むが、人物の手元, 床や道具に残る痕跡によって選択へ狭まる",
            )
            self.assertEqual(
                projected["semantic_contract"]["required_visual_evidence"],
                ["門"],
            )

    def test_preserves_normal_irreversible_knowledge_without_withheld_collision(self) -> None:
        scene = _scene(character_id="hero-base")
        learned = "観客は門を越えたことが不可逆な出来事だと理解する"
        scene["scene_event"]["turning_event"] = {
            "source_event_beat_id": "scene10-turn",
            "irreversible_change": "主人公が門を選ぶ",
        }
        scene["scene_intent"] = {
            "audience_knowledge_delta": {
                "learned_during_scene": [learned],
                "still_unknown_after_scene": ["秘密の鍵"],
                "forbidden_early_reveals": [],
            }
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            self.assertEqual(
                document["scenes"][0]["scene_intent"]
                ["audience_knowledge_delta"]["learned_during_scene"],
                [learned],
            )

    def test_symbolic_proof_preserves_optional_participants_when_repair_omits_them(self) -> None:
        scene = _scene(character_id="hero-base")
        beat = scene["scene_event"]["event_sequence"][0]
        beat["concrete_event"]["obligation_overrides"] = {
            "symbolic_proof": {
                "primary_subject": "hero",
                "required_roles": ["hero", "witness"],
            }
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
        )

        for document in (script, manifest):
            symbolic = document["scenes"][0]["scene_event"]["event_sequence"][0][
                "obligation_overrides"
            ]["symbolic_proof"]
            self.assertEqual(symbolic["primary_subject"], "hero")
            self.assertEqual(symbolic["required_roles"], ["hero", "witness"])

    def test_knowledge_repair_fails_if_replacement_still_leaks_withheld_token(self) -> None:
        scene = _scene(character_id="hero-base")
        scene["scene_event"]["turning_event"] = {
            "source_event_beat_id": "scene10-turn",
            "irreversible_change": "秘密の鍵が現れる",
        }
        scene["scene_intent"] = {
            "causal_turn": "秘密の鍵が現れる",
            "audience_knowledge_delta": {
                "learned_during_scene": ["秘密の鍵が現れたと理解する"],
                "still_unknown_after_scene": ["秘密の鍵"],
                "forbidden_early_reveals": [],
            }
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}
        before = deepcopy((script, manifest))

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "still leaks withheld information",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )
        self.assertEqual((script, manifest), before)

    def test_obligation_without_explicit_source_beat_fails_closed(self) -> None:
        scene = _scene(character_id="hero-base")
        scene["scene_intent"] = {
            "story_event_obligations": [
                {"event_id": "scene10_story_event", "visual_evidence": ["古い証拠"]}
            ]
        }
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "missing explicit source event beat ids",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )

    def test_visible_proof_with_unknown_trigger_fails_closed(self) -> None:
        scene = _scene(character_id="hero-base")
        scene["scene_character_state_timeline"]["characters"][0]["start_state"][
            "trigger_event_beat_id"
        ] = "missing-beat"
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}
        before = deepcopy((script, manifest))

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "unknown trigger beat",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )
        self.assertEqual((script, manifest), before)

    def test_unsafe_sound_or_light_story_function_repair_fails_closed(self) -> None:
        for element_type in ("sound", "light"):
            with self.subTest(element_type=element_type):
                scene = _scene(character_id="hero-base")
                beat = scene["scene_event"]["event_sequence"][0]
                beat["story_grounding"]["concrete_story_elements"] = [
                    {
                        "element_id": f"unsafe-{element_type}",
                        "element_type": element_type,
                        "concrete_description": "物語内の具体的な音または光",
                        "story_function": "causal_bridge",
                        "visible_form": "画面または音で確認できる",
                    }
                ]
                script = {"scenes": [scene]}
                manifest = {"scenes": [deepcopy(scene)]}
                before = deepcopy((script, manifest))

                with self.assertRaisesRegex(
                    SemanticRepairReconciliationError,
                    "no deterministic story function",
                ):
                    reconcile_semantic_repair_documents(
                        script=script,
                        manifest=manifest,
                        asset_plan={"assets": []},
                    )
                self.assertEqual((script, manifest), before)

    def test_replaces_stale_variant_with_allowed_parent_and_updates_asset_plan(self) -> None:
        script_scene = _scene(character_id="hero-base")
        script_scene["cuts"] = [
            _cut(
                "scene10_cut01",
                "scene10-turn",
                character_id="hero-transformed",
            )
        ]
        transformed_scene = _scene(character_id="hero-transformed")
        transformed_scene["scene_id"] = 20
        transformed_scene["cuts"][0]["selector"] = "scene20_cut01"
        script = {"scenes": [script_scene, transformed_scene]}
        manifest = {"scenes": [deepcopy(script_scene)]}
        manifest["scenes"].append(deepcopy(transformed_scene))
        asset_plan = {
            "assets": [
                {
                    "asset_id": "hero-base",
                    "asset_type": "character_reference",
                    "source_script_selectors": [],
                    "reuse_contract": {"mode": "neutral_anchor"},
                },
                {
                    "asset_id": "hero-transformed",
                    "asset_type": "character_reference",
                    "source_script_selectors": ["scene10_cut01"],
                    "reuse_contract": {
                        "mode": "state_variant",
                        "derived_from_asset_id": "hero-base",
                    },
                },
                {
                    "asset_id": "location-garden",
                    "asset_type": "location_reference",
                },
            ]
        }

        result = reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
        )

        self.assertEqual(result.unresolved_character_ids, ())
        for document in (script, manifest):
            cut = document["scenes"][0]["cuts"][0]
            self.assertEqual(
                cut["cut_contract"]["asset_dependency"][
                    "character_ids_required"
                ],
                ["hero-base"],
            )
            self.assertEqual(
                cut["image_generation"]["character_ids"], ["hero-base"]
            )
            self.assertEqual(
                cut["image_generation"]["references"],
                [
                    "assets/characters/hero-base.png",
                    "assets/locations/location-garden.png",
                ],
            )
            reference = cut["image_generation"]["first_frame_visual_plan"][
                "reference_binding"
            ]["character_references"][0]
            self.assertEqual(reference["target_character_id"], "hero-base")
            self.assertEqual(reference["path"], "assets/characters/hero-base.png")
            later_cut = document["scenes"][1]["cuts"][0]
            self.assertEqual(
                later_cut["image_generation"]["character_ids"],
                ["hero-transformed"],
            )
            self.assertEqual(
                later_cut["cut_contract"]["asset_dependency"][
                    "character_ids_required"
                ],
                ["hero-transformed"],
            )

        by_id = {entry["asset_id"]: entry for entry in asset_plan["assets"]}
        self.assertEqual(
            by_id["hero-base"]["source_script_selectors"], ["scene10_cut01"]
        )
        self.assertEqual(
            by_id["hero-transformed"]["source_script_selectors"],
            ["scene20_cut01"],
        )

    def test_unknown_missing_character_reference_fails_closed(self) -> None:
        script_scene = _scene(character_id="hero-base")
        script_scene["cuts"] = [
            _cut("scene10_cut01", "scene10-turn", character_id="unknown-variant")
        ]
        script = {"scenes": [script_scene]}
        manifest = {"scenes": [deepcopy(script_scene)]}
        before = deepcopy((script, manifest))

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "unknown-variant",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )
        self.assertEqual((script, manifest), before)

    def test_rebinds_object_and_location_references_from_current_dependencies(self) -> None:
        scene = _scene(character_id="hero-base")
        cut = scene["cuts"][0]
        for contract_name in ("cut_contract", "scene_contract"):
            dependency = cut[contract_name]["asset_dependency"]
            dependency["object_ids_required"] = ["gate-key"]
            dependency["reusable_anchor_ids"] = [
                "hero-base",
                "old-object",
                "location-garden",
            ]
        cut["image_generation"]["object_ids"] = ["gate-key"]
        cut["image_generation"]["references"] = [
            "assets/characters/hero-base.png",
            "assets/objects/old-object.png",
            "assets/locations/old-location.png",
        ]
        binding = cut["image_generation"]["first_frame_visual_plan"][
            "reference_binding"
        ]
        binding["object_references"] = ["assets/objects/old-object.png"]
        binding["location_references"] = ["assets/locations/old-location.png"]
        script = {"scenes": [scene]}
        manifest = {"scenes": [deepcopy(scene)]}
        asset_plan = {
            "assets": [
                {
                    "asset_id": "hero-base",
                    "asset_type": "character_reference",
                },
                {
                    "asset_id": "gate-key",
                    "asset_type": "object_reference",
                    "generation_plan": {
                        "output": "assets/objects/gate-key.png"
                    },
                },
                {
                    "asset_id": "location-garden",
                    "asset_type": "location_reference",
                    "generation_plan": {
                        "output": "assets/locations/location-garden.png"
                    },
                },
            ]
        }

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
        )

        for document in (script, manifest):
            projected = document["scenes"][0]["cuts"][0]
            self.assertEqual(
                projected["image_generation"]["references"],
                [
                    "assets/characters/hero-base.png",
                    "assets/objects/gate-key.png",
                    "assets/locations/location-garden.png",
                ],
            )
            projected_binding = projected["image_generation"][
                "first_frame_visual_plan"
            ]["reference_binding"]
            self.assertEqual(
                projected_binding["object_references"],
                ["assets/objects/gate-key.png"],
            )
            self.assertEqual(
                projected_binding["location_references"],
                ["assets/locations/location-garden.png"],
            )
            self.assertEqual(
                projected["cut_contract"]["asset_dependency"][
                    "reusable_anchor_ids"
                ],
                ["hero-base", "gate-key", "location-garden"],
            )

    def test_scene_or_cut_set_drift_fails_closed(self) -> None:
        script = {"scenes": [_scene(character_id="hero-base")]}
        manifest = {"scenes": [deepcopy(script["scenes"][0])]}
        manifest["scenes"][0]["cuts"][0]["selector"] = "unexpected_cut"
        before = deepcopy((script, manifest))

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "cut identity/order mismatch",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )
        self.assertEqual((script, manifest), before)

    def test_cut_identity_status_or_structure_drift_fails_closed(self) -> None:
        corruptions = (
            lambda manifest: manifest["scenes"][0]["cuts"][0].__setitem__(
                "cut_id", "99"
            ),
            lambda manifest: manifest["scenes"][0]["cuts"][0].__setitem__(
                "cut_status", "deleted"
            ),
            lambda manifest: manifest["scenes"][0]["cuts"].append(
                deepcopy(manifest["scenes"][0]["cuts"][0])
            ),
            lambda manifest: manifest["scenes"][0]["cuts"].append("invalid"),
        )
        for corrupt in corruptions:
            with self.subTest(corrupt=corrupt):
                script = {"scenes": [_scene(character_id="hero-base")]}
                manifest = {"scenes": [deepcopy(script["scenes"][0])]}
                corrupt(manifest)
                before = deepcopy((script, manifest))

                with self.assertRaises(SemanticRepairReconciliationError):
                    reconcile_semantic_repair_documents(
                        script=script,
                        manifest=manifest,
                        asset_plan={"assets": []},
                    )
                self.assertEqual((script, manifest), before)

    def test_non_list_cut_collection_fails_closed(self) -> None:
        script = {"scenes": [_scene(character_id="hero-base")]}
        manifest = {"scenes": [deepcopy(script["scenes"][0])]}
        script["scenes"][0]["cuts"] = "invalid"

        with self.assertRaisesRegex(
            SemanticRepairReconciliationError,
            "script cuts must be a list",
        ):
            reconcile_semantic_repair_documents(
                script=script,
                manifest=manifest,
                asset_plan={"assets": []},
            )

    def test_empty_asset_plan_remains_empty(self) -> None:
        script = {"scenes": [_scene(character_id="hero-base")]}
        manifest = {"scenes": [deepcopy(script["scenes"][0])]}
        asset_plan: dict = {}

        reconcile_semantic_repair_documents(
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
        )

        self.assertEqual(asset_plan, {})

    def test_server_projection_reconciles_real_fenced_yaml_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            script = {"scenes": [_scene(character_id="hero-base")]}
            manifest = {"scenes": [deepcopy(script["scenes"][0])]}
            for document in (script, manifest):
                source = document["scenes"][0]["cuts"][0]["cut_contract"][
                    "source_event_contract"
                ]
                source["source_visible_action"] = "ディスク上の古い行動"
                source["canonical_source_visible_action"] = "ディスク上の古い行動"
            for name, data in (
                ("script.md", script),
                ("video_manifest.md", manifest),
                ("asset_plan.md", {"assets": []}),
            ):
                (run_dir / name).write_text(
                    "# fixture\n\n```yaml\n"
                    + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
                    + "```\n",
                    encoding="utf-8",
                )
            (run_dir / "state.txt").write_text("status: test\n", encoding="utf-8")

            with patch(
                "server.image_gen_app.append_state_snapshot"
            ) as append_state:
                result = image_gen_app._reconcile_semantic_repair_authoring_projections(
                    run_dir
                )

            self.assertTrue(result.script_changed)
            self.assertTrue(result.manifest_changed)
            append_state.assert_called_once()
            for name in ("script.md", "video_manifest.md"):
                loaded = yaml.safe_load(
                    image_gen_app._extract_manifest_yaml_text(
                        (run_dir / name).read_text(encoding="utf-8")
                    )
                )
                cut = loaded["scenes"][0]["cuts"][0]
                self.assertEqual(
                    cut["cut_contract"]["source_event_contract"][
                        "source_visible_action"
                    ],
                    "主人公が月を見て自分で門へ進む",
                )
                self.assertNotIn(
                    "api_prompt_payload", cut["image_generation"]
                )

    def test_reconciliation_runs_before_p400_review_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            calls: list[str] = []
            for relpath in (
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "video_manifest.md",
                "asset_inventory.md",
                "asset_plan.md",
            ):
                (run_dir / relpath).write_text(f"# {relpath}\n", encoding="utf-8")

            class FakeFrontend:
                @staticmethod
                def _prepare_authoring_grounding(_run_dir: Path) -> None:
                    calls.append("authoring_grounding")

                @staticmethod
                def _refresh_p400_review_artifacts(_run_dir: Path) -> None:
                    calls.append("p400_reviews")

                @staticmethod
                def _require_fresh_p400_readiness(_run_dir: Path) -> None:
                    calls.append("p400_gate")

                @staticmethod
                def prepare_grounding(
                    _run_dir: Path,
                    *,
                    verify_p450: bool = True,
                ) -> None:
                    self.assertFalse(verify_p450)
                    calls.append("downstream_grounding")

                @staticmethod
                def _refresh_downstream_review_artifacts(_run_dir: Path) -> None:
                    calls.append("downstream_reviews")

            with (
                patch(
                    "server.image_gen_app._load_frontend_review_runner",
                    return_value=FakeFrontend,
                ),
                patch(
                    "server.image_gen_app._reconcile_semantic_repair_authoring_projections",
                    side_effect=lambda _run_dir: calls.append("authoring_projection"),
                    create=True,
                ),
                patch(
                    "server.image_gen_app._recompile_image_prompt_payloads_from_plans",
                    side_effect=lambda _run_dir: calls.append("prompt_compile") or [],
                ),
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    side_effect=lambda *_args, **_kwargs: calls.append("request_sync"),
                ),
            ):
                asyncio.run(
                    image_gen_app._reconcile_after_semantic_repair(
                        run_dir,
                        stage="scene_detail",
                        changed_artifacts=["script.md", "video_manifest.md"],
                    )
                )

        self.assertLess(calls.index("authoring_projection"), calls.index("p400_reviews"))

    def test_real_fenced_yaml_projection_precedes_p400_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            calls: list[str] = []
            script = {"scenes": [_scene(character_id="hero-base")]}
            manifest = {"scenes": [deepcopy(script["scenes"][0])]}
            for document in (script, manifest):
                source = document["scenes"][0]["cuts"][0]["cut_contract"][
                    "source_event_contract"
                ]
                source["source_visible_action"] = "P400が読んではいけない古い行動"
                source["canonical_source_visible_action"] = (
                    "P400が読んではいけない古い行動"
                )
            for name, data in (
                ("script.md", script),
                ("video_manifest.md", manifest),
                ("asset_plan.md", {"assets": []}),
            ):
                (run_dir / name).write_text(
                    "```yaml\n"
                    + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
                    + "```\n",
                    encoding="utf-8",
                )
            for name in (
                "research.md",
                "story.md",
                "visual_value.md",
                "asset_inventory.md",
            ):
                (run_dir / name).write_text(f"# {name}\n", encoding="utf-8")
            (run_dir / "state.txt").write_text("status: test\n", encoding="utf-8")

            def assert_projected(label: str) -> None:
                loaded = yaml.safe_load(
                    image_gen_app._extract_manifest_yaml_text(
                        (run_dir / "video_manifest.md").read_text(
                            encoding="utf-8"
                        )
                    )
                )
                action = loaded["scenes"][0]["cuts"][0]["cut_contract"][
                    "source_event_contract"
                ]["source_visible_action"]
                self.assertEqual(
                    action,
                    "主人公が月を見て自分で門へ進む",
                )
                calls.append(label)

            class FakeFrontend:
                @staticmethod
                def _prepare_authoring_grounding(_run_dir: Path) -> None:
                    assert_projected("authoring_grounding")

                @staticmethod
                def _refresh_p400_review_artifacts(_run_dir: Path) -> None:
                    assert_projected("p400_reviews")

                @staticmethod
                def _require_fresh_p400_readiness(_run_dir: Path) -> None:
                    calls.append("p400_gate")

                @staticmethod
                def prepare_grounding(
                    _run_dir: Path,
                    *,
                    verify_p450: bool = True,
                ) -> None:
                    self.assertFalse(verify_p450)
                    calls.append("downstream_grounding")

                @staticmethod
                def _refresh_downstream_review_artifacts(_run_dir: Path) -> None:
                    calls.append("downstream_reviews")

            with (
                patch(
                    "server.image_gen_app._load_frontend_review_runner",
                    return_value=FakeFrontend,
                ),
                patch(
                    "server.image_gen_app._recompile_image_prompt_payloads_from_plans",
                    side_effect=lambda _run_dir: (
                        assert_projected("prompt_compile") or []
                    ),
                ),
                patch(
                    "server.image_gen_app._synchronize_image_prompt_repair_outputs",
                    side_effect=lambda *_args, **_kwargs: calls.append(
                        "request_sync"
                    ),
                ),
                patch(
                    "server.image_gen_app._invalidate_p600_supervisor_result"
                ),
            ):
                asyncio.run(
                    image_gen_app._reconcile_after_semantic_repair(
                        run_dir,
                        stage="scene_detail",
                        changed_artifacts=["script.md", "video_manifest.md"],
                    )
                )

            self.assertLess(calls.index("prompt_compile"), calls.index("p400_reviews"))


if __name__ == "__main__":
    unittest.main()
