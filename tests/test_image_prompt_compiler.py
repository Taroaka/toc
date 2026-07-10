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
    def test_environment_only_cut_omits_character_object_and_reference_sections(self) -> None:
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=_environment_plan(),
            location_ids=["location_opaque_id"],
        )

        self.assertEqual(payload["policy_version"], IMAGE_API_PROMPT_POLICY_VERSION)
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
            reference_images=[
                "assets/locations/undersea_corridor.png",
                "assets/styles/live_action.png",
            ],
        )

        self.assertIn("references", _groups(payload))
        self.assertIn("[参照画像]", payload["prompt"])
        self.assertIn("場所参照画像1", payload["prompt"])
        self.assertNotIn("assets/", payload["prompt"])
        self.assertNotIn("undersea_corridor", payload["prompt"])

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
        self.assertEqual(first["source_digest"], reordered["source_digest"])
        self.assertNotEqual(first["source_digest"], changed_dependency["source_digest"])

    def test_missing_current_moment_is_rejected(self) -> None:
        plan = _environment_plan()
        plan["temporal_boundary"] = {}
        plan["subject_binding"] = {"primary_subject": {}}

        with self.assertRaisesRegex(ValueError, "drawable_prompt_current_moment_missing"):
            compile_image_api_prompt_v2(first_frame_visual_plan=plan)

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
