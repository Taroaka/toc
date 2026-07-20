import unittest

from toc.narration_prompt_projection_registry import (
    NARRATION_PROMPT_PROJECTION_REGISTRY_VERSION,
    build_narration_prompt_projection,
    narration_projection_registry_issues,
    rule_for_source_key,
)


class NarrationPromptProjectionRegistryTests(unittest.TestCase):
    def test_registry_is_well_formed_and_classifies_visual_only_motion(self) -> None:
        self.assertEqual(narration_projection_registry_issues(), [])

        rule = rule_for_source_key("cut.cut_contract.motion_contract.motion_brief")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.usage, "exclude")
        self.assertEqual(rule.authoring_relevance, "none")
        self.assertEqual(rule.spoken_projection, "must_not_surface")
        self.assertEqual(rule.transform, "exclude_visual_motion_instruction")

        visual_basis_rule = rule_for_source_key(
            "scene.time_of_day_visual_basis"
        )
        self.assertIsNotNone(visual_basis_rule)
        self.assertEqual(visual_basis_rule.usage, "exclude")
        self.assertEqual(visual_basis_rule.review_visibility, "review_only")
        self.assertEqual(
            visual_basis_rule.transform,
            "review_visual_daypart_basis_without_speaking_it",
        )

        location_sequence_rule = rule_for_source_key("scene.location_sequence")
        self.assertIsNotNone(location_sequence_rule)
        self.assertEqual(location_sequence_rule.usage, "candidate")
        self.assertEqual(
            location_sequence_rule.transform,
            "mention_spatial_transition_only_when_orientation_needs_voice",
        )
        location_segments_rule = rule_for_source_key("scene.location_segments")
        self.assertIsNotNone(location_segments_rule)
        self.assertEqual(location_segments_rule.usage, "candidate")
        self.assertEqual(
            location_segments_rule.transform,
            "mention_spatial_transition_only_when_orientation_needs_voice",
        )

    def test_projection_distinguishes_context_candidates_constraints_and_exclusions(self) -> None:
        manifest = {
            "video_metadata": {
                "time": "17世紀末フランス・ルイ14世時代",
                "ending_mode": "happy",
            },
        }
        scene = {
            "scene_id": 1,
            "time_of_day": "朝",
            "scene_intent": {
                "audience_information": ["シンデレラが家事を強いられている"],
                "withheld_information": ["舞踏会への招待"],
                "handoff_to_next_scene": "戸口の向こうから鐘が聞こえる",
                "handoff_notes": {
                    "p700_narration": ["自由を望む内面だけを補う"],
                },
            },
        }
        cut = {
            "cut_id": 1,
            "visual_beat": "灰の床で立ち止まり、出口へ視線だけを向ける",
            "cut_contract": {
                "viewer_contract": {
                    "audience_knowledge_delta": "彼女が出口を望んでいると気づく",
                },
                "source_event_contract": {
                    "event_facts_to_preserve": ["外出を許されていない"],
                    "event_facts_not_to_invent": ["招待状を受け取った"],
                    "forbidden_reveal_info_ids": ["fairy_arrival"],
                },
                "narration_contract": {
                    "story_role": {
                        "voice_function": "emotion",
                        "must_cover": ["自由への願い"],
                        "must_not_reveal": ["妖精の登場"],
                    },
                    "visual_distance": {
                        "distance_policy": "contextual",
                        "visible_facts_in_frame": ["灰の床", "出口を見る視線"],
                        "narration_should_add": ["抑圧の中でも願いは消えていない"],
                    },
                    "rhythm_and_timing": {"target_speech_seconds": 5},
                    "tts_readiness": {"pronunciation_targets": ["継母"]},
                },
                "motion_contract": {"motion_brief": "出口へ駆け出す"},
            },
        }

        projection = build_narration_prompt_projection(
            manifest=manifest,
            scene=scene,
            cut=cut,
        )

        self.assertEqual(
            projection["registry_version"],
            NARRATION_PROMPT_PROJECTION_REGISTRY_VERSION,
        )
        buckets = projection["buckets"]
        self.assertIn("自由への願い", str(buckets["required_content"]))
        self.assertIn("外出を許されていない", str(buckets["required_content"]))
        self.assertIn("抑圧の中でも願いは消えていない", str(buckets["preferred_additions"]))
        self.assertIn("灰の床", str(buckets["do_not_caption"]))
        self.assertIn("妖精の登場", str(buckets["reveal_constraints"]))
        self.assertIn("招待状を受け取った", str(buckets["reveal_constraints"]))
        self.assertIn("fairy_arrival", str(buckets["reveal_constraints"]))
        self.assertIn("17世紀末フランス・ルイ14世時代", str(buckets["background_context"]))
        self.assertIn("朝", str(buckets["conditional_candidates"]))
        self.assertNotIn("出口へ駆け出す", str(buckets))
        self.assertTrue(
            any(
                item["source_key"] == "cut.cut_contract.motion_contract.motion_brief"
                for item in projection["excluded"]
            )
        )
        active = {item["source_key"]: item for item in projection["active_rules"]}
        self.assertEqual(
            active["manifest.video_metadata.time"]["spoken_projection"],
            "derive",
        )
        self.assertEqual(
            active["manifest.video_metadata.ending_mode"]["spoken_projection"],
            "derive",
        )
        self.assertEqual(
            active[
                "cut.cut_contract.narration_contract.visual_distance.narration_should_add"
            ]["spoken_projection"],
            "may_surface",
        )
        self.assertEqual(
            active["cut.visual_beat"]["spoken_projection"],
            "must_not_surface",
        )

    def test_empty_optional_values_do_not_materialize(self) -> None:
        projection = build_narration_prompt_projection(
            manifest={"video_metadata": {"time": ""}},
            scene={"scene_id": 1, "time_of_day": ""},
            cut={"cut_id": 1, "cut_contract": {}},
        )

        self.assertFalse(projection["buckets"]["background_context"])
        self.assertFalse(projection["buckets"]["conditional_candidates"])

    def test_legacy_flat_contract_and_scene_contract_alias_project_to_same_ir(self) -> None:
        projection = build_narration_prompt_projection(
            manifest={},
            scene={"scene_id": 1},
            cut={
                "cut_id": 1,
                "scene_contract": {
                    "narration_contract": {
                        "role": "emotion",
                        "target_function": "抑圧の中に願いがあると伝える",
                        "must_cover": ["自由への願い"],
                        "must_avoid": ["妖精を先に語る"],
                        "done_when": ["願いだけが残る"],
                        "timing_intent": "after_visual_read",
                    },
                    "downstream_handoff": {
                        "p700_narration": ["画面にない内面だけを補う"],
                    },
                },
            },
        )

        buckets = projection["buckets"]
        self.assertIn("抑圧の中に願いがあると伝える", str(buckets["required_content"]))
        self.assertIn("自由への願い", str(buckets["required_content"]))
        self.assertIn("妖精を先に語る", str(buckets["reveal_constraints"]))
        self.assertIn("after_visual_read", str(buckets["delivery_constraints"]))
        self.assertIn("画面にない内面だけを補う", str(buckets["preferred_additions"]))


if __name__ == "__main__":
    unittest.main()
