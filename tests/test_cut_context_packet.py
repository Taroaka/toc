from __future__ import annotations

import unittest

from toc.cut_context_packet import compile_cut_context_packet, cut_context_packet_for_review


def _scene() -> dict:
    return {
        "scene_id": 10,
        "scene_intent": {
            "dramatic_question": "公的な靴合わせで身元が戻るか",
            "reveal_constraints": ["王子との再会はまだ見せない"],
        },
        "scene_event": {
            "schema_version": "scene_event_v1",
            "event_logline": "使者が靴を持ち込み、証人の前で足に合うか試す",
            "event_sequence": [
                {
                    "beat_id": "scene10_event_pressure",
                    "beat_function": "pressure",
                    "what_happens": "使者が証人の前で靴を差し出す",
                    "visible_action": "使者の手に靴があり、証人が見ている",
                    "visible_reaction": "シンデレラが息を止める",
                    "required_visual_evidence": ["使者", "証人", "ガラスの靴"],
                }
            ],
            "forbidden_event_changes": ["王子が登場する"],
        },
        "scene_cut_coverage_plan": {
            "coverage_strategy": "reverse_from_scene_event",
            "scene_obligations": [
                {
                    "obligation_id": "public_proof_01",
                    "source": "story_event_obligations",
                    "evidence": ["使者", "証人", "ガラスの靴"],
                    "assigned_cut_ids": ["scene10_cut01"],
                }
            ],
            "cut_assignments": [
                {
                    "cut_selector": "scene10_cut01",
                    "obligation_ids": ["public_proof_01"],
                    "visual_proof": "使者、証人、靴が同じ画面で見える",
                    "required_roles": ["messenger", "witness"],
                }
            ],
        },
        "scene_character_state_timeline": {
            "characters": [
                {
                    "character_id": "cinderella",
                    "start_state": {"visible_proof": {"gaze": "靴を見る"}},
                    "midpoint_state": {"visible_proof": {"hands": "膝の上で止まる"}},
                    "end_state": {"visible_proof": {"face": "身元が戻る前の緊張"}},
                }
            ]
        },
        "scene_film_coverage_plan": {
            "shot_mix": {"actual_shots": [{"selector": "scene10_cut01", "shot_role": "object_proof", "shot_scale": "medium"}]}
        },
    }


def _cut() -> dict:
    return {
        "cut_id": "01",
        "selector": "scene10_cut01",
        "cut_contract": {
            "schema_version": "3.0",
            "source_event_contract": {
                "primary_event_beat_id": "scene10_event_pressure",
                "source_event_beat_ids": ["scene10_event_pressure"],
                "event_beat_function": "pressure",
                "event_time_position": "early_action",
                "source_visible_action": "使者の手に靴があり、証人が見ている",
                "source_visible_reaction": "シンデレラが息を止める",
                "source_required_visual_evidence": ["使者", "証人", "ガラスの靴"],
                "event_facts_to_preserve": ["使者が証人の前で靴を差し出す"],
                "event_facts_not_to_invent": ["王子が登場する"],
                "allowed_reveal_info_ids": [],
                "forbidden_reveal_info_ids": ["王子との再会はまだ見せない"],
            },
            "viewer_contract": {
                "target_beat": "公的な靴合わせの圧力",
                "visual_proof": "使者、証人、靴が同じ画面で見える",
                "required_roles": ["messenger", "witness"],
                "visual_evidence": ["使者", "証人", "ガラスの靴"],
                "must_show": ["シンデレラ", "使者", "証人", "ガラスの靴"],
                "reveal_constraints": {"forbidden_until_later_scene": ["王子との再会はまだ見せない"]},
            },
            "cut_character_emotion_transition": {
                "focal_character_id": "cinderella",
                "emotion_from": {"label": "緊張"},
                "emotion_to": {"label": "認識"},
                "transition_visible_in_cut": {"gaze_change": "靴を見る"},
            },
            "cut_film_grammar_contract": {
                "required_modules": {
                    "edit_motivation": {"why_current_cut_is_needed": "公的証明を見せる"},
                    "attention_state": {"viewer_attention_target": "使者の手の靴"},
                }
            },
            "cinematic_contract": {
                "screen_geography": {
                    "foreground": "使者の手の靴",
                    "midground": "シンデレラ",
                    "background": "証人",
                    "screen_direction": "proof_enters",
                }
            },
            "continuity_contract": {
                "location_ids": ["fitting_room"],
                "character_ids": ["cinderella", "messenger", "witness"],
                "object_ids": ["glass_slipper"],
                "start_state": {"spatial_state": "靴合わせの部屋"},
                "end_state": {"prop_state": "靴はまだ足に合っていない"},
            },
            "asset_dependency": {
                "character_ids_required": ["cinderella", "messenger", "witness"],
                "object_ids_required": ["glass_slipper"],
                "location_ids_required": ["fitting_room"],
            },
        },
    }


class TestCutContextPacket(unittest.TestCase):
    def test_compiles_scene_obligations_into_derived_cut_packet(self) -> None:
        packet, diagnostics = compile_cut_context_packet(_scene(), _cut(), previous_cut=None, next_cut={"selector": "scene10_cut02"})

        self.assertEqual(packet["schema_version"], "cut_context_packet_v1")
        self.assertFalse(packet["editable"])
        self.assertIn("scene_cut_coverage_plan", packet["derived_from"])
        self.assertEqual(packet["cut_selector"], "scene10_cut01")
        self.assertEqual(packet["source_event"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
        self.assertEqual(packet["scene_obligations"][0]["obligation_id"], "public_proof_01")
        self.assertEqual(packet["scene_obligations"][0]["required_roles"], ["messenger", "witness"])
        self.assertEqual(packet["previous_next_delta"]["next_cut_selector"], "scene10_cut02")
        self.assertEqual(packet["film_grammar"]["shot_role"], "object_proof")
        self.assertEqual(packet["location_use"]["location_ids"], ["fitting_room"])
        self.assertEqual(packet["object_reference_use"]["required_object_ids"], ["glass_slipper"])
        self.assertIn("王子が登場する", packet["boundary"]["forbidden_event_changes"])
        self.assertEqual(diagnostics["warning_keys"], [])

    def test_diagnostics_warn_when_required_roles_are_not_preserved(self) -> None:
        cut = _cut()
        cut["cut_contract"]["cut_context_packet"] = {
            "schema_version": "cut_context_packet_v1",
            "derived_from": ["scene_intent"],
            "editable": False,
            "cut_selector": "scene10_cut01",
            "source_event": {},
            "scene_obligations": [{"required_roles": []}],
            "previous_next_delta": {},
            "boundary": {},
        }

        packet, diagnostics = cut_context_packet_for_review(_scene(), cut, previous_cut=None, next_cut=None)

        self.assertIn("script.cut_context_packet_required_roles_preserved", diagnostics["warning_keys"])
        self.assertEqual(packet["diagnostics"]["missing_required_roles"], ["messenger", "witness"])


if __name__ == "__main__":
    unittest.main()
