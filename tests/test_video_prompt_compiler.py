from __future__ import annotations

import copy
import hashlib
import unittest
from typing import Any, Mapping

from toc.video_prompt_compiler import (
    VIDEO_API_PROMPT_POLICY_VERSION,
    VIDEO_PROMPT_COMPILER_VERSION,
    compile_video_api_prompt_v1,
    compose_video_render_unit_contract,
)
from toc.video_prompt_projection_registry import (
    VIDEO_PROMPT_GROUP_ORDER,
    VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
)


def _canonical_cut_contract() -> dict[str, Any]:
    return {
        "cut_id": "scene04_cut02_internal",
        "viewer_contract": {
            "target_beat": "target_beat_internal_only",
        },
        "first_frame_contract": {
            "source_event_beat_id": "scene04_event_threshold_internal",
            "first_frame_brief": "扉の前で足を止めている",
            "visible_start_state": {
                "character_state": "主人公は扉の前で足を止めている",
                "prop_state": "扉は閉じている",
                "spatial_state": "主人公と扉の間に一歩分の距離がある",
                "emotional_state": "警戒している",
                "gaze_or_attention": "閉じた扉を見る",
                "character_id": "hero_internal_id",
                "object_id": "door_internal_id",
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
        "narration_contract": {
            "tts_text": "NARRATION_SECRET_SHOULD_NOT_SURFACE",
            "story_role": {"must_cover": ["NARRATION_ROLE_SECRET"]},
        },
        "image_generation": {
            "prompt": "IMAGE_PROMPT_SECRET_SHOULD_NOT_SURFACE",
            "api_prompt_payload": {
                "sha256": "image_prompt_hash_internal",
                "prompt": "IMAGE_API_PROMPT_SECRET",
            },
        },
        "review_instruction": "REVIEW_INSTRUCTION_SECRET_SHOULD_NOT_SURFACE",
    }


def _fragments(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(payload["included_fragments"])


def _fragment_groups(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(item["group"]) for item in _fragments(payload))


def _fragment_text(payload: Mapping[str, Any], group: str) -> str:
    return "\n".join(
        str(item["text"])
        for item in _fragments(payload)
        if item.get("group") == group
    )


def _other_fragment_text(payload: Mapping[str, Any], group: str) -> str:
    return "\n".join(
        str(item["text"])
        for item in _fragments(payload)
        if item.get("group") != group
    )


class VideoPromptCompilerTests(unittest.TestCase):
    def test_canonical_contract_compiles_conditional_provider_fragments(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            video_generation={
                "motion_prompt": "SOURCE_PROMPT_SECOND_INTENT_SHOULD_NOT_SURFACE",
                "narration": "VIDEO_GENERATION_NARRATION_SECRET",
                "image_prompt": "VIDEO_GENERATION_IMAGE_PROMPT_SECRET",
            },
            source_prompt="SOURCE_PROMPT_SECOND_INTENT_SHOULD_NOT_SURFACE",
            story_time="架空王朝の第七紀",
            time_of_day="暁前の青い薄明",
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            duration_seconds=8,
            direction_notes=("主人公の進行方向を画面右へ保つ",),
            continuity_notes=("顔、衣装、扉の外観を開始画像と一致させる",),
        )

        self.assertEqual(payload["policy_version"], VIDEO_API_PROMPT_POLICY_VERSION)
        self.assertEqual(payload["compiler_version"], VIDEO_PROMPT_COMPILER_VERSION)
        self.assertEqual(payload["provider"], "kling_3_0")
        self.assertEqual(payload["mode"], "image_to_video")
        self.assertEqual(
            _fragment_groups(payload),
            tuple(
                group
                for group in VIDEO_PROMPT_GROUP_ORDER
                if group not in payload["omitted_groups"]
            ),
        )
        self.assertEqual(set(_fragment_groups(payload)), set(VIDEO_PROMPT_GROUP_ORDER))
        self.assertEqual(
            payload["projection_review_contract"]["registry_version"],
            VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
        )
        self.assertEqual(
            payload["video_prompt_ir"]["included_fragments"],
            payload["included_fragments"],
        )
        self.assertEqual(
            payload["video_prompt_ir"]["omitted_groups"],
            payload["omitted_groups"],
        )

        expected_values = {
            "start_state": "扉の前で足を止めた状態",
            "primary_motion": "主人公が扉へ一歩だけ進む",
            "camera_motion": "胸の高さを保ち、ゆっくり寄る",
            "environment_motion": "薄い霧だけが流れる",
            "emotional_change": "警戒から決意へ変わる",
            "end_state": "手を伸ばす直前で止まる",
            "continuity": "架空王朝の第七紀",
            "constraints": "扉が開いた結果",
        }
        for group, value in expected_values.items():
            with self.subTest(group=group, value=value):
                self.assertIn(value, _fragment_text(payload, group))
                self.assertNotIn(value, _other_fragment_text(payload, group))

        continuity = _fragment_text(payload, "continuity")
        self.assertIn("主人公の顔と衣装", continuity)
        self.assertIn("暁前の青い薄明", continuity)
        self.assertIn("顔、衣装、扉の外観を開始画像と一致させる", continuity)
        self.assertIn("新しい人物", _fragment_text(payload, "constraints"))
        self.assertEqual(
            _fragment_text(payload, "primary_motion").count(
                "主人公が扉へ一歩だけ進む"
            ),
            1,
        )
        self.assertNotIn(
            "SOURCE_PROMPT_SECOND_INTENT_SHOULD_NOT_SURFACE",
            payload["prompt"],
        )

    def test_kling_prompt_is_one_intent_and_one_continuous_shot(self) -> None:
        for tool in ("kling_3_0", "kling_3_0_omni"):
            with self.subTest(tool=tool):
                payload = compile_video_api_prompt_v1(
                    cut_contract=_canonical_cut_contract(),
                    source_prompt=(
                        "主人公が扉へ進んだ後、振り返って走り去る。"
                        "SOURCE_PROMPT_SECOND_INTENT_SHOULD_NOT_SURFACE"
                    ),
                    tool=tool,
                    first_frame="assets/scenes/scene04_cut02_base.png",
                )

                prompt = payload["prompt"]
                constraints = _fragment_text(payload, "constraints")
                provider_policy = payload["provider_policy"]
                self.assertIs(provider_policy["one_clip_one_intent"], True)
                self.assertEqual(provider_policy["max_camera_instructions"], 2)
                self.assertIs(provider_policy["single_continuous_shot"], True)
                self.assertIn("単一の連続ショット", constraints)
                self.assertIn("別ショット", constraints)
                self.assertIn("切り替えない", constraints)
                self.assertEqual(_fragment_groups(payload).count("primary_motion"), 1)
                self.assertNotIn("振り返って走り去る", prompt)
                self.assertNotIn(
                    "SOURCE_PROMPT_SECOND_INTENT_SHOULD_NOT_SURFACE",
                    prompt,
                )

    def test_kling_camera_projection_keeps_at_most_two_instructions(self) -> None:
        for tool in ("kling_3_0", "kling_3_0_omni"):
            with self.subTest(tool=tool):
                contract = _canonical_cut_contract()
                contract["motion_contract"]["camera_motion"] = (
                    "カメラはゆっくり寄る。"
                    "カメラは右へパンする。"
                    "カメラは上へクレーン移動する。"
                )

                payload = compile_video_api_prompt_v1(
                    cut_contract=contract,
                    tool=tool,
                )

                camera = _fragment_text(payload, "camera_motion")
                self.assertIn("カメラはゆっくり寄る", camera)
                self.assertIn("カメラは右へパンする", camera)
                self.assertNotIn("カメラは上へクレーン移動する", camera)

    def test_kling_camera_projection_limits_compound_sentence_to_two_operations(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩進む",
                    "camera_motion": "カメラは左へパンし、上へティルトし、その後ズームする",
                }
            },
            tool="kling_3_0",
        )

        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("左へパン", camera)
        self.assertIn("上へティルト", camera)
        self.assertNotIn("ズーム", camera)

    def test_kling_camera_projection_limits_japanese_conjugated_operations(self) -> None:
        cases = (
            (
                "カメラは被写体へゆっくり寄り、右へ横移動し、その後上昇して回転する",
                ("ゆっくり寄り", "右へ横移動"),
                ("上昇", "回転"),
            ),
            (
                "カメラはゆっくり引き、下降し、その後左へパンして回転する",
                ("ゆっくり引き", "下降"),
                ("パン", "回転"),
            ),
        )
        for camera_motion, included, excluded in cases:
            with self.subTest(camera_motion=camera_motion):
                payload = compile_video_api_prompt_v1(
                    cut_contract={
                        "motion_contract": {
                            "motion_brief": "主人公が扉へ一歩進む",
                            "camera_motion": camera_motion,
                        }
                    },
                    tool="kling_3_0",
                )

                camera = _fragment_text(payload, "camera_motion")
                for operation in included:
                    self.assertIn(operation, camera)
                for operation in excluded:
                    self.assertNotIn(operation, camera)

    def test_non_camera_japanese_motion_words_do_not_consume_kling_camera_budget(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": (
                        "主人公が荷車を引き、坂を上昇し、顔を横へ回転する"
                    ),
                    "camera_motion": "カメラは被写体へ寄り、右へ横移動する",
                }
            },
            tool="kling_3_0",
        )

        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("被写体へ寄り", camera)
        self.assertIn("右へ横移動", camera)

    def test_negated_japanese_camera_operation_does_not_consume_kling_budget(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩進む",
                    "camera_motion": "カメラは被写体へ寄り、右へ横移動する",
                }
            },
            direction_notes=("急なカメラ回転は行わない",),
            tool="kling_3_0",
        )

        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("被写体へ寄り", camera)
        self.assertIn("右へ横移動", camera)

    def test_non_kling_camera_projection_does_not_apply_kling_operation_limit(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩進む",
                    "camera_motion": "カメラは左へパンし、上へティルトし、その後ズームする",
                }
            },
            tool="seedance",
        )

        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("左へパン", camera)
        self.assertIn("上へティルト", camera)
        self.assertIn("ズーム", camera)

    def test_non_kling_keeps_all_japanese_camera_operations(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩進む",
                    "camera_motion": (
                        "カメラは被写体へ寄り、右へ横移動し、上昇して回転する"
                    ),
                }
            },
            tool="seedance",
        )

        camera = _fragment_text(payload, "camera_motion")
        for operation in ("寄り", "横移動", "上昇", "回転"):
            with self.subTest(operation=operation):
                self.assertIn(operation, camera)

    def test_authoring_camera_labels_have_normalized_projection_trace_parity(self) -> None:
        for label in ("camera", "カメラ"):
            with self.subTest(label=label):
                payload = compile_video_api_prompt_v1(
                    source_prompt=(
                        "action: 主人公が扉へ一歩進む\n"
                        f"{label}: カメラは被写体へゆっくり寄る"
                    ),
                    tool="kling_3_0",
                )

                projection = payload["projection_review_contract"]
                camera_values = [
                    str(item.get("value") or "")
                    for item in projection["groups"]["camera_motion"]
                ]
                primary_values = [
                    str(item.get("value") or "")
                    for item in projection["groups"]["primary_motion"]
                ]
                active_source_keys = {
                    str(item.get("source_key") or "")
                    for item in projection["active_rules"]
                }

                self.assertIn(
                    "カメラは被写体へゆっくり寄る",
                    "\n".join(camera_values),
                )
                self.assertNotIn(
                    "カメラは被写体へゆっくり寄る",
                    "\n".join(primary_values),
                )
                self.assertIn(
                    "compiler_normalized.authoring_source.camera_motion",
                    active_source_keys,
                )
                self.assertNotIn(
                    "video_generation.prompt_authoring_source",
                    active_source_keys,
                )
                self.assertIn(
                    "カメラは被写体へゆっくり寄る",
                    _fragment_text(payload, "camera_motion"),
                )

    def test_kling_camera_limit_applies_across_non_camera_fragments(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が進む間、カメラは左へパンし上へティルトする",
                    "camera_motion": "その後ズームする",
                }
            },
            tool="kling_3_0",
        )

        self.assertIn("左へパン", _fragment_text(payload, "primary_motion"))
        self.assertIn("上へティルト", _fragment_text(payload, "primary_motion"))
        self.assertNotIn("ズーム", payload["prompt"])
        self.assertIn("camera_motion", payload["omitted_groups"])

    def test_kling_camera_enum_cannot_bypass_exhausted_global_budget(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": (
                        "主人公が進む間、カメラは左へパンし上へティルトする"
                    ),
                    "camera_motion": "slow_push",
                }
            },
            tool="kling_3_0",
        )

        self.assertNotIn("被写体へゆっくり寄る", payload["prompt"])
        self.assertIn("camera_motion", payload["omitted_groups"])

    def test_kling_camera_truncation_does_not_leave_next_operation_modifier(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が進む間、カメラは固定する",
                    "camera_motion": "カメラは被写体へ寄り、右へ横移動する",
                }
            },
            tool="kling_3_0",
        )

        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("被写体へ寄る", camera)
        self.assertNotIn("右へ", camera)
        self.assertNotIn("横移動", camera)

    def test_kling_rejects_three_camera_operations_hidden_in_direction_notes(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "video_api_prompt_exceeds_camera_instruction_limit",
        ):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "主人公が扉へ一歩進む",
                    }
                },
                direction_notes=(
                    "カメラは左へパンし、上へティルトし、その後ズームする",
                ),
                tool="kling_3_0",
            )

    def test_camera_enum_and_handoff_jargon_become_visible_provider_instructions(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "first_frame_contract": {
                    "visible_start_state": {
                        "emotional_state": "sceneの圧力を受けている",
                        "prop_state": "前cutから進んだ小道具・場所の状態が見える",
                    }
                },
                "motion_contract": {
                    "motion_brief": "主人公の視線によってsceneの変化が始まる",
                    "camera_motion": "slow_push",
                    "end_state": "次cutで扱う変化点へ視線が残る",
                    "must_not_add": ["次sceneのreveal"],
                },
            },
            tool="kling_3_0_omni",
            first_frame="assets/scenes/start.png",
        )

        self.assertIn("周囲からの圧力を受けている", _fragment_text(payload, "start_state"))
        self.assertIn("開始画像にある小道具・場所の状態が見える", _fragment_text(payload, "start_state"))
        self.assertIn("画面内の変化が始まる", _fragment_text(payload, "primary_motion"))
        self.assertIn("カメラは被写体へゆっくり寄る", _fragment_text(payload, "camera_motion"))
        self.assertIn("変化点へ視線が残る", _fragment_text(payload, "end_state"))
        self.assertIn("後続の出来事の先取り", _fragment_text(payload, "constraints"))
        self.assertNotIn("slow_push", payload["prompt"])
        self.assertNotIn("scene", payload["prompt"])
        self.assertNotIn("cut", payload["prompt"])

    def test_kling_canonical_motion_cannot_request_a_second_shot(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": (
                        "主人公が扉へ一歩進み、その後フェードして"
                        "別ショットへ切り替わって走り去る"
                    )
                }
            },
            tool="kling_3_0",
        )

        primary_motion = _fragment_text(payload, "primary_motion")
        self.assertNotIn("フェードして", primary_motion)
        self.assertNotIn("別ショットへ切り替わって", primary_motion)
        self.assertNotIn("走り去る", primary_motion)

    def test_canonical_contract_outranks_flat_legacy_and_free_text_sources(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "正本の主動作として扉へ一歩進む",
                    "camera_motion": "正本のカメラとして緩やかに寄る",
                    "end_state": "正本の終了状態として接触前で止まる",
                }
            },
            scene_contract={
                "motion_brief": "旧scene入力の主動作として走り去る",
                "motion_end_state": "旧scene入力の終了状態として扉を通過する",
            },
            video_generation={
                "motion_contract": {
                    "motion_intent": "flat入力の主動作として二歩戻る",
                    "camera_motion": "flat入力のカメラとして急旋回する",
                    "handoff_state": "flat入力の終了状態として振り返る",
                }
            },
            source_prompt="自由入力の主動作としてその場から跳び去る",
        )

        self.assertIn(
            "正本の主動作として扉へ一歩進む",
            _fragment_text(payload, "primary_motion"),
        )
        self.assertIn(
            "正本のカメラとして緩やかに寄る",
            _fragment_text(payload, "camera_motion"),
        )
        self.assertIn(
            "正本の終了状態として接触前で止まる",
            _fragment_text(payload, "end_state"),
        )
        for lower_priority_value in (
            "旧scene入力の主動作として走り去る",
            "旧scene入力の終了状態として扉を通過する",
            "flat入力の主動作として二歩戻る",
            "flat入力のカメラとして急旋回する",
            "flat入力の終了状態として振り返る",
            "自由入力の主動作としてその場から跳び去る",
        ):
            with self.subTest(lower_priority_value=lower_priority_value):
                self.assertNotIn(lower_priority_value, payload["prompt"])

    def test_partial_canonical_contract_fills_only_missing_groups_from_scene_alias(self) -> None:
        payload = compile_video_api_prompt_v1(
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
            _fragment_text(payload, "primary_motion"),
        )
        self.assertIn(
            "旧scene入力から補う終了状態で止まる",
            _fragment_text(payload, "end_state"),
        )
        camera = _fragment_text(payload, "camera_motion")
        self.assertIn("正本のカメラとしてゆっくり寄る", camera)
        self.assertNotIn("旧scene入力の競合カメラとして急旋回する", camera)

    def test_canonical_start_state_suppresses_conflicting_free_text_start_state(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "start_from_visible_state": "正本の開始状態で扉の前に立つ",
                    "motion_brief": "扉へ一歩進む",
                }
            },
            source_prompt="start_from_visible_state: 旧入力の開始状態で床に座る",
        )

        start_state = _fragment_text(payload, "start_state")
        self.assertIn("正本の開始状態で扉の前に立つ", start_state)
        self.assertNotIn("旧入力の開始状態で床に座る", start_state)

    def test_flat_motion_contract_outranks_conflicting_free_text(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={},
            video_generation={
                "motion_contract": {
                    "motion_intent": "flat入力の主動作として扉へ一歩進む"
                }
            },
            source_prompt="自由入力の主動作としてその場から走り去る",
        )

        primary_motion = _fragment_text(payload, "primary_motion")
        self.assertIn("flat入力の主動作として扉へ一歩進む", primary_motion)
        self.assertNotIn("自由入力の主動作としてその場から走り去る", primary_motion)

    def test_embedded_internal_id_is_removed_from_provider_prompt(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が hero_internal_id の扉へ一歩進む",
                },
                "continuity_contract": {
                    "carry_forward_to_next_cut": [
                        "door_internal_id の位置を保つ"
                    ]
                },
            },
            additional_negative_prompt="prop_internal_id を出さない",
        )

        self.assertNotIn("hero_internal_id", payload["prompt"])
        self.assertNotIn("door_internal_id", payload["prompt"])
        self.assertNotIn("prop_internal_id", payload["negative_prompt"])

    def test_embedded_prefixed_event_reveal_and_asset_ids_are_removed(self) -> None:
        for token in (
            "evt_secret_42",
            "event_threshold_7",
            "reveal_fairy_arrival",
            "asset_glass_slipper_2",
            "character_cinderella_1",
        ):
            with self.subTest(token=token):
                payload = compile_video_api_prompt_v1(
                    cut_contract={
                        "motion_contract": {
                            "motion_brief": f"主人公が {token} の位置へ一歩進む",
                        }
                    },
                    tool="kling_3_0",
                )

                self.assertNotIn(token, payload["prompt"])

    def test_flat_and_scene_contract_aliases_compile_when_canonical_is_absent(self) -> None:
        flat_payload = compile_video_api_prompt_v1(
            cut_contract={},
            video_generation={
                "motion_contract": {
                    "motion_intent": "flat入力から扉へ一歩進む",
                    "must_preserve": ["flat入力の顔と衣装"],
                    "must_not_add": ["flat入力にない人物"],
                    "handoff_state": "flat入力の接触前で止まる",
                }
            },
        )
        scene_payload = compile_video_api_prompt_v1(
            cut_contract={},
            scene_contract={
                "motion_brief": "旧scene入力から扉へ一歩進む",
                "motion_end_state": "旧scene入力の接触前で止まる",
                "must_avoid": ["旧scene入力にない人物"],
                "continuity_contract": {
                    "carry_forward_to_next_cut": ["旧scene入力の顔と衣装"]
                },
            },
        )

        self.assertIn(
            "flat入力から扉へ一歩進む",
            _fragment_text(flat_payload, "primary_motion"),
        )
        self.assertIn(
            "flat入力の接触前で止まる",
            _fragment_text(flat_payload, "end_state"),
        )
        self.assertIn("flat入力の顔と衣装", _fragment_text(flat_payload, "continuity"))
        self.assertIn("flat入力にない人物", _fragment_text(flat_payload, "constraints"))
        self.assertIn(
            "旧scene入力から扉へ一歩進む",
            _fragment_text(scene_payload, "primary_motion"),
        )
        self.assertIn(
            "旧scene入力の接触前で止まる",
            _fragment_text(scene_payload, "end_state"),
        )
        self.assertIn(
            "旧scene入力の顔と衣装",
            _fragment_text(scene_payload, "continuity"),
        )
        self.assertIn(
            "旧scene入力にない人物",
            _fragment_text(scene_payload, "constraints"),
        )

        motion_prompt_payload = compile_video_api_prompt_v1(
            cut_contract={},
            video_generation={"motion_prompt": "旧motion_promptから一歩進む"},
        )
        source_prompt_payload = compile_video_api_prompt_v1(
            cut_contract={},
            video_generation={"motion_prompt": "下位のmotion_promptから二歩戻る"},
            source_prompt="明示source_promptから一歩進む",
        )
        self.assertIn(
            "旧motion_promptから一歩進む",
            _fragment_text(motion_prompt_payload, "primary_motion"),
        )
        self.assertIn(
            "明示source_promptから一歩進む",
            _fragment_text(source_prompt_payload, "primary_motion"),
        )
        self.assertNotIn(
            "下位のmotion_promptから二歩戻る",
            source_prompt_payload["prompt"],
        )

    def test_image_to_video_adds_invention_safeguards_without_authored_negatives(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {"motion_brief": "主人公が一度だけ瞬きをする"}
            },
            tool="kling_3_0",
            first_frame="assets/scenes/minimal_start.png",
        )

        constraints = _fragment_text(payload, "constraints")
        self.assertIn("開始画像にない人物", constraints)
        self.assertIn("重要な小道具", constraints)
        self.assertIn("未提示の出来事", constraints)
        self.assertNotIn("assets/scenes/minimal_start.png", payload["prompt"])

    def test_authored_reveal_allowlist_replaces_blanket_invention_prohibition(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": (
                        "光が普段着の少女とかぼちゃを包み、"
                        "舞踏会のドレス、ガラスの靴、馬車へ変える"
                    ),
                    "end_state": (
                        "舞踏会のドレス姿の少女がガラスの靴で立ち、"
                        "隣に馬車が止まっている"
                    ),
                    "allowed_new_reveal_elements": [
                        "舞踏会のドレス姿の少女",
                        "ガラスの靴",
                        "馬車",
                    ],
                }
            },
            tool="kling_3_0",
            first_frame="assets/scenes/transformation_start.png",
            last_frame="assets/scenes/transformation_end.png",
        )

        constraints = _fragment_text(payload, "constraints")
        self.assertIn(
            "主動作によって新しく現れてよいものは、舞踏会のドレス姿の少女、ガラスの靴、馬車",
            constraints,
        )
        self.assertIn("上記の承認済み要素以外", constraints)
        self.assertNotIn(
            "開始画像にない人物、重要な小道具、建築、物語上の未提示の出来事を新しく出さない。",
            constraints,
        )
        self.assertNotIn("舞踏会のドレス姿の少女", payload["negative_prompt"])
        self.assertNotIn("ガラスの靴", payload["negative_prompt"])
        self.assertNotIn("馬車", payload["negative_prompt"])
        self.assertIn("承認済み要素以外", payload["negative_prompt"])
        active_sources = {
            item.get("source_key")
            for item in payload["projection_review_contract"]["active_rules"]
        }
        self.assertIn(
            "cut.cut_contract.motion_contract.allowed_new_reveal_elements",
            active_sources,
        )

    def test_flat_reveal_allowlist_matches_canonical_projection(self) -> None:
        motion = "光が少女を包み、ガラスの靴を新しく出現させる"
        end_state = "少女がガラスの靴を履いて立っている"
        canonical = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": motion,
                    "end_state": end_state,
                    "allowed_new_reveal_elements": ["ガラスの靴"],
                }
            },
            tool="kling_3_0",
        )
        flat = compile_video_api_prompt_v1(
            cut_contract={},
            video_generation={
                "motion_contract": {
                    "motion_intent": motion,
                    "handoff_state": end_state,
                    "allowed_new_reveal_elements": ["ガラスの靴"],
                }
            },
            tool="kling_3_0",
        )

        self.assertEqual(
            _fragment_text(flat, "constraints"),
            _fragment_text(canonical, "constraints"),
        )
        self.assertEqual(flat["negative_prompt"], canonical["negative_prompt"])

    def test_canonical_reveal_allowlist_outranks_conflicting_flat_alias(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "光が少女を包み、ガラスの靴を新しく出現させる",
                    "end_state": "少女がガラスの靴を履いて立っている",
                    "allowed_new_reveal_elements": ["ガラスの靴"],
                }
            },
            video_generation={
                "motion_contract": {
                    "motion_intent": "かぼちゃの馬車を新しく出現させる",
                    "handoff_state": "かぼちゃの馬車が庭に止まっている",
                    "allowed_new_reveal_elements": ["かぼちゃの馬車"],
                }
            },
            tool="kling_3_0",
        )

        constraints = _fragment_text(payload, "constraints")
        self.assertIn("新しく現れてよいものは、ガラスの靴", constraints)
        self.assertNotIn("新しく現れてよいものは、かぼちゃの馬車", constraints)
        self.assertNotIn("かぼちゃの馬車", payload["prompt"])

    def test_reveal_allowlist_rejects_malformed_scalar(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "video_reveal_allowlist_requires_sequence",
        ):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "光が少女を包み、ガラスの靴を新しく出現させる",
                        "end_state": "少女がガラスの靴を履いて立っている",
                        "allowed_new_reveal_elements": "ガラスの靴",
                    }
                }
            )

    def test_reveal_allowlist_rejects_more_than_eight_elements(self) -> None:
        elements = [f"承認済み要素{i}" for i in range(1, 10)]
        with self.assertRaisesRegex(
            ValueError,
            "video_reveal_allowlist_exceeds_limit",
        ):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "、".join(elements) + "が新しく現れる",
                        "end_state": "、".join(elements) + "が画面内に残る",
                        "allowed_new_reveal_elements": elements,
                    }
                }
            )

    def test_reveal_allowlist_rejects_overlap_with_must_not_add(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "video_reveal_allowlist_conflicts_with_forbidden",
        ):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "光が少女を包み、ガラスの靴を新しく出現させる",
                        "end_state": "少女がガラスの靴を履いて立っている",
                        "allowed_new_reveal_elements": ["ガラスの靴"],
                        "must_not_add": ["ガラスの靴"],
                    }
                }
            )

    def test_reveal_allowlist_rejects_element_not_grounded_in_motion_or_end(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "video_reveal_allowlist_not_grounded_in_motion_or_end_state",
        ):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "少女がその場で一度だけ振り返る",
                        "end_state": "少女が閉じた扉を見て止まる",
                        "allowed_new_reveal_elements": ["ガラスの靴"],
                    }
                }
            )

    def test_multi_cut_render_unit_rejects_source_reveal_allowlist_leakage(self) -> None:
        contracts = [
            {
                "motion_contract": {
                    "motion_brief": "光が少女を包み、ガラスの靴を新しく出現させる",
                    "allowed_new_reveal_elements": ["ガラスの靴"],
                }
            },
            {
                "motion_contract": {
                    "motion_brief": "少女がガラスの靴で一歩進む",
                    "end_state": "少女が階段前で止まる",
                }
            },
        ]

        with self.assertRaisesRegex(
            ValueError,
            "video_render_unit_requires_explicit_reveal_authorization",
        ):
            compose_video_render_unit_contract(contracts)

    def test_first_frame_visual_plan_replaces_generic_visible_start_state_prose(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "first_frame_contract": {
                    "visible_start_state": {
                        "character_state": "汎用の人物状態",
                        "prop_state": "開始画像にある小道具・場所の状態が見える",
                        "spatial_state": "汎用の場所",
                        "emotional_state": "周囲からの圧力を受けている",
                    }
                },
                "motion_contract": {"motion_brief": "主人公が顔を扉へ向ける"},
            },
            first_frame="assets/scenes/start.png",
            first_frame_visual_plan={
                "temporal_boundary": {
                    "event_fact_visible_in_still": "主人公の片手が灰の床で止まり、顔は継母の足元へ向いている"
                }
            },
        )

        start = _fragment_text(payload, "start_state")
        self.assertIn("主人公の片手が灰の床で止まり", start)
        self.assertNotIn("汎用の人物状態", start)
        self.assertNotIn("開始画像にある小道具・場所の状態が見える", start)
        self.assertNotIn("周囲からの圧力を受けている", start)

    def test_provider_prompt_excludes_internal_keys_ids_paths_and_other_stage_prose(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            video_generation={
                "motion_contract": {"source_event_beat_id": "legacy_event_internal"},
                "narration": "VIDEO_NARRATION_SECRET",
                "image_prompt": "VIDEO_IMAGE_PROMPT_SECRET",
            },
            story_time="17世紀末フランス・ルイ14世時代",
            time_of_day="夜明け",
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            last_frame="assets/scenes/scene04_cut02_end.png",
        )

        prompt = payload["prompt"]
        leaked_tokens = (
            "cut_contract",
            "motion_contract",
            "first_frame_contract",
            "continuity_contract",
            "narration_contract",
            "image_generation",
            "source_event_beat_id",
            "target_beat",
            "tts_text",
            "image_prompt",
            "source_digest",
            "sha256",
            "start_state",
            "primary_motion",
            "camera_motion",
            "end_state",
            "scene04_cut02_internal",
            "scene04_event_threshold_internal",
            "target_beat_internal_only",
            "hero_internal_id",
            "door_internal_id",
            "legacy_event_internal",
            "NARRATION_SECRET_SHOULD_NOT_SURFACE",
            "NARRATION_ROLE_SECRET",
            "VIDEO_NARRATION_SECRET",
            "IMAGE_PROMPT_SECRET_SHOULD_NOT_SURFACE",
            "IMAGE_API_PROMPT_SECRET",
            "VIDEO_IMAGE_PROMPT_SECRET",
            "image_prompt_hash_internal",
            "REVIEW_INSTRUCTION_SECRET_SHOULD_NOT_SURFACE",
            "assets/",
            ".png",
        )
        for token in leaked_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, prompt)

    def test_empty_optional_values_are_omitted_and_hash_like_absent_values(self) -> None:
        with_empty_values = compile_video_api_prompt_v1(
            cut_contract={
                "first_frame_contract": {"first_frame_brief": "  "},
                "motion_contract": {
                    "motion_brief": "主人公が一度だけ瞬きをする",
                    "camera_motion": "",
                    "environment_motion": [],
                    "emotional_change": None,
                    "end_state": " ",
                    "must_not_add": [],
                },
                "continuity_contract": {
                    "carry_forward_to_next_cut": [],
                    "continuity_risks": {},
                },
            },
            scene_contract={},
            video_generation={"motion_contract": {}},
            source_prompt=" ",
            story_time=" ",
            time_of_day="",
            tool="",
            first_frame="",
            last_frame="",
            direction_notes=("", "  "),
            continuity_notes=(),
        )
        absent_values = compile_video_api_prompt_v1(
            cut_contract={
                "motion_contract": {
                    "motion_brief": "主人公が一度だけ瞬きをする",
                }
            }
        )

        for group in (
            "start_state",
            "camera_motion",
            "environment_motion",
            "emotional_change",
            "end_state",
        ):
            with self.subTest(group=group):
                self.assertIn(group, with_empty_values["omitted_groups"])
                self.assertNotIn(group, _fragment_groups(with_empty_values))

        self.assertEqual(with_empty_values["prompt"], absent_values["prompt"])
        self.assertEqual(with_empty_values["sha256"], absent_values["sha256"])
        self.assertIn("primary_motion", _fragment_groups(with_empty_values))
        self.assertIn(
            "主人公が一度だけ瞬きをする",
            _fragment_text(with_empty_values, "primary_motion"),
        )
        self.assertNotIn("None", with_empty_values["prompt"])
        self.assertNotIn("[]", with_empty_values["prompt"])

    def test_prompt_hash_and_source_digest_are_stable_and_have_distinct_jobs(self) -> None:
        kwargs = {
            "cut_contract": _canonical_cut_contract(),
            "story_time": "17世紀末フランス・ルイ14世時代",
            "time_of_day": "夜明け",
            "tool": "kling_3_0",
            "first_frame": "assets/scenes/scene04_cut02_base.png",
            "duration_seconds": 8,
            "direction_notes": ("主人公の進行方向を画面右へ保つ",),
            "continuity_notes": ("顔と衣装を開始画像と一致させる",),
        }

        first = compile_video_api_prompt_v1(**kwargs)
        second = compile_video_api_prompt_v1(**kwargs)
        reordered_kwargs = dict(kwargs)
        reordered_kwargs["cut_contract"] = _reverse_mapping_order(
            kwargs["cut_contract"]
        )
        reordered = compile_video_api_prompt_v1(**reordered_kwargs)

        self.assertEqual(first["prompt"], second["prompt"])
        self.assertEqual(first["prompt"], reordered["prompt"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["sha256"], reordered["sha256"])
        self.assertEqual(first["source_digest"], second["source_digest"])
        self.assertEqual(first["source_digest"], reordered["source_digest"])
        self.assertRegex(first["source_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            first["sha256"],
            hashlib.sha256(first["prompt"].encode("utf-8")).hexdigest(),
        )

        changed_kwargs = copy.deepcopy(kwargs)
        changed_kwargs["cut_contract"]["motion_contract"]["motion_brief"] = (
            "主人公が扉へ二歩進む"
        )
        changed_kwargs["cut_contract"]["motion_contract"]["subject_motion"] = (
            "主人公が扉へ二歩進む"
        )
        changed = compile_video_api_prompt_v1(**changed_kwargs)

        self.assertNotEqual(first["source_digest"], changed["source_digest"])
        self.assertNotEqual(first["sha256"], changed["sha256"])

        review_only_kwargs = copy.deepcopy(kwargs)
        review_only_kwargs["cut_contract"]["motion_contract"][
            "source_event_beat_id"
        ] = "another_internal_event_boundary"
        review_only_change = compile_video_api_prompt_v1(**review_only_kwargs)

        self.assertEqual(first["prompt"], review_only_change["prompt"])
        self.assertEqual(first["sha256"], review_only_change["sha256"])
        self.assertNotEqual(
            first["source_digest"],
            review_only_change["source_digest"],
        )

    def test_render_unit_review_only_source_cut_change_stales_digest_not_prompt(self) -> None:
        common = {
            "cut_contract": {
                "motion_contract": {
                    "end_state": "扉の前で止まる",
                }
            },
            "source_prompt": "主人公が廊下を進み扉の前で止まる",
            "tool": "kling_3_0",
        }
        before = compile_video_api_prompt_v1(
            **common,
            review_only_dependencies={
                "render_unit_source_cut_ids": ["1", "2"],
                "render_unit_source_cut_contracts": [
                    {"motion_contract": {"motion_brief": "廊下へ一歩進む"}},
                    {"motion_contract": {"motion_brief": "扉の前で止まる"}},
                ],
            },
        )
        after = compile_video_api_prompt_v1(
            **common,
            review_only_dependencies={
                "render_unit_source_cut_ids": ["1", "2"],
                "render_unit_source_cut_contracts": [
                    {"motion_contract": {"motion_brief": "廊下を走り抜ける"}},
                    {"motion_contract": {"motion_brief": "扉の前で止まる"}},
                ],
            },
        )

        self.assertEqual(before["prompt"], after["prompt"])
        self.assertEqual(before["sha256"], after["sha256"])
        self.assertNotEqual(before["source_digest"], after["source_digest"])

    def test_execution_bindings_stale_source_digest_without_changing_prompt_text(self) -> None:
        base = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            duration_seconds=8,
            references=("assets/characters/hero.png",),
            quality="720p",
            aspect_ratio="9:16",
        )
        changed_references = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            duration_seconds=8,
            references=("assets/characters/hero_alt.png",),
            quality="720p",
            aspect_ratio="9:16",
        )
        changed_quality = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            duration_seconds=8,
            references=("assets/characters/hero.png",),
            quality="1080p",
            aspect_ratio="16:9",
        )

        self.assertEqual(base["prompt"], changed_references["prompt"])
        self.assertEqual(base["sha256"], changed_references["sha256"])
        self.assertNotEqual(base["source_digest"], changed_references["source_digest"])
        self.assertNotEqual(base["source_digest"], changed_quality["source_digest"])
        self.assertEqual(
            base["provider_request_binding"],
            {
                "duration_seconds": 8,
                "quality": "720p",
                "aspect_ratio": "9:16",
                "first_frame": "assets/scenes/scene04_cut02_base.png",
                "last_frame": "",
                "references": ["assets/characters/hero.png"],
            },
        )

    def test_review_only_scene_sources_stale_digest_without_surface_text(self) -> None:
        common = {
            "cut_contract": _canonical_cut_contract(),
            "story_time": "17世紀末フランス",
            "time_of_day": "朝",
            "scene_location_mode": "sequence",
            "scene_location_sequence": ("灰の台所", "屋敷の玄関"),
            "scene_location_segments": (
                {
                    "location": "灰の台所",
                    "responsibility": "開始状態を示す",
                },
                {
                    "location": "屋敷の玄関",
                    "responsibility": "退出の結果を示す",
                },
            ),
        }
        first = compile_video_api_prompt_v1(
            **common,
            scene_time_of_day_visual_basis={
                "light_source": "東向きの小窓から入る朝日",
                "brightness": "薄暗い室内に朝日が差す",
                "shadow": "床へ長い影が伸びる",
                "color_temperature": "灰色に淡い暖色が混じる",
            },
        )
        changed = compile_video_api_prompt_v1(
            **common,
            scene_time_of_day_visual_basis={
                "light_source": "北向きの高窓から入る朝日",
                "brightness": "薄暗い室内に朝日が差す",
                "shadow": "床へ短い影が落ちる",
                "color_temperature": "灰色に淡い暖色が混じる",
            },
        )

        self.assertEqual(first["prompt"], changed["prompt"])
        self.assertEqual(first["sha256"], changed["sha256"])
        self.assertNotEqual(first["source_digest"], changed["source_digest"])
        traced = {
            item["source_key"]: item["value"]
            for item in first["projection_review_contract"]["review_only_sources"]
        }
        self.assertEqual(
            traced["scene.location_sequence"],
            ["灰の台所", "屋敷の玄関"],
        )
        self.assertEqual(
            traced["scene.location_segments"][1]["location"],
            "屋敷の玄関",
        )
        self.assertNotIn("東向きの小窓", first["prompt"])
        self.assertNotIn("灰の台所", first["prompt"])

    def test_reference_roles_are_validated_rendered_without_paths_and_digest_bound(self) -> None:
        references = (
            "assets/scenes/start.png",
            "assets/storyboards/ordered.png",
        )
        roles = (
            {"image_index": 1, "role": "start_state_visual_anchor"},
            {"image_index": 2, "role": "ordered_storyboard_sequence_guide"},
        )
        payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="seedance",
            references=references,
            reference_roles=roles,
        )

        continuity = _fragment_text(payload, "continuity")
        self.assertIn("参照画像1は開始状態の基準", continuity)
        self.assertIn("参照画像2は順序付き絵コンテの案内", continuity)
        self.assertNotIn("assets/scenes/start.png", payload["prompt"])
        self.assertNotIn("assets/storyboards/ordered.png", payload["prompt"])
        self.assertEqual(
            payload["provider_request_binding"]["reference_roles"],
            list(roles),
        )
        self.assertEqual(
            payload["video_prompt_ir"]["dependencies"]["reference_roles"],
            list(roles),
        )

        changed = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="seedance",
            references=references,
            reference_roles=(
                {"image_index": 1, "role": "ordered_storyboard_sequence_guide"},
                {"image_index": 2, "role": "start_state_visual_anchor"},
            ),
        )
        self.assertNotEqual(payload["prompt"], changed["prompt"])
        self.assertNotEqual(payload["source_digest"], changed["source_digest"])

        invalid_roles = (
            ({"image_index": 1, "role": "start_state_visual_anchor"},),
            (
                {"image_index": 1, "role": "start_state_visual_anchor"},
                {"image_index": 1, "role": "ordered_storyboard_sequence_guide"},
            ),
            (
                {"image_index": 1, "role": "start_state_visual_anchor"},
                {"image_index": 2, "role": "unknown_role"},
            ),
        )
        for reference_roles in invalid_roles:
            with self.subTest(reference_roles=reference_roles):
                with self.assertRaisesRegex(ValueError, "reference_roles"):
                    compile_video_api_prompt_v1(
                        tool="seedance",
                        references=references,
                        reference_roles=reference_roles,
                    )

    def test_quality_issues_expose_fallback_alternatives_abstract_motion_and_duplicates(self) -> None:
        fallback = compile_video_api_prompt_v1(cut_contract={})
        self.assertIn(
            "video_motion_generated_fallback",
            {issue["code"] for issue in fallback["quality_issues"]},
        )

        contract = {
            "motion_contract": {
                "motion_brief": "主人公または従者の内面の変化を見せる",
                "environment_motion": "主人公または従者の内面の変化を見せる",
                "emotional_change": "主人公または従者の内面の変化を見せる",
                "end_state": "sceneの変化点の物証が残る",
            }
        }
        payload = compile_video_api_prompt_v1(cut_contract=contract)
        issues = payload["quality_issues"]
        issue_codes = {issue["code"] for issue in issues}
        self.assertIn("video_motion_unresolved_alternative", issue_codes)
        self.assertIn("video_motion_abstract_primary", issue_codes)
        self.assertIn("video_motion_abstract_end_state", issue_codes)
        self.assertIn("video_motion_duplicate_environment", issue_codes)
        self.assertIn("video_motion_duplicate_emotion", issue_codes)
        self.assertTrue(all(issue["blocking"] is True for issue in issues))
        self.assertEqual(
            payload["video_prompt_ir"]["quality_issues"],
            issues,
        )

    def test_scene_sequence_overview_is_blocking_in_every_temporal_motion_group(self) -> None:
        sequence = "家族が去る{arrow}助力者が現れる{arrow}衣装が変わる"
        cases = (
            ("first_frame_contract", "first_frame_brief", "start_state"),
            ("motion_contract", "motion_brief", "primary_motion"),
            ("motion_contract", "environment_motion", "environment_motion"),
            ("motion_contract", "emotional_change", "emotional_change"),
            ("motion_contract", "end_state", "end_state"),
        )

        for arrow in ("→", "⇒", "->", "=>"):
            for section, key, expected_group in cases:
                with self.subTest(arrow=arrow, section=section, key=key):
                    contract = {
                        "first_frame_contract": {
                            "first_frame_brief": "主人公は扉の前で止まっている"
                        },
                        "motion_contract": {
                            "motion_brief": "主人公が扉へ一歩だけ進む",
                            "environment_motion": "薄い霧だけが流れる",
                            "emotional_change": "警戒から決意へ変わる",
                            "end_state": "主人公の片足が扉の手前で止まる",
                        },
                    }
                    contract[section][key] = sequence.format(arrow=arrow)

                    payload = compile_video_api_prompt_v1(
                        cut_contract=contract,
                        tool="kling_3_0",
                    )

                    matching = [
                        issue
                        for issue in payload["quality_issues"]
                        if issue["code"] == "video_motion_sequential_overview"
                    ]
                    self.assertTrue(matching)
                    self.assertTrue(all(issue["blocking"] is True for issue in matching))
                    self.assertIn(expected_group, {issue["group"] for issue in matching})

    def test_single_cut_local_state_does_not_trigger_sequential_overview_issue(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract={
                "first_frame_contract": {
                    "first_frame_brief": "主人公は閉じた扉の前で片足を止めている"
                },
                "motion_contract": {
                    "motion_brief": "主人公が扉へ一歩だけ進む",
                    "end_state": "主人公の片足が扉の手前で止まる",
                },
            },
            tool="kling_3_0",
        )

        self.assertNotIn(
            "video_motion_sequential_overview",
            {issue["code"] for issue in payload["quality_issues"]},
        )

    def test_missing_motion_sources_receive_an_explicit_single_motion_fallback(self) -> None:
        payload = compile_video_api_prompt_v1(cut_contract={})

        self.assertEqual(_fragment_groups(payload).count("primary_motion"), 1)
        self.assertTrue(_fragment_text(payload, "primary_motion").strip())
        self.assertIs(payload["provider_policy"]["one_clip_one_intent"], True)

    def test_first_last_frame_mode_uses_last_frame_as_arrival_boundary(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
            last_frame="assets/scenes/scene04_cut02_end.png",
        )

        self.assertEqual(payload["mode"], "first_last_frame")
        self.assertIs(payload["provider_policy"]["first_last_frame_boundary"], True)
        end_state = _fragment_text(payload, "end_state")
        constraints = _fragment_text(payload, "constraints")
        self.assertIn("最後は指定された終了画像", end_state)
        self.assertIn("自然に一致させる", end_state)
        self.assertIn("フェード", constraints)
        self.assertIn("別ショット", constraints)
        self.assertIn("切り替えない", constraints)
        self.assertNotIn("assets/scenes/scene04_cut02_end.png", payload["prompt"])

        first_frame_only = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            first_frame="assets/scenes/scene04_cut02_base.png",
        )
        self.assertEqual(first_frame_only["mode"], "image_to_video")
        self.assertIs(
            first_frame_only["provider_policy"]["first_last_frame_boundary"],
            False,
        )
        self.assertNotIn(
            "指定された終了画像",
            _fragment_text(first_frame_only, "end_state"),
        )

    def test_explicit_empty_last_frame_clears_manifest_fallback(self) -> None:
        payload = compile_video_api_prompt_v1(
            video_generation={
                "first_frame": "assets/scenes/start.png",
                "last_frame": "assets/scenes/end.png",
            },
            last_frame="",
        )

        self.assertEqual(payload["mode"], "image_to_video")
        self.assertEqual(payload["provider_request_binding"]["last_frame"], "")
        self.assertNotIn("指定された終了画像", payload["prompt"])

    def test_last_frame_without_first_frame_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "last_frame_requires_first_frame"):
            compile_video_api_prompt_v1(
                cut_contract={
                    "motion_contract": {
                        "motion_brief": "少女が閉じた扉へ一歩進む",
                        "end_state": "少女が扉の前で止まっている",
                    }
                },
                last_frame="assets/scenes/arrival.png",
            )

    def test_seedance_inlines_additional_negatives_instead_of_approving_an_unsupported_channel(self) -> None:
        payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="seedance",
            additional_negative_prompt="Do not add blue fog.",
        )

        self.assertEqual(payload["provider_policy"]["negative_prompt_mode"], "inline")
        self.assertEqual(payload["negative_prompt"], "")
        self.assertIn("Do not add blue fog", _fragment_text(payload, "constraints"))
        self.assertIn("Do not add blue fog", payload["prompt"])

        reference_payload = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="seedance",
            references=("assets/scenes/opening.png", "assets/storyboards/unit.png"),
        )
        self.assertEqual(reference_payload["mode"], "reference_to_video")
        self.assertEqual(
            reference_payload["projection_review_contract"]["mode"],
            "reference_to_video",
        )
        self.assertIs(
            reference_payload["provider_policy"]["multimodal_reference"],
            True,
        )
        with self.assertRaisesRegex(ValueError, "mutually_exclusive"):
            compile_video_api_prompt_v1(
                cut_contract=_canonical_cut_contract(),
                tool="seedance",
                first_frame="assets/scenes/opening.png",
                references=("assets/storyboards/unit.png",),
            )

        kling = compile_video_api_prompt_v1(
            cut_contract=_canonical_cut_contract(),
            tool="kling_3_0",
            additional_negative_prompt="Do not add blue fog.",
        )
        self.assertEqual(kling["provider_policy"]["negative_prompt_mode"], "separate")
        self.assertIn("Do not add blue fog", kling["negative_prompt"])

    def test_persisted_compiled_motion_prompt_is_not_fed_back_as_authoring_prose(self) -> None:
        first = compile_video_api_prompt_v1(video_generation={}, tool="kling_3_0")
        current = compile_video_api_prompt_v1(
            video_generation={
                "motion_prompt": first["prompt"],
                "api_prompt_payload": first,
            },
            tool="kling_3_0",
        )

        self.assertEqual(current["prompt"], first["prompt"])
        self.assertEqual(current["sha256"], first["sha256"])
        self.assertEqual(current["source_digest"], first["source_digest"])


def _reverse_mapping_order(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _reverse_mapping_order(item)
            for key, item in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_mapping_order(item) for item in value]
    return value


if __name__ == "__main__":
    unittest.main()
