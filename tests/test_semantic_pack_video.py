from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_video import collect_entries
from toc.video_prompt_compiler import compile_video_api_prompt_v1
from toc.video_prompt_projection_registry import (
    VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
)


BUILD_PACK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build-semantic-review-pack.py"


def load_pack_builder():
    spec = importlib.util.spec_from_file_location(
        "build_semantic_review_pack_video_motion",
        BUILD_PACK_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BUILD_PACK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANIFEST = """# Manifest

```yaml
quality_check:
  review_contract:
    render_meaning: "final video preserves the approved story order"
render:
  output: "dist/final_story.mp4"
  sampled_frames:
    - "logs/review/semantic/render_frame001.jpg"
    - "logs/review/semantic/render_frame002.jpg"
  contact_sheet: "logs/review/semantic/render_contact_sheet.jpg"
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        cut_contract:
          target_beat: "Cinderella sees the invitation"
          must_show: ["Cinderella", "invitation"]
        video_generation:
          tool: "kling_3_0"
          motion_prompt: "Cinderella slowly lifts the invitation toward the window light."
          motion_contract:
            motion_intent: "Cinderella notices the invitation with restrained hope."
            must_preserve: ["Cinderella", "invitation", "window light"]
            must_not_add: ["palace arrival"]
            handoff_state: "The invitation is visible in her hand."
          first_frame: "assets/scenes/scene03_cut01.png"
          last_frame: "assets/scenes/scene03_cut01_end.png"
          duration_seconds: 6
          output: "assets/videos/scene03_cut01.mp4"
          contact_sheet: "logs/review/semantic/scene3_cut1_contact_sheet.jpg"
          retry_history:
            - status: "failed"
              reason: "provider timeout"
          retry_count: 1
      - cut_id: 2
        cut_status: deleted
        video_generation:
          motion_prompt: "deleted"
          output: "assets/videos/deleted.mp4"
  - scene_id: 4
    cuts:
      - cut_id: 1
        audio:
          narration:
            output: "assets/audio/scene04_cut01.mp3"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene04_cut02.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        semantic_contract:
          target_beat: "The coach leaves for the palace"
        video_generation:
          prompt: "The coach rolls away under lantern light."
          first_frame_image: "assets/scenes/scene04_cut01.png"
          sampled_frames:
            - "logs/review/semantic/scene4_unit1_frame001.jpg"
            - "logs/review/semantic/scene4_unit1_frame002.jpg"
          failures:
            - "first attempt drifted from coach"
          output: "assets/videos/scene04_unit01.mp4"
```
"""


class TestSemanticPackVideo(unittest.TestCase):
    def _manifest_with_materialized_payload(
        self,
        payload: dict[str, object],
        *,
        authoring_source: str = "主人公が窓辺へ一歩進む",
    ) -> dict[str, object]:
        return {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {
                                "tool": "kling_3_0",
                                "prompt_authoring_source": authoring_source,
                                "api_prompt_payload": payload,
                            },
                        }
                    ],
                }
            ]
        }

    def test_render_units_are_the_only_provider_entries_when_declared(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {
                                "tool": "seedance",
                                "motion_prompt": "The subject takes one step.",
                            },
                        },
                        {
                            "cut_id": 2,
                            "video_generation": {
                                "tool": "seedance",
                                "motion_prompt": "The subject stops.",
                            },
                        },
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1, 2],
                            "video_generation": {
                                "tool": "seedance",
                                "motion_prompt": "The subject crosses the room and stops.",
                            },
                        }
                    ],
                }
            ]
        }

        entries = collect_entries("video_motion", Path("."), manifest)

        self.assertEqual([entry["selector"] for entry in entries], ["scene1_unit1"])
        dependencies = entries[0]["provider_prompt_payload"]["projection_review_contract"]
        self.assertEqual(dependencies["provider"], "seedance")

    def test_render_unit_uses_its_literal_first_source_cut_visual_plan(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": {
                                "motion_contract": {"motion_brief": "She reaches for the door."}
                            },
                            "image_generation": {
                                "first_frame_visual_plan": {
                                    "temporal_boundary": {
                                        "first_visible_moment": "She stands beside the closed door."
                                    }
                                }
                            },
                        },
                        {"cut_id": 2, "cut_contract": {}},
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1, 2],
                            "video_generation": {
                                "tool": "seedance",
                                "first_frame": "assets/scenes/scene1_cut1.png",
                                "motion_prompt": "She reaches for the door.",
                            },
                        }
                    ],
                }
            ]
        }

        entry = collect_entries("video_motion", Path("."), manifest)[0]
        design_source = entry["provider_prompt_payload"]["video_prompt_ir"]

        self.assertIn("She stands beside the closed door", entry["provider_prompt"])
        self.assertEqual(design_source["mode"], "image_to_video")

    def test_video_motion_review_guidance_defines_projection_pass_fail_criteria(self) -> None:
        builder = load_pack_builder()

        guidance = "\n".join(builder._stage_specific_review_instructions("video_motion"))

        for expected in (
            "projection_review_contract",
            "video_prompt_ir",
            "one primary motion",
            "maximum of two camera",
            "historical time",
            "time_of_day",
            "quality_issues",
            "observable action",
            "unresolved alternatives",
            "reference role",
            "near-duplicate primary motions",
            "reason keys",
        ):
            self.assertIn(expected, guidance)

        for expected in (
            "source causal action",
            "start state",
            "previous end state",
            "same location",
            "acquired",
            "later possession",
            "video_prompt_source_causal_action_missing",
            "video_prompt_start_preconsumes_primary_motion",
            "video_prompt_adjacent_cut_state_reset",
            "video_prompt_prop_possession_jump",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, guidance)

    def test_video_motion_scope_diagnostics_fail_blocking_quality_issue_entries(self) -> None:
        builder = load_pack_builder()
        diagnostics = builder.entry_diagnostics(
            [
                {
                    "id": "video_motion:scene1_cut1",
                    "quality_issues": [
                        {
                            "code": "video_motion_abstract_primary",
                            "blocking": True,
                        },
                        {
                            "code": "advisory_only",
                            "blocking": False,
                        },
                    ],
                    "provider_prompt_payload": {
                        "quality_issues": [
                            {
                                "code": "video_motion_abstract_primary",
                                "blocking": True,
                            }
                        ]
                    },
                },
                {
                    "id": "video_motion:scene1_cut2",
                    "provider_prompt_payload": {
                        "quality_issues": [],
                        "video_prompt_ir": {
                            "quality_issues": [
                                {
                                    "code": "video_motion_abstract_end_state",
                                    "blocking": True,
                                },
                                {
                                    "code": "   ",
                                    "blocking": True,
                                }
                            ]
                        },
                    },
                },
            ]
        )

        self.assertEqual(diagnostics["blocking_quality_issue_count"], 3)
        self.assertEqual(
            diagnostics["blocking_quality_issue_entries"],
            ["video_motion:scene1_cut1", "video_motion:scene1_cut2"],
        )
        self.assertEqual(
            diagnostics["blocking_quality_issue_codes"],
            [
                "video_motion_abstract_end_state",
                "video_motion_abstract_primary",
                "video_motion_blocking_quality_issue",
            ],
        )
        self.assertEqual(
            diagnostics["failed_selectors"],
            ["video_motion:scene1_cut1", "video_motion:scene1_cut2"],
        )

    def test_video_motion_collects_cut_and_render_unit_prompts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            entries = collect_entries("video_motion", run_dir)

            selectors = [entry["selector"] for entry in entries]
            self.assertEqual(selectors, ["scene3_cut1", "scene4_unit1"])
            self.assertEqual(entries[0]["motion_prompt"], "Cinderella slowly lifts the invitation toward the window light.")
            self.assertEqual(entries[0]["provider_prompt_payload"]["policy_version"], "video_api_prompt_v1")
            self.assertEqual(entries[0]["provider_prompt"], entries[0]["provider_prompt_payload"]["prompt"])
            self.assertIn(
                "Cinderella notices the invitation with restrained hope",
                entries[0]["provider_prompt"],
            )
            self.assertNotIn(
                "Cinderella slowly lifts the invitation toward the window light",
                entries[0]["provider_prompt"],
            )
            self.assertNotIn("motion_intent:", entries[0]["provider_prompt"])
            self.assertEqual(
                entries[0]["video_prompt_projection"]["registry_version"],
                VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
            )
            self.assertEqual(entries[0]["semantic_contract"]["target_beat"], "Cinderella sees the invitation")
            self.assertFalse(entries[0]["motion_contract_missing"])
            self.assertEqual(entries[0]["motion_contract_required_fields_missing"], [])
            self.assertEqual(entries[0]["provider_history"][0]["status"], "failed")
            self.assertEqual(entries[0]["provider_history"][1]["provider_summary"]["retry_count"], 1)
            self.assertEqual(entries[1]["source_cut_ids"], [1, 2])
            self.assertEqual(entries[1]["motion_prompt"], "The coach rolls away under lantern light.")
            self.assertEqual(entries[1]["semantic_contract"]["target_beat"], "The coach leaves for the palace")
            self.assertTrue(entries[1]["motion_contract_missing"])
            self.assertEqual(
                entries[1]["motion_contract_required_fields_missing"],
                ["motion_intent", "must_preserve", "must_not_add", "handoff_state"],
            )

    def test_video_motion_collects_v3_cut_contract_motion_boundary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_v3_") as td:
            run_dir = Path(td)
            manifest = {
                "scenes": [
                    {
                        "scene_id": 10,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "cut_contract": {
                                    "source_event_contract": {
                                        "primary_event_beat_id": "scene10_event_pressure",
                                        "source_event_beat_ids": ["scene10_event_pressure"],
                                    },
                                    "motion_contract": {
                                        "source_event_beat_id": "scene10_event_pressure",
                                        "starts_from_first_frame": True,
                                        "must_not_advance_to_event_beat_ids": ["scene10_event_turn"],
                                        "motion_brief": "圧力の姿勢だけが小さく動く",
                                        "start_from_visible_state": "first_frame_contract.visible_start_state",
                                        "end_state": "turnの直前で止まる",
                                        "must_not_add": ["解決"],
                                    },
                                    "event_context_for_cut": {
                                        "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
                                        "editable": False,
                                        "primary_event_beat": {"beat_id": "scene10_event_pressure"},
                                    },
                                },
                                "video_generation": {
                                    "tool": "kling_3_0",
                                    "motion_prompt": "圧力の姿勢だけが小さく動く",
                                    "first_frame": "assets/scenes/scene10_cut01.png",
                                    "duration_seconds": 8,
                                    "output": "assets/videos/scene10_cut01.mp4",
                                },
                            }
                        ],
                    }
                ]
            }

            entries = collect_entries("video_motion", run_dir, manifest)

            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertFalse(entry["motion_contract_missing"])
            self.assertEqual(entry["motion_contract_required_fields_missing"], [])
            self.assertEqual(entry["motion_contract"]["source_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(entry["source_event_contract"]["primary_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(entry["event_context_for_cut"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
            self.assertIn("圧力の姿勢だけが小さく動く", entry["provider_prompt"])
            self.assertIn("turnの直前で止まる", entry["provider_prompt"])
            self.assertNotIn("scene10_event_pressure", entry["provider_prompt"])

    def test_video_motion_reviews_the_exact_current_materialized_provider_payload(self) -> None:
        authoring_source = "主人公が窓辺へ一歩進む"
        materialized = compile_video_api_prompt_v1(
            source_prompt=authoring_source,
            tool="kling_3_0",
            duration_seconds=8,
            quality="1080p",
            aspect_ratio="16:9",
        )
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {
                                "tool": "kling_3_0",
                                "prompt_authoring_source": authoring_source,
                                "motion_prompt": "互換field",
                                "duration_seconds": 8,
                                "quality": "1080p",
                                "aspect_ratio": "16:9",
                                "api_prompt_payload": materialized,
                            },
                        }
                    ],
                }
            ]
        }

        entries = collect_entries("video_motion", Path("."), manifest)

        self.assertEqual(entries[0]["provider_prompt"], materialized["prompt"])
        self.assertEqual(
            entries[0]["provider_prompt_payload"]["negative_prompt"],
            materialized["negative_prompt"],
        )
        self.assertEqual(
            entries[0]["provider_prompt_payload"]["source_digest"],
            materialized["source_digest"],
        )

    def test_render_unit_recompile_preserves_reference_roles_and_review_only_scene_sources(self) -> None:
        source_contract = {
            "location": "灰の台所",
            "motion_contract": {
                "motion_brief": "シンデレラが出口へ一歩進む",
                "end_state": "右足を踏み出した姿勢で止まる",
            }
        }
        references = [
            "assets/scenes/scene1_cut1.png",
            "assets/storyboards/scene1_storyboard.png",
        ]
        roles = [
            {"image_index": 1, "role": "start_state_visual_anchor"},
            {
                "image_index": 2,
                "role": "ordered_storyboard_sequence_guide",
            },
        ]
        review_dependencies = {
            "render_unit_source_cut_ids": ["1"],
            "render_unit_source_cut_contracts": [source_contract],
        }
        location_segments = [
            {"location": "灰の台所", "responsibility": "開始状態を示す"},
            {"location": "玄関", "responsibility": "退出の結果を示す"},
        ]
        materialized = compile_video_api_prompt_v1(
            cut_contract=source_contract,
            source_prompt="シンデレラが出口へ一歩進む",
            time_of_day="朝",
            tool="seedance",
            references=references,
            reference_roles=roles,
            duration_seconds=8,
            scene_time_of_day_visual_basis="朝日、低い明るさ、長い影、淡い暖色",
            scene_location_mode="sequence",
            scene_location_sequence=["灰の台所", "玄関"],
            scene_location_segments=location_segments,
            review_only_dependencies=review_dependencies,
        )
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "time_of_day": "朝",
                    "time_of_day_visual_basis": "朝日、低い明るさ、長い影、淡い暖色",
                    "location_mode": "sequence",
                    "location_sequence": ["灰の台所", "玄関"],
                    "location_segments": location_segments,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": source_contract,
                        }
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1],
                            "video_input_contract": {
                                "reference_roles": roles,
                            },
                            "video_generation": {
                                "tool": "seedance",
                                "references": references,
                                "prompt_authoring_source": "シンデレラが出口へ一歩進む",
                                "duration_seconds": 8,
                                "api_prompt_payload": materialized,
                            },
                        }
                    ],
                }
            ]
        }

        entries = collect_entries("video_motion", Path("."), manifest)

        current = entries[0]["provider_prompt_payload"]
        self.assertEqual(current["source_digest"], materialized["source_digest"])
        self.assertEqual(
            current["provider_request_binding"]["reference_roles"],
            roles,
        )
        self.assertIn("参照画像1は開始状態の基準", current["prompt"])
        traced = {
            item["source_key"]: item["value"]
            for item in current["projection_review_contract"][
                "review_only_sources"
            ]
        }
        self.assertEqual(traced["scene.location_segments"], location_segments)

    def test_render_unit_explicit_reveal_allowlist_materializes_and_reviews(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "scene_intent": {
                        "review_only_visualizable_action": "scene全体で主人公が銀の鍵を得て屋敷を出る",
                    },
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": {
                                "first_frame_contract": {
                                    "first_frame_brief": "主人公が閉じた扉の前に立っている",
                                },
                                "motion_contract": {
                                    "motion_brief": "光の中で銀の鍵が新しく現れる",
                                    "allowed_new_reveal_elements": ["銀の鍵"],
                                    "must_not_add": ["新しい人物"],
                                }
                            },
                        },
                        {
                            "cut_id": 2,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "ランタンが新しく灯り、主人公が銀の鍵を持って扉へ進む",
                                    "end_state": "銀の鍵を持った主人公が扉の前で止まる",
                                    "must_not_add": ["別の場所"],
                                    "allowed_new_reveal_elements": ["ランタン"],
                                }
                            },
                        },
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1, 2],
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "ランタンが灯り、光の中で銀の鍵が現れ、主人公が扉へ進む",
                                    "allowed_new_reveal_elements": [
                                        "ランタン",
                                        "銀の鍵",
                                    ],
                                }
                            },
                            "video_generation": {
                                "tool": "seedance",
                                "prompt_authoring_source": "ランタンが灯り、銀の鍵を持った主人公が扉へ進む",
                                "duration_seconds": 8,
                            },
                        }
                    ],
                }
            ]
        }

        for invalid_unit_allowlist in (
            ["銀の鍵"],
            ["ランタン", "銀の鍵", "魔法の馬車"],
        ):
            invalid_allowlist_manifest = copy.deepcopy(manifest)
            invalid_allowlist_manifest["scenes"][0]["render_units"][0][
                "cut_contract"
            ]["motion_contract"][
                "allowed_new_reveal_elements"
            ] = invalid_unit_allowlist
            with self.subTest(invalid_unit_allowlist=invalid_unit_allowlist):
                with self.assertRaisesRegex(
                    ValueError,
                    "video_render_unit_requires_explicit_reveal_authorization",
                ):
                    collect_entries(
                        "video_motion",
                        Path("."),
                        invalid_allowlist_manifest,
                    )

        first_entry = collect_entries("video_motion", Path("."), manifest)[0]
        materialized = first_entry["provider_prompt_payload"]

        self.assertEqual(
            first_entry["motion_contract"]["allowed_new_reveal_elements"],
            ["銀の鍵", "ランタン"],
        )
        self.assertEqual(
            first_entry["motion_contract"]["motion_brief"],
            "ランタンが灯り、光の中で銀の鍵が現れ、主人公が扉へ進む",
        )
        self.assertEqual(
            first_entry["motion_contract"]["end_state"],
            "銀の鍵を持った主人公が扉の前で止まる",
        )
        self.assertEqual(
            first_entry["motion_contract"]["must_not_add"],
            ["新しい人物", "別の場所"],
        )
        self.assertIn(
            "主人公が閉じた扉の前に立っている",
            materialized["prompt"],
        )
        self.assertIn(
            "銀の鍵を持った主人公が扉の前で止まる",
            materialized["prompt"],
        )
        self.assertIn("新しく現れてよいものは、銀の鍵、ランタン", materialized["prompt"])
        review_only_sources = {
            item["source_key"]: item["value"]
            for item in materialized["projection_review_contract"][
                "review_only_sources"
            ]
        }
        self.assertEqual(
            review_only_sources["scene.visualizable_action"],
            "scene全体で主人公が銀の鍵を得て屋敷を出る",
        )
        self.assertNotIn(
            "scene全体で主人公が銀の鍵を得て屋敷を出る",
            materialized["prompt"],
        )
        review_dependencies = first_entry["video_prompt_projection"][
            "review_only_dependencies"
        ]
        self.assertEqual(
            review_dependencies["render_unit_source_cut_ids"],
            ["1", "2"],
        )
        self.assertEqual(
            [
                contract["motion_contract"][
                    "allowed_new_reveal_elements"
                ]
                for contract in review_dependencies[
                    "render_unit_source_cut_contracts"
                ]
            ],
            [["銀の鍵"], ["ランタン"]],
        )

        reviewed_manifest = copy.deepcopy(manifest)
        reviewed_manifest["scenes"][0]["render_units"][0]["video_generation"][
            "api_prompt_payload"
        ] = materialized
        reviewed_entry = collect_entries(
            "video_motion",
            Path("."),
            reviewed_manifest,
        )[0]

        self.assertEqual(
            reviewed_entry["provider_prompt_payload"]["source_digest"],
            materialized["source_digest"],
        )

        stale_manifest = copy.deepcopy(reviewed_manifest)
        stale_manifest["scenes"][0]["scene_intent"][
            "review_only_visualizable_action"
        ] = "scene全体で主人公が別の鍵を得て宮殿へ向かう"
        with self.assertRaisesRegex(
            ValueError,
            "stale for semantic review",
        ):
            collect_entries("video_motion", Path("."), stale_manifest)

    def test_render_unit_rejects_missing_or_empty_allowlist_with_empty_second_source_contract(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "光の中で銀の鍵が新しく現れる",
                                    "allowed_new_reveal_elements": ["銀の鍵"],
                                }
                            },
                        },
                        {"cut_id": 2, "cut_contract": {}},
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1, 2],
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "主人公が扉へ進む",
                                }
                            },
                            "video_generation": {
                                "tool": "seedance",
                                "prompt_authoring_source": "主人公が扉へ進む",
                                "duration_seconds": 8,
                            },
                        }
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            "video_render_unit_requires_explicit_reveal_authorization",
        ):
            collect_entries("video_motion", Path("."), manifest)

        single_source_manifest = copy.deepcopy(manifest)
        single_source_manifest["scenes"][0]["cuts"] = single_source_manifest[
            "scenes"
        ][0]["cuts"][:1]
        single_source_manifest["scenes"][0]["render_units"][0][
            "source_cut_ids"
        ] = [1]
        single_source_motion = single_source_manifest["scenes"][0]["cuts"][0][
            "cut_contract"
        ]["motion_contract"]
        single_source_motion[
            "motion_brief"
        ] = "光の中で銀の鍵とランタンが新しく現れる"
        single_source_motion["allowed_new_reveal_elements"] = [
            "銀の鍵",
            "ランタン",
        ]
        single_source_manifest["scenes"][0]["render_units"][0][
            "cut_contract"
        ] = {}

        missing_allowlist_entry = collect_entries(
            "video_motion",
            Path("."),
            single_source_manifest,
        )[0]
        self.assertEqual(
            missing_allowlist_entry["motion_contract"],
            single_source_manifest["scenes"][0]["cuts"][0]["cut_contract"][
                "motion_contract"
            ],
        )

        empty_allowlist_manifest = copy.deepcopy(single_source_manifest)
        empty_allowlist_manifest["scenes"][0]["render_units"][0][
            "cut_contract"
        ] = {"motion_contract": {"allowed_new_reveal_elements": []}}
        empty_allowlist_entry = collect_entries(
            "video_motion",
            Path("."),
            empty_allowlist_manifest,
        )[0]
        self.assertEqual(
            empty_allowlist_entry["motion_contract"][
                "allowed_new_reveal_elements"
            ],
            ["銀の鍵", "ランタン"],
        )

        for unit_allowlist in (
            ["銀の鍵"],
            ["銀の鍵", "ランタン", "魔法の馬車"],
        ):
            override_manifest = copy.deepcopy(single_source_manifest)
            override_manifest["scenes"][0]["render_units"][0][
                "cut_contract"
            ] = {
                "motion_contract": {
                    "allowed_new_reveal_elements": unit_allowlist,
                }
            }
            with self.subTest(unit_allowlist=unit_allowlist):
                with self.assertRaises(ValueError):
                    collect_entries(
                        "video_motion",
                        Path("."),
                        override_manifest,
                    )

        unresolved_source_manifest = copy.deepcopy(single_source_manifest)
        unresolved_source_manifest["scenes"][0]["render_units"][0][
            "source_cut_ids"
        ] = [1, 999]
        unresolved_source_manifest["scenes"][0]["render_units"][0][
            "cut_contract"
        ] = {}
        with self.assertRaisesRegex(
            ValueError,
            "video_render_unit_source_cut_ids_unresolved",
        ):
            collect_entries(
                "video_motion",
                Path("."),
                unresolved_source_manifest,
            )

        manifest["scenes"][0]["render_units"][0]["cut_contract"][
            "motion_contract"
        ]["allowed_new_reveal_elements"] = []
        with self.assertRaisesRegex(
            ValueError,
            "video_render_unit_requires_explicit_reveal_authorization",
        ):
            collect_entries("video_motion", Path("."), manifest)

    def test_video_motion_rejects_stale_materialized_provider_payload(self) -> None:
        old_contract = {
            "motion_contract": {
                "motion_brief": "主人公が窓辺へ一歩進む",
            }
        }
        materialized = compile_video_api_prompt_v1(
            cut_contract=old_contract,
            tool="kling_3_0",
        )
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "主人公が扉の前で立ち止まる",
                                }
                            },
                            "video_generation": {
                                "tool": "kling_3_0",
                                "api_prompt_payload": materialized,
                            },
                        }
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "stale for semantic review"):
            collect_entries("video_motion", Path("."), manifest)

    def test_video_motion_rejects_tampered_projection_review_contract(self) -> None:
        materialized = compile_video_api_prompt_v1(
            source_prompt="主人公が窓辺へ一歩進む",
            tool="kling_3_0",
        )
        exact_prompt = materialized["prompt"]
        exact_sha256 = materialized["sha256"]
        exact_binding = copy.deepcopy(materialized["provider_request_binding"])
        materialized["projection_review_contract"]["provider"] = "tampered-provider"

        self.assertEqual(materialized["prompt"], exact_prompt)
        self.assertEqual(materialized["sha256"], exact_sha256)
        self.assertEqual(materialized["provider_request_binding"], exact_binding)
        with self.assertRaisesRegex(
            ValueError,
            r"stale for semantic review: .*projection_review_contract",
        ):
            collect_entries(
                "video_motion",
                Path("."),
                self._manifest_with_materialized_payload(materialized),
            )

    def test_video_motion_rejects_tampered_video_prompt_ir(self) -> None:
        materialized = compile_video_api_prompt_v1(
            source_prompt="主人公が窓辺へ一歩進む",
            tool="kling_3_0",
        )
        exact_prompt = materialized["prompt"]
        exact_sha256 = materialized["sha256"]
        exact_binding = copy.deepcopy(materialized["provider_request_binding"])
        materialized["video_prompt_ir"]["mode"] = "tampered-mode"

        self.assertEqual(materialized["prompt"], exact_prompt)
        self.assertEqual(materialized["sha256"], exact_sha256)
        self.assertEqual(materialized["provider_request_binding"], exact_binding)
        with self.assertRaisesRegex(
            ValueError,
            r"stale for semantic review: .*video_prompt_ir",
        ):
            collect_entries(
                "video_motion",
                Path("."),
                self._manifest_with_materialized_payload(materialized),
            )

    def test_video_motion_rejects_tampered_included_fragments(self) -> None:
        materialized = compile_video_api_prompt_v1(
            source_prompt="主人公が窓辺へ一歩進む",
            tool="kling_3_0",
        )
        exact_prompt = materialized["prompt"]
        exact_sha256 = materialized["sha256"]
        exact_binding = copy.deepcopy(materialized["provider_request_binding"])
        materialized["included_fragments"][0]["text"] = "tampered review evidence"

        self.assertEqual(materialized["prompt"], exact_prompt)
        self.assertEqual(materialized["sha256"], exact_sha256)
        self.assertEqual(materialized["provider_request_binding"], exact_binding)
        with self.assertRaisesRegex(
            ValueError,
            r"stale for semantic review: .*included_fragments",
        ):
            collect_entries(
                "video_motion",
                Path("."),
                self._manifest_with_materialized_payload(materialized),
            )

    def test_video_motion_rejects_tampered_provider_policy(self) -> None:
        materialized = compile_video_api_prompt_v1(
            source_prompt="主人公が窓辺へ一歩進む",
            tool="kling_3_0",
        )
        exact_prompt = materialized["prompt"]
        exact_sha256 = materialized["sha256"]
        exact_binding = copy.deepcopy(materialized["provider_request_binding"])
        materialized["provider_policy"]["one_clip_one_intent"] = False

        self.assertEqual(materialized["prompt"], exact_prompt)
        self.assertEqual(materialized["sha256"], exact_sha256)
        self.assertEqual(materialized["provider_request_binding"], exact_binding)
        with self.assertRaisesRegex(
            ValueError,
            r"stale for semantic review: .*provider_policy",
        ):
            collect_entries(
                "video_motion",
                Path("."),
                self._manifest_with_materialized_payload(materialized),
            )

    def test_materialized_motion_prompt_is_not_reinterpreted_as_authoring_source(self) -> None:
        materialized = compile_video_api_prompt_v1(
            source_prompt="主人公が窓辺へ一歩進む",
            tool="kling_3_0",
        )
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {
                                "tool": "kling_3_0",
                                "motion_prompt": materialized["prompt"],
                                "api_prompt_payload": materialized,
                            },
                        }
                    ],
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "stale for semantic review"):
            collect_entries("video_motion", Path("."), manifest)

    def test_video_motion_review_evidence_uses_canonical_contract_precedence(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "cut_contract": {
                                "motion_contract": {
                                    "motion_brief": "正本の動作として扉へ一歩進む",
                                }
                            },
                            "video_generation": {
                                "tool": "kling_3_0",
                                "motion_prompt": "自由文では窓へ走る",
                                "motion_contract": {
                                    "motion_intent": "旧形式では階段を下りる",
                                },
                            },
                        }
                    ],
                }
            ]
        }

        entry = collect_entries("video_motion", Path("."), manifest)[0]

        self.assertEqual(
            entry["motion_contract"]["motion_brief"],
            "正本の動作として扉へ一歩進む",
        )
        self.assertIn("正本の動作として扉へ一歩進む", entry["provider_prompt"])
        self.assertNotIn("旧形式では階段を下りる", entry["provider_prompt"])
        self.assertNotIn("自由文では窓へ走る", entry["provider_prompt"])

    def test_video_clip_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("video_clip", run_dir)

    def test_video_clip_sample_frame_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("video_clip", run_dir)

    def test_render_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("render", run_dir)

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td), manifest={})


if __name__ == "__main__":
    unittest.main()
