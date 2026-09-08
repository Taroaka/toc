import subprocess
import sys
import tempfile
import unittest
import re
import json
import hashlib
import importlib.util
import os
import shutil
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import yaml

from toc.harness import load_structured_document
from toc.story_duration import build_duration_plan


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_frontend_run_module():
    spec = importlib.util.spec_from_file_location(
        "toc_immersive_frontend_run_under_test",
        REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_state(path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def write_test_llm_story(
    *, run_dir: Path, topic: str, target_duration_seconds: int
) -> None:
    """Test double for the external Story Author boundary.

    It writes authored-looking structured content from research records; it is
    intentionally test-only and never serves as a production prose fallback.
    """

    _text, research = load_structured_document(run_dir / "research.md")
    materials = research.get("story_materials", {})
    events = [
        event
        for event in materials.get("chronological_events", [])
        if isinstance(event, dict)
    ]
    if not events:
        raise AssertionError("test research must contain chronological events")
    setting = materials.get("setting") if isinstance(materials.get("setting"), dict) else {}
    raw_places = setting.get("places") if isinstance(setting.get("places"), list) else []
    places = [
        str(place.get("name") or place.get("place_id") or "物語の場所").strip()
        if isinstance(place, dict)
        else str(place).strip()
        for place in raw_places
        if (str(place.get("name") or place.get("place_id") or "").strip() if isinstance(place, dict) else str(place).strip())
    ] or ["物語の場所"]
    scene_base, scene_remainder = divmod(target_duration_seconds, len(events))
    narration_total = build_duration_plan(target_duration_seconds).minimum_narration_seconds
    narration_base, narration_remainder = divmod(narration_total, len(events))
    scenes = []
    for index, event in enumerate(events, start=1):
        event_id = str(event.get("event_id") or f"E{index:02d}")
        event_text = str(event.get("event") or event_id)
        scene_id = f"scene_{index:02d}"
        previous_id = f"scene_{index - 1:02d}" if index > 1 else ""
        next_id = f"scene_{index + 1:02d}" if index < len(events) else ""
        start_state = f"state_after_scene_{index - 1:02d}" if index > 1 else "state_story_start"
        end_state = f"state_after_scene_{index:02d}"
        location = places[min(index - 1, len(places) - 1)]
        refs = [f"research.story_materials.chronological_events[{event_id}]"]
        scenes.append(
            {
                "scene_id": scene_id,
                "canonical_scene_index": index,
                "title": event_text,
                "phase": "opening" if index == 1 else "ending" if index == len(events) else "development",
                "purpose": event_text,
                "conflict": f"{location}の制約の中で{event_text}を成立させる。",
                "turn": event_text,
                "affect": {"label_hint": "tension", "audience_job": "follow_causality"},
                "visualizable_action": event_text,
                "grounding_note": f"research event {event_id}",
                "source_basis": {"event_ids": [event_id]},
                "research_refs": refs,
                "location": {"name": location, "sequence": [location], "segments": []},
                "time_of_day": "昼",
                "time_of_day_visual_basis": (
                    f"光源: {location}の窓から入る自然光。"
                    "明るさ: 中間調。影: 人物の足元に柔らかく落ちる。"
                    "色温度: 5200Kの中性光。"
                ),
                "target_duration_seconds": scene_base + (1 if index <= scene_remainder else 0),
                "narration_target_seconds": narration_base + (1 if index <= narration_remainder else 0),
                "scene_intent": {
                    "story_purpose": event_text,
                    "dramatic_question": f"{event_text}はどう次の原因になるか",
                    "value_shift": {"from": start_state, "to": end_state},
                    "causal_turn": event_text,
                },
                "start_state": {"state_id": start_state},
                "event_sequence": [
                    {
                        "beat_id": f"{scene_id}_beat_01",
                        "beat_function": "source_event",
                        "source_event_ids": [event_id],
                        "participants": list(
                            event.get("involved_characters") or ["protagonist"]
                        ),
                        "location": location,
                        "what_happens": event_text,
                        "visible_action": event_text,
                        "immediate_consequence": end_state,
                        "required_visual_evidence": [event_text, location],
                    }
                ],
                "turning_event": {
                    "beat_id": f"{scene_id}_beat_01",
                    "irreversible_change": event_text,
                },
                "end_state": {"state_id": end_state},
                "handoff_chain": {
                    "incoming": {"producer_scene_id": previous_id, "state_id": start_state},
                    "outgoing": {"consumer_scene_id": next_id, "state_id": end_state},
                },
                "preservation": {"must_preserve": [event_text], "must_not_show": []},
            }
        )
    story = {
        "story_metadata": {
            "scene_authoring_contract": "story_scene_contract_v1",
            "topic": topic,
            "time": str(setting.get("time_or_era") or "架空の時代"),
            "target_duration_seconds": target_duration_seconds,
            "scene_time_of_day_contract": "required_v1",
            "scene_time_of_day_visual_basis_contract": "required_v1",
        },
        "adaptation_source_contract": {
            "schema_version": "adaptation_source_contract_v1",
            "mode": "existing_story",
            "authoring_provenance": "test_llm_double",
            "source_story_promise": f"{topic}の出来事を因果順に描く。",
            "core_values": [
                {
                    "value_id": "value_source_causality",
                    "statement": "researchの出来事と主体の選択を因果順に保つ。",
                    "audience_effect": "出来事の連鎖を納得して追える。",
                    "source_event_refs": [str(event.get("event_id") or "") for event in events],
                }
            ],
            "non_negotiable_events": [str(event.get("event") or "") for event in events],
            "non_negotiable_meanings": ["researchの因果順を変えない"],
            "iconic_moments": [str(events[-1].get("event") or "結末")],
            "forbidden_value_distortions": ["generic montageへ置換しない"],
        },
        "selection": {"chosen_candidate_id": "test_grounded"},
        "script": {"scenes": scenes},
    }
    (run_dir / "story.md").write_text(
        "# 物語（story）\n\n```yaml\n"
        + yaml.safe_dump(story, allow_unicode=True, sort_keys=False)
        + "```\n",
        encoding="utf-8",
    )


def minimal_authored_story_for_time_contract() -> dict:
    """Provide authored-shaped scenes for focused time-of-day contract tests."""

    basis = (
        "光源: 窓からの自然光。明るさ: 中間調。"
        "影: 人物の足元に柔らかく落ちる。色温度: 5200K。"
    )
    scenes = []
    for index in range(1, 3):
        scene_id = f"scene_{index:02d}"
        scenes.append(
            {
                "scene_id": scene_id,
                "canonical_scene_index": index,
                "title": f"scene {index}の出来事",
                "phase": "opening" if index == 1 else "ending",
                "purpose": f"scene {index}の出来事を成立させる。",
                "conflict": "固有の制約が前進を遅らせる。",
                "turn": f"scene {index}で不可逆な変化が起きる。",
                "affect": {"label_hint": "tension", "audience_job": "follow_causality"},
                "visualizable_action": f"scene {index}の具体的な行為。",
                "grounding_note": "researchを保持したtest fixture",
                "source_basis": {"event_ids": [f"E{index:02d}"]},
                "research_refs": [
                    f"research.story_materials.chronological_events[E{index:02d}]"
                ],
                "location": {
                    "location_id": f"L{index:02d}",
                    "name": f"scene {index}の場所",
                    "mode": "single",
                    "sequence": [f"scene {index}の場所"],
                    "segments": [],
                },
                "time_of_day": "昼",
                "time_of_day_visual_basis": basis,
                "scene_intent": {
                    "story_purpose": f"scene {index}の出来事を成立させる。",
                    "dramatic_question": "次に何が変わるか。",
                    "value_shift": {
                        "from": f"state_{index - 1:02d}",
                        "to": f"state_{index:02d}",
                    },
                    "causal_turn": f"scene {index}で不可逆な変化が起きる。",
                },
                "start_state": {"state_id": f"state_{index - 1:02d}"},
                "event_sequence": [
                    {
                        "beat_id": f"{scene_id}_beat_01",
                        "beat_function": "source_event",
                        "source_event_ids": [f"E{index:02d}"],
                        "what_happens": f"scene {index}の具体的な行為。",
                        "immediate_consequence": f"state_{index:02d}",
                        "required_visual_evidence": [f"scene {index}の場所"],
                    }
                ],
                "turning_event": {
                    "beat_id": f"{scene_id}_beat_01",
                    "irreversible_change": f"scene {index}で不可逆な変化が起きる。",
                },
                "end_state": {"state_id": f"state_{index:02d}"},
                "handoff_chain": {
                    "incoming": {
                        "producer_scene_id": f"scene_{index - 1:02d}" if index > 1 else "",
                        "state_id": f"state_{index - 1:02d}",
                    },
                    "outgoing": {
                        "consumer_scene_id": f"scene_{index + 1:02d}" if index < 2 else "",
                        "state_id": f"state_{index:02d}",
                    },
                },
                "preservation": {
                    "must_preserve": [f"scene {index}の具体的な行為。"],
                    "must_not_show": [],
                },
            }
        )
    return {
        "story_metadata": {
            "scene_authoring_contract": "story_scene_contract_v1",
            "scene_time_of_day_contract": "required_v1",
            "scene_time_of_day_visual_basis_contract": "required_v1",
        },
        "script": {"scenes": scenes},
    }


class TestTocImmersiveFrontendRun(unittest.TestCase):
    @staticmethod
    def _scene_design_bundle(module, profile, idx: int):
        title = profile["scene_titles"][idx - 1]
        location = module._location_spec_for_scene(profile, idx)
        include_artifact = module._scene_uses_artifact(profile, idx)
        intent = module._scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location,
            profile=profile,
            include_artifact=include_artifact,
        )
        event = module._scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=profile,
            include_artifact=include_artifact,
        )
        intent["story_event_obligations"] = module._story_event_obligations_from_scene_event(
            event
        )
        return title, location, intent, event, include_artifact

    def test_world_walk_binds_canonical_source_metadata(self) -> None:
        module = load_frontend_run_module()
        source_run = REPO_ROOT / "output" / "桃太郎_20260727_1200"
        manifest = {"video_metadata": {"experience": "cinematic_story"}}

        module._bind_experience_metadata(
            manifest,
            experience="world_walk",
            source_run=source_run,
        )

        metadata = manifest["video_metadata"]
        source_relative = "output/桃太郎_20260727_1200"
        self.assertEqual(metadata["experience"], "world_walk")
        self.assertEqual(metadata["source_run"], source_relative)
        self.assertEqual(metadata["source_story"], f"{source_relative}/story.md")
        self.assertEqual(metadata["source_assets"], f"{source_relative}/assets")

    def test_create_input_contract_preserves_exact_multiline_source(self) -> None:
        module = load_frontend_run_module()
        exact_source = "冒頭の空白を保持。  \n\n第二段落。\n"
        with tempfile.TemporaryDirectory(
            prefix="frontend_create_input_",
            dir=REPO_ROOT / "output",
        ) as tmp:
            run_dir = Path(tmp)

            path = module._write_create_input_contract(
                run_dir=run_dir,
                topic="創作",
                source=exact_source,
                experience="cinematic_story",
                source_run=None,
                target_duration_seconds=600,
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "toc.create_input.v1")
            self.assertEqual(payload["source"], exact_source)
            self.assertEqual(
                payload["source_sha256"],
                hashlib.sha256(exact_source.encode("utf-8")).hexdigest(),
            )
            self.assertIsNone(payload["source_run"])
            self.assertEqual(payload["target_duration_seconds"], 600)

    def test_world_walk_create_input_uses_actual_source_story_bytes(self) -> None:
        module = load_frontend_run_module()
        exact_story = "# Source Story\n\n行末と空行をそのまま使う。  \n"
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_world_walk_input_",
            dir=output_root,
        ) as tmp:
            root = Path(tmp)
            source_run = root / "source"
            run_dir = root / "target"
            source_run.mkdir()
            (source_run / "story.md").write_text(
                exact_story,
                encoding="utf-8",
            )

            resolved_source = module._exact_materialization_source(
                source="output/source",
                experience="world_walk",
                source_run=source_run,
            )
            path = module._write_create_input_contract(
                run_dir=run_dir,
                topic="世界観散歩",
                source=resolved_source,
                experience="world_walk",
                source_run=source_run,
                target_duration_seconds=300,
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source"], exact_story)
            self.assertNotEqual(payload["source"], "output/source")
            self.assertEqual(
                payload["source_run"],
                source_run.relative_to(REPO_ROOT).as_posix(),
            )

    def test_world_walk_generation_contract_uses_source_assets_and_observer_pov(self) -> None:
        module = load_frontend_run_module()
        script = {"scenes": [{"cuts": [{"cut_contract": {}, "scene_contract": {}}]}]}
        manifest = {
            "video_metadata": {},
            "assets": {"style_guide": {"reference_images": []}},
            "scenes": [
                {
                    "time_of_day": "day",
                    "cuts": [
                        {
                            "cut_contract": {"cinematic_contract": {}},
                            "scene_contract": {"must_avoid": []},
                            "image_generation": {
                                "character_ids": [],
                                "object_ids": [],
                                "location_ids": [],
                                "first_frame_visual_plan": {
                                    "temporal_boundary": {
                                        "event_fact_visible_in_still": "村の門前を歩いている"
                                    },
                                    "subject_binding": {
                                        "primary_subject": {"name": "村の門前の生活空間"}
                                    },
                                    "spatial_composition": {
                                        "foreground": "土の道",
                                        "midground": "村の門",
                                        "background": "遠い家並み",
                                    },
                                    "scene_material_pack": {
                                        "dominant_materials": ["木、土、麻布"]
                                    },
                                },
                                "api_prompt_payload": {},
                            },
                            "video_generation": {"motion_prompt": "ゆっくり前へ進む"},
                        }
                    ],
                }
            ],
        }
        references = [
            "assets/source_references/characters/momotaro.png",
            "assets/source_references/locations/village.png",
        ]

        module._apply_world_walk_generation_contract(
            script=script,
            manifest=manifest,
            source_references=references,
        )

        cut = manifest["scenes"][0]["cuts"][0]
        self.assertEqual(manifest["world_walk_contract"]["viewpoint"], "observer_pov")
        self.assertEqual(manifest["assets"]["style_guide"]["reference_images"], references)
        self.assertEqual(cut["image_generation"]["references"], references)
        self.assertEqual(
            cut["image_generation"]["api_prompt_payload"]["reference_images"],
            references,
        )
        self.assertIn(
            "観察者POV",
            cut["image_generation"]["api_prompt_payload"]["prompt"],
        )
        self.assertIn(
            "物語を進めず",
            cut["image_generation"]["api_prompt_payload"]["prompt"],
        )
        self.assertIn("観察者POV", cut["cut_contract"]["world_walk_contract"]["prompt_requirement"])
        self.assertIn("顔の大写し", cut["scene_contract"]["must_avoid"])
        self.assertIn("観察者POV", cut["video_generation"]["motion_prompt"])

    def test_world_walk_materializes_source_images_inside_target_run(self) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_run = root / "source"
            run_dir = root / "target"
            source_image = source_run / "assets" / "characters" / "hero.png"
            source_image.parent.mkdir(parents=True)
            source_image.write_bytes(b"source-image")
            run_dir.mkdir()

            references = module._materialize_world_walk_source_references(
                source_run,
                run_dir,
            )

            self.assertEqual(references, ["assets/source_references/characters/hero.png"])
            self.assertEqual((run_dir / references[0]).read_bytes(), b"source-image")

    def test_world_walk_source_reference_lease_blocks_concurrent_mutation(
        self,
    ) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_run = root / "source"
            run_dir = root / "target"
            first_image = (
                source_run / "assets" / "characters" / "hero.png"
            )
            second_image = (
                source_run / "assets" / "locations" / "village.png"
            )
            first_image.parent.mkdir(parents=True)
            second_image.parent.mkdir(parents=True)
            first_image.write_bytes(b"hero-v1")
            second_image.write_bytes(b"village-v1")
            run_dir.mkdir()
            source_identity = module.directory_identity_nofollow(source_run)
            destination_identity = module.directory_identity_nofollow(run_dir)
            lease = module._freeze_world_walk_source_reference_inventory(
                source_run,
                source_root_identity=source_identity,
            )
            original_copy = module.copy_regular_file_atomic_nofollow
            copy_count = 0

            def mutate_after_first_copy(**kwargs):
                nonlocal copy_count
                result = original_copy(**kwargs)
                copy_count += 1
                if copy_count == 1:
                    second_image.write_bytes(b"village-mutated")
                return result

            with (
                patch.object(
                    module,
                    "copy_regular_file_atomic_nofollow",
                    side_effect=mutate_after_first_copy,
                ),
                self.assertRaisesRegex(
                    (RuntimeError, ValueError),
                    "source (reference inventory changed|sha256 mismatch)",
                ),
            ):
                module._materialize_world_walk_source_references(
                    source_run,
                    run_dir,
                    source_root_identity=source_identity,
                    destination_root_identity=destination_identity,
                    source_reference_lease=lease,
                )

            copied_root = run_dir / "assets" / "source_references"
            self.assertFalse(
                copied_root.exists()
                and any(
                    path.is_file()
                    for path in copied_root.rglob("*")
                )
            )

    def test_world_walk_source_reference_lease_rejects_root_replacement(
        self,
    ) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_run = root / "source"
            original_source = root / "source-original"
            run_dir = root / "target"
            source_image = (
                source_run / "assets" / "characters" / "hero.png"
            )
            source_image.parent.mkdir(parents=True)
            source_image.write_bytes(b"trusted-hero")
            run_dir.mkdir()
            source_identity = module.directory_identity_nofollow(source_run)
            lease = module._freeze_world_walk_source_reference_inventory(
                source_run,
                source_root_identity=source_identity,
            )
            source_run.rename(original_source)
            replacement_image = (
                source_run / "assets" / "characters" / "hero.png"
            )
            replacement_image.parent.mkdir(parents=True)
            replacement_image.write_bytes(b"replacement-hero")

            with self.assertRaisesRegex(
                ValueError,
                "directory identity changed",
            ):
                module._materialize_world_walk_source_references(
                    source_run,
                    run_dir,
                    source_root_identity=source_identity,
                    destination_root_identity=(
                        module.directory_identity_nofollow(run_dir)
                    ),
                    source_reference_lease=lease,
                )

            self.assertFalse(
                (
                    run_dir
                    / "assets"
                    / "source_references"
                    / "characters"
                    / "hero.png"
                ).exists()
            )

    def test_fresh_run_validator_accepts_safe_server_preamble(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_server_preamble_",
            dir=output_root,
        ) as td:
            run_dir = Path(td)
            lock = run_dir / ".locks/create_resume.lock"
            lock.parent.mkdir()
            lock.write_text("pid=123\n", encoding="utf-8")
            event = (
                run_dir
                / "logs/app_server/create_job_step/started.json"
            )
            event.parent.mkdir(parents=True)
            event.write_text("{}\n", encoding="utf-8")

            self.assertEqual(
                module._validated_fresh_cli_run_dir(str(run_dir)),
                run_dir,
            )

    def test_fresh_run_lock_rejects_validated_root_symlink_swap(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_root_swap_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            accepted = module._validated_fresh_cli_run_dir(str(run_dir))
            original_run = parent / "run-original"
            outside = parent / "outside"
            outside.mkdir()
            run_dir.rename(original_run)
            run_dir.symlink_to(outside, target_is_directory=True)
            try:
                with self.assertRaisesRegex(
                    ValueError,
                    "real directory",
                ):
                    with module._run_materialization_lock(accepted):
                        self.fail("swapped root must never acquire the lock")
                self.assertFalse(
                    (outside / ".toc_frontend_create.lock").exists()
                )
            finally:
                run_dir.unlink()
                original_run.rename(run_dir)

            with module._run_materialization_lock(run_dir):
                locked_original = parent / "run-locked-original"
                run_dir.rename(locked_original)
                run_dir.symlink_to(outside, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(
                        ValueError,
                        "real directory",
                    ):
                        module._write_create_input_contract(
                            run_dir=run_dir,
                            topic="創作",
                            source="source",
                            experience="cinematic_story",
                            source_run=None,
                            target_duration_seconds=300,
                        )
                    self.assertFalse(
                        (
                            outside
                            / "logs/orchestration/create_input.json"
                        ).exists()
                    )
                finally:
                    run_dir.unlink()
                    locked_original.rename(run_dir)

            with module._run_materialization_lock(
                run_dir,
                expected_identity=(
                    module.directory_identity_nofollow(run_dir)
                ),
                protect_pathname=True,
            ):
                (run_dir / "state.txt").write_text(
                    "status=AUTHORING\n---\n",
                    encoding="utf-8",
                )
                (run_dir / "logs").mkdir()
                outside_research = outside / "research.md"
                outside_research.write_text(
                    "outside-original",
                    encoding="utf-8",
                )
                injected_research = run_dir / "research.md"
                injected_research.symlink_to(outside_research)
                with self.assertRaises((OSError, ValueError)):
                    module._write_run_text_nofollow(
                        run_dir,
                        injected_research,
                        "must-not-escape",
                    )
                self.assertEqual(
                    outside_research.read_text(encoding="utf-8"),
                    "outside-original",
                )
            self.assertTrue(run_dir.is_dir())
            self.assertTrue((run_dir / "state.txt").is_file())
            (run_dir / "research.md").unlink()

    def test_fresh_run_lock_fails_closed_without_chflags(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_no_chflags_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            run_identity = module.directory_identity_nofollow(run_dir)

            with patch.object(module.os, "chflags", None):
                with module._run_materialization_lock(
                    run_dir,
                    expected_identity=run_identity,
                    protect_pathname=True,
                ):
                    module._write_run_text_nofollow(
                        run_dir,
                        run_dir / "research.md",
                        "trusted",
                    )
            self.assertEqual(
                (run_dir / "research.md").read_text(encoding="utf-8"),
                "trusted",
            )

            original_run = parent / "run-original"
            with (
                patch.object(module.os, "chflags", None),
                self.assertRaisesRegex(
                    ValueError,
                    "directory identity changed",
                ),
            ):
                with module._run_materialization_lock(
                    run_dir,
                    expected_identity=run_identity,
                    protect_pathname=True,
                ):
                    run_dir.rename(original_run)
                    run_dir.mkdir()
                    module._write_run_text_nofollow(
                        run_dir,
                        run_dir / "story.md",
                        "must-not-write-to-replacement",
                    )

            self.assertFalse((run_dir / "story.md").exists())
            shutil.rmtree(run_dir)
            original_run.rename(run_dir)

    def test_frontend_lock_recovers_after_owner_process_dies(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_owner_death_lock_",
            dir=output_root,
        ) as td:
            run_dir = Path(td)
            legacy_marker = run_dir / ".toc_frontend_create.lock"
            legacy_marker.write_text("pid=stale\n", encoding="utf-8")
            self.assertEqual(
                module._validated_fresh_cli_run_dir(str(run_dir)),
                run_dir,
            )
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "\n".join(
                        (
                            "import importlib.util, os",
                            (
                                "spec=importlib.util.spec_from_file_location("
                                "'frontend_child', "
                                f"{str(REPO_ROOT / 'scripts' / 'toc-immersive-frontend-run.py')!r})"
                            ),
                            "module=importlib.util.module_from_spec(spec)",
                            "spec.loader.exec_module(module)",
                            (
                                "lock=module._run_materialization_lock("
                                f"module.Path({str(run_dir)!r}))"
                            ),
                            "lock.__enter__()",
                            "os._exit(0)",
                        )
                    ),
                ],
                cwd=REPO_ROOT,
                check=False,
            )
            self.assertEqual(child.returncode, 0)
            with module._run_materialization_lock(run_dir):
                module._write_run_text_nofollow(
                    run_dir,
                    run_dir / "owner_death_recovered.md",
                    "recovered",
                )
            self.assertEqual(
                legacy_marker.read_text(encoding="utf-8"),
                "pid=stale\n",
            )

    def test_frontend_lock_rejects_a_live_owner(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_live_owner_lock_",
            dir=output_root,
        ) as td:
            run_dir = Path(td)
            with module._run_materialization_lock(run_dir):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "another frontend-create process owns this run",
                ):
                    with module._run_materialization_lock(run_dir):
                        self.fail("a second live owner must not acquire")

    def test_frontend_lock_never_deletes_a_replaced_legacy_marker(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_lock_name_substitution_",
            dir=output_root,
        ) as td:
            run_dir = Path(td)
            marker = run_dir / ".toc_frontend_create.lock"
            old_marker = run_dir / ".toc_frontend_create.lock.old"
            marker.write_text("legacy-owner\n", encoding="utf-8")
            with module._run_materialization_lock(run_dir):
                marker.rename(old_marker)
                marker.write_text("replacement-owner\n", encoding="utf-8")
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "replacement-owner\n",
            )
            self.assertEqual(
                old_marker.read_text(encoding="utf-8"),
                "legacy-owner\n",
            )

    def test_state_writer_does_not_follow_replaced_run_without_chflags(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_state_root_replacement_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            run_identity = module.directory_identity_nofollow(run_dir)
            original_run = parent / "run-original"

            with (
                patch.object(module.os, "chflags", None),
                self.assertRaisesRegex(
                    ValueError,
                    "directory identity changed",
                ),
            ):
                with module._run_materialization_lock(
                    run_dir,
                    expected_identity=run_identity,
                    protect_pathname=True,
                ):
                    run_dir.rename(original_run)
                    run_dir.mkdir()
                    (run_dir / "state.txt").write_text(
                        "replacement=untouched\n---\n",
                        encoding="utf-8",
                    )
                    module.append_state_snapshot(
                        run_dir / "state.txt",
                        {"runtime.stage": "must_not_reach_replacement"},
                    )

            self.assertEqual(
                (run_dir / "state.txt").read_text(encoding="utf-8"),
                "replacement=untouched\n---\n",
            )

    def test_state_writer_rejects_hardlinked_state_file(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_state_hardlink_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            outside = parent / "outside-state.txt"
            outside.write_text(
                "runtime.stage=outside\n---\n",
                encoding="utf-8",
            )
            os.link(outside, run_dir / "state.txt")
            run_identity = module.directory_identity_nofollow(run_dir)

            with module._run_materialization_lock(
                run_dir,
                expected_identity=run_identity,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "identity changed|singly-linked regular file",
                ):
                    module.append_state_snapshot(
                        run_dir / "state.txt",
                        {"runtime.stage": "must_not_append"},
                    )

            self.assertEqual(
                outside.read_text(encoding="utf-8"),
                "runtime.stage=outside\n---\n",
            )

    def test_state_writer_uses_serialized_reader_under_materialization_lock(
        self,
    ) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_state_serialized_read_",
            dir=output_root,
        ) as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "runtime.stage=prepared\n---\n",
                encoding="utf-8",
            )
            run_identity = module.directory_identity_nofollow(run_dir)
            strict_reader = module.read_regular_file_nofollow

            def reject_strict_state_read(*args, **kwargs):
                relative_path = Path(args[1])
                if relative_path == Path("state.txt"):
                    raise AssertionError(
                        "active state reads must share append serialization"
                    )
                return strict_reader(*args, **kwargs)

            with module._run_materialization_lock(
                run_dir,
                expected_identity=run_identity,
            ):
                with patch.object(
                    module,
                    "read_regular_file_nofollow",
                    side_effect=reject_strict_state_read,
                ):
                    state = module.append_state_snapshot(
                        run_dir / "state.txt",
                        {"runtime.stage": "reviewing"},
                    )

            self.assertEqual(state["runtime.stage"], "reviewing")

    def test_subprocess_uses_pinned_run_root_without_chflags(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_subprocess_root_replacement_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            run_identity = module.directory_identity_nofollow(run_dir)
            original_run = parent / "run-original"

            def replace_root_and_write(command, **kwargs):
                output_arg = Path(command[command.index("--out") + 1])
                run_dir.rename(original_run)
                run_dir.mkdir()
                root_descriptor = int(kwargs["pass_fds"][0])
                output_descriptor = os.open(
                    output_arg,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=root_descriptor,
                )
                try:
                    os.write(
                        output_descriptor,
                        b"written-via-pinned-root",
                    )
                finally:
                    os.close(output_descriptor)
                self.assertTrue(callable(kwargs["preexec_fn"]))
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(module.os, "chflags", None),
                patch.object(
                    module.subprocess,
                    "run",
                    side_effect=replace_root_and_write,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "directory identity changed",
                ),
            ):
                with module._run_materialization_lock(
                    run_dir,
                    expected_identity=run_identity,
                    protect_pathname=True,
                ):
                    module._run_materialization_subprocess(
                        run_dir,
                        [
                            sys.executable,
                            "synthetic-child.py",
                            "--out",
                            str(run_dir / "child.txt"),
                        ],
                        check=True,
                    )

            self.assertFalse((run_dir / "child.txt").exists())
            self.assertEqual(
                (original_run / "child.txt").read_text(encoding="utf-8"),
                "written-via-pinned-root",
            )

    def test_pinned_subprocess_closes_root_descriptor_before_exec(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_subprocess_fd_close_",
            dir=output_root,
        ) as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            identity = module.directory_identity_nofollow(run_dir)

            with module._run_materialization_lock(
                run_dir,
                expected_identity=identity,
            ):
                active = module._active_materialization_root(run_dir)
                self.assertIsNotNone(active)
                root_descriptor = active[2]
                completed = module._run_materialization_subprocess(
                    run_dir,
                    [
                        sys.executable,
                        "-c",
                        (
                            "import os,sys; fd=int(sys.argv[1]); "
                            "\ntry: os.fstat(fd)"
                            "\nexcept OSError: raise SystemExit(0)"
                            "\nraise SystemExit(7)"
                        ),
                        str(root_descriptor),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(
                completed.returncode,
                0,
                msg=f"stdout={completed.stdout!r} stderr={completed.stderr!r}",
            )

    def test_prepare_grounding_only_prepares_source_readsets(self) -> None:
        module = load_frontend_run_module()
        run_dir = Path("/tmp/frontend-grounding-order")

        with (
            patch.object(module, "_prepare_authoring_grounding") as authoring_grounding,
            patch.object(module.subprocess, "run") as subprocess_run,
        ):
            module.prepare_grounding(run_dir)

        authoring_grounding.assert_not_called()
        commands = [call.args[0] for call in subprocess_run.call_args_list]
        self.assertEqual(
            [
                command[command.index("--stage") + 1]
                for command in commands
            ],
            ["asset", "scene_implementation"],
        )

    def test_prepare_grounding_completes_only_successful_grounding_slots(self) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory(prefix="frontend_grounding_slots_") as tmp:
            run_dir = Path(tmp)
            with (
                patch.object(module, "_prepare_authoring_grounding"),
                patch.object(module.subprocess, "run"),
            ):
                module.prepare_grounding(run_dir)

            state = parse_state(run_dir / "state.txt")

        self.assertEqual(state["slot.p510.status"], "done")
        self.assertEqual(state["slot.p610.status"], "done")

    def test_prepare_grounding_preserves_completed_asset_slot_when_scene_grounding_fails(self) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory(prefix="frontend_grounding_failure_") as tmp:
            run_dir = Path(tmp)
            (run_dir / "state.txt").write_text(
                "slot.p510.status=pending\nslot.p610.status=pending\n",
                encoding="utf-8",
            )

            def fail_scene_grounding(command, **_kwargs):
                if "--stage" in command and command[command.index("--stage") + 1] == "scene_implementation":
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with (
                patch.object(module, "_prepare_authoring_grounding"),
                patch.object(module.subprocess, "run", side_effect=fail_scene_grounding),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                module.prepare_grounding(run_dir)

            state = parse_state(run_dir / "state.txt")

        self.assertEqual(state["slot.p510.status"], "done")
        self.assertEqual(state["slot.p610.status"], "pending")

    def test_materialization_disk_preflight_rejects_106_mib_with_recovery_guidance(self) -> None:
        module = load_frontend_run_module()
        disk_usage = shutil._ntuple_diskusage(
            total=1024 * 1024 * 1024,
            used=918 * 1024 * 1024,
            free=106 * 1024 * 1024,
        )

        with (
            patch.object(module.shutil, "disk_usage", return_value=disk_usage),
            self.assertRaisesRegex(
                RuntimeError,
                r"storage preflight failed.*required 512 MiB.*available 106 MiB.*unused output runs",
            ),
        ):
            module._require_materialization_free_space(Path("/tmp/example-run"))

    def test_materialization_disk_preflight_allows_825_mib(self) -> None:
        module = load_frontend_run_module()
        disk_usage = shutil._ntuple_diskusage(
            total=1024 * 1024 * 1024,
            used=199 * 1024 * 1024,
            free=825 * 1024 * 1024,
        )

        with patch.object(module.shutil, "disk_usage", return_value=disk_usage):
            module._require_materialization_free_space(Path("/tmp/example-run"))

    def test_main_runs_disk_preflight_before_materialization(self) -> None:
        module = load_frontend_run_module()
        materialize = Mock()

        with (
            patch.object(
                module,
                "_validated_fresh_cli_run_dir",
                return_value=Path("/tmp/materialized-run"),
            ),
            patch.object(
                module,
                "directory_identity_nofollow",
                return_value=(1, 2),
            ),
            patch.object(
                module,
                "_require_materialization_free_space",
                side_effect=RuntimeError("synthetic storage preflight failed"),
            ) as preflight,
            patch.object(module, "materialize_run", materialize),
            patch.object(
                sys,
                "argv",
                [
                    "toc-immersive-frontend-run.py",
                    "--topic",
                    "創作",
                    "--run-dir",
                    "/tmp/materialized-run",
                    "--stop-target",
                    "p680",
                ],
            ),
            self.assertRaisesRegex(RuntimeError, "synthetic storage preflight failed"),
        ):
            module.main()

        preflight.assert_called_once_with(Path("/tmp/materialized-run"))
        materialize.assert_not_called()

    def test_fresh_materialized_media_slots_only_complete_executed_work(self) -> None:
        module = load_frontend_run_module()
        expected_common_statuses = {
            "p510": "pending",
            "p520": "done",
            "p530": "done",
            "p550": "pending",
            "p560": "pending",
            "p570": "pending",
            "p610": "pending",
            "p620": "done",
            "p650": "pending",
        }

        for stop_target in ("p650", "p680"):
            with self.subTest(stop_target=stop_target):
                updates = module._fresh_materialized_media_slot_updates(stop_target)
                self.assertEqual(
                    {
                        slot: updates[f"slot.{slot}.status"]
                        for slot in expected_common_statuses
                    },
                    expected_common_statuses,
                )
                for slot in ("p660", "p670", "p680"):
                    key = f"slot.{slot}.status"
                    if stop_target == "p680":
                        self.assertEqual(updates[key], "pending")
                    else:
                        self.assertNotIn(key, updates)

    def test_researched_foundations_feed_story_and_cut_builders(self) -> None:
        module = load_frontend_run_module()
        base_profile = module._duration_aware_profile(
            module._story_profile("桃太郎", "桃太郎", variant_seed="authored-foundation"),
            target_duration_seconds=600,
        )
        authored_event = "確定した出来事が、主人公を橋の向こうへ進ませる。"
        researched_source = {
            "story_materials": {
                "canonical_story_dump": "研究済みの物語基準。",
                "chronological_events": [{"event_id": "E99", "event": authored_event}],
                "characters": [{"character_id": "protagonist", "name": "研究済み主人公", "role": "主人公"}],
            },
            "source_passages": [{"passage_id": "P99", "passage": authored_event}],
        }

        research_profile = module._profile_from_research(base_profile, researched_source)
        story = {
            "story_metadata": {
                "time": "",
                "scene_authoring_contract": "story_scene_contract_v1",
                "target_duration_seconds": 600,
            },
            "script": {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "canonical_scene_index": 1,
                        "title": "橋の向こうへ",
                        "purpose": authored_event,
                        "conflict": "橋の境界が前進を阻む。",
                        "turn": authored_event,
                        "affect": {"label_hint": "resolve"},
                        "visualizable_action": authored_event,
                        "grounding_note": "researched source event E99",
                        "research_refs": [
                            "research.story_materials.chronological_events[E99]",
                            "research.source_passages[P99]",
                        ],
                        "target_duration_seconds": 600,
                        "narration_target_seconds": 420,
                    }
                ]
            },
        }

        self.assertIn("time", story["story_metadata"])
        self.assertIsInstance(story["story_metadata"]["time"], str)
        self.assertEqual(research_profile["events"], [authored_event])
        self.assertIn(authored_event, story["script"]["scenes"][0]["purpose"])
        self.assertIn("research.story_materials.chronological_events[E99]", story["script"]["scenes"][0]["research_refs"])
        self.assertIn("research.source_passages[P99]", story["script"]["scenes"][0]["research_refs"])

        authored_turn = "確定した不可逆な転換を画面上の事実にする。"
        story["script"]["scenes"][0]["purpose"] = "authoringで確定したscene目的"
        story["script"]["scenes"][0]["turn"] = authored_turn
        story["story_metadata"]["time"] = "室町時代"
        cut_profile = module._profile_from_story(research_profile, story)
        self.assertEqual(cut_profile["story_time"], "室町時代")
        location = module._location_spec_for_scene(cut_profile, 1)
        scene_intent = module._scene_intent_for_cut_design(
            title=cut_profile["scene_titles"][0],
            idx=1,
            location_spec=location,
            profile=cut_profile,
            include_artifact=False,
        )
        scene_event = module._scene_event_for_cut_design(
            title=cut_profile["scene_titles"][0],
            idx=1,
            scene_intent=scene_intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=cut_profile,
            include_artifact=False,
        )

        self.assertEqual(scene_intent["story_purpose"], "authoringで確定したscene目的")
        self.assertEqual(scene_intent["causal_turn"], authored_turn)
        turn_beat = next(item for item in scene_event["event_sequence"] if item["beat_function"] == "turn")
        self.assertEqual(turn_beat["what_happens"], authored_turn)

    def test_rich_story_duration_contract_does_not_pad_semantic_scenes(self) -> None:
        module = load_frontend_run_module()
        story = {
            "story_metadata": {
                "scene_authoring_contract": "story_scene_contract_v1",
                "target_duration_seconds": 600,
            },
            "script": {
                "scenes": [
                    {
                        "scene_id": "scene_01",
                        "target_duration_seconds": 300,
                        "narration_target_seconds": 210,
                    },
                    {
                        "scene_id": "scene_02",
                        "target_duration_seconds": 300,
                        "narration_target_seconds": 210,
                    },
                ]
            },
        }

        errors = module._story_duration_contract_errors(
            story,
            target_duration_seconds=600,
        )

        self.assertEqual(errors, [])

    def test_story_scene_overview_stays_out_of_drawable_evidence(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile(
            "桃太郎", "桃太郎", variant_seed="story-scene-overview"
        )
        overview = "炉を掃除する → 籠を置かれる → 一人だけ台所に残される"
        profile["story_scenes"] = [
            {
                "scene_id": 1,
                "visualizable_action": overview,
                "research_refs": [],
            }
        ]
        blueprint = {
            "visible_evidence": ["灰の床", "家事道具の籠"],
            "research_refs": [],
        }

        authored = module._apply_story_scene_to_blueprint(
            blueprint,
            profile=profile,
            idx=1,
        )

        self.assertEqual(authored["visible_evidence"], blueprint["visible_evidence"])
        self.assertEqual(authored["story_overview_visualizable_action"], overview)
        self.assertNotIn("→", " / ".join(authored["visible_evidence"]))

    def test_story_time_of_day_contract_blocks_missing_or_non_string_scene_values(self) -> None:
        module = load_frontend_run_module()
        story = minimal_authored_story_for_time_contract()

        story["script"]["scenes"][0]["time_of_day"] = ""
        story["script"]["scenes"][1]["time_of_day"] = ["夜"]

        with self.assertRaisesRegex(RuntimeError, r"scene\[1\]\.time_of_day.*scene\[2\]\.time_of_day"):
            module._validate_story_time_of_day_contract(story)

    def test_blank_scene_time_of_day_never_becomes_an_unknown_prompt_placeholder(self) -> None:
        module = load_frontend_run_module()

        self.assertEqual(module._scene_time_of_day({"scene_times_of_day": [""]}, 1), "")

    def test_time_of_day_visual_basis_names_every_lighting_dimension(self) -> None:
        module = load_frontend_run_module()

        self.assertEqual(module._time_of_day_visual_basis(""), "")
        for time_of_day in ("朝", "昼", "夕方", "夜", "真夜中", "薄明の架空時間"):
            basis = module._time_of_day_visual_basis(time_of_day)
            for dimension in ("光源", "明るさ", "影", "色温度"):
                self.assertIn(dimension, basis, (time_of_day, basis))

    def test_story_time_of_day_contract_requires_visual_basis(self) -> None:
        module = load_frontend_run_module()
        story = minimal_authored_story_for_time_contract()

        story["script"]["scenes"][0]["time_of_day_visual_basis"] = ""

        with self.assertRaisesRegex(RuntimeError, r"scene\[1\]\.time_of_day_visual_basis"):
            module._validate_story_time_of_day_contract(story)

    def test_scaffold_not_yet_never_copies_next_positive_first_frame_brief(self) -> None:
        module = load_frontend_run_module()
        self.assertEqual(
            module._drawable_phrase_for_scaffold(
                "前cutの「扉が閉じている」から、このcutでは「旅人が「古い鍵」を掲げる」へ進む"
            ),
            "旅人が「古い鍵」を掲げる",
        )
        plan = module._first_frame_visual_plan_for_scaffold(
            selector="scene10_cut01",
            profile={
                "slug": "sample",
                "protagonist_name": "旅人",
                "artifact_name": "古い鍵",
                "artifact_output_dir": "objects",
            },
            location_spec={
                "asset_id": "stone_gate",
                "visual_spec": {"subject": "石造りの城門、夕方の斜光"},
            },
            location_name="石造りの城門",
            cut_number=1,
            cut_plan={
                "foreground": "古い鍵",
                "midground": "旅人",
                "background": "石造りの城門",
                "screen_direction": "右奥",
            },
            cut_blueprint={
                "cut_function": "setup",
                "visual_beat": "旅人が古い鍵を手に城門の前で立ち止まる",
                "target_beat": "城門を越える前",
                "first_frame_brief": "旅人と古い鍵が城門の前に見える",
                "causal_proof": "古い鍵",
                "dramatic_job": "越境の準備",
            },
            cut_contract={
                "source_event_contract": {},
                "first_frame_contract": {
                    "event_fact_visible_in_still": "旅人が古い鍵を手に城門の前で立ち止まる",
                    "event_time_position": "before_trigger",
                },
                "viewer_contract": {
                    "reveal_constraints": {
                        "forbidden_until_later_cut": ["城門の向こうにいる人物の正体"],
                    },
                },
                "cinematic_contract": {
                    "screen_geography": {
                        "foreground": "古い鍵",
                        "midground": "旅人",
                        "background": "石造りの城門",
                    }
                },
                "cut_state_progression": {
                    "must_not_advance_beyond": "古い鍵を前景で明確に見せる",
                },
            },
            character_ids=["traveler"],
            object_ids=["old_key"],
            references=["assets/characters/traveler.png", "assets/objects/old_key.png"],
            cut_uses_artifact=False,
        )

        not_yet = plan["temporal_boundary"]["not_yet_happened_in_still"]
        self.assertEqual(not_yet, ["城門の向こうにいる人物の正体"])
        self.assertNotIn("古い鍵を前景で明確に見せる", not_yet)

    def test_scene_target_seconds_are_distributed_deterministically_across_semantic_cuts(self) -> None:
        module = load_frontend_run_module()

        self.assertEqual(
            module._allocate_scene_cut_durations(
                scene_target_seconds=38,
                cut_count=4,
            ),
            [10, 10, 9, 9],
        )
        self.assertEqual(
            module._allocate_scene_cut_durations(
                scene_target_seconds=37,
                cut_count=8,
            ),
            [5, 5, 5, 5, 5, 4, 4, 4],
        )
        self.assertEqual(
            module._allocate_scene_cut_durations(
                scene_target_seconds=40,
                cut_count=1,
            ),
            [40],
        )
        self.assertEqual(
            module._allocate_scene_cut_durations(
                scene_target_seconds=60,
                cut_count=4,
            ),
            [15, 15, 15, 15],
        )
        fifteen_second_exception = module._duration_exception_for_cut(15)
        self.assertTrue(fifteen_second_exception["allowed"])
        self.assertTrue(fifteen_second_exception["reason"])
        self.assertEqual(
            module._duration_exception_for_cut(12),
            {"allowed": False, "reason": ""},
        )
        with self.assertRaisesRegex(RuntimeError, "Kling duration range"):
            module._allocate_scene_cut_durations(
                scene_target_seconds=61,
                cut_count=1,
            )

    def test_scaffold_prompt_compiler_omits_unbound_character_and_object_sections(self) -> None:
        module = load_frontend_run_module()
        first_frame_visual_plan = {
            "schema_version": "first_frame_visual_plan_v1",
            "editable": False,
            "temporal_boundary": {
                "event_fact_visible_in_still": "月光を受けた空の門が半分だけ開いている",
                "not_yet_happened_in_still": [],
            },
            "subject_binding": {
                "primary_subject": {"name": "半分だけ開いた空の門"},
            },
            "object_visibility_gate": {"objects": []},
            "spatial_composition": {
                "foreground": "濡れた石畳",
                "midground": "半分だけ開いた門",
                "background": "月明かりの道",
            },
            "scene_material_pack": {
                "light_source": "門の上から差す月光",
                "dominant_materials": ["濡れた石と古い鉄"],
            },
        }

        payload = module._image_api_prompt_payload_for_scaffold(
            first_frame_visual_plan=first_frame_visual_plan,
            character_ids=[],
            object_ids=[],
            location_ids=["opaque_gate_id"],
            references=[],
        )

        self.assertEqual(payload["policy_version"], "image_api_prompt_v2")
        self.assertNotIn("[登場人物]", payload["prompt"])
        self.assertNotIn("[小道具 / 舞台装置]", payload["prompt"])
        self.assertNotIn("opaque_gate_id", payload["prompt"])

    def test_scaffold_handoff_visible_behavior_uses_post_action_hands(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile("桃太郎", "桃太郎", variant_seed="handoff-hands")

        behavior = module._visible_behavior_from_cut(
            profile=profile,
            cut_plan={"screen_direction": "出口方向"},
            cut_blueprint={
                "cut_function": "handoff",
                "action_completion_state": "handoff_state",
                "first_frame_brief": "主人公は行動後の姿勢で出口へ重心を移している",
            },
            location_name="村の門前",
            object_ids=[],
        )

        self.assertNotIn("行為直前", behavior["hands"])
        self.assertIn("直前の動きが終わった位置", behavior["hands"])
        self.assertNotIn("主要な視覚証拠", " ".join(behavior.values()))
        self.assertNotIn("まだ結果へ到達していない", behavior["feet"])
        self.assertIn("行動後の位置", behavior["feet"])

    def test_scaffold_payoff_visible_behavior_uses_resolved_face_and_feet(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile("桃太郎", "桃太郎", variant_seed="payoff-state")

        behavior = module._visible_behavior_from_cut(
            profile=profile,
            cut_plan={"screen_direction": "終結位置"},
            cut_blueprint={
                "cut_function": "payoff",
                "action_completion_state": "handoff_state",
                "first_frame_brief": "主人公の肩から緊張が抜け、前景の痕跡のそばに立つ",
            },
            location_name="村の広場",
            object_ids=[],
        )

        self.assertNotIn("主要な視覚証拠", " ".join(behavior.values()))
        self.assertIn("安堵", behavior["face"])
        self.assertNotIn("まだ結果へ到達していない", behavior["feet"])
        self.assertIn("重心は安定", behavior["feet"])

    def test_last_frame_boundary_validation_rejects_route_authorization_and_state_mismatches(self) -> None:
        module = load_frontend_run_module()
        route = ["出発地", "到着地"]
        valid_current = {
            "background": "出発地",
            "motion_end_state": "主人公が到着地の敷居内で止まっている",
            "allowed_new_reveal_elements": ["到着地"],
            "use_next_cut_first_frame_as_last_frame": True,
        }
        valid_next = {
            "background": "到着地",
            "first_frame_brief": "到着地。主人公が敷居内で止まっている",
            "visual_proof": valid_current["motion_end_state"],
        }

        boundary = module._validate_next_cut_last_frame_boundary(
            selector="scene10_cut01",
            current_cut_plan=valid_current,
            next_cut_plan=valid_next,
            route_locations=route,
        )
        self.assertEqual(boundary["destination_location"], "到着地")
        self.assertEqual(
            boundary["actual_end_state"], valid_current["motion_end_state"]
        )

        with self.assertRaisesRegex(RuntimeError, "not declared in scene route"):
            module._validate_next_cut_last_frame_boundary(
                selector="scene10_cut01",
                current_cut_plan={
                    **valid_current,
                    "allowed_new_reveal_elements": ["ルート外"],
                    "motion_end_state": "主人公がルート外へ到着する",
                },
                next_cut_plan={**valid_next, "background": "ルート外"},
                route_locations=route,
            )
        with self.assertRaisesRegex(RuntimeError, "exact obligation authorization"):
            module._validate_next_cut_last_frame_boundary(
                selector="scene10_cut01",
                current_cut_plan={**valid_current, "allowed_new_reveal_elements": []},
                next_cut_plan=valid_next,
                route_locations=route,
            )
        with self.assertRaisesRegex(RuntimeError, "motion end state does not reach"):
            module._validate_next_cut_last_frame_boundary(
                selector="scene10_cut01",
                current_cut_plan={
                    **valid_current,
                    "motion_end_state": "主人公が出発地に留まっている",
                },
                next_cut_plan=valid_next,
                route_locations=route,
            )
        with self.assertRaisesRegex(RuntimeError, "actual motion end state"):
            module._validate_next_cut_last_frame_boundary(
                selector="scene10_cut01",
                current_cut_plan=valid_current,
                next_cut_plan={
                    **valid_next,
                    "first_frame_brief": "到着地。主人公が別の姿勢で立つ",
                    "visual_proof": "主人公が到着地で別の姿勢を取る",
                },
                route_locations=route,
            )

        same_location_current = {
            "background": "同じ場所",
            "motion_end_state": "主人公の右手が扉の取っ手に触れている",
            "allowed_new_reveal_elements": [],
            "use_next_cut_first_frame_as_last_frame": True,
        }
        with self.assertRaisesRegex(RuntimeError, "actual motion end state"):
            module._validate_next_cut_last_frame_boundary(
                selector="scene10_cut02",
                current_cut_plan=same_location_current,
                next_cut_plan={
                    "background": "同じ場所",
                    "first_frame_brief": "同じ場所。主人公は扉から離れている",
                    "visual_proof": "主人公の両手は身体の横にある",
                },
                route_locations=["同じ場所"],
            )

    def test_adjacent_semantic_cuts_fail_closed_when_they_replay_identical_motion(self) -> None:
        module = load_frontend_run_module()
        distinct = [
            {"motion_brief": "人物が扉へ手を伸ばす", "motion_end_state": "手が扉の前で止まる"},
            {"motion_brief": "人物が扉を開く", "motion_end_state": "扉が身体一人分だけ開く"},
        ]
        module._validate_adjacent_cut_motion_is_distinct(
            scene_id=10,
            cut_plans=distinct,
        )
        with self.assertRaisesRegex(RuntimeError, "replay identical motion"):
            module._validate_adjacent_cut_motion_is_distinct(
                scene_id=10,
                cut_plans=[distinct[0], dict(distinct[0])],
            )

    def test_character_reference_binding_never_uses_positional_non_character_refs(self) -> None:
        module = load_frontend_run_module()
        with self.assertRaisesRegex(RuntimeError, "character reference binding"):
            module._bind_character_reference_pairs(
                character_ids=["hero", "ally"],
                references=[
                    "assets/characters/hero.png",
                    "assets/locations/palace.png",
                    "assets/objects/key.png",
                ],
                context="scene10_cut01",
            )
        self.assertEqual(
            module._bind_character_reference_pairs(
                character_ids=["hero", "ally"],
                references=[
                    "assets/characters/ally.png",
                    "assets/locations/palace.png",
                    "assets/characters/hero.png",
                ],
                context="scene10_cut02",
            ),
            [
                ("hero", "assets/characters/hero.png"),
                ("ally", "assets/characters/ally.png"),
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "id mismatch"):
            module._bind_character_reference_pairs(
                character_ids=["hero", "ally"],
                references=[
                    "assets/characters/hero.png",
                    "assets/characters/rival.png",
                ],
                context="scene10_cut03",
            )
