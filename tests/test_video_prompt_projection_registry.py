from __future__ import annotations

import unittest
from typing import Any, Mapping

from toc.video_prompt_projection_registry import (
    VIDEO_PROMPT_GROUP_ORDER,
    VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
    build_video_prompt_projection,
    rule_for_source_key,
    video_projection_registry_issues,
)


EXPECTED_GROUP_ORDER = (
    "start_state",
    "primary_motion",
    "camera_motion",
    "environment_motion",
    "emotional_change",
    "end_state",
    "continuity",
    "constraints",
)


def _canonical_cut_contract() -> dict[str, Any]:
    return {
        "cut_id": "scene04_cut02_internal",
        "first_frame_contract": {
            "source_event_beat_id": "scene04_event_threshold_internal",
            "first_frame_brief": "扉の前で足を止めている",
            "visible_start_state": {
                "character_state": "主人公は扉の前で足を止めている",
                "prop_state": "扉は閉じている",
                "spatial_state": "主人公と扉の間に一歩分の距離がある",
                "emotional_state": "警戒している",
                "gaze_or_attention": "閉じた扉を見る",
            },
        },
        "motion_contract": {
            "source_event_beat_id": "scene04_event_threshold_internal",
            "motion_brief": "主人公が扉へ一歩だけ進む",
            "start_from_visible_state": "扉の前で足を止めた状態",
            "camera_motion": "胸の高さを保ち、ゆっくり寄る",
            "subject_motion": "主人公の右足が扉の方向へ踏み出す",
            "environment_motion": "薄い霧だけが流れる",
            "emotional_change": "警戒から決意へ変わる",
            "end_state": "手を伸ばす直前で止まる",
            "end_frame_brief": "手と扉の距離が縮まり、接触前で止まる",
            "must_not_add": ["新しい人物", "扉が開いた結果"],
        },
        "continuity_contract": {
            "start_state": {"blocking": "扉の前で静止"},
            "end_state": {"blocking": "手を伸ばす直前"},
            "carry_forward_to_next_cut": [
                "主人公の顔と衣装",
                "閉じた扉",
                "進行方向",
                "光源方向",
            ],
            "continuity_risks": ["扉の左右反転", "夜明けの光が夜になる"],
        },
    }


def _group_values(projection: Mapping[str, Any], group: str) -> tuple[str, ...]:
    values: list[str] = []
    for item in projection["groups"][group]:
        value = item.get("value") if isinstance(item, Mapping) else item
        if isinstance(value, Mapping):
            values.extend(str(part) for part in value.values() if str(part).strip())
        elif isinstance(value, (list, tuple, set)):
            values.extend(str(part) for part in value if str(part).strip())
        elif str(value or "").strip():
            values.append(str(value).strip())
    return tuple(values)


def _group_text(projection: Mapping[str, Any], group: str) -> str:
    return "\n".join(_group_values(projection, group))


def _other_group_text(projection: Mapping[str, Any], group: str) -> str:
    return "\n".join(
        _group_text(projection, candidate)
        for candidate in VIDEO_PROMPT_GROUP_ORDER
        if candidate != group
    )


