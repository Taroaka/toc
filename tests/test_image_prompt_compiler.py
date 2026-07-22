from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.image_prompt_compiler import (
    DRAWABLE_PROMPT_IR_SCHEMA_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION,
    compile_image_api_prompt_v2,
)


def _load_generate_assets_module():
    spec = importlib.util.spec_from_file_location(
        "generate_assets_from_manifest_image_prompt_compiler_test",
        REPO_ROOT / "scripts" / "generate-assets-from-manifest.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _environment_plan() -> dict:
    return {
        "schema_version": "first_frame_visual_plan_v1",
        "source_grounding": {
            "source_event_beat_id": "scene10_event_setup",
            "what_happens": "内部レビュー用の出来事説明",
        },
        "temporal_boundary": {
            "event_fact_visible_in_still": "半分開いた珊瑚門の奥に、発光する回廊が見える",
            "not_yet_happened_in_still": ["門の奥の人物はまだ現れない"],
        },
        "subject_binding": {
            "primary_subject": {"id": "location_opaque_id", "name": "半分開いた珊瑚門"},
            "secondary_subjects": [],
            "background_subjects": [],
        },
        "reference_binding": {
            "character_references": [],
            "object_references": [],
            "location_references": [],
        },
        "character_state_gate": {
            "costume_state": "参照画像とcutの時点に合う衣装状態を維持する。",
            "pose": "行為が始まる直前の姿勢。",
            "gaze": "主要な出来事の証拠へ向く。",
        },
        "object_visibility_gate": {"objects": []},
        "spatial_composition": {
            "foreground": "濡れた珊瑚の床と小さな泡",
            "midground": "半分開いた門",
            "background": "奥へ続く発光する回廊",
            "subject_priority_order": ["半分開いた珊瑚門"],
        },
        "scene_material_pack": {
            "light_source": "上方から揺れる水面光",
            "light_direction": "回廊の奥から手前へ差す",
            "dominant_materials": ["珊瑚、真珠層、濡れた青銅"],
            "story_specific_texture": "濡れた珊瑚と真珠層の艶",
        },
        "scene_state_progression": {"progression_mode": "suspended_moment"},
        "motion_affordance": {
            "camera_start_reason": "motion_brief: カメラが門の奥へ進む",
            "movable_subjects": [{"movement_vector": "次sceneへ進む"}],
        },
    }


def _groups(payload: dict) -> set[str]:
    return {
        str(item["group"])
        for item in payload["drawable_prompt_ir"]["included_fragments"]
    }


class TestImagePromptCompiler(unittest.TestCase):
    def test_manifest_story_time_is_attached_to_scene_compilation_inputs(self) -> None:
        module = _load_generate_assets_module()
        metadata, scenes = module.parse_manifest_yaml(
            """
video_metadata:
  topic: 桃太郎
  time: 室町時代
scenes:
  - scene_id: 1
    time_of_day: 夕方
    image_generation:
      tool: codex_builtin_image
      prompt: 門前に立つ旅人
      output: assets/scenes/scene01.png
"""
        )

        self.assertEqual(metadata["time"], "室町時代")
        self.assertEqual(scenes[0].story_time, "室町時代")
        self.assertEqual(scenes[0].scene_time_of_day, "夕方")

    def test_minimal_manifest_parser_keeps_scene_time_over_nested_visual_plan_copy(self) -> None:
        module = _load_generate_assets_module()
        _metadata, scenes = module._parse_manifest_yaml_minimal(
            """
scenes:
  - scene_id: 1
    time_of_day: 夜
    image_generation:
      first_frame_visual_plan:
        scene_material_pack:
          time_of_day: 朝
      tool: codex_builtin_image
      output: assets/scenes/scene01.png
"""
        )

        self.assertEqual(scenes[0].scene_time_of_day, "夜")

    def test_environment_only_cut_omits_character_object_and_reference_sections(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
        )

        self.assertEqual(payload["policy_version"], IMAGE_API_PROMPT_POLICY_VERSION)
        self.assertIn("画面内の主被写体は、半分開いた珊瑚門", payload["prompt"])
        self.assertNotIn("観客が最初に読む", payload["prompt"])
        self.assertEqual(
            payload["drawable_prompt_ir"]["schema_version"],
            DRAWABLE_PROMPT_IR_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload["drawable_prompt_ir"]["dependencies"],
            {
                "character_ids": [],
                "object_ids": [],
                "location_ids": ["location_opaque_id"],
                "references": [],
                "required_groups": [
                    "style",
                    "current_moment",
                    "primary_subject",
                    "location",
                    "composition",
                    "light_material",
                    "constraints",
                ],
            },
        )
        self.assertFalse({"references", "characters", "objects"} & _groups(payload))
        self.assertNotIn("[参照画像]", payload["prompt"])
        self.assertNotIn("[登場人物]", payload["prompt"])
        self.assertNotIn("[小道具 / 舞台装置]", payload["prompt"])
        self.assertNotIn("location_opaque_id", payload["prompt"])
        self.assertIn("半分開いた珊瑚門", payload["prompt"])
        self.assertIn("発光する回廊", payload["prompt"])

    def test_story_time_is_rendered_as_a_historical_visual_constraint(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="江戸時代",
        )

        self.assertEqual(
            payload["drawable_prompt_ir"]["dependencies"]["story_time"],
            "江戸時代",
        )
        self.assertIn("物語の時代背景は江戸時代", payload["prompt"])
        self.assertIn("衣装、髪型、建築、生活道具、素材、技術水準", payload["prompt"])

    def test_empty_story_time_does_not_add_an_era_placeholder(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="",
        )
        legacy_compatible = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
        )

        self.assertNotIn("物語の時代背景", payload["prompt"])
        self.assertNotIn("〇〇時代", payload["prompt"])
        self.assertNotIn("story_time", payload["drawable_prompt_ir"]["dependencies"])
        self.assertNotIn("story_time", payload["drawable_prompt_ir"]["omitted_groups"])
        self.assertEqual(payload["source_digest"], legacy_compatible["source_digest"])

    def test_scene_time_of_day_is_rendered_as_a_light_and_sky_constraint(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="江戸時代",
            scene_time_of_day="夕方",
        )

        dependencies = payload["drawable_prompt_ir"]["dependencies"]
        self.assertEqual(dependencies["story_time"], "江戸時代")
        self.assertEqual(dependencies["time_of_day"], "夕方")
        self.assertIn("story_time", dependencies["required_groups"])
        self.assertIn("time_of_day", dependencies["required_groups"])
        self.assertIn("物語の時代背景は江戸時代", payload["prompt"])
        self.assertIn("このシーンの時間帯は夕方", payload["prompt"])
        self.assertIn("空の明るさ、自然光と人工光、影、色温度", payload["prompt"])

    def test_open_string_time_contracts_preserve_exact_trimmed_values_and_digest(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="  Victorian era  ",
            scene_time_of_day="  blue hour / night  ",
        )
        punctuation_variant = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="Victorian era",
            scene_time_of_day="blue hour / night。",
        )

        dependencies = payload["drawable_prompt_ir"]["dependencies"]
        self.assertEqual(dependencies["story_time"], "Victorian era")
        self.assertEqual(dependencies["time_of_day"], "blue hour / night")
        self.assertIn("物語の時代背景はVictorian era", payload["prompt"])
        self.assertIn("このシーンの時間帯はblue hour / night", payload["prompt"])
        self.assertNotEqual(payload["source_digest"], punctuation_variant["source_digest"])

    def test_empty_scene_time_of_day_does_not_add_a_placeholder(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            scene_time_of_day="",
        )
        legacy_compatible = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
        )

        self.assertNotIn("このシーンの時間帯", payload["prompt"])
        self.assertNotIn("time_of_day", payload["drawable_prompt_ir"]["dependencies"])
        self.assertNotIn("time_of_day", payload["drawable_prompt_ir"]["omitted_groups"])
        self.assertEqual(payload["source_digest"], legacy_compatible["source_digest"])

    def test_character_cut_includes_only_explicit_character_state(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "若い女性が閉じた扉の前で立ち止まり、扉の隙間へ視線を向けている"
        )
        plan["subject_binding"]["primary_subject"] = {
            "id": "protagonist_fullbody",
            "name": "閉じた扉の前で立ち止まる若い女性",
        }
        plan["character_state_gate"] = {
            "costume_state": "灰の付いた質素な作業着",
            "pose": "肩をすぼめ、片手を胸元に置いて立ち止まる",
            "gaze": "閉じた扉の細い光へ向く",
            "expression": "期待とためらいが同時に読める表情",
            "hand_position": "片手は胸元、もう片方は身体の横",
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=["protagonist_fullbody"],
            location_ids=["kitchen_door"],
        )

        self.assertIn("characters", _groups(payload))
        self.assertNotIn("objects", _groups(payload))
        self.assertIn("[登場人物]", payload["prompt"])
        self.assertIn("期待とためらい", payload["prompt"])
        self.assertIn("閉じた扉の細い光", payload["prompt"])
        self.assertNotIn("protagonist_fullbody", payload["prompt"])
        self.assertNotIn("小道具への接触状態", payload["prompt"])

    def test_character_state_bindings_render_each_visible_person_by_name(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "王子が階段の上から、質素な服へ戻った若い女性を見ている"
        )
        plan["character_state_gate"] = {
            "pose": "二人が階段上で離れて立っている",
            "character_states": [
                {
                    "character_id": "prince_fullbody",
                    "character_name": "王子",
                    "appearance_continuity": {
                        "costume_state": "濃紺の宮廷礼装",
                        "forbidden_costume_states": ["現代のスーツ"],
                    },
                },
                {
                    "character_id": "heroine_after_midnight",
                    "character_name": "若い女性",
                    "appearance_continuity": {
                        "costume_state": "魔法が解けた後の質素な衣装",
                        "forbidden_costume_states": ["舞踏会ドレス"],
                    },
                },
            ],
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=["prince_fullbody", "heroine_after_midnight"],
        )
        reversed_payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=["heroine_after_midnight", "prince_fullbody"],
        )

        self.assertIn(
            "王子の衣装は、濃紺の宮廷礼装を維持し、現代のスーツには変えない。",
            payload["prompt"],
        )
        self.assertIn(
            "若い女性の衣装は、魔法が解けた後の質素な衣装を維持し、舞踏会ドレスには変えない。",
            payload["prompt"],
        )
        self.assertNotIn("prince_fullbody", payload["prompt"])
        self.assertNotIn("heroine_after_midnight", payload["prompt"])
        self.assertEqual(payload["prompt"], reversed_payload["prompt"])

    def test_character_state_binding_must_target_a_visible_character(self) -> None:
        plan = _environment_plan()
        plan["character_state_gate"] = {
            "character_states": [
                {
                    "character_id": "unbound_character",
                    "character_name": "画面外の人物",
                    "appearance_continuity": {"costume_state": "赤い外套"},
                }
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            "drawable_prompt_character_state_binding_unbound",
        ):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                character_ids=["visible_character"],
            )

        with self.assertRaisesRegex(
            ValueError,
            "drawable_prompt_character_state_binding_unbound",
        ):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                character_ids=[],
            )

    def test_character_state_binding_must_match_reference_identity(self) -> None:
        plan = _environment_plan()
        plan["reference_binding"]["character_references"] = [
            {
                "target_character_id": "prince_fullbody",
                "target_character_name": "王子",
                "target_identity_name": "王子",
            }
        ]
        plan["character_state_gate"] = {
            "character_states": [
                {
                    "character_id": "prince_fullbody",
                    "character_name": "シンデレラ",
                    "appearance_continuity": {"costume_state": "宮廷礼装"},
                }
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            "drawable_prompt_character_state_binding_identity_mismatch",
        ):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                character_ids=["prince_fullbody"],
            )

    def test_character_state_binding_rejects_invalid_or_conflicting_states(self) -> None:
        cases = (
            (
                {"costume_state": "宮廷礼装", "forbidden_costume_states": [{}]},
                "drawable_prompt_forbidden_costume_state_invalid",
            ),
            (
                {
                    "costume_state": "宮廷礼装",
                    "forbidden_costume_states": ["宮廷礼装"],
                },
                "drawable_prompt_character_appearance_state_conflict",
            ),
        )
        for appearance, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                plan = _environment_plan()
                plan["character_state_gate"] = {
                    "character_states": [
                        {
                            "character_id": "visible_character",
                            "character_name": "若い女性",
                            "appearance_continuity": appearance,
                        }
                    ]
                }
                with self.assertRaisesRegex(ValueError, expected_error):
                    compile_image_api_prompt_v2(
                        first_frame_visual_plan=plan,
                        character_ids=["visible_character"],
                    )

    def test_object_cut_uses_drawable_object_name_without_character_filler(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "石段の前景に片方のガラスの靴が残り、奥の扉だけが開いている"
        )
        plan["subject_binding"]["primary_subject"] = {
            "id": "glass_slipper",
            "name": "石段に残された片方のガラスの靴",
        }
        plan["object_visibility_gate"] = {
            "objects": [
                {
                    "object_id": "glass_slipper",
                    "object_name": "片方のガラスの靴",
                    "visibility_in_this_cut": "clearly_visible",
                    "object_state": "片方だけが石段の端に残っている",
                    "story_meaning_in_this_cut": "去った人物の身元を示す唯一の証拠",
                    "required_screen_position": "foreground",
                }
            ]
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            object_ids=["glass_slipper"],
            location_ids=["palace_stairs"],
        )

        self.assertIn("objects", _groups(payload))
        self.assertNotIn("characters", _groups(payload))
        self.assertIn("[小道具 / 舞台装置]", payload["prompt"])
        self.assertIn("片方のガラスの靴", payload["prompt"])
        self.assertIn("石段の端", payload["prompt"])
        self.assertNotIn("glass_slipper", payload["prompt"])
        self.assertNotIn("[登場人物]", payload["prompt"])

    def test_dependency_id_embedded_in_drawable_source_is_removed(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "馬車が門前を離れ始め、車輪と月光の道が見える"
        )
        plan["subject_binding"]["primary_subject"] = {
            "id": "pumpkin_carriage",
            "name": "門前を離れ始めた馬車",
        }
        plan["object_visibility_gate"] = {
            "objects": [
                {
                    "object_id": "pumpkin_carriage",
                    "object_name": "pumpkin_carriage",
                    "object_state": (
                        "pumpkin_carriage をこのcutの出来事に関係する実物として画面内に置く"
                    ),
                    "story_meaning_in_this_cut": "車輪と月光の道が出発を示す",
                    "required_screen_position": "foreground",
                }
            ]
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            object_ids=["pumpkin_carriage"],
            location_ids=["gate_road"],
        )

        self.assertNotIn("pumpkin_carriage", payload["prompt"])
        self.assertNotIn("gate_road", payload["prompt"])
        self.assertIn("車輪と月光の道", payload["prompt"])

    def test_reference_section_is_conditional_and_never_renders_paths(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["undersea_corridor"],
            scene_time_of_day="夕方",
            reference_images=[
                "assets/locations/undersea_corridor.png",
                "assets/styles/live_action.png",
            ],
        )

        self.assertIn("references", _groups(payload))
        self.assertIn("[参照画像]", payload["prompt"])
        self.assertIn("場所参照画像1", payload["prompt"])
        self.assertIn("空間構造、固定素材の同一性", payload["prompt"])
        self.assertIn("光と色温度はこのシーンの時間帯を優先", payload["prompt"])
        self.assertNotIn("空間構造、素材、光の同一性", payload["prompt"])
        self.assertNotIn("assets/", payload["prompt"])
        self.assertNotIn("undersea_corridor", payload["prompt"])

        legacy_without_daypart = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["undersea_corridor"],
            reference_images=["assets/locations/undersea_corridor.png"],
        )
        self.assertNotIn(
            "光と色温度はこのシーンの時間帯を優先",
            legacy_without_daypart["prompt"],
        )

    def test_character_reference_instruction_names_the_bound_subject(self) -> None:
        plan = _environment_plan()
        plan["reference_binding"]["character_references"] = [
            {
                "path": "assets/characters/cinderella.png",
                "target_character_id": "cinderella",
                "target_character_name": "シンデレラ",
                "role_in_frame": "primary_subject",
            }
        ]

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            reference_images=["assets/characters/cinderella.png"],
        )

        self.assertIn("人物参照画像1（シンデレラ）", payload["prompt"])
        self.assertNotIn("assets/characters", payload["prompt"])

    def test_scene_time_of_day_rejects_conflicting_positive_material_light(self) -> None:
        plan = _environment_plan()
        plan["scene_material_pack"] = {
            "light_source": "低い自然光",
            "dominant_materials": [
                "薄暗い屋内、朝夕どちらにも寄りすぎない低い自然光"
            ],
        }

        with self.assertRaisesRegex(ValueError, "drawable_prompt_time_of_day_conflict"):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                scene_time_of_day="朝",
            )

    def test_negative_opposing_light_marker_does_not_trigger_time_conflict(self) -> None:
        plan = _environment_plan()
        plan["scene_material_pack"] = {
            "light_source": "月光",
            "dominant_materials": ["深夜の門前、朝日なし、昼光なし"],
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            scene_time_of_day="深夜",
        )

        self.assertIn("深夜", payload["prompt"])

    def test_sequential_delta_renders_only_current_visible_state(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "馬車が門前を離れ始め、車輪と月光の道が見える"
        )
        plan["subject_binding"]["primary_subject"] = {
            "id": "pumpkin_carriage",
            "name": "門前を離れ始めた馬車",
        }
        plan["object_visibility_gate"] = {
            "objects": [
                {
                    "object_id": "pumpkin_carriage",
                    "object_name": "門前を離れ始めた馬車",
                    "object_state": "車輪が月光の道へ向いている",
                    "required_screen_position": "foreground",
                }
            ]
        }
        plan["scene_state_progression"] = {
            "progression_mode": "sequential_state_progression",
            "state_after_previous_cut": "女性が馬車の扉に片足をかけている",
            "state_visible_in_first_frame": "馬車が門前を離れ始め、車輪が月光の道へ向く",
            "visible_state_delta_from_previous_cut": "車輪が道へ向き、門との間に距離が生まれている",
            "must_not_revert_to": "乗る前の門前待機",
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            object_ids=["pumpkin_carriage"],
            location_ids=["gate_road"],
        )

        self.assertIn("current_state_delta", _groups(payload))
        self.assertIn("車輪が道へ向き", payload["prompt"])
        self.assertNotIn("女性が馬車の扉に片足", payload["prompt"])
        self.assertNotIn("前cut", payload["prompt"])
        self.assertNotIn("previous", payload["prompt"])

    def test_generic_motion_and_internal_metadata_are_not_rendered(self) -> None:
        plan = _environment_plan()
        plan["scene_material_pack"] = {
            "light_source": "scene固有の自然な光源",
            "light_direction": "人物と小道具の形が読める方向",
            "dominant_materials": ["場所固有の床、壁、衣服、小道具の質感"],
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            location_ids=["location_opaque_id"],
        )

        self.assertNotIn("light_material", _groups(payload))
        self.assertNotIn("この項目は、他の具体描写", payload["prompt"])
        self.assertNotIn("motion_brief", payload["prompt"])
        self.assertNotIn("次scene", payload["prompt"])
        self.assertNotIn("source_event_beat_id", payload["prompt"])
        self.assertNotIn("scene10_event_setup", payload["prompt"])

    def test_cut_local_visible_evidence_is_rendered_without_abstract_story_language(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"] = {
            "event_fact_visible_in_still": (
                "扉の前の現在位置と場のルールが一目で分かる"
            ),
            "first_visible_moment": "主人公の制限と場所の圧力が見える",
        }
        plan["visual_translation"] = {
            "concrete_visible_evidence": [
                {
                    "source_field": "viewer_contract.must_show",
                    "must_be_drawn_as": "半分開いた扉",
                },
                {
                    "source_field": "viewer_contract.visual_evidence",
                    "must_be_drawn_as": "濡れた珊瑚の床",
                },
            ]
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            location_ids=["location_opaque_id"],
        )

        self.assertIn("半分開いた扉", payload["prompt"])
        self.assertIn("濡れた珊瑚の床", payload["prompt"])
        self.assertNotIn("場のルール", payload["prompt"])
        self.assertNotIn("主人公の制限", payload["prompt"])
        self.assertNotIn("場所の圧力", payload["prompt"])

    def test_compilation_is_stable_and_preserves_review_metadata_outside_prompt(self) -> None:
        kwargs = {
            "first_frame_visual_plan": _environment_plan(),
            "location_ids": ["location_opaque_id"],
            "review_metadata": {
                "shot_design_contract": {"shot_role": "establishing"},
                "cut_location_frame_plan": {"location_zone_id": "corridor"},
            },
        }

        first = compile_image_api_prompt_v2(**kwargs)
        second = compile_image_api_prompt_v2(**kwargs)

        self.assertEqual(first["prompt"], second["prompt"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertRegex(first["source_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["source_digest"], second["source_digest"])
        self.assertEqual(first["shot_design_contract"], {"shot_role": "establishing"})
        self.assertNotIn("shot_design_contract", first["prompt"])

        reordered_plan = dict(reversed(tuple(_environment_plan().items())))
        reordered = compile_image_api_prompt_v2(
            first_frame_visual_plan=reordered_plan,
            location_ids=["location_opaque_id"],
            review_metadata={"shot_design_contract": {"shot_role": "closeup"}},
        )
        changed_dependency = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["another_location_id"],
        )
        changed_story_time = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            story_time="江戸時代",
        )
        changed_scene_time_of_day = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
            scene_time_of_day="夜",
        )
        self.assertEqual(first["source_digest"], reordered["source_digest"])
        self.assertNotEqual(first["source_digest"], changed_dependency["source_digest"])
        self.assertNotEqual(first["source_digest"], changed_story_time["source_digest"])
        self.assertNotEqual(first["source_digest"], changed_scene_time_of_day["source_digest"])

    def test_missing_current_moment_is_rejected(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"] = {}
        plan["subject_binding"] = {"primary_subject": {}}

        with self.assertRaisesRegex(ValueError, "drawable_prompt_current_moment_missing"):
            compile_image_api_prompt_v2(first_frame_visual_plan=plan)

    def test_unresolved_visual_alternative_is_rejected_before_provider_prompt(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "若い女性の手元または表情に緊張が見える"
        )

        with self.assertRaisesRegex(ValueError, "drawable_prompt_unresolved_alternative"):
            compile_image_api_prompt_v2(first_frame_visual_plan=plan)

    def test_abstract_design_placeholder_is_rejected_before_provider_prompt(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "変化の証拠が画面内に残る"
        )

        with self.assertRaisesRegex(ValueError, "drawable_prompt_abstract_placeholder"):
            compile_image_api_prompt_v2(first_frame_visual_plan=plan)

    def test_scene_sequence_overview_is_rejected_before_provider_prompt(self) -> None:
        cases = (
            (
                "current_moment",
                "→",
                lambda plan, value: plan["temporal_boundary"].__setitem__(
                    "event_fact_visible_in_still", value
                ),
                {},
            ),
            (
                "character_pose",
                "⇒",
                lambda plan, value: plan["character_state_gate"].__setitem__(
                    "pose", value
                ),
                {"character_ids": ["hero"]},
            ),
            (
                "foreground",
                "->",
                lambda plan, value: plan["spatial_composition"].__setitem__(
                    "foreground", value
                ),
                {"location_ids": ["location_opaque_id"]},
            ),
            (
                "state_delta",
                "=>",
                lambda plan, value: plan["scene_state_progression"].update(
                    {
                        "progression_mode": "sequential_state_progression",
                        "state_visible_in_first_frame": "炉の前に立っている",
                        "visible_state_delta_from_previous_cut": value,
                    }
                ),
                {},
            ),
        )
        for label, arrow, inject, kwargs in cases:
            with self.subTest(label=label, arrow=arrow):
                plan = _environment_plan()
                sequence = f"炉を掃除する {arrow} 籠を置かれる {arrow} 一人だけ残される"
                inject(plan, sequence)

                with self.assertRaisesRegex(
                    ValueError, "drawable_prompt_sequential_overview"
                ):
                    compile_image_api_prompt_v2(
                        first_frame_visual_plan=plan,
                        **kwargs,
                    )

    def test_broken_particle_join_is_rejected_before_provider_prompt(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"]["event_fact_visible_in_still"] = (
            "指先がガラスの靴をの手前で止まっている"
        )

        with self.assertRaisesRegex(ValueError, "drawable_prompt_broken_japanese_join"):
            compile_image_api_prompt_v2(first_frame_visual_plan=plan)

    def test_reference_uses_current_cut_plan_for_composition_and_state(self) -> None:
        plan = _environment_plan()

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            reference_images=["assets/locations/room.png"],
            scene_time_of_day="朝",
        )

        self.assertIn("構図と状態はこの場面の記述を優先する", payload["prompt"])
        self.assertNotIn("構図と状態はこの画像の描写に合わせる", payload["prompt"])

    def test_minimal_cut_omits_unprovided_subject_and_composition_without_filler(self) -> None:
        plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "半分開いた扉から細い朝日が差している"
            },
            "subject_binding": {},
            "spatial_composition": {},
        }

        payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan)

        self.assertEqual(
            _groups(payload),
            {"style", "current_moment", "constraints"},
        )
        self.assertNotIn("primary_subject", payload["drawable_prompt_ir"]["dependencies"]["required_groups"])
        self.assertNotIn("composition", payload["drawable_prompt_ir"]["dependencies"]["required_groups"])
        self.assertNotIn("観客が最初に読む主被写体", payload["prompt"])
        self.assertNotIn("最初に読める構図", payload["prompt"])

    def test_not_yet_constraints_keep_drawable_name_but_drop_ids_and_review_metadata(self) -> None:
        plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "灰の台所の閉じた扉に朝の光が細く差している",
                "not_yet_happened_in_still": [
                    "ガラスの靴",
                    "future_artifact_id",
                    "source_event_contract.forbidden_reveal_info_ids",
                ],
            }
        }

        payload = compile_image_api_prompt_v2(first_frame_visual_plan=plan)

        self.assertIn("まだ描かないものは、ガラスの靴。", payload["prompt"])
        self.assertNotIn("future_artifact_id", payload["prompt"])
        self.assertNotIn("source_event_contract", payload["prompt"])
        constraints = next(
            fragment["text"]
            for fragment in payload["drawable_prompt_ir"]["included_fragments"]
            if fragment["group"] == "constraints"
        )
        self.assertIn("ガラスの靴", constraints)
        self.assertNotIn("future_artifact_id", constraints)

    def test_declared_dependency_without_concrete_drawable_state_is_rejected(self) -> None:
        plan = {
            "temporal_boundary": {
                "event_fact_visible_in_still": "半分開いた扉から細い朝日が差している"
            }
        }

        with self.assertRaisesRegex(ValueError, "drawable_prompt_character_state_missing"):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                character_ids=["hero"],
            )
        with self.assertRaisesRegex(ValueError, "drawable_prompt_object_state_missing"):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                object_ids=["key"],
            )
        with self.assertRaisesRegex(ValueError, "drawable_prompt_location_state_missing"):
            compile_image_api_prompt_v2(
                first_frame_visual_plan=plan,
                location_ids=["room"],
            )

    def test_review_metadata_field_names_cannot_enter_drawable_prompt(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"] = {
            "event_fact_visible_in_still": "shot_design_contract: establishing。扉が半分開いている"
        }
        plan["visual_translation"] = {
            "concrete_visible_evidence": [
                {"must_be_drawn_as": "半分開いた珊瑚門と濡れた床"}
            ]
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            location_ids=["location_opaque_id"],
        )

        self.assertNotIn("shot_design_contract", payload["prompt"])
        self.assertIn("半分開いた珊瑚門", payload["prompt"])

    def test_bare_scene_selector_cannot_enter_drawable_prompt(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"] = {
            "event_fact_visible_in_still": "scene10 の台所に半分開いた扉がある"
        }
        plan["visual_translation"] = {
            "concrete_visible_evidence": [
                {"must_be_drawn_as": "灰の台所にある半分開いた扉"}
            ]
        }

        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            location_ids=["location_opaque_id"],
        )

        self.assertNotIn("scene10", payload["prompt"])
        self.assertIn("灰の台所", payload["prompt"])


class TestGenerateAssetsCompilerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_generate_assets_module()

    def test_new_payload_is_v2_and_does_not_require_legacy_prompt(self) -> None:
        manifest_yaml = """
video_metadata:
  topic: "海底の門"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        cut_contract:
          cut_function: setup
          viewer_contract:
            visual_proof: "半分開いた門の奥に回廊が見える"
            must_show: ["半分開いた門"]
          cinematic_contract:
            subject_priority: {primary: "半分開いた門"}
            screen_geography:
              foreground: "濡れた珊瑚の床"
              midground: "半分開いた門"
              background: "発光する回廊"
          first_frame_contract:
            event_fact_visible_in_still: "半分開いた門の奥に発光する回廊が見える"
            first_frame_brief: "半分開いた門の奥に発光する回廊が見える"
        still_image_plan: {mode: generate_still, generation_status: missing}
        image_generation:
          tool: codex_builtin_image
          character_ids: []
          object_ids: []
          location_ids: [undersea_gate]
          output: assets/scenes/scene1_cut1.png
"""
        _, _, scenes = self.module.parse_manifest_yaml_full(manifest_yaml)

        payload = self.module._build_image_api_prompt_payload(scenes[0])

        self.assertEqual(payload["policy_version"], "image_api_prompt_v2")
        self.assertNotIn("[登場人物]", payload["prompt"])
        self.assertNotIn("[小道具 / 舞台装置]", payload["prompt"])
        self.assertTrue(
            self.module._should_generate_image_scene(
                scenes[0], allowed_story_modes={"generate_still"}, base_dir=REPO_ROOT
            )
        )

    def test_existing_v1_payload_remains_frozen(self) -> None:
        manifest_yaml = """
video_metadata: {topic: "legacy"}
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: codex_builtin_image
          prompt: "legacy authoring prompt"
          output: assets/scenes/scene1_cut1.png
          api_prompt_payload:
            policy_version: image_api_prompt_v1
            prompt: "frozen v1 api prompt"
            shot_design_contract: {shot_role: establishing}
            cut_location_frame_plan: {location_zone_id: room}
            cut_visual_delta: {this_cut_new_information: door}
            blocking_and_interaction: {character_blocking: {gaze_target: door}}
"""
        _, _, scenes = self.module.parse_manifest_yaml_full(manifest_yaml)

        payload = self.module._image_api_prompt_payload_for_scene(scenes[0])

        self.assertEqual(payload["policy_version"], "image_api_prompt_v1")
        self.assertEqual(payload["prompt"], "frozen v1 api prompt")

    def test_v2_runtime_gate_rejects_ir_metadata_names_in_prompt(self) -> None:
        manifest_yaml = """
video_metadata: {topic: "metadata leak"}
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: codex_builtin_image
          output: assets/scenes/scene1_cut1.png
"""
        _, _, scenes = self.module.parse_manifest_yaml_full(manifest_yaml)

        for leaked_name in (
            "drawable_prompt_ir",
            "dependencies",
            "included_fragments",
            "omitted_groups",
            "required_groups",
            "compiler_version",
        ):
            with self.subTest(leaked_name=leaked_name):
                with self.assertRaisesRegex(
                    SystemExit,
                    "api_prompt_contains_no_yaml_field_names",
                ):
                    self.module._validate_image_api_prompt_payload(
                        scenes[0],
                        {
                            "policy_version": "image_api_prompt_v2",
                            "prompt": f"実写映画調。{leaked_name} は内部メタデータ。",
                        },
                    )


if __name__ == "__main__":
    unittest.main()
