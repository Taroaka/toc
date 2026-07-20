import unittest

from toc.image_prompt_compiler import FRAGMENT_GROUP_ORDER, compile_image_api_prompt_v2
from toc.image_prompt_projection_registry import (
    PROMPT_PROJECTION_REGISTRY_VERSION,
    build_projection_review_contract,
    projection_registry_contract_issues,
    projection_trace_issues,
    registered_drawable_group_order,
    rule_for_source_key,
)


class ImagePromptProjectionRegistryTests(unittest.TestCase):
    def test_registry_covers_every_compiler_drawable_group_in_order(self) -> None:
        self.assertEqual(projection_registry_contract_issues(), [])
        self.assertEqual(registered_drawable_group_order(), FRAGMENT_GROUP_ORDER)

    def test_non_prompt_source_key_is_explicitly_classified(self) -> None:
        rule = rule_for_source_key("cut_contract.motion_contract.motion_brief")

        self.assertIsNotNone(rule)
        self.assertEqual(rule.relevance, "none")
        self.assertEqual(rule.transform, "exclude_video_motion_from_still_prompt")

        visual_basis_rule = rule_for_source_key(
            "scenes[].time_of_day_visual_basis"
        )
        self.assertIsNotNone(visual_basis_rule)
        self.assertEqual(visual_basis_rule.relevance, "none")
        self.assertEqual(
            visual_basis_rule.transform,
            "review_derived_daypart_basis_without_duplicate_prompt_source",
        )

        location_sequence_rule = rule_for_source_key(
            "scenes[].location_sequence"
        )
        self.assertIsNotNone(location_sequence_rule)
        self.assertEqual(location_sequence_rule.relevance, "none")
        self.assertEqual(
            location_sequence_rule.transform,
            "review_scene_location_sequence_but_project_one_cut_location",
        )
        location_segments_rule = rule_for_source_key("scenes[].location_segments")
        self.assertIsNotNone(location_segments_rule)
        self.assertEqual(location_segments_rule.relevance, "none")
        self.assertEqual(
            location_segments_rule.transform,
            "review_scene_location_sequence_but_project_one_cut_location",
        )

        visualizable_action_rule = rule_for_source_key(
            "story.script.scenes[].visualizable_action"
        )
        self.assertIsNotNone(visualizable_action_rule)
        self.assertEqual(visualizable_action_rule.relevance, "none")
        self.assertEqual(
            visualizable_action_rule.transform,
            "review_scene_overview_but_project_cut_local_drawable_evidence",
        )
        self.assertIn(
            "reject_sequential_notation_in_positive_fragment",
            visualizable_action_rule.deterministic_checks,
        )

        raw_reveal_rule = rule_for_source_key(
            "cut_contract.source_event_contract.forbidden_reveal_info_ids"
        )
        self.assertIsNotNone(raw_reveal_rule)
        self.assertEqual(raw_reveal_rule.relevance, "none")
        self.assertEqual(
            raw_reveal_rule.transform,
            "resolve_known_drawable_asset_names_into_temporal_not_yet",
        )
        self.assertIn(
            "resolved_name_does_not_activate_dependency",
            raw_reveal_rule.deterministic_checks,
        )

    def test_review_contract_resolves_active_key_rules_for_one_cut(self) -> None:
        contract = build_projection_review_contract(
            story_time="17世紀末フランス・ルイ14世時代",
            time_of_day="朝",
            dependencies={
                "character_ids": ["cinderella"],
                "object_ids": [],
                "location_ids": ["ash_kitchen"],
                "references": ["assets/cinderella.png", "assets/ash_kitchen.png"],
            },
            first_frame_visual_plan={
                "temporal_boundary": {"event_fact_visible_in_still": "炉の前で立ち止まる"},
                "subject_binding": {"primary_subject": {"name": "シンデレラ"}},
                "spatial_composition": {"foreground": "灰の床"},
                "scene_material_pack": {"light_source": "朝の窓光"},
            },
        )

        self.assertEqual(contract["registry_version"], PROMPT_PROJECTION_REGISTRY_VERSION)
        active = {item["target_group"]: item for item in contract["active_rules"]}
        self.assertEqual(active["story_time"]["expected_value"], "17世紀末フランス・ルイ14世時代")
        self.assertEqual(active["time_of_day"]["expected_value"], "朝")
        self.assertIn("exact_value_binding", active["time_of_day"]["deterministic_checks"])
        self.assertIn("characters", active)
        self.assertIn("location", active)
        self.assertIn("references", active)
        excluded = {item["source_keys"][0]: item for item in contract["excluded_rules"]}
        self.assertIn("cut_contract.motion_contract.motion_brief", excluded)

    def test_compiler_output_and_registry_activation_have_no_drift(self) -> None:
        plan = {
            "temporal_boundary": {"event_fact_visible_in_still": "窓辺に立っている"},
            "subject_binding": {"primary_subject": {"name": "opaque_subject_id"}},
            "spatial_composition": {"aspect_ratio": "16:9"},
            "scene_material_pack": {"time_of_day": "夜"},
            "scene_state_progression": {"progression_mode": "suspended_moment"},
        }
        payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan)
        ir = payload["drawable_prompt_ir"]

        issues = projection_trace_issues(
            prompt=payload["prompt"],
            dependencies=ir["dependencies"],
            included_fragments=ir["included_fragments"],
            first_frame_visual_plan=plan,
        )

        self.assertEqual(issues, [])

    def test_trace_rejects_an_omitted_per_character_appearance_value(self) -> None:
        plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "若い女性が王子の前に立っている"
            },
            "character_state_gate": {
                "character_states": [
                    {
                        "character_id": "heroine_after_midnight",
                        "character_name": "若い女性",
                        "appearance_continuity": {
                            "costume_state": "質素な衣装",
                            "forbidden_costume_states": ["舞踏会ドレス"],
                        },
                    }
                ]
            },
        }
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=["heroine_after_midnight"],
        )
        fragments = [dict(item) for item in payload["drawable_prompt_ir"]["included_fragments"]]
        for fragment in fragments:
            if fragment["group"] == "characters":
                fragment["text"] = fragment["text"].replace("舞踏会ドレス", "")
        prompt = payload["prompt"].replace("舞踏会ドレス", "")

        issues = projection_trace_issues(
            prompt=prompt,
            dependencies=payload["drawable_prompt_ir"]["dependencies"],
            included_fragments=fragments,
            first_frame_visual_plan=plan,
        )
        codes = {issue.code for issue in issues}

        self.assertIn(
            "api_prompt_v2_character_appearance_fragment_value_missing",
            codes,
        )
        self.assertIn(
            "api_prompt_v2_character_appearance_prompt_value_missing",
            codes,
        )

    def test_trace_rejects_appearance_values_swapped_between_people(self) -> None:
        plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "赤い外套の女性と青い上着の男性が並ぶ"
            },
            "character_state_gate": {
                "character_states": [
                    {
                        "character_id": "alice",
                        "character_name": "アリス",
                        "appearance_continuity": {"costume_state": "赤い外套"},
                    },
                    {
                        "character_id": "bob",
                        "character_name": "ボブ",
                        "appearance_continuity": {"costume_state": "青い上着"},
                    },
                ]
            },
        }
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=["alice", "bob"],
        )
        swapped = (
            "アリスの衣装は、青い上着を維持し続ける。\n"
            "ボブの衣装は、赤い外套を維持し続ける。"
        )
        fragments = [dict(item) for item in payload["drawable_prompt_ir"]["included_fragments"]]
        original_character_fragment = ""
        for fragment in fragments:
            if fragment["group"] == "characters":
                original_character_fragment = fragment["text"]
                fragment["text"] = swapped
        prompt = payload["prompt"].replace(original_character_fragment, swapped)

        codes = {
            issue.code
            for issue in projection_trace_issues(
                prompt=prompt,
                dependencies=payload["drawable_prompt_ir"]["dependencies"],
                included_fragments=fragments,
                first_frame_visual_plan=plan,
            )
        }

        self.assertIn(
            "api_prompt_v2_character_appearance_fragment_value_missing",
            codes,
        )
        self.assertIn(
            "api_prompt_v2_character_appearance_prompt_value_missing",
            codes,
        )

    def test_localized_shot_activation_matches_compiler_projection(self) -> None:
        plan = {
            "temporal_boundary": {"event_fact_visible_in_still": "門前に立っている"},
            "spatial_composition": {"shot_size": "wide"},
        }
        payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan)
        ir = payload["drawable_prompt_ir"]

        issues = projection_trace_issues(
            prompt=payload["prompt"],
            dependencies=ir["dependencies"],
            included_fragments=ir["included_fragments"],
            first_frame_visual_plan=plan,
        )

        self.assertEqual(issues, [])

    def test_inactive_group_cannot_self_authorize_through_required_groups(self) -> None:
        issues = projection_trace_issues(
            prompt="光源は月明かり。",
            dependencies={"required_groups": ["light_material"]},
            included_fragments=[{"group": "light_material", "text": "光源は月明かり。"}],
            first_frame_visual_plan={},
        )

        self.assertIn(
            "api_prompt_v2_unneeded_light_material_fragment",
            {issue.code for issue in issues},
        )

    def test_inactive_fragment_is_only_unneeded_not_required_group_missing(self) -> None:
        issues = projection_trace_issues(
            prompt="人物なし。",
            dependencies={"character_ids": [], "required_groups": []},
            included_fragments=[{"group": "characters", "text": "人物なし。"}],
            first_frame_visual_plan={},
        )
        codes = [issue.code for issue in issues]

        self.assertEqual(codes.count("api_prompt_v2_unneeded_character_fragment"), 1)
        self.assertNotIn("api_prompt_v2_characters_required_group_missing", codes)

    def test_inactive_required_only_group_is_unneeded_not_missing_fragment(self) -> None:
        issues = projection_trace_issues(
            prompt="実写映画調。画面には石段が見える。文字なし。",
            dependencies={
                "required_groups": ["style", "current_moment", "light_material", "constraints"]
            },
            included_fragments=[
                {"group": "style", "text": "実写映画調。"},
                {"group": "current_moment", "text": "画面には石段が見える。"},
                {"group": "constraints", "text": "文字なし。"},
            ],
            first_frame_visual_plan={},
        )
        codes = [issue.code for issue in issues]

        self.assertEqual(codes.count("api_prompt_v2_unneeded_light_material_fragment"), 1)
        self.assertNotIn("api_prompt_v2_missing_light_material_fragment", codes)

    def test_exact_source_value_must_match_traced_dependency(self) -> None:
        marker = "物語の時代背景は江戸時代"
        issues = projection_trace_issues(
            prompt=marker,
            dependencies={"story_time": "平安時代", "required_groups": ["story_time"]},
            included_fragments=[{"group": "story_time", "text": marker}],
            expected_story_time="江戸時代",
        )

        self.assertIn(
            "api_prompt_v2_story_time_dependency_mismatch",
            {issue.code for issue in issues},
        )

    def test_required_groups_are_unique_and_in_registry_order(self) -> None:
        issues = projection_trace_issues(
            prompt="実写映画調。\n画面には、窓辺に立つ。\n禁止。",
            dependencies={
                "required_groups": ["current_moment", "style", "style", "constraints"]
            },
            included_fragments=[
                {"group": "style", "text": "実写映画調。"},
                {"group": "current_moment", "text": "画面には、窓辺に立つ。"},
                {"group": "constraints", "text": "禁止。"},
            ],
            first_frame_visual_plan={},
        )
        codes = {issue.code for issue in issues}

        self.assertIn("api_prompt_v2_required_groups_duplicate", codes)
        self.assertIn("api_prompt_v2_required_groups_order", codes)


if __name__ == "__main__":
    unittest.main()