class VideoPromptProjectionRegistryTests(unittest.TestCase):
    def test_registry_is_well_formed_and_declares_provider_group_order(self) -> None:
        self.assertEqual(video_projection_registry_issues(), [])
        self.assertEqual(VIDEO_PROMPT_GROUP_ORDER, EXPECTED_GROUP_ORDER)

    def test_registry_classifies_canonical_and_legacy_motion_sources(self) -> None:
        expectations = {
            "cut.cut_contract.motion_contract.motion_brief": (
                "primary_motion",
                "required",
                "derive",
                "projection",
            ),
            "video_generation.motion_contract.motion_intent": (
                "primary_motion",
                "required",
                "derive",
                "projection",
            ),
            "cut.cut_contract.motion_contract.end_state": (
                "end_state",
                "required",
                "derive",
                "projection",
            ),
            "video_generation.motion_contract.handoff_state": (
                "end_state",
                "required",
                "derive",
                "projection",
            ),
            "video_generation.motion_contract.must_preserve": (
                "continuity",
                "conditional",
                "derive",
                "projection",
            ),
            "compiler_normalized.authoring_source.primary_motion": (
                "primary_motion",
                "required",
                "derive",
                "projection",
            ),
            "compiler_normalized.authoring_source.camera_motion": (
                "camera_motion",
                "conditional",
                "derive",
                "projection",
            ),
            "scene.time_of_day_visual_basis": (
                None,
                "conditional",
                "must_not_surface",
                "review_only",
            ),
            "scene.location_sequence": (
                None,
                "conditional",
                "must_not_surface",
                "review_only",
            ),
            "scene.visualizable_action": (
                None,
                "none",
                "must_not_surface",
                "review_only",
            ),
        }

        for source_key, expected in expectations.items():
            with self.subTest(source_key=source_key):
                rule = rule_for_source_key(source_key)

                self.assertIsNotNone(rule)
                self.assertEqual(
                    (
                        rule.target_group,
                        rule.authoring_relevance,
                        rule.provider_projection,
                        rule.review_visibility,
                    ),
                    expected,
                )
                self.assertTrue(rule.transform)
                self.assertTrue(rule.semantic_checks)

    def test_scene_visualizable_action_is_review_only_and_never_provider_projection(self) -> None:
        overview = "家族が去る→助力者が現れる→衣装が変わる"
        projection = build_video_prompt_projection(
            scene={
                "visualizable_action": overview,
                "review_only_visualizable_action": overview,
            },
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩だけ進む",
                }
            },
        )

        self.assertNotIn(
            overview,
            "\n".join(
                _group_text(projection, group)
                for group in VIDEO_PROMPT_GROUP_ORDER
            ),
        )
        traced = {
            item["source_key"]: item["value"]
            for item in projection["review_only_sources"]
        }
        self.assertEqual(traced["scene.visualizable_action"], overview)
        self.assertEqual(traced["scene.review_only_visualizable_action"], overview)

    def test_compiler_normalized_authoring_groups_replace_raw_free_text_trace(self) -> None:
        projection = build_video_prompt_projection(
            video_generation={
                "prompt_authoring_source": (
                    "action: 主人公が扉へ一歩進む\n"
                    "camera: カメラは被写体へゆっくり寄る"
                )
            },
            normalized_authoring_groups={
                "primary_motion": ["主人公が扉へ一歩進む"],
                "camera_motion": ["カメラは被写体へゆっくり寄る"],
            },
        )

        self.assertEqual(
            _group_values(projection, "primary_motion"),
            ("主人公が扉へ一歩進む",),
        )
        self.assertEqual(
            _group_values(projection, "camera_motion"),
            ("カメラは被写体へゆっくり寄る",),
        )
        active_source_keys = {
            str(item.get("source_key") or "")
            for item in projection["active_rules"]
        }
        self.assertIn(
            "compiler_normalized.authoring_source.primary_motion",
            active_source_keys,
        )
        self.assertIn(
            "compiler_normalized.authoring_source.camera_motion",
            active_source_keys,
        )
        self.assertNotIn(
            "video_generation.prompt_authoring_source",
            active_source_keys,
        )

        internal_id_rule = rule_for_source_key(
            "cut.cut_contract.motion_contract.source_event_beat_id"
        )
        self.assertIsNotNone(internal_id_rule)
        self.assertEqual(internal_id_rule.provider_projection, "must_not_surface")
        self.assertEqual(internal_id_rule.review_visibility, "review_only")

        for excluded_key in (
            "cut.image_generation.prompt",
            "cut.audio.narration.tts_text",
        ):
            with self.subTest(excluded_key=excluded_key):
                excluded_rule = rule_for_source_key(excluded_key)
                self.assertIsNotNone(excluded_rule)
                self.assertEqual(excluded_rule.authoring_relevance, "none")
                self.assertEqual(
                    excluded_rule.provider_projection,
                    "must_not_surface",
                )
                self.assertEqual(excluded_rule.review_visibility, "review_only")

    def test_review_only_sources_keep_exact_resolved_values_outside_provider_groups(self) -> None:
        basis = {
            "light_source": "東向きの小窓から入る朝日",
            "brightness": "薄暗い室内に朝の光が差す",
            "shadow": "床へ長い影が伸びる",
            "color_temperature": "冷たい灰色に淡い暖色が混じる",
        }
        location_sequence = ["灰の台所", "屋敷の玄関"]
        location_segments = [
            {"location": "灰の台所", "responsibility": "開始状態"},
            {"location": "屋敷の玄関", "responsibility": "退出の結果"},
        ]
        projection = build_video_prompt_projection(
            scene={
                "time_of_day": "朝",
                "time_of_day_visual_basis": basis,
                "location_mode": "sequence",
                "location_sequence": location_sequence,
                "location_segments": location_segments,
            },
            cut_contract=_canonical_cut_contract(),
        )

        traced = {
            item["source_key"]: item["value"]
            for item in projection["review_only_sources"]
        }
        self.assertEqual(traced["scene.time_of_day_visual_basis"], basis)
        self.assertEqual(traced["scene.location_mode"], "sequence")
        self.assertEqual(traced["scene.location_sequence"], location_sequence)
        self.assertEqual(traced["scene.location_segments"], location_segments)
        self.assertEqual(
            traced["cut.cut_contract.motion_contract.source_event_beat_id"],
            "scene04_event_threshold_internal",
        )
        provider_group_text = "\n".join(
            _group_text(projection, group) for group in VIDEO_PROMPT_GROUP_ORDER
        )
        self.assertNotIn("東向きの小窓", provider_group_text)
        self.assertNotIn("灰の台所", provider_group_text)
        self.assertNotIn("scene04_event_threshold_internal", provider_group_text)

    def test_reference_roles_project_to_continuity_without_reference_paths(self) -> None:
        projection = build_video_prompt_projection(
            video_generation={
                "references": [
                    "assets/scenes/start.png",
                    "assets/storyboards/ordered.png",
                ],
                "reference_roles": [
                    {"image_index": 1, "role": "start_state_visual_anchor"},
                    {
                        "image_index": 2,
                        "role": "ordered_storyboard_sequence_guide",
                    },
                ],
            }
        )

        continuity = _group_text(projection, "continuity")
        self.assertIn("start_state_visual_anchor", continuity)
        self.assertIn("ordered_storyboard_sequence_guide", continuity)
        self.assertNotIn("assets/scenes/start.png", continuity)
        self.assertNotIn("assets/storyboards/ordered.png", continuity)

    def test_canonical_contract_projects_motion_temporal_continuity_and_constraints(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract=_canonical_cut_contract(),
            story_time="架空王朝の第七紀",
            time_of_day="暁前の青い薄明",
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            direction_notes=("主人公の進行方向を画面右へ保つ",),
            continuity_notes=("顔、衣装、扉の外観を開始画像と一致させる",),
        )

        self.assertEqual(
            projection["registry_version"],
            VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
        )
        self.assertEqual(tuple(projection["groups"]), VIDEO_PROMPT_GROUP_ORDER)
        self.assertIn("扉の前で足を止めた状態", _group_text(projection, "start_state"))
        self.assertIn(
            "主人公が扉へ一歩だけ進む",
            _group_text(projection, "primary_motion"),
        )
        self.assertIn(
            "胸の高さを保ち、ゆっくり寄る",
            _group_text(projection, "camera_motion"),
        )
        self.assertIn("薄い霧だけが流れる", _group_text(projection, "environment_motion"))
        self.assertIn("警戒から決意へ変わる", _group_text(projection, "emotional_change"))
        self.assertIn("手を伸ばす直前で止まる", _group_text(projection, "end_state"))

        continuity = _group_text(projection, "continuity")
        self.assertIn("主人公の顔と衣装", continuity)
        self.assertIn("架空王朝の第七紀", continuity)
        self.assertIn("暁前の青い薄明", continuity)
        self.assertNotIn(
            "架空王朝の第七紀",
            _other_group_text(projection, "continuity"),
        )
        self.assertNotIn(
            "暁前の青い薄明",
            _other_group_text(projection, "continuity"),
        )

        constraints = _group_text(projection, "constraints")
        self.assertIn("新しい人物", constraints)
        self.assertIn("扉が開いた結果", constraints)

        active_groups = {
            item["target_group"]
            for item in projection["active_rules"]
            if item.get("target_group")
        }
        self.assertEqual(active_groups, set(VIDEO_PROMPT_GROUP_ORDER))

    def test_legacy_contract_aliases_project_to_the_same_group_values(self) -> None:
        motion = "主人公が扉へ一歩だけ進む"
        end_state = "手を伸ばす直前で止まる"
        preserve = ["主人公", "閉じた扉", "夜明けの光"]
        forbid = ["扉の先のreveal"]

        canonical = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {
                    "motion_brief": motion,
                    "end_state": end_state,
                    "must_not_add": forbid,
                },
                "continuity_contract": {"carry_forward_to_next_cut": preserve},
            }
        )
        legacy_video_generation = build_video_prompt_projection(
            cut_contract={},
            video_generation={
                "motion_contract": {
                    "motion_intent": motion,
                    "handoff_state": end_state,
                    "must_preserve": preserve,
                    "must_not_add": forbid,
                }
            },
        )
        legacy_scene_contract = build_video_prompt_projection(
            cut_contract={},
            scene_contract={
                "motion_brief": motion,
                "motion_end_state": end_state,
                "must_avoid": forbid,
                "continuity_contract": {"carry_forward_to_next_cut": preserve},
            },
        )

        compared_groups = ("primary_motion", "end_state", "continuity", "constraints")
        for group in compared_groups:
            with self.subTest(group=group):
                expected = _group_values(canonical, group)
                self.assertEqual(_group_values(legacy_video_generation, group), expected)
                self.assertEqual(_group_values(legacy_scene_contract, group), expected)

    def test_reveal_allowlist_flat_alias_matches_canonical_constraint_projection(self) -> None:
        allowlist = ["ガラスの靴", "かぼちゃの馬車"]
        canonical = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "光が少女を包み変身させる",
                    "allowed_new_reveal_elements": allowlist,
                }
            }
        )
        flat = build_video_prompt_projection(
            cut_contract={},
            video_generation={
                "motion_contract": {
                    "motion_intent": "光が少女を包み変身させる",
                    "allowed_new_reveal_elements": allowlist,
                }
            },
        )

        self.assertEqual(
            _group_values(flat, "constraints"),
            _group_values(canonical, "constraints"),
        )
        canonical_sources = {
            str(item.get("source_key") or "")
            for item in canonical["active_rules"]
        }
        flat_sources = {
            str(item.get("source_key") or "")
            for item in flat["active_rules"]
        }
        self.assertIn(
            "cut.cut_contract.motion_contract.allowed_new_reveal_elements",
            canonical_sources,
        )
        self.assertIn(
            "video_generation.motion_contract.allowed_new_reveal_elements",
            flat_sources,
        )

    def test_canonical_reveal_allowlist_shadows_conflicting_flat_alias(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "光が少女を包み変身させる",
                    "allowed_new_reveal_elements": ["ガラスの靴"],
                }
            },
            video_generation={
                "motion_contract": {
                    "allowed_new_reveal_elements": ["かぼちゃの馬車"],
                }
            },
        )

        constraints = _group_text(projection, "constraints")
        self.assertIn("ガラスの靴", constraints)
        self.assertNotIn("かぼちゃの馬車", constraints)
        shadowed_sources = {
            str(item.get("source_key") or "")
            for item in projection["shadowed_sources"]
        }
        self.assertIn(
            "video_generation.motion_contract.allowed_new_reveal_elements",
            shadowed_sources,
        )

    def test_canonical_values_outrank_conflicting_legacy_aliases(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "正本の主動作として一歩進む",
                    "end_state": "正本の終了状態として接触前で止まる",
                    "must_not_add": ["正本が禁止する新しい人物"],
                }
            },
            scene_contract={
                "motion_brief": "旧scene入力の主動作として走り去る",
                "motion_end_state": "旧scene入力の終了状態として扉を通過する",
                "must_avoid": ["旧scene入力だけの禁止"],
            },
            video_generation={
                "motion_contract": {
                    "motion_intent": "flat入力の主動作として二歩戻る",
                    "handoff_state": "flat入力の終了状態として振り返る",
                    "must_not_add": ["flat入力だけの禁止"],
                }
            },
            source_prompt="自由入力の主動作として跳び去る",
        )

        self.assertIn(
            "正本の主動作として一歩進む",
            _group_text(projection, "primary_motion"),
        )
        self.assertIn(
            "正本の終了状態として接触前で止まる",
            _group_text(projection, "end_state"),
        )
        self.assertIn(
            "正本が禁止する新しい人物",
            _group_text(projection, "constraints"),
        )
        lower_priority_text = "\n".join(
            _group_text(projection, group)
            for group in ("primary_motion", "end_state", "constraints")
        )
        for lower_priority_value in (
            "旧scene入力の主動作として走り去る",
            "旧scene入力の終了状態として扉を通過する",
            "旧scene入力だけの禁止",
            "flat入力の主動作として二歩戻る",
            "flat入力の終了状態として振り返る",
            "flat入力だけの禁止",
            "自由入力の主動作として跳び去る",
        ):
            with self.subTest(lower_priority_value=lower_priority_value):
                self.assertNotIn(lower_priority_value, lower_priority_text)

    def test_partial_canonical_contract_fills_only_missing_groups_from_scene_alias(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {
                    "camera_motion": "正本のカメラとしてゆっくり寄る",
                }
            },
            scene_contract={
                "motion_brief": "旧scene入力から補う主動作として一歩進む",
                "motion_end_state": "旧scene入力から補う終了状態で止まる",
                "camera_motion": "旧scene入力の競合カメラとして急旋回する",
            },
        )

        self.assertIn(
            "旧scene入力から補う主動作として一歩進む",
            _group_text(projection, "primary_motion"),
        )
        self.assertIn(
            "旧scene入力から補う終了状態で止まる",
            _group_text(projection, "end_state"),
        )
        camera = _group_text(projection, "camera_motion")
        self.assertIn("正本のカメラとしてゆっくり寄る", camera)
        self.assertNotIn("旧scene入力の競合カメラとして急旋回する", camera)

    def test_kling_provider_policy_activates_a_constraint_projection_rule(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract={
                "motion_contract": {"motion_brief": "主人公が一歩だけ進む"}
            },
            tool="kling_3_0",
        )

        policy_rules = [
            item
            for item in projection["active_rules"]
            if "video_generation.tool" in _rule_source_keys(item)
        ]
        self.assertTrue(policy_rules)
        self.assertTrue(
            all(
                item["transform"] == "select_provider_specific_motion_policy"
                for item in policy_rules
            )
        )
        kling_policy_rules = [
            item
            for item in projection["active_rules"]
            if any(
                source_key.startswith("provider_policy.kling")
                for source_key in _rule_source_keys(item)
            )
        ]
        self.assertTrue(kling_policy_rules)
        self.assertTrue(
            all(item["target_group"] == "constraints" for item in kling_policy_rules)
        )

    def test_empty_optional_sources_do_not_materialize_projection_values(self) -> None:
        projection = build_video_prompt_projection(
            cut_contract={
                "first_frame_contract": {"first_frame_brief": "  "},
                "motion_contract": {
                    "motion_brief": "主人公が一度だけ瞬きをする",
                    "camera_motion": "",
                    "environment_motion": [],
                    "emotional_change": None,
                    "end_state": "  ",
                    "must_not_add": [],
                },
                "continuity_contract": {
                    "carry_forward_to_next_cut": [],
                    "continuity_risks": {},
                },
            },
            video_generation={"motion_contract": {}},
            story_time=" ",
            time_of_day="",
            direction_notes=("", "  "),
            continuity_notes=(),
        )

        self.assertEqual(
            _group_values(projection, "primary_motion"),
            ("主人公が一度だけ瞬きをする",),
        )
        for group in (
            "start_state",
            "camera_motion",
            "environment_motion",
            "emotional_change",
            "end_state",
            "continuity",
            "constraints",
        ):
            with self.subTest(group=group):
                self.assertEqual(_group_values(projection, group), ())
        active_groups = {
            item.get("target_group")
            for item in projection["active_rules"]
            if item.get("target_group")
        }
        self.assertEqual(active_groups, {"primary_motion"})


def _rule_source_keys(item: Mapping[str, Any]) -> tuple[str, ...]:
    source_key = str(item.get("source_key") or "").strip()
    if source_key:
        return (source_key,)
    source_keys = item.get("source_keys")
    if isinstance(source_keys, (list, tuple, set)):
        return tuple(str(value).strip() for value in source_keys if str(value).strip())
    return ()


if __name__ == "__main__":
    unittest.main()
