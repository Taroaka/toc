import subprocess
import sys
import tempfile
import unittest
import re
import json
import importlib.util
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import yaml

from toc.semantic_review import FOUNDATION_SEMANTIC_CRITERIA


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


def load_image_prompt_review_module():
    spec = importlib.util.spec_from_file_location(
        "image_prompt_story_review_under_test",
        REPO_ROOT / "scripts" / "review-image-prompt-story-consistency.py",
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


class TestTocImmersiveFrontendRun(unittest.TestCase):
    @staticmethod
    def _legacy_cinderella_profile(module, *, target_seconds: int = 300, seed: str = "boundary"):
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            return module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed=seed),
                target_duration_seconds=target_seconds,
            )

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

    def test_pre_media_semantic_pipeline_reviews_every_design_stage_without_media(self) -> None:
        module = load_frontend_run_module()
        calls: list[tuple[str, bool]] = []

        async def review(_job_id, *, run_dir, stage, image_prompt_provider_ready=True):
            self.assertEqual(run_dir, Path("/tmp/example-run"))
            calls.append((stage, image_prompt_provider_ready))

        with patch("server.image_gen_app._run_semantic_review", side_effect=review):
            import asyncio

            asyncio.run(
                module.run_pre_media_semantic_pipeline(
                    Path("/tmp/example-run"),
                    image_prompt_provider_ready=False,
                )
            )

        self.assertEqual(
            calls,
            [
                ("scene_set", True),
                ("scene_detail", True),
                ("cut_blueprint", True),
                ("asset_plan", True),
                ("image_prompt", False),
            ],
        )

    def test_materialize_only_main_runs_semantic_pipeline_but_not_media_generation(self) -> None:
        module = load_frontend_run_module()
        semantic_pipeline = AsyncMock()
        media_generation = AsyncMock()

        with (
            patch.object(module, "materialize_run"),
            patch.object(module, "prepare_grounding"),
            patch.object(module, "run_pre_media_semantic_pipeline", semantic_pipeline),
            patch.object(module, "generate_images", media_generation),
            patch.object(module, "write_run_index"),
            patch.object(
                sys,
                "argv",
                [
                    "toc-immersive-frontend-run.py",
                    "--topic",
                    "創作",
                    "--run-dir",
                    "/tmp/materialized-run",
                    "--materialize-only",
                    "--skip-validation",
                ],
            ),
        ):
            module.main()

        semantic_pipeline.assert_awaited_once_with(
            Path("/tmp/materialized-run"),
            image_prompt_provider_ready=False,
        )
        media_generation.assert_not_awaited()

    @staticmethod
    def _write_passing_foundation_review(run_dir: Path, stage: str) -> None:
        review_dir = run_dir / "logs" / "review" / "semantic"
        review_dir.mkdir(parents=True, exist_ok=True)
        entry_id = f"{stage}:foundation"
        (review_dir / f"{stage}.collection.md").write_text(f"# Collection\n\n## {entry_id}\n", encoding="utf-8")
        (review_dir / f"{stage}.scope.json").write_text(
            json.dumps(
                {
                    "entry_count": 1,
                    "entry_ids": [entry_id],
                    "source_artifacts": ["research.md"] if stage == "research" else ["research.md", "story.md"],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (review_dir / f"{stage}.prompt.md").write_text("review prompt\n", encoding="utf-8")
        criteria_results = [
            {
                "criterion_id": criterion_id,
                "status": "passed",
                "evidence": f"{stage}.md:{criterion_id}",
            }
            for criterion_id in FOUNDATION_SEMANTIC_CRITERIA[stage]
        ]
        (review_dir / f"{stage}.report.md").write_text(
            "\n".join(
                [
                    "status: passed",
                    f"reviewed_entries: [{entry_id}]",
                    "blocked_entries: []",
                    "failed_selectors: []",
                    "criteria_results_json: " + json.dumps(criteria_results, ensure_ascii=False),
                    "findings: []",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_research_semantic_failure_stops_before_story_and_cut_generation(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_foundation_research_fail_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            cut_builder = Mock(side_effect=AssertionError("cut builder must not run"))

            def fail_research(_run_dir: Path, stage: str) -> None:
                self.assertEqual(stage, "research")
                raise RuntimeError("research semantic review failed")

            with patch.object(module, "_build_script_and_manifest", cut_builder):
                with self.assertRaisesRegex(RuntimeError, "research semantic review failed"):
                    module.materialize_run(
                        "桃太郎",
                        "桃太郎",
                        run_dir,
                        "p650",
                        target_duration_seconds=900,
                        foundation_review_runner=fail_research,
                    )

            self.assertTrue((run_dir / "research.md").exists())
            self.assertFalse((run_dir / "story.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "scene_design" / "scene_event_input.json").exists())
            cut_builder.assert_not_called()
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.target_video_seconds"], "900")
            self.assertEqual(state["runtime.duration_plan.minimum_scene_count"], "23")
            self.assertNotIn("runtime.duration_plan.minimum_cut_count", state)
            self.assertEqual(state["runtime.duration_plan.minimum_narration_seconds"], "630")

    def test_story_semantic_transport_failure_stops_before_cut_generation(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_foundation_story_transport_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            cut_builder = Mock(side_effect=AssertionError("cut builder must not run"))
            reviewed: list[str] = []

            def review_foundation(target_run_dir: Path, stage: str) -> None:
                reviewed.append(stage)
                if stage == "story":
                    raise RuntimeError("Codex app-server transport failed")
                self._write_passing_foundation_review(target_run_dir, stage)

            with patch.object(module, "_build_script_and_manifest", cut_builder):
                with self.assertRaisesRegex(RuntimeError, "transport failed"):
                    module.materialize_run(
                        "桃太郎",
                        "桃太郎",
                        run_dir,
                        "p650",
                        foundation_review_runner=review_foundation,
                    )

            self.assertEqual(reviewed, ["research", "story"])
            self.assertTrue((run_dir / "research.md").exists())
            self.assertTrue((run_dir / "story.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "scene_design" / "scene_event_input.json").exists())
            cut_builder.assert_not_called()

    def test_cli_main_always_enables_foundation_semantic_reviews(self) -> None:
        module = load_frontend_run_module()
        calls: list[dict[str, object]] = []
        semantic_pipeline = AsyncMock()

        def fake_materialize(*args, **kwargs) -> None:
            calls.append({"args": args, "kwargs": kwargs})

        with (
            patch.object(module, "materialize_run", fake_materialize),
            patch.object(module, "prepare_grounding", Mock()),
            patch.object(
                module,
                "run_pre_media_semantic_pipeline",
                semantic_pipeline,
            ),
            patch.object(module, "write_run_index", Mock()),
            patch.object(
                sys,
                "argv",
                [
                    "toc-immersive-frontend-run.py",
                    "--topic",
                    "桃太郎",
                    "--run-dir",
                    "output/test_foundation_cli",
                    "--materialize-only",
                    "--skip-validation",
                ],
            ),
        ):
            module.main()

        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]["kwargs"]["foundation_review_runner"], module._run_foundation_semantic_review)
        semantic_pipeline.assert_awaited_once_with(
            Path("output/test_foundation_cli"),
            image_prompt_provider_ready=False,
        )

    def test_orchestration_results_match_completed_foundation_review_slots(self) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory(prefix="frontend_orchestration_foundations_") as tmp:
            run_dir = Path(tmp)
            module._write_orchestration(
                run_dir,
                "p680",
                "2099-01-01T00:00:00+09:00",
                foundation_reviews_passed=True,
            )
            p100 = json.loads(
                (run_dir / "logs" / "orchestration" / "p100.supervisor_result.json").read_text(encoding="utf-8")
            )
            p200 = json.loads(
                (run_dir / "logs" / "orchestration" / "p200.supervisor_result.json").read_text(encoding="utf-8")
            )
            p600 = json.loads(
                (run_dir / "logs" / "orchestration" / "p600.supervisor_result.json").read_text(encoding="utf-8")
            )

        self.assertEqual(p100["state_keys"]["slot.p130.status"], "done")
        self.assertEqual(p200["state_keys"]["slot.p230.status"], "done")
        self.assertEqual(p600["status"], "pending")
        self.assertEqual(p600["completed_slots"], ["p610", "p620"])
        self.assertEqual(p600["state_keys"]["slot.p680.status"], "pending")

    def test_reviewed_foundations_feed_story_and_cut_builders(self) -> None:
        module = load_frontend_run_module()
        base_profile = module._duration_aware_profile(
            module._story_profile("桃太郎", "桃太郎", variant_seed="reviewed-foundation"),
            target_duration_seconds=300,
        )
        reviewed_event = "審査で確定した出来事が、主人公を橋の向こうへ進ませる。"
        reviewed_research = {
            "story_materials": {
                "canonical_story_dump": "審査済みの内部物語基準。",
                "chronological_events": [{"event_id": "E99", "event": reviewed_event}],
                "characters": [{"character_id": "protagonist", "name": "審査済み主人公", "role": "主人公"}],
            },
            "source_passages": [{"passage_id": "P99", "passage": reviewed_event}],
        }

        research_profile = module._profile_from_reviewed_research(base_profile, reviewed_research)
        story = module._build_story("桃太郎", Path("output/reviewed-foundation"), "2026-07-11T00:00:00+09:00", research_profile)

        self.assertIn("time", story["story_metadata"])
        self.assertIsInstance(story["story_metadata"]["time"], str)
        self.assertEqual(research_profile["events"], [reviewed_event])
        self.assertIn(reviewed_event, story["script"]["scenes"][0]["purpose"])
        self.assertIn("research.story_materials.chronological_events[E99]", story["script"]["scenes"][0]["research_refs"])
        self.assertIn("research.source_passages[P99]", story["script"]["scenes"][0]["research_refs"])

        reviewed_turn = "審査で修正された不可逆な転換を画面上の事実にする。"
        story["script"]["scenes"][0]["purpose"] = "審査で修正されたscene目的"
        story["script"]["scenes"][0]["turn"] = reviewed_turn
        story["story_metadata"]["time"] = "室町時代"
        cut_profile = module._profile_from_reviewed_story(research_profile, story)
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

        self.assertEqual(scene_intent["story_purpose"], "審査で修正されたscene目的")
        self.assertEqual(scene_intent["causal_turn"], reviewed_turn)
        turn_beat = next(item for item in scene_event["event_sequence"] if item["beat_function"] == "turn")
        self.assertEqual(turn_beat["what_happens"], reviewed_turn)

    def test_reviewed_story_scene_overview_stays_out_of_drawable_evidence(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile(
            "桃太郎", "桃太郎", variant_seed="reviewed-scene-overview"
        )
        overview = "炉を掃除する → 籠を置かれる → 一人だけ台所に残される"
        profile["reviewed_story_scenes"] = [
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

        reviewed = module._apply_reviewed_story_scene_to_blueprint(
            blueprint,
            profile=profile,
            idx=1,
        )

        self.assertEqual(reviewed["visible_evidence"], blueprint["visible_evidence"])
        self.assertEqual(reviewed["review_only_visualizable_action"], overview)
        self.assertNotIn("→", " / ".join(reviewed["visible_evidence"]))

    def test_reviewed_story_preserves_explicit_empty_time_instead_of_profile_fallback(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile("シンデレラを下敷きにした創作", "ユーザー創作")
        self.assertTrue(profile["story_time"])

        reviewed = module._profile_from_reviewed_story(
            profile,
            {
                "story_metadata": {"time": ""},
                "script": {"scenes": []},
            },
        )

        self.assertEqual(reviewed["story_time"], "")

    def test_reviewed_story_time_of_day_contract_blocks_missing_or_non_string_scene_values(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("桃太郎", "桃太郎", variant_seed="daypart-contract"),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            story = module._build_story(
                "桃太郎",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        story["script"]["scenes"][0]["time_of_day"] = ""
        story["script"]["scenes"][1]["time_of_day"] = ["夜"]

        with self.assertRaisesRegex(RuntimeError, r"scene\[1\]\.time_of_day.*scene\[2\]\.time_of_day"):
            module._validate_reviewed_story_time_of_day_contract(story)

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

    def test_reviewed_story_time_of_day_contract_requires_visual_basis(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("桃太郎", "桃太郎", variant_seed="daypart-visual-contract"),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            story = module._build_story(
                "桃太郎",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        story["script"]["scenes"][0]["time_of_day_visual_basis"] = ""

        with self.assertRaisesRegex(RuntimeError, r"scene\[1\]\.time_of_day_visual_basis"):
            module._validate_reviewed_story_time_of_day_contract(story)

    def test_reviewed_story_multi_location_contract_requires_one_segment_per_location(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="location-segment-gate"),
            target_duration_seconds=300,
        )
        story = module._build_story(
            "シンデレラ",
            Path("output/location-segment-gate"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        story["script"]["scenes"][7]["location"]["segments"] = story["script"]["scenes"][7]["location"]["segments"][:-1]

        with self.assertRaisesRegex(RuntimeError, "location.segments must cover every sequence location"):
            module._validate_reviewed_story_time_of_day_contract(story)

    def test_scene_time_of_day_reaches_story_script_manifest_and_scene_prompts(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            profile = module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed="daypart-audit"),
                target_duration_seconds=300,
            )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            story = module._build_story(
                "シンデレラ",
                run_dir,
                "2099-01-01T00:00:00+09:00",
                profile,
            )
            reviewed_profile = module._profile_from_reviewed_story(profile, story)
            script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                run_dir,
                "2099-01-01T00:00:00+09:00",
                reviewed_profile,
            )

        story_times = [scene["time_of_day"] for scene in story["script"]["scenes"]]
        script_times = [scene["time_of_day"] for scene in script["scenes"]]
        manifest_times = [scene["time_of_day"] for scene in manifest["scenes"]]
        story_bases = [scene["time_of_day_visual_basis"] for scene in story["script"]["scenes"]]
        script_bases = [scene["time_of_day_visual_basis"] for scene in script["scenes"]]
        manifest_bases = [scene["time_of_day_visual_basis"] for scene in manifest["scenes"]]
        self.assertEqual(story["story_metadata"]["scene_time_of_day_contract"], "required_v1")
        self.assertEqual(story["story_metadata"]["scene_time_of_day_visual_basis_contract"], "required_v1")
        self.assertEqual(script["script_metadata"]["scene_time_of_day_contract"], "required_v1")
        self.assertEqual(script["script_metadata"]["scene_time_of_day_visual_basis_contract"], "required_v1")
        self.assertEqual(manifest["video_metadata"]["scene_time_of_day_contract"], "required_v1")
        self.assertEqual(manifest["video_metadata"]["scene_time_of_day_visual_basis_contract"], "required_v1")
        self.assertEqual(story_times, script_times)
        self.assertEqual(script_times, manifest_times)
        self.assertEqual(story_bases, script_bases)
        self.assertEqual(script_bases, manifest_bases)
        self.assertTrue(all(story_times))
        self.assertTrue(all(story_bases))
        self.assertIn("朝", story_times)
        self.assertIn("夜", story_times)
        self.assertIn("真夜中", story_times)
        self.assertIn("昼", story_times)
        for scene, time_of_day, visual_basis in zip(
            script["scenes"], script_times, script_bases, strict=True
        ):
            authoring_context = scene["scene_generation"]["scene_authoring_context"]
            self.assertEqual(authoring_context["time_of_day"], time_of_day)
            self.assertEqual(authoring_context["time_of_day_visual_basis"], visual_basis)
            self.assertIn(
                f"時間帯: {time_of_day}",
                scene["scene_generation"]["scene_prompt_payload"]["prompt"],
            )
            self.assertIn(
                f"時間帯の視覚根拠: {visual_basis}",
                scene["scene_generation"]["scene_prompt_payload"]["prompt"],
            )
        for scene, time_of_day in zip(manifest["scenes"], manifest_times, strict=True):
            for cut in scene["cuts"]:
                payload = cut["image_generation"]["api_prompt_payload"]
                visual_plan = cut["image_generation"]["first_frame_visual_plan"]
                self.assertEqual(
                    visual_plan["scene_material_pack"]["time_of_day"],
                    time_of_day,
                )
                self.assertEqual(
                    payload["drawable_prompt_ir"]["dependencies"]["time_of_day"],
                    time_of_day,
                )
                self.assertIn(f"このシーンの時間帯は{time_of_day}", payload["prompt"])

    def test_story_time_reaches_asset_and_scene_image_prompts(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            cinderella_profile = module._story_profile("シンデレラ", "シンデレラ")
        self.assertEqual(cinderella_profile["story_time"], "17世紀末フランス・ルイ14世時代")
        profile = module._story_profile("桃太郎", "桃太郎", variant_seed="story-time")
        self.assertEqual(profile["story_time"], "")
        profile["story_time"] = "室町時代"
        asset_prompt = module._prompt_for_asset(
            {
                "asset_id": "protagonist",
                "asset_type": "character_reference",
                "story_purpose": "主人公の同一性を固定する",
                "visual_spec": {"subject": "若い旅人の全身参照"},
                "generation_plan": {"reference_inputs": []},
            },
            profile,
        )
        self.assertIn("物語の時代背景は室町時代", asset_prompt)

        plan = {
            "temporal_boundary": {"event_fact_visible_in_still": "旅人が木造の門前に立っている"},
            "subject_binding": {"primary_subject": {"name": "門前に立つ旅人"}},
            "spatial_composition": {
                "foreground": "土の道",
                "midground": "門前に立つ旅人",
                "background": "木造の門",
            },
            "scene_material_pack": {"dominant_materials": ["木、土、麻布"]},
        }
        payload = module._image_api_prompt_payload_for_scaffold(
            first_frame_visual_plan=plan,
            character_ids=[],
            object_ids=[],
            location_ids=["village_gate"],
            references=[],
            story_time=profile["story_time"],
        )
        self.assertIn("物語の時代背景は室町時代", payload["prompt"])

        with tempfile.TemporaryDirectory() as tmp:
            build_profile = module._duration_aware_profile(profile, target_duration_seconds=300)
            script, manifest, _selectors = module._build_script_and_manifest(
                "桃太郎",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                build_profile,
            )
        self.assertEqual(script["script_metadata"]["time"], "室町時代")
        self.assertEqual(manifest["video_metadata"]["time"], "室町時代")
        first_prompt = manifest["scenes"][0]["cuts"][0]["image_generation"]["api_prompt_payload"]["prompt"]
        self.assertIn("物語の時代背景は室町時代", first_prompt)
        provider_prompts = [
            cut["image_generation"]["api_prompt_payload"]["prompt"]
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        ]
        for production_term in (
            "setup beat",
            "pressure beat",
            "turn beat",
            "payoff beat",
            "観客がscene",
            "sceneを誤読",
            "scene理解",
            "画面に置く",
            "人物を囲む配置",
            "へ具体的に反応する",
            "sceneの結果を次へ渡す",
            "場面の結果を次へ渡す",
            "主要な視覚証拠",
        ):
            self.assertFalse(
                any(production_term in prompt for prompt in provider_prompts),
                production_term,
            )
        for prompt in provider_prompts:
            self.assertFalse(
                "行動後" in prompt and "行為直前" in prompt,
                prompt,
            )

        profile["story_time"] = ""
        empty_asset_prompt = module._prompt_for_asset(
            {
                "asset_id": "protagonist",
                "asset_type": "character_reference",
                "visual_spec": {"subject": "創作世界の旅人"},
                "generation_plan": {"reference_inputs": []},
            },
            profile,
        )
        self.assertNotIn("物語の時代背景", empty_asset_prompt)

    def test_cinderella_provider_prompts_are_era_grounded_and_free_of_production_shorthand(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            profile = module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed="provider-audit"),
                target_duration_seconds=300,
            )
        with tempfile.TemporaryDirectory() as tmp:
            script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        prompts = [
            cut["image_generation"]["api_prompt_payload"]["prompt"]
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        ]
        self.assertGreaterEqual(len(prompts), 40)
        self.assertTrue(
            all("物語の時代背景は17世紀末フランス・ルイ14世時代" in prompt for prompt in prompts)
        )
        _inventory, asset_plan = module._build_asset_artifacts_from_manifest(
            profile=profile,
            manifest=manifest,
        )
        asset_prompts = [
            module._prompt_for_asset(entry, profile)
            for entry in asset_plan["assets"]
        ]
        self.assertGreaterEqual(len(asset_prompts), 10)
        self.assertTrue(
            all(
                "物語の時代背景は17世紀末フランス・ルイ14世時代" in prompt
                for prompt in asset_prompts
            )
        )
        for production_term in (
            "setup beat",
            "pressure beat",
            "turn beat",
            "payoff beat",
            "観客がscene",
            "sceneを誤読",
            "scene理解",
            "画面に置く",
            "人物を囲む配置",
            "へ具体的に反応する",
            "sceneの結果を次へ渡す",
            "場面の結果を次へ渡す",
            "主要な視覚証拠",
        ):
            self.assertFalse(any(production_term in prompt for prompt in prompts), production_term)
        self.assertFalse(any("行動後" in prompt and "行為直前" in prompt for prompt in prompts))
        self.assertFalse(
            any("行動後" in prompt and "まだ結果へ到達していない" in prompt for prompt in prompts)
        )
        self.assertFalse(
            any("証明を受け止めた姿勢" in prompt and "圧力を受け止めている表情" in prompt for prompt in prompts)
        )
        reviewer = load_image_prompt_review_module()
        entries = reviewer.manifest_prompt_entries(
            manifest,
            allowed_story_modes={"generate_still"},
        )
        outcomes = reviewer.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={},
            script_scene_map=reviewer.extract_scene_context_map(script),
            story_text="",
            script_text="",
            reveal_constraints=[],
        )
        hard_findings = [
            (reviewer._selector_label(outcome.entry.scene_id, outcome.entry.cut_id), finding.code)
            for outcome in outcomes
            for finding in outcome.findings
            if reviewer.is_hard_finding(finding)
        ]
        self.assertEqual(hard_findings, [])

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

    def test_cinderella_research_is_causally_complete_and_yaml_round_trippable(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="research-sufficiency"),
            target_duration_seconds=300,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )

        character_ids = {
            item["character_id"]
            for item in research["story_materials"]["characters"]
        }
        self.assertTrue(
            {"protagonist", "stepmother", "stepsisters", "helper", "prince", "royal_envoy"}.issubset(character_ids)
        )
        conflict = research["conflicts"][0]
        self.assertEqual(conflict["selection_notes"]["selected_choice"], "A")
        self.assertEqual(conflict["selection_notes"]["resolution_status"], "resolved")
        self.assertEqual(research["open_questions"], [])
        events_by_id = {
            item["event_id"]: item["event"]
            for item in research["story_materials"]["chronological_events"]
        }
        self.assertIn("助力者", events_by_id["E04"])
        self.assertIn("門を越えて", events_by_id["E05"])
        shoe_symbol = next(
            item
            for item in research["story_materials"]["symbols_and_themes"]
            if item["item_id"] == "SYM2"
        )
        self.assertEqual(shoe_symbol["evidence_refs"], ["P4"])
        passages_by_id = {item["passage_id"]: item["passage"] for item in research["source_passages"]}
        self.assertIn("ガラスの靴", passages_by_id["P4"])
        self.assertGreaterEqual(len(research["handoff_to_story"]["character_event_contract"]), 6)
        self.assertGreaterEqual(len(research["handoff_to_story"]["resolved_causal_chain"]), 5)

        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="research_roundtrip_", dir=output_root) as tmp:
            path = Path(tmp) / "research.md"
            path.write_text(module._md_yaml("Research", research), encoding="utf-8")
            _text, reloaded = module.load_structured_document(path)

        self.assertEqual(reloaded["metadata"]["target_duration_seconds"], 300)
        self.assertEqual(reloaded["conflicts"][0]["selection_notes"]["resolution_status"], "resolved")

    def test_cinderella_story_allocates_all_research_events_in_causal_order(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="story-allocation"),
            target_duration_seconds=300,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        profile = module._profile_from_reviewed_research(profile, research)
        story = module._build_story(
            "シンデレラ",
            Path("output/story-allocation"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )

        event_ids = [
            ref.rsplit("[", 1)[1][:-1]
            for scene in story["script"]["scenes"]
            for ref in scene["research_refs"]
            if ref.startswith("research.story_materials.chronological_events[")
        ]

        self.assertEqual(event_ids, [f"E{index:02d}" for index in range(1, 11)])

    def test_cinderella_story_has_scene_specific_causal_and_visual_contracts(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="story-semantic-readiness"),
            target_duration_seconds=300,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        profile = module._profile_from_reviewed_research(profile, research)
        story = module._build_story(
            "シンデレラ",
            Path("output/story-semantic-readiness"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        scenes = story["script"]["scenes"]

        expected_passage_ids = [
            ["P1"],
            ["P2", "P3"],
            ["P4"],
            ["P5"],
            [],
            [],
            [],
            [],
        ]
        actual_passage_ids = [
            [
                ref.rsplit("[", 1)[1][:-1]
                for ref in scene["research_refs"]
                if ref.startswith("research.source_passages[")
            ]
            for scene in scenes
        ]
        self.assertEqual(actual_passage_ids, expected_passage_ids)

        self.assertEqual(len({scene["purpose"] for scene in scenes}), 8)
        self.assertEqual(len({scene["conflict"] for scene in scenes}), 8)
        self.assertEqual(len({scene["turn"] for scene in scenes}), 8)
        self.assertEqual(len({scene["visualizable_action"] for scene in scenes}), 8)
        self.assertEqual(len({scene["narration"] for scene in scenes}), 8)
        self.assertTrue(all(scene["character_ids"] for scene in scenes))
        self.assertTrue(all(scene["story_event_obligations"] for scene in scenes))

        self.assertIn("主人公自身", scenes[3]["purpose"])
        self.assertIn("門", scenes[3]["visualizable_action"])
        self.assertIn("裏口", scenes[1]["causal_handoff"])
        self.assertIn("月明かりの庭", scenes[1]["causal_handoff"])
        self.assertIn("王子", scenes[6]["turn"])
        self.assertIn("探索", scenes[6]["causal_handoff"])
        self.assertNotIn("探索を命じる", scenes[6]["segment_responsibility"])
        self.assertIn("探索を命じ", scenes[7]["segment_responsibility"])
        self.assertIn("王宮の使者", scenes[7]["visualizable_action"])
        self.assertIn("試着", scenes[7]["visualizable_action"])
        self.assertEqual(scenes[7]["location"]["mode"], "sequence")
        self.assertEqual(
            scenes[7]["location"]["sequence"],
            ["王宮の命令の間", "町の家々", "靴合わせの部屋"],
        )
        self.assertIn("王宮の命令の間", scenes[7]["visualizable_action"])
        self.assertIn("町の家々", scenes[7]["visualizable_action"])
        self.assertIn("探索", scenes[7]["narration"])
        self.assertIn("試着", scenes[7]["narration"])
        self.assertIn("公に", scenes[7]["turn"])

    def test_twenty_minute_cinderella_scenes_have_distinct_segment_responsibilities(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="story-longform-readiness"),
            target_duration_seconds=1200,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        profile = module._profile_from_reviewed_research(profile, research)
        story = module._build_story(
            "シンデレラ",
            Path("output/story-longform-readiness"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        scenes = story["script"]["scenes"]

        self.assertEqual(len(scenes), 30)
        self.assertEqual(len({scene["semantic_scene_responsibility_id"] for scene in scenes}), 30)
        self.assertEqual(len({scene["segment_responsibility"] for scene in scenes}), 30)
        self.assertTrue(all(scene["segment_beat_ids"] for scene in scenes))
        self.assertFalse(any("不可逆な一歩" in scene["turn"] for scene in scenes))

        for canonical_index in range(1, 9):
            group = [scene for scene in scenes if scene["canonical_scene_index"] == canonical_index]
            self.assertEqual(len({scene["segment_responsibility"] for scene in group}), len(group))
            self.assertEqual(len({scene["turn"] for scene in group}), len(group))

        departure_group = [scene for scene in scenes if scene["canonical_scene_index"] == 4]
        self.assertIn("馬車の扉", departure_group[0]["segment_responsibility"])
        self.assertIn("門を越える", departure_group[-1]["segment_responsibility"])
        proof_group = [scene for scene in scenes if scene["canonical_scene_index"] == 8]
        self.assertIn("王宮の使者", proof_group[0]["segment_responsibility"])
        self.assertIn("公に確認", proof_group[-1]["segment_responsibility"])

    def test_reviewed_story_research_refs_drive_downstream_source_grounding(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_reviewed_refs_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            profile = module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed="reviewed-refs"),
                target_duration_seconds=300,
            )
            now = "2099-01-01T00:00:00+09:00"
            research = module._build_research("シンデレラ", "シンデレラ", now, profile)
            profile = module._profile_from_reviewed_research(profile, research)
            story = module._build_story("シンデレラ", run_dir, now, profile)
            reviewed_ref = "research.story_materials.chronological_events[E10]"
            reviewed_event = research["story_materials"]["chronological_events"][-1]["event"]
            story["script"]["scenes"][0]["title"] = "審査済みの中立タイトル"
            story["script"]["scenes"][0]["research_refs"] = [reviewed_ref]
            profile = module._profile_from_reviewed_story(profile, story)
            (run_dir / "research.md").write_text(module._md_yaml("Research", research), encoding="utf-8")
            (run_dir / "story.md").write_text(module._md_yaml("Story", story), encoding="utf-8")

            script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                run_dir,
                now,
                profile,
            )

        for downstream_scene in (script["scenes"][0], manifest["scenes"][0]):
            self.assertEqual(downstream_scene["research_refs"], [reviewed_ref])
            scene_event = downstream_scene["scene_event"]
            self.assertEqual(scene_event["research_refs"], [reviewed_ref])
            self.assertTrue(
                all(beat["story_grounding"]["research_refs"] == [reviewed_ref] for beat in scene_event["event_sequence"])
            )
            setup_grounding = scene_event["event_sequence"][0]["story_grounding"]
            self.assertEqual(setup_grounding["research_refs"], [reviewed_ref])
            self.assertEqual(setup_grounding["source_text_or_summary"], reviewed_event)

            for cut in downstream_scene["cuts"]:
                source_grounding = cut["cut_contract"]["source_event_contract"]["source_story_grounding"]
                self.assertTrue(source_grounding)
                self.assertTrue(
                    all(item["research_refs"] == [reviewed_ref] for item in source_grounding)
                )

    def test_reviewed_story_conflict_ref_does_not_fall_back_to_heuristic_event(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="reviewed-conflict-ref"),
            target_duration_seconds=300,
        )
        now = "2099-01-01T00:00:00+09:00"
        research = module._build_research("シンデレラ", "シンデレラ", now, profile)
        profile = module._profile_from_reviewed_research(profile, research)
        story = module._build_story("シンデレラ", Path("output/reviewed-conflict-ref"), now, profile)
        reviewed_ref = "research.conflicts[C1]"
        conflict = research["conflicts"][0]
        expected_source = " / ".join(
            [
                conflict["topic"],
                conflict["accounts"][0]["claim"],
                conflict["impact_on_story"],
            ]
        )
        story["script"]["scenes"][0]["title"] = "審査済みの中立タイトル"
        story["script"]["scenes"][0]["research_refs"] = [reviewed_ref]
        profile = module._profile_from_reviewed_story(profile, story)

        self.assertEqual(module._scene_source_events(profile, 1), [expected_source])

        location = module._location_spec_for_scene(profile, 1)
        scene_intent = module._scene_intent_for_cut_design(
            title=profile["scene_titles"][0],
            idx=1,
            location_spec=location,
            profile=profile,
            include_artifact=False,
        )
        scene_event = module._scene_event_for_cut_design(
            title=profile["scene_titles"][0],
            idx=1,
            scene_intent=scene_intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=profile,
            include_artifact=False,
        )

        self.assertEqual(scene_event["research_refs"], [reviewed_ref])
        self.assertEqual(
            scene_event["event_sequence"][0]["story_grounding"]["source_text_or_summary"],
            expected_source,
        )

    def test_reviewed_story_duration_shrink_stops_before_cut_materialization(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_reviewed_duration_shrink_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            cut_builder = Mock(side_effect=AssertionError("cut builder must not run"))

            def review_and_shrink_story(target_run_dir: Path, stage: str) -> None:
                if stage == "story":
                    _text, story = module.load_structured_document(target_run_dir / "story.md")
                    story["script"]["scenes"] = story["script"]["scenes"][:1]
                    (target_run_dir / "story.md").write_text(
                        module._md_yaml("Story", story),
                        encoding="utf-8",
                    )
                self._write_passing_foundation_review(target_run_dir, stage)

            with patch.object(module, "_build_script_and_manifest", cut_builder):
                with self.assertRaisesRegex(RuntimeError, "reviewed story duration contract failed before cut materialization"):
                    module.materialize_run(
                        "シンデレラ",
                        "シンデレラ",
                        run_dir,
                        "p650",
                        target_duration_seconds=1200,
                        foundation_review_runner=review_and_shrink_story,
                    )

            cut_builder.assert_not_called()
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stage"], "reviewed_story_duration_contract_failed")
            self.assertEqual(state["slot.p230.status"], "failed")

    def test_reviewed_research_duration_change_stops_before_story_and_cuts(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_reviewed_research_duration_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            story_builder = Mock(side_effect=AssertionError("story builder must not run"))
            cut_builder = Mock(side_effect=AssertionError("cut builder must not run"))

            def review_and_change_research(target_run_dir: Path, stage: str) -> None:
                self.assertEqual(stage, "research")
                _text, research = module.load_structured_document(target_run_dir / "research.md")
                research["metadata"]["target_duration_seconds"] = 300
                research["metadata"]["duration_plan"]["target_seconds"] = 300
                (target_run_dir / "research.md").write_text(
                    module._md_yaml("Research", research),
                    encoding="utf-8",
                )
                self._write_passing_foundation_review(target_run_dir, stage)

            with (
                patch.object(module, "_build_story", story_builder),
                patch.object(module, "_build_script_and_manifest", cut_builder),
            ):
                with self.assertRaisesRegex(RuntimeError, "reviewed research duration contract failed"):
                    module.materialize_run(
                        "シンデレラ",
                        "シンデレラ",
                        run_dir,
                        "p650",
                        target_duration_seconds=1200,
                        foundation_review_runner=review_and_change_research,
                    )

            story_builder.assert_not_called()
            cut_builder.assert_not_called()
            self.assertFalse((run_dir / "story.md").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stage"], "reviewed_research_duration_contract_failed")
            self.assertEqual(state["slot.p130.status"], "failed")

    def test_reviewed_research_duration_contract_has_no_duration_cut_floor(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="reviewed-research-target"),
            target_duration_seconds=300,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        self.assertNotIn(
            "minimum_cut_count", research["metadata"]["duration_plan"]
        )
        module._validate_reviewed_research_duration_contract(
            research,
            target_duration_seconds=300,
        )

    def test_reviewed_story_duration_contract_requires_explicit_requested_target(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="reviewed-target"),
            target_duration_seconds=300,
        )
        story = module._build_story(
            "シンデレラ",
            Path("output/reviewed-target"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        story["story_metadata"].pop("target_duration_seconds")

        with self.assertRaisesRegex(RuntimeError, "story_metadata.target_duration_seconds"):
            module._validate_reviewed_story_duration_contract(
                story,
                target_duration_seconds=300,
            )

    def test_reviewed_story_scene_targets_must_be_exact_positive_integers(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="reviewed-integer-targets",
            ),
            target_duration_seconds=300,
        )
        story = module._build_story(
            "シンデレラ",
            Path("output/reviewed-integer-targets"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )

        fractional = deepcopy(story)
        for scene in fractional["script"]["scenes"]:
            scene["target_duration_seconds"] = 37.5
        with self.assertRaisesRegex(RuntimeError, "positive integer"):
            module._validate_reviewed_story_duration_contract(
                fractional,
                target_duration_seconds=300,
            )

        oversized = deepcopy(story)
        oversized["script"]["scenes"][0]["target_duration_seconds"] += 1
        with self.assertRaisesRegex(RuntimeError, "must equal requested target"):
            module._validate_reviewed_story_duration_contract(
                oversized,
                target_duration_seconds=300,
            )

    def test_duration_aware_profile_expands_canonical_beats_without_losing_order(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile("シンデレラ", "シンデレラ", variant_seed="duration-test")

        five_minutes = module._duration_aware_profile(profile, target_duration_seconds=300)
        twenty_minutes = module._duration_aware_profile(profile, target_duration_seconds=1200)

        self.assertEqual(len(five_minutes["scene_titles"]), 8)
        self.assertEqual(five_minutes["canonical_scene_indices"], list(range(1, 9)))
        self.assertEqual(len(twenty_minutes["scene_titles"]), 30)
        self.assertEqual(len(twenty_minutes["scene_locations"]), 30)
        self.assertEqual(len(twenty_minutes["scene_location_sequences"]), 30)
        self.assertTrue(all(sequence for sequence in twenty_minutes["scene_location_sequences"]))
        self.assertEqual(len(twenty_minutes["scene_location_segments"]), 30)
        for sequence, segments in zip(
            twenty_minutes["scene_location_sequences"],
            twenty_minutes["scene_location_segments"],
            strict=True,
        ):
            if segments:
                self.assertEqual(
                    {segment["location"] for segment in segments},
                    set(sequence),
                )
        self.assertEqual(len(twenty_minutes["scene_times_of_day"]), 30)
        self.assertEqual(len(twenty_minutes["canonical_scene_indices"]), 30)
        self.assertEqual(twenty_minutes["canonical_scene_indices"][0], 1)
        self.assertEqual(twenty_minutes["canonical_scene_indices"][-1], 8)
        self.assertEqual(sorted(twenty_minutes["canonical_scene_indices"]), twenty_minutes["canonical_scene_indices"])
        self.assertEqual(
            twenty_minutes["scene_times_of_day"],
            [
                twenty_minutes["canonical_scene_times_of_day"][canonical_index - 1]
                for canonical_index in twenty_minutes["canonical_scene_indices"]
            ],
        )
        self.assertEqual(twenty_minutes["duration_plan"]["target_seconds"], 1200)
        self.assertEqual(twenty_minutes["duration_plan"]["minimum_scene_count"], 30)
        self.assertNotIn("minimum_cut_count", twenty_minutes["duration_plan"])
        self.assertEqual(twenty_minutes["duration_plan"]["minimum_narration_seconds"], 840)
        self.assertEqual(sum(twenty_minutes["scene_target_durations"]), 1200)

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

    def test_cut_duration_fields_exactly_partition_cinderella_and_generic_targets(self) -> None:
        module = load_frontend_run_module()

        def build(profile: dict[str, object], *, topic: str):
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                research = module._build_research(topic, topic, "now", profile)
                (run_dir / "research.md").write_text(
                    module._md_yaml("Research", research), encoding="utf-8"
                )
                story = module._build_story(topic, run_dir, "now", profile)
                (run_dir / "story.md").write_text(
                    module._md_yaml("Story", story), encoding="utf-8"
                )
                return module._build_script_and_manifest(
                    topic, run_dir, "now", profile
                )[:2]

        long_semantic_cut_profile = module._duration_aware_profile(
            module._story_profile(
                "長い一場面",
                "長い一場面",
                variant_seed="exact-cut-duration-long-semantic-cut",
            ),
            target_duration_seconds=300,
        )
        long_semantic_cut_profile["scene_target_durations"] = [
            100,
            29,
            29,
            29,
            29,
            28,
            28,
            28,
        ]
        profiles = [
            (
                "シンデレラ",
                self._legacy_cinderella_profile(
                    module, seed="exact-cut-duration-cinderella"
                ),
            ),
            (
                "星の旅人",
                module._duration_aware_profile(
                    module._story_profile(
                        "星の旅人",
                        "星の旅人",
                        variant_seed="exact-cut-duration-generic",
                    ),
                    target_duration_seconds=300,
                ),
            ),
            ("長い一場面", long_semantic_cut_profile),
        ]

        saw_long_cut_exception = False
        saw_normal_cut_without_exception = False
        for topic, profile in profiles:
            with self.subTest(topic=topic):
                script, manifest = build(profile, topic=topic)
                target_seconds = int(
                    manifest["video_metadata"]["target_duration_seconds"]
                )
                self.assertEqual(target_seconds, 300)
                self.assertEqual(
                    manifest["video_metadata"]["duration_seconds"],
                    target_seconds,
                )
                self.assertEqual(
                    manifest["video_metadata"]["minimum_cut_count"],
                    sum(
                        int(
                            scene["scene_cut_coverage_plan"]["min_cut_count"][
                                "selected"
                            ]
                        )
                        for scene in manifest["scenes"]
                    ),
                )
                self.assertEqual(
                    sum(
                        int(cut["duration_seconds"])
                        for scene in manifest["scenes"]
                        for cut in scene["cuts"]
                    ),
                    target_seconds,
                )

                for script_scene, manifest_scene in zip(
                    script["scenes"], manifest["scenes"], strict=True
                ):
                    scene_target = int(manifest_scene["target_duration_seconds"])
                    self.assertEqual(
                        manifest_scene["estimated_duration_seconds"], scene_target
                    )
                    self.assertEqual(
                        script_scene["estimated_duration_seconds"], scene_target
                    )
                    manifest_cuts = {
                        cut["selector"]: cut for cut in manifest_scene["cuts"]
                    }
                    self.assertEqual(
                        sum(int(cut["duration_seconds"]) for cut in manifest_cuts.values()),
                        scene_target,
                    )
                    scene_cut_durations = [
                        int(cut["duration_seconds"])
                        for cut in manifest_scene["cuts"]
                    ]
                    self.assertLessEqual(
                        max(scene_cut_durations) - min(scene_cut_durations), 1
                    )
                    for script_cut in script_scene["cuts"]:
                        manifest_cut = manifest_cuts[script_cut["selector"]]
                        cut_seconds = int(manifest_cut["duration_seconds"])
                        self.assertGreaterEqual(cut_seconds, 1)
                        self.assertLessEqual(cut_seconds, 60)
                        self.assertEqual(
                            script_cut["target_duration_seconds"], cut_seconds
                        )
                        self.assertEqual(
                            script_cut["estimated_duration_seconds"], cut_seconds
                        )
                        self.assertEqual(
                            script_cut["cut_contract"]["target_duration_seconds"],
                            cut_seconds,
                        )
                        self.assertEqual(
                            script_cut["cut_contract"]["rhythm_contract"][
                                "expected_duration_seconds"
                            ],
                            cut_seconds,
                        )
                        self.assertIn(
                            f"{cut_seconds}秒",
                            script_cut["cut_blueprint"]["duration_intent"],
                        )
                        self.assertEqual(
                            manifest_cut["video_generation"]["duration_seconds"],
                            cut_seconds,
                        )
                        self.assertEqual(
                            manifest_cut["cut_contract"]["target_duration_seconds"],
                            cut_seconds,
                        )
                        self.assertEqual(
                            manifest_cut["cut_contract"]["rhythm_contract"][
                                "expected_duration_seconds"
                            ],
                            cut_seconds,
                        )
                        duration_exception = manifest_cut["cut_contract"][
                            "rhythm_contract"
                        ]["duration_exception"]
                        self.assertEqual(
                            duration_exception["allowed"], cut_seconds > 12
                        )
                        self.assertEqual(
                            bool(duration_exception["reason"]), cut_seconds > 12
                        )
                        self.assertEqual(
                            manifest_cut["video_generation"]["duration_exception"],
                            duration_exception,
                        )
                        saw_long_cut_exception |= cut_seconds > 12
                        saw_normal_cut_without_exception |= cut_seconds <= 12
        self.assertTrue(saw_long_cut_exception)
        self.assertTrue(saw_normal_cut_without_exception)

    def test_twenty_minute_builders_propagate_target_and_minimum_budgets(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_20m_", dir=output_root) as tmp:
            run_dir = Path(tmp)
            profile = module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed="duration-20m"),
                target_duration_seconds=1200,
            )
            now = "2099-01-01T00:00:00+09:00"
            research = module._build_research("シンデレラ", "シンデレラ", now, profile)
            (run_dir / "research.md").write_text(module._md_yaml("Research", research), encoding="utf-8")
            story = module._build_story("シンデレラ", run_dir, now, profile)
            (run_dir / "story.md").write_text(module._md_yaml("Story", story), encoding="utf-8")
            script, manifest, selectors = module._build_script_and_manifest("シンデレラ", run_dir, now, profile)

        self.assertEqual(research["metadata"]["target_duration_seconds"], 1200)
        self.assertEqual(research["metadata"]["duration_plan"]["minimum_scene_count"], 30)
        self.assertEqual(story["story_metadata"]["target_duration_seconds"], 1200)
        self.assertEqual(len(story["script"]["scenes"]), 30)
        self.assertEqual(script["script_metadata"]["target_duration"], 1200)
        self.assertEqual(script["script_metadata"]["minimum_narration_seconds"], 840)
        self.assertGreaterEqual(len(script["scenes"]), 30)
        self.assertEqual(
            len(selectors),
            sum(len(scene["cuts"]) for scene in manifest["scenes"]),
        )
        self.assertEqual(manifest["video_metadata"]["target_duration_seconds"], 1200)
        self.assertEqual(manifest["video_metadata"]["minimum_duration_seconds"], 960)
        self.assertEqual(
            sum(scene["target_duration_seconds"] for scene in manifest["scenes"]),
            1200,
        )
        self.assertEqual(
            sum(scene["estimated_duration_seconds"] for scene in manifest["scenes"]),
            1200,
        )
        self.assertEqual(manifest["video_metadata"]["duration_seconds"], 1200)
        self.assertEqual(
            manifest["video_metadata"]["minimum_cut_count"],
            sum(
                scene["scene_cut_coverage_plan"]["min_cut_count"]["selected"]
                for scene in manifest["scenes"]
            ),
        )
        self.assertTrue(
            all(
                not str(cut["coverage_obligation_id"]).startswith("duration_")
                for scene in script["scenes"]
                for cut in (item["cut_contract"] for item in scene["cuts"])
            )
        )

    def test_scene_cut_coverage_uses_authored_obligations_and_event_beats_not_duration_fillers(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="duration-cut-floor"),
            target_duration_seconds=300,
        )
        idx = 1
        title = profile["scene_titles"][idx - 1]
        location = module._location_spec_for_scene(profile, idx)
        scene_intent = module._scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location,
            profile=profile,
            include_artifact=False,
        )
        scene_event = module._scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=profile,
            include_artifact=False,
        )

        result = module._scene_cut_coverage_plan(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            scene_event=scene_event,
            location_name=str(location["name"]),
            profile=profile,
            include_artifact=False,
        )
        cuts = result["cuts"]
        coverage = result["coverage_plan"]
        distinct_obligation_count = len(
            {str(cut["obligation_id"]) for cut in cuts}
        )
        event_beat_count = len(scene_event["event_sequence"])

        self.assertEqual(
            coverage["min_cut_count"]["by_distinct_semantic_obligations"],
            distinct_obligation_count,
        )
        self.assertEqual(
            coverage["min_cut_count"]["by_event_beats"], event_beat_count
        )
        self.assertEqual(
            coverage["min_cut_count"]["selected"],
            max(distinct_obligation_count, event_beat_count),
        )
        self.assertEqual(coverage["min_cut_count"].get("by_importance"), 0)
        self.assertEqual(coverage["min_cut_count"].get("by_duration"), 0)
        self.assertEqual(coverage["selected_cut_count"], len(cuts))
        self.assertEqual(len(coverage["cut_assignments"]), len(cuts))
        self.assertEqual(len({cut["obligation_id"] for cut in cuts}), len(cuts))
        declared_obligation_selectors = {
            str(obligation["obligation_id"]): set(obligation["assigned_cut_ids"])
            for obligation in coverage["scene_obligations"]
        }
        assigned_obligation_selectors = {
            str(assignment["obligation_id"]): {str(assignment["cut_selector"])}
            for assignment in coverage["cut_assignments"]
        }
        self.assertEqual(
            declared_obligation_selectors,
            assigned_obligation_selectors,
        )
        self.assertTrue(all(cut.get("primary_event_beat_id") for cut in cuts))
        self.assertFalse(
            any(str(cut["obligation_id"]).startswith("duration_") for cut in cuts)
        )

    def test_core_cut_obligations_use_concrete_single_states_and_distinct_motion(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="concrete-cut-projection"),
            target_duration_seconds=300,
        )
        idx = 1
        title = profile["scene_titles"][idx - 1]
        location = module._location_spec_for_scene(profile, idx)
        scene_intent = module._scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location,
            profile=profile,
            include_artifact=False,
        )
        scene_event = module._scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=profile,
            include_artifact=False,
        )
        result = module._scene_cut_coverage_plan(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            scene_event=scene_event,
            location_name=str(location["name"]),
            profile=profile,
            include_artifact=False,
        )
        by_id = {cut["obligation_id"]: cut for cut in result["cuts"]}
        pressure = by_id["scene_pressure"]
        shift = by_id["visible_value_shift"]
        provider_fields = " / ".join(
            str(cut.get(key) or "")
            for cut in (pressure, shift)
            for key in (
                "target_beat",
                "visual_proof",
                "first_frame_brief",
                "foreground",
                "motion_brief",
                "motion_end_state",
            )
        )

        for unresolved in (
            "または",
            "変化点",
            "変化の証拠",
            "物証",
            "空間の締めつけ",
            "人物の制約",
            "押し戻すに",
            ", ",
        ):
            self.assertNotIn(unresolved, provider_fields)
        self.assertNotEqual(pressure["motion_brief"], shift["motion_brief"])
        self.assertNotEqual(pressure["motion_end_state"], shift["motion_end_state"])
        self.assertIn("手", pressure["motion_brief"])
        self.assertIn("継母", pressure["motion_brief"])
        self.assertIn(profile["protagonist_name"], pressure["motion_end_state"])
        turn = next(beat for beat in scene_event["event_sequence"] if beat["beat_function"] == "turn")
        self.assertNotIn(f"{profile['protagonist_name']}が「", turn["visible_action"])
        self.assertNotIn("直後", turn["visible_action"])
        self.assertIn("手を止め", turn["visible_action"])

    def test_first_two_cuts_bind_motion_channels_to_visible_people_and_physical_end_states(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="cut-motion-binding"),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        first, second = manifest["scenes"][0]["cuts"][:2]
        first_motion = first["cut_contract"]["motion_contract"]
        second_motion = second["cut_contract"]["motion_contract"]
        second_start_state = second["cut_contract"]["first_frame_contract"]["visible_start_state"]
        first_gate = first["image_generation"]["first_frame_visual_plan"]["character_state_gate"]
        second_gate = second["image_generation"]["first_frame_visual_plan"]["character_state_gate"]
        first_prompt = first["image_generation"]["api_prompt_payload"]["prompt"]
        second_prompt = second["image_generation"]["api_prompt_payload"]["prompt"]
        self.assertEqual(first_motion["camera_motion"], "locked_off")
        self.assertEqual(second_motion["camera_motion"], "slow_push")
        self.assertNotEqual(first_motion["subject_motion"], second_motion["subject_motion"])
        self.assertIn("継母", first_gate["gaze"])
        self.assertIn("出入口", second_gate["gaze"])
        self.assertIn("出入口へ向き", second_gate["foot_position"])
        self.assertNotIn("出入口から外れ", second_gate["foot_position"])
        self.assertIn("出入口", first_motion["emotional_change"])
        self.assertIn("継母", second_motion["emotional_change"])
        self.assertNotIn("を受け、", second_start_state["character_state"])
        self.assertNotIn("同じ画面に、光が明確に見える", first_prompt)
        self.assertNotIn("同じ画面に、灰の台所、光が明確に見える", second_prompt)
        for motion in (first_motion, second_motion):
            provider_motion = " / ".join(
                str(motion.get(key) or "")
                for key in (
                    "subject_motion",
                    "environment_motion",
                    "emotional_change",
                    "end_state",
                )
            )
            for unresolved in (
                "押し戻すに",
                "変化点",
                "変化の証拠",
                "sceneの前提",
                "次cut",
                "内面の変化",
                "または",
            ):
                self.assertNotIn(unresolved, provider_motion)
            self.assertIn("シンデレラ", motion["subject_motion"])
            self.assertIn("シンデレラ", motion["end_state"])

    def test_multi_location_scene_assigns_every_location_as_primary_without_cross_location_text(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="multi-location-primary"),
            target_duration_seconds=300,
        )
        idx = 8
        title = profile["scene_titles"][idx - 1]
        location = module._location_spec_for_scene(profile, idx)
        scene_intent = module._scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location,
            profile=profile,
            include_artifact=True,
        )
        scene_event = module._scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            location_name=str(location["name"]),
            location_id=str(location["asset_id"]),
            profile=profile,
            include_artifact=True,
        )
        result = module._scene_cut_coverage_plan(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            scene_event=scene_event,
            location_name=str(location["name"]),
            profile=profile,
            include_artifact=True,
        )
        beat_by_id = {beat["beat_id"]: beat for beat in scene_event["event_sequence"]}
        expected_locations = set(profile["scene_location_sequences"][idx - 1])
        primary_locations = {
            beat_by_id[cut["primary_event_beat_id"]]["concrete_event"]["where"]
            for cut in result["cuts"]
        }

        self.assertEqual(primary_locations, expected_locations)
        for cut in result["cuts"]:
            primary_location = beat_by_id[cut["primary_event_beat_id"]]["concrete_event"]["where"]
            provider_text = " / ".join(
                str(cut.get(key) or "")
                for key in ("target_beat", "visual_proof", "first_frame_brief", "foreground", "background")
            )
            self.assertIn(primary_location, provider_text)
            for other_location in expected_locations - {primary_location}:
                self.assertNotIn(other_location, provider_text)

    def test_multi_location_manifest_binds_location_and_focal_character_per_cut(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="multi-location-manifest"),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        scene = manifest["scenes"][7]
        expected_locations = set(scene["location_sequence"])
        actual_locations: set[str] = set()
        expected_primary_subject = {
            "王宮の命令の間": "王子",
            "町の家々": "王宮の使者",
            "靴合わせの部屋": "シンデレラ",
        }
        previous_cut = None
        for cut in scene["cuts"]:
            contract = cut["cut_contract"]
            concrete_event = contract["source_event_contract"]["source_concrete_events"][0]
            location_name = concrete_event["where"]
            actual_locations.add(location_name)
            prompt = cut["image_generation"]["api_prompt_payload"]["prompt"]
            self.assertIn(location_name, prompt)
            for other_location in expected_locations - {location_name}:
                self.assertNotIn(other_location, prompt)
            primary_subject = contract["cinematic_contract"]["subject_priority"]["primary"]
            expected_subject = (
                "王宮の使者"
                if cut["selector"] == "scene80_cut06"
                else expected_primary_subject[location_name]
            )
            self.assertEqual(primary_subject, expected_subject)
            character_bindings = cut["image_generation"]["first_frame_visual_plan"][
                "reference_binding"
            ]["character_references"]
            self.assertTrue(character_bindings)
            self.assertIn(primary_subject, character_bindings[0]["target_character_name"])

            if cut["selector"] == "scene80_cut03":
                plan = cut["image_generation"]["first_frame_visual_plan"]
                self.assertIn(
                    "椅子の横の床", plan["character_state_gate"]["foot_position"]
                )
                self.assertNotIn(
                    "隙間なく合",
                    plan["object_visibility_gate"]["objects"][0]["object_state"],
                )
            if cut["selector"] == "scene80_cut04":
                plan = cut["image_generation"]["first_frame_visual_plan"]
                self.assertIn(
                    "数センチ手前", plan["character_state_gate"]["foot_position"]
                )
                self.assertNotIn(
                    "隙間なく合",
                    plan["object_visibility_gate"]["objects"][0]["object_state"],
                )

            first_visible_moment = contract["first_frame_contract"][
                "event_fact_visible_in_still"
            ]
            subject_motion = contract["motion_contract"]["subject_motion"]
            if location_name == "町の家々":
                self.assertNotIn("家の人物", subject_motion)
            if location_name == "靴合わせの部屋":
                self.assertNotIn("視線は靴からシンデレラの顔へ上がる", first_visible_moment)
                self.assertNotIn(subject_motion, first_visible_moment)
            if (
                previous_cut is not None
                and previous_cut["location_name"] == location_name
            ):
                self.assertIn(previous_cut["end_state"], first_visible_moment)
            previous_cut = {
                "location_name": location_name,
                "source_event_beat_id": contract["source_event_contract"][
                    "primary_event_beat_id"
                ],
                "end_state": contract["motion_contract"]["end_state"],
            }

        self.assertEqual(actual_locations, expected_locations)

    def test_duration_expanded_cuts_keep_motion_and_end_state_distinct_within_each_scene(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile("シンデレラ", "シンデレラ", variant_seed="distinct-cut-motion"),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        for scene in manifest["scenes"]:
            motions = [
                cut["cut_contract"]["motion_contract"]["subject_motion"]
                for cut in scene["cuts"]
            ]
            end_states = [
                cut["cut_contract"]["motion_contract"]["end_state"]
                for cut in scene["cuts"]
            ]
            self.assertEqual(len(motions), len(set(motions)), scene["scene_id"])
            self.assertEqual(len(end_states), len(set(end_states)), scene["scene_id"])
            for cut in scene["cuts"]:
                plan = cut["image_generation"]["first_frame_visual_plan"]
                primary_name = plan["subject_binding"]["primary_subject"]["name"]
                character_references = plan["reference_binding"][
                    "character_references"
                ]
                if primary_name == "シンデレラ" and character_references:
                    self.assertEqual(
                        character_references[0]["role_in_frame"],
                        "primary_subject",
                        cut["selector"],
                    )
                if cut["selector"] == "scene70_cut03":
                    self.assertIn(
                        "踵から半分外れ",
                        plan["character_state_gate"]["foot_position"],
                    )
                    self.assertNotIn(
                        "隙間なく合",
                        plan["object_visibility_gate"]["objects"][0][
                            "object_state"
                        ],
                    )

    def test_cinderella_turn_actions_and_slipper_handoff_are_physically_continuous(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="physical-turn-continuity",
            ),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        cuts = {
            cut["selector"]: cut
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        }
        character_bible_by_id = {
            entry["character_id"]: entry
            for entry in manifest["assets"]["character_bible"]
        }
        post_midnight_bible = character_bible_by_id[
            profile["protagonist_post_midnight_asset_id"]
        ]
        self.assertEqual(
            post_midnight_bible["appearance_continuity"],
            {
                "costume_state": "魔法が解けた後の質素な衣装",
                "forbidden_costume_states": ["舞踏会ドレス"],
            },
        )
        self.assertEqual(
            post_midnight_bible["review_aliases"][0],
            profile["protagonist_name"],
        )
        self.assertTrue(
            any(
                "魔法が解けた後の質素な衣装" in fixed_prompt
                for fixed_prompt in post_midnight_bible["fixed_prompts"]
            )
        )
        artifact_reference = f"assets/objects/{profile['artifact_asset_id']}.png"
        for scene_prefix in ("scene10", "scene20"):
            for selector, cut in cuts.items():
                if not selector.startswith(f"{scene_prefix}_cut"):
                    continue
                source_forbidden = cut["cut_contract"]["source_event_contract"][
                    "forbidden_reveal_info_ids"
                ]
                self.assertIn("ガラスの靴", source_forbidden, selector)
                image_generation = cut["image_generation"]
                visual_plan = image_generation["first_frame_visual_plan"]
                self.assertIn(
                    "ガラスの靴",
                    visual_plan["temporal_boundary"]["not_yet_happened_in_still"],
                    selector,
                )
                api_payload = image_generation["api_prompt_payload"]
                self.assertIn(
                    "まだ描かないものは、ガラスの靴",
                    api_payload["prompt"],
                    selector,
                )
                self.assertNotIn(
                    profile["artifact_asset_id"], image_generation["object_ids"], selector
                )
                self.assertNotIn(
                    profile["artifact_asset_id"],
                    api_payload["drawable_prompt_ir"]["dependencies"]["object_ids"],
                    selector,
                )
                self.assertNotIn(artifact_reference, image_generation["references"], selector)
                self.assertFalse(
                    any(
                        item.get("object_id") == profile["artifact_asset_id"]
                        for item in visual_plan["object_visibility_gate"]["objects"]
                    ),
                    selector,
                )

        for selector, cut in cuts.items():
            if not selector.startswith("scene70_cut"):
                continue
            visual_plan = cut["image_generation"]["first_frame_visual_plan"]
            self.assertNotIn(
                "時間制限の結果",
                visual_plan["temporal_boundary"]["not_yet_happened_in_still"],
                selector,
            )
            self.assertNotIn(
                "時間制限の結果",
                cut["image_generation"]["api_prompt_payload"]["prompt"],
                selector,
            )
        scene40 = next(
            scene for scene in manifest["scenes"] if scene["scene_id"] == 40
        )
        scene40_payoff = next(
            beat
            for beat in scene40["scene_event"]["event_sequence"]
            if beat["beat_function"] == "payoff"
        )
        self.assertIn(
            "protagonist", scene40_payoff["concrete_event"]["who"]
        )
        for selector in ("scene40_cut05", "scene40_cut06"):
            self.assertIn(
                "protagonist",
                cuts[selector]["cut_contract"]["viewer_contract"]["required_roles"],
                selector,
            )
        expected_turn_motion = {
            "scene10_cut03": "家事道具を入れた籠を灰の床へ",
            "scene20_cut03": "裏口の掛け金を外し",
            "scene30_cut03": "ドレス、ガラスの靴、馬車の形へ変える",
            "scene40_cut03": "身体を一度だけ客室内へ乗り入れる",
            "scene50_cut03": "大階段を上り切り",
            "scene60_cut03": "最初の一歩だけ踊り始める",
            "scene70_cut03": "ガラスの靴が踵から外れて一段上に残る",
            "scene80_cut03": "椅子へ腰を下ろし",
        }
        for selector, expected in expected_turn_motion.items():
            self.assertIn(
                expected,
                cuts[selector]["cut_contract"]["motion_contract"][
                    "subject_motion"
                ],
                selector,
            )

        scene30_cut3 = cuts["scene30_cut03"]
        scene30_cut4 = cuts["scene30_cut04"]
        self.assertNotIn(
            profile["artifact_asset_id"],
            scene30_cut3["image_generation"]["object_ids"],
        )
        self.assertNotIn(
            profile["carriage_asset_id"],
            scene30_cut3["image_generation"]["object_ids"],
        )
        self.assertIn(
            profile["protagonist_asset_id"],
            scene30_cut3["image_generation"]["character_ids"],
        )
        self.assertNotIn(
            profile["protagonist_transformed_asset_id"],
            scene30_cut3["image_generation"]["character_ids"],
        )
        first_frame_prompt = scene30_cut3["image_generation"][
            "api_prompt_payload"
        ]["prompt"]
        positive_prompt, separator, forbidden_prompt = first_frame_prompt.partition(
            "[禁止]"
        )
        self.assertTrue(separator)
        self.assertNotIn("ガラスの靴", positive_prompt)
        self.assertNotIn("馬車", positive_prompt)
        self.assertNotIn("舞踏会ドレス姿を維持", positive_prompt)
        self.assertIn("ガラスの靴", forbidden_prompt)
        self.assertIn("馬車", forbidden_prompt)
        self.assertIn(
            "ドレス、ガラスの靴、馬車の形へ変える",
            scene30_cut3["cut_contract"]["motion_contract"]["subject_motion"],
        )
        self.assertEqual(
            scene30_cut3["cut_contract"]["motion_contract"][
                "allowed_new_reveal_elements"
            ],
            ["変身後のシンデレラ", "ガラスの靴", "完成したかぼちゃの馬車"],
        )
        self.assertEqual(
            scene30_cut3["video_generation"]["last_frame"],
            "assets/scenes/scene30_cut04.png",
        )
        self.assertIn(
            scene30_cut3["cut_contract"]["motion_contract"]["end_state"],
            scene30_cut4["cut_contract"]["first_frame_contract"][
                "event_fact_visible_in_still"
            ],
        )
        scene30_plan = scene30_cut4["image_generation"][
            "first_frame_visual_plan"
        ]
        self.assertTrue(
            any(
                "魔法の助力者" in binding["target_character_name"]
                for binding in scene30_plan["reference_binding"][
                    "character_references"
                ]
            )
        )
        object_states = {
            item["object_name"]: item["object_state"]
            for item in scene30_plan["object_visibility_gate"]["objects"]
        }
        self.assertNotIn("足に隙間なく合", object_states["馬車"])
        self.assertIn("足に隙間なく合", object_states["ガラスの靴"])

        for transition_from, transition_to, from_location, to_location in (
            (
                "scene20_cut03",
                "scene20_cut04",
                "屋敷の裏口",
                "月明かりの庭",
            ),
            (
                "scene40_cut04",
                "scene40_cut05",
                "馬車が待つ門前",
                "宮殿へ続く石畳",
            ),
            (
                "scene50_cut03",
                "scene50_cut04",
                "宮殿の階段",
                "舞踏会の大広間",
            ),
        ):
            from_cut = cuts[transition_from]
            to_cut = cuts[transition_to]
            self.assertEqual(
                from_cut["cut_contract"]["first_frame_contract"][
                    "visible_start_state"
                ]["spatial_state"],
                from_location,
                transition_from,
            )
            self.assertEqual(
                to_cut["cut_contract"]["first_frame_contract"][
                    "visible_start_state"
                ]["spatial_state"],
                to_location,
                transition_to,
            )
            self.assertNotEqual(
                from_cut["image_generation"]["location_ids"],
                to_cut["image_generation"]["location_ids"],
            )
            self.assertEqual(
                from_cut["video_generation"]["last_frame"],
                f"assets/scenes/{transition_to}.png",
                transition_from,
            )

        scene70_cut4 = cuts["scene70_cut04"]
        scene70_cut5 = cuts["scene70_cut05"]
        self.assertEqual(
            scene70_cut4["cut_contract"]["motion_contract"][
                "allowed_new_reveal_elements"
            ],
            ["質素な普段着へ戻ったシンデレラ"],
        )
        self.assertEqual(
            scene70_cut4["video_generation"]["last_frame"],
            "assets/scenes/scene70_cut05.png",
        )
        self.assertIn(
            "時間制限の結果",
            scene70_cut4["cut_contract"]["source_event_contract"][
                "allowed_reveal_info_ids"
            ],
        )
        self.assertNotIn(
            "時間制限の結果",
            scene70_cut4["cut_contract"]["source_event_contract"][
                "forbidden_reveal_info_ids"
            ],
        )
        scene70_cut5_start = scene70_cut5["cut_contract"]["first_frame_contract"][
            "event_fact_visible_in_still"
        ]
        self.assertIn("ガラスの靴の三段下", scene70_cut5_start)
        self.assertNotIn("靴の一段下", scene70_cut5_start)

        scene70_cut7 = cuts["scene70_cut07"]
        scene70_cut8 = cuts["scene70_cut08"]
        self.assertIn(
            "片手を一度だけ伸ばす",
            scene70_cut7["cut_contract"]["motion_contract"]["subject_motion"],
        )
        self.assertIn(
            "指先がガラスの靴の踵に触れ",
            scene70_cut8["cut_contract"]["first_frame_contract"][
                "event_fact_visible_in_still"
            ],
        )
        self.assertIn(
            "片方のガラスの靴を胸元で支え",
            scene70_cut8["cut_contract"]["motion_contract"]["end_state"],
        )
        self.assertIn(
            "gaze",
            scene70_cut8["image_generation"]["first_frame_visual_plan"][
                "character_state_gate"
            ],
        )
        scene70_cut5_character_states = scene70_cut5["image_generation"][
            "first_frame_visual_plan"
        ]["character_state_gate"]["character_states"]
        self.assertEqual(
            scene70_cut5_character_states,
            [
                {
                    "character_id": profile["protagonist_post_midnight_asset_id"],
                    "character_name": profile["protagonist_name"],
                    "appearance_continuity": {
                        "costume_state": "魔法が解けた後の質素な衣装",
                        "forbidden_costume_states": ["舞踏会ドレス"],
                    },
                }
            ],
        )
        expected_source_hand_state = {
            "scene70_cut06": "片手が身体の横で止まっている",
            "scene70_cut07": "片手が身体の横で止まっている",
            "scene70_cut08": "ガラスの靴の踵に触れている",
        }
        for selector in ("scene70_cut06", "scene70_cut07", "scene70_cut08"):
            source_state = cuts[selector]["cut_contract"]["source_event_contract"][
                "source_concrete_events"
            ][0]["visible_character_state"]
            self.assertIn(
                expected_source_hand_state[selector],
                source_state["hands"],
                selector,
            )
            character_names = [
                binding["target_character_name"]
                for binding in cuts[selector]["image_generation"][
                    "first_frame_visual_plan"
                ]["reference_binding"]["character_references"]
            ]
            self.assertFalse(
                any("シンデレラ" in name for name in character_names),
                selector,
            )
        self.assertIn(
            "片方のガラスの靴",
            cuts["scene80_cut01"]["cut_contract"]["first_frame_contract"][
                "event_fact_visible_in_still"
            ],
        )
        self.assertIn(
            "不適合だった家の扉を背にし",
            cuts["scene80_cut02"]["cut_contract"]["motion_contract"][
                "subject_motion"
            ],
        )
        scene80_cut5_gate = cuts["scene80_cut05"]["image_generation"][
            "first_frame_visual_plan"
        ]["character_state_gate"]
        self.assertIn("両肩をまだわずかに上げ", scene80_cut5_gate["pose"])
        scene80_cut6_gate = cuts["scene80_cut06"]["image_generation"][
            "first_frame_visual_plan"
        ]["character_state_gate"]
        self.assertIn("gaze", scene80_cut6_gate)
        self.assertIn("王宮の使者", scene80_cut6_gate["pose"])
        scene80_cut6_objects = cuts["scene80_cut06"]["image_generation"][
            "first_frame_visual_plan"
        ]["object_visibility_gate"]["objects"]
        self.assertTrue(
            any(
                "隙間なく合" in str(item.get("object_state") or "")
                for item in scene80_cut6_objects
            )
        )

    def test_cinderella_video_cut_projection_uses_authored_local_causal_actions(self) -> None:
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="video-local-causal-actions",
            ),
            target_duration_seconds=300,
        )
        with tempfile.TemporaryDirectory() as tmp:
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        cuts = {
            cut["selector"]: cut
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        }
        self.assertFalse(
            any(
                str(cut["cut_contract"]["cut_function"]).startswith("duration_")
                or str(
                    cut["cut_contract"]["viewer_contract"][
                        "anti_redundancy_key"
                    ]
                ).startswith("scene_event.event_sequence")
                and "duration_" in str(
                    cut["cut_contract"]["viewer_contract"][
                        "anti_redundancy_key"
                    ]
                )
                for cut in cuts.values()
            )
        )

        motion = lambda selector: cuts[selector]["cut_contract"]["motion_contract"][
            "subject_motion"
        ]
        end = lambda selector: cuts[selector]["cut_contract"]["motion_contract"][
            "end_state"
        ]
        start = lambda selector: cuts[selector]["cut_contract"][
            "first_frame_contract"
        ]["event_fact_visible_in_still"]

        self.assertIn("裏口を庭側から閉じる", motion("scene20_cut04"))
        self.assertIn("月明かりの庭", end("scene20_cut04"))
        self.assertIn(end("scene20_cut04"), start("scene20_cut05"))
        self.assertIn("庭の奥へ二歩", motion("scene20_cut05"))

        self.assertIn("月光の外から一歩", motion("scene30_cut01"))
        self.assertIn("文字盤", motion("scene30_cut02"))
        self.assertNotIn("ドレス", motion("scene30_cut02"))
        self.assertIn("ドレス、ガラスの靴、馬車の形へ変える", motion("scene30_cut03"))
        self.assertEqual(
            cuts["scene30_cut03"]["video_generation"]["last_frame"],
            "assets/scenes/scene30_cut04.png",
        )
        self.assertIn(end("scene30_cut03"), start("scene30_cut04"))
        self.assertIn("ガラスの靴を履いた足元", motion("scene30_cut04"))
        self.assertIn("馬車扉へ一歩", motion("scene30_cut05"))
        self.assertIn("扉枠へ片手", motion("scene30_cut06"))

        self.assertIn("かぼちゃの馬車", motion("scene40_cut05"))
        self.assertNotIn("シンデレラがシンデレラの手元", motion("scene40_cut05"))
        self.assertIn("宮殿の灯り", motion("scene40_cut06"))
        self.assertNotIn("シンデレラの手元との距離", end("scene40_cut06"))

        self.assertIn("王子が", motion("scene50_cut04"))
        self.assertIn("シンデレラへ顔", motion("scene50_cut04"))
        self.assertIn("大広間の内側へ二歩", motion("scene50_cut05"))
        self.assertNotIn("宮殿の階段の中景", end("scene50_cut05"))

        self.assertIn("半回転だけ", motion("scene60_cut04"))
        self.assertIn("壁時計", motion("scene60_cut05"))

        self.assertIn("画面外へ出る", motion("scene70_cut05"))
        self.assertIn("階段下方の出入口は空いている", end("scene70_cut05"))
        self.assertIn("三段だけ下り", motion("scene70_cut06"))
        self.assertIn("片手を一度だけ伸ばす", motion("scene70_cut07"))
        self.assertIn("胸元まで一度だけ持ち上げる", motion("scene70_cut08"))

        self.assertIn("椅子へ腰を下ろ", motion("scene80_cut03"))
        self.assertNotIn("踵まで入れる", motion("scene80_cut03"))
        self.assertIn("ガラスの靴へ踵まで入れる", motion("scene80_cut04"))
        self.assertIn("足首を一度だけ", motion("scene80_cut05"))
        self.assertIn("王宮の使者が", motion("scene80_cut06"))
        self.assertIn("一度うなずく", motion("scene80_cut06"))

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
            review_metadata={},
        )

        self.assertEqual(payload["policy_version"], "image_api_prompt_v2")
        self.assertNotIn("[登場人物]", payload["prompt"])
        self.assertNotIn("[小道具 / 舞台装置]", payload["prompt"])
        self.assertNotIn("opaque_gate_id", payload["prompt"])

    def test_scaffold_plan_uses_cut_specific_drawable_evidence(self) -> None:
        module = load_frontend_run_module()

        evidence = module._cut_specific_drawable_evidence_for_scaffold(
            {
                "must_show": ["灰の床", "scene10_cut01", "場のルール"],
                "visual_evidence": ["舞踏会の知らせ", "灰の床"],
            }
        )

        self.assertEqual(
            evidence,
            [
                {
                    "source_field": "viewer_contract.must_show",
                    "must_be_drawn_as": "灰の床",
                },
                {
                    "source_field": "viewer_contract.must_show",
                    "must_be_drawn_as": "人物同士の距離と出入口への位置関係",
                },
                {
                    "source_field": "viewer_contract.visual_evidence",
                    "must_be_drawn_as": "舞踏会の知らせ",
                },
            ],
        )

    def test_scaffold_multi_object_proof_uses_readable_depth_instead_of_extreme_closeup(self) -> None:
        module = load_frontend_run_module()

        shot = module._scaffold_shot_design(
            cut_number=3,
            cut_blueprint={"cut_function": "proof"},
            cut_uses_artifact=True,
            object_ids=["carriage", "glass_slipper"],
        )

        self.assertEqual(shot["shot_role"], "object_proof")
        self.assertEqual(shot["shot_scale"], "medium_wide")

    def test_scaffold_artifact_payoff_keeps_character_and_witnesses_in_frame(self) -> None:
        module = load_frontend_run_module()

        shot = module._scaffold_shot_design(
            cut_number=3,
            cut_blueprint={"cut_function": "payoff"},
            cut_uses_artifact=True,
            object_ids=["glass_slipper"],
        )

        self.assertEqual(shot["shot_role"], "object_proof")
        self.assertEqual(shot["shot_scale"], "medium_wide")

    def test_transformation_handoff_keeps_named_carriage_reference(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            profile = module._story_profile("シンデレラ", "シンデレラ")
        drawable_evidence: list[dict[str, str]] = []

        object_ids = module._supporting_object_ids_for_cut(
            profile,
            drawable_evidence,
            cut_plan={
                "obligation_id": "causal_handoff",
                "primary_event_beat_id": "transformation_turn",
            },
            scene_event={
                "event_sequence": [
                    {
                        "beat_id": "transformation_turn",
                        "what_happens": "かぼちゃの馬車とガラスの靴を整える",
                        "concrete_event": {
                            "what_happens": "シンデレラが馬車で出発できる状態になる",
                        },
                    }
                ]
            },
        )

        self.assertIn("pumpkin_carriage", object_ids)
        self.assertIn("馬車", [item["must_be_drawn_as"] for item in drawable_evidence])

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

    def test_same_topic_runs_use_story_specific_cinderella_without_fixed_scaffold_ids(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_repeat_a_", dir=output_root) as tmp_a, tempfile.TemporaryDirectory(prefix="frontend_run_repeat_b_", dir=output_root) as tmp_b:
            run_a = Path(tmp_a)
            run_b = Path(tmp_b)

            module.materialize_run("シンデレラ", "シンデレラ", run_a, "p650")
            module.materialize_run("シンデレラ", "シンデレラ", run_b, "p650")

            request_a = (run_a / "image_generation_requests.md").read_text(encoding="utf-8")
            request_b = (run_b / "image_generation_requests.md").read_text(encoding="utf-8")
            manifest_a = (run_a / "video_manifest.md").read_text(encoding="utf-8")
            manifest_b = (run_b / "video_manifest.md").read_text(encoding="utf-8")
            asset_request_a = (run_a / "asset_generation_requests.md").read_text(encoding="utf-8")
            combined = "\n".join(
                [
                    request_a,
                    request_b,
                    manifest_a,
                    manifest_b,
                    (run_a / "research.md").read_text(encoding="utf-8"),
                    (run_a / "story.md").read_text(encoding="utf-8"),
                    asset_request_a,
                    (run_b / "research.md").read_text(encoding="utf-8"),
                    (run_b / "story.md").read_text(encoding="utf-8"),
                    (run_b / "asset_generation_requests.md").read_text(encoding="utf-8"),
                ]
            )

        self.assertNotIn("cinderella_fullbody", combined)
        self.assertNotIn("cinderella_transformed_fullbody", combined)
        self.assertNotIn("cinderella_post_midnight_fullbody", combined)
        self.assertNotIn("glass_slipper", combined)
        self.assertNotIn("pumpkin_carriage", combined)
        self.assertNotIn("prince_dance_partner", combined)
        self.assertIn("ガラスの靴", combined)
        self.assertIn("靴合わせ", combined)
        self.assertIn("舞踏会", combined)
        self.assertIn("王子", combined)
        self.assertIn("灰と家事に縛られたシンデレラは、家の中で尊厳を失わずにいられるか", combined)
        self.assertRegex(
            asset_request_a,
            r"(?s)asset_id: `[a-z0-9_]+_transformed_fullbody`.*?references:\n\s+- `人物参照画像1`: `assets/characters/[a-z0-9_]+_protagonist_fullbody\.png`",
        )
        self.assertRegex(
            asset_request_a,
            r"(?s)asset_id: `[a-z0-9_]+_post_midnight_fullbody`.*?references:\n\s+- `人物参照画像1`: `assets/characters/[a-z0-9_]+_protagonist_fullbody\.png`",
        )
        scene30_cut1 = request_a.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
        scene30_cut3 = request_a.split("## scene30_cut3", 1)[1].split("## scene30_cut4", 1)[0]
        scene30_cut4 = request_a.split("## scene30_cut4", 1)[1].split("## scene30_cut5", 1)[0]
        scene70_cut1 = request_a.split("## scene70_cut1", 1)[1].split("## scene70_cut2", 1)[0]
        scene70_cut3 = request_a.split("## scene70_cut3", 1)[1].split("## scene70_cut4", 1)[0]
        scene70_cut5 = request_a.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
        self.assertNotRegex(scene30_cut1, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertNotRegex(scene30_cut3, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertRegex(scene30_cut4, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertNotRegex(scene70_cut1, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertRegex(scene70_cut3, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertRegex(scene70_cut5, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertNotEqual(request_a, request_b)
        self.assertNotEqual(manifest_a, manifest_b)
        self.assertIn("run_variant:", manifest_a)
        self.assertIn("run_variant:", manifest_b)

    def test_cut_design_failure_writes_context_log_and_state(self) -> None:
        module = load_frontend_run_module()
        original_coverage_plan = module._scene_cut_coverage_plan
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_failure_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            def fail_coverage_plan(*args, **kwargs):
                raise RuntimeError("synthetic cut design failure")

            module._scene_cut_coverage_plan = fail_coverage_plan
            try:
                with self.assertRaisesRegex(RuntimeError, "synthetic cut design failure"):
                    module.materialize_run("シンデレラ", "シンデレラ", run_dir, "p650")
            finally:
                module._scene_cut_coverage_plan = original_coverage_plan

            latest_context_path = run_dir / "logs" / "scene_design" / "latest_generation_context.json"
            failure_path = run_dir / "logs" / "scene_design" / "cut_contract_failure.json"
            self.assertTrue(latest_context_path.exists())
            self.assertTrue(failure_path.exists())
            latest_context = json.loads(latest_context_path.read_text(encoding="utf-8"))
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(latest_context["schema_version"], "cut_design_generation_context_v1")
            self.assertEqual(latest_context["phase"], "scene_cut_coverage_planning")
            self.assertEqual(latest_context["scene_context"]["scene_id"], 10)
            self.assertEqual(failure["schema_version"], "cut_design_failure_v1")
            self.assertEqual(failure["phase"], "build_script_and_manifest")
            self.assertEqual(failure["error"]["type"], "RuntimeError")
            self.assertIn("synthetic cut design failure", failure["error"]["message"])
            self.assertIn("scene_event_input", failure["partial_artifacts"])
            self.assertIn("scene_generation_prompts", failure["partial_artifacts"])
            self.assertEqual(failure["partial_artifacts"]["scene_generation_prompts"]["path"], "logs/scene_design/scene_generation_prompts.json")

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stage"], "cut_design_failed")
            self.assertEqual(state["runtime.cut_design.status"], "failed")
            self.assertEqual(state["runtime.cut_design.failure_log"], "logs/scene_design/cut_contract_failure.json")
            self.assertEqual(state["slot.p420.status"], "failed")

    def test_materialize_only_reaches_frontend_p680_text_contract(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
                module.materialize_run("シンデレラ", "シンデレラ", run_dir, "p650")
                module.write_run_index(run_dir)
            for name in (
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "video_manifest.md",
                "image_prompt_story_review.md",
                "logs/review/image_prompt.review_collection.md",
                "logs/review/image_prompt.review_scope.json",
                "logs/review/image_prompt.judgment_prompt.md",
                "logs/review/image_prompt.judgment.md",
                "logs/review/semantic/scene_set.collection.md",
                "logs/review/semantic/scene_detail.collection.md",
                "logs/review/semantic/cut_blueprint.collection.md",
                "logs/review/semantic/asset_plan.collection.md",
                "logs/review/semantic/image_prompt.collection.md",
                "logs/scene_design/scene_event_input.json",
                "logs/scene_design/scene_event_output.json",
                "logs/scene_design/scene_generation_prompts.json",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
                "image_generation_requests.md",
                "image_generation_request_snapshot.json",
                "video_generation_requests.md",
                "p000_index.md",
            ):
                self.assertGreater((run_dir / name).stat().st_size, 80, name)
            self.assertIn(
                "除外対象はありません。",
                (run_dir / "generation_exclusion_report.md").read_text(encoding="utf-8"),
            )

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertNotIn("slot.p660.status", state)
            self.assertNotIn("slot.p680.status", state)
            self.assertEqual(state["review.image.status"], "pending")
            self.assertEqual(state["gate.image_review"], "required")
            self.assertEqual(state["review.image_prompt.judgment.status"], "pending")
            self.assertEqual(state["slot.p650.status"], "pending")
            self.assertEqual(state["review.image_prompt.request_freeze.status"], "draft")
            for stage in ("scene_implementation_hard", "scene_implementation_judgment"):
                self.assertEqual(state[f"eval.{stage}.loop.status"], "pending")
                self.assertFalse((run_dir / f"logs/eval/{stage}/round_01/critic_1.md").exists())
            asset_scope = json.loads(
                (run_dir / "logs/review/semantic/asset_plan.scope.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertGreaterEqual(asset_scope["entry_count"], 20)
            self.assertEqual(
                state["review.semantic.asset_plan.entry_count"],
                str(asset_scope["entry_count"]),
            )
            for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
                self.assertEqual(state[f"review.semantic.{stage}.status"], "pending")
                self.assertIn(f"review.semantic.{stage}.entry_count", state)
            self.assertNotIn("review.semantic.asset_output.status", state)
            self.assertNotIn("review.semantic.scene_image.status", state)
            scope = json.loads((run_dir / "logs/review/image_prompt.review_scope.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(scope["entry_count"], 40)
            self.assertEqual(state["review.image_prompt.judgment.entry_count"], str(scope["entry_count"]))
            generic_scope = json.loads((run_dir / "logs/review/semantic/image_prompt.scope.json").read_text(encoding="utf-8"))
            self.assertEqual(generic_scope["entry_count"], scope["entry_count"])
            scene_event_input = json.loads((run_dir / "logs/scene_design/scene_event_input.json").read_text(encoding="utf-8"))
            scene_event_output = json.loads((run_dir / "logs/scene_design/scene_event_output.json").read_text(encoding="utf-8"))
            scene_generation_prompts = json.loads((run_dir / "logs/scene_design/scene_generation_prompts.json").read_text(encoding="utf-8"))
            self.assertEqual(scene_event_input["schema_version"], "scene_event_log_v1")
            self.assertEqual(scene_event_output["schema_version"], "scene_event_log_v1")
            self.assertEqual(scene_generation_prompts["schema_version"], "scene_generation_prompt_log_v1")
            self.assertEqual(scene_event_input["scene_count"], scene_event_output["scene_count"])
            self.assertEqual(scene_generation_prompts["scene_count"], scene_event_output["scene_count"])
            self.assertEqual(scene_generation_prompts["scenes"][0]["scene_generation"]["schema_version"], "scene_generation_v1")
            self.assertEqual(scene_event_output["scenes"][0]["scene_event"]["schema_version"], "scene_event_v1")
            first_scene_event = scene_event_output["scenes"][0]["scene_event"]
            first_scene_generation = scene_event_output["scenes"][0]["scene_generation"]
            self.assertIn("scene_authoring_context", first_scene_generation)
            self.assertIn("scene_prompt_payload", first_scene_generation)
            self.assertIn("scene_debug_prompt_source", first_scene_generation)
            self.assertIn("scene_generation_contract", first_scene_generation)
            self.assertIn("prompt", first_scene_generation["scene_prompt_payload"])
            self.assertNotIn("first_frame_brief", first_scene_generation["scene_prompt_payload"]["prompt"])
            self.assertNotIn("motion_brief", first_scene_generation["scene_prompt_payload"]["prompt"])
            self.assertNotIn("api_prompt_payload", first_scene_generation["scene_prompt_payload"]["prompt"])
            first_event_beat = first_scene_event["event_sequence"][0]
            self.assertIn("story_specificity", first_scene_event)
            self.assertIn("abstract_function", first_event_beat)
            self.assertIn("concrete_event", first_event_beat)
            self.assertIn("story_grounding", first_event_beat)
            self.assertIn("non_replaceable_elements", first_event_beat["story_grounding"])
            self.assertIn("concrete_story_elements", first_event_beat["story_grounding"])
            self.assertIn("asset_story_function_usage", first_event_beat["story_grounding"])
            self.assertIn("specificity_budget", first_event_beat)
            self.assertIn("source_event_contract", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertIn("source_concrete_events", scene_event_output["scenes"][0]["cut_contracts"][0]["source_event_contract"])
            self.assertIn("source_story_grounding", scene_event_output["scenes"][0]["cut_contracts"][0]["source_event_contract"])
            self.assertIn("source_non_replaceable_elements", scene_event_output["scenes"][0]["cut_contracts"][0]["source_event_contract"])
            self.assertIn("event_context_for_cut", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertIn("cut_context_packet", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertEqual(scene_event_output["scenes"][0]["cut_contracts"][0]["cut_context_packet"]["schema_version"], "cut_context_packet_v1")
            self.assertFalse(scene_event_output["scenes"][0]["cut_contracts"][0]["cut_context_packet"]["editable"])

            asset_request_text = (run_dir / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertGreaterEqual(len(re.findall(r"^##\s+", asset_request_text, flags=re.MULTILINE)), 10)
            self.assertIn("location_reference", asset_request_text)
            self.assertIn("人物なし、空の部屋、場所だけ", asset_request_text)
            self.assertIn("主要人物、全身ポートレート", asset_request_text)
            self.assertIn("pumpkin_carriage", asset_request_text)
            self.assertIn("prince_dance_partner", asset_request_text)
            self.assertIn("cinderella_stepmother_fullbody", asset_request_text)
            self.assertIn("cinderella_stepsisters_fullbody", asset_request_text)
            self.assertIn("cinderella_helper_fullbody", asset_request_text)
            self.assertIn("cinderella_royal_envoy_fullbody", asset_request_text)
            self.assertIn("cinderella_transformed_fullbody", asset_request_text)
            self.assertIn("cinderella_post_midnight_fullbody", asset_request_text)
            self.assertIn("参照画像が渡される場合は、その人物の顔・髪・体格・年齢感を同一人物として維持", asset_request_text)
            transformed_asset_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `cinderella_transformed_fullbody`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            post_midnight_asset_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `cinderella_post_midnight_fullbody`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("assets/characters/cinderella_fullbody.png", transformed_asset_section)
            self.assertIn("assets/characters/cinderella_fullbody.png", post_midnight_asset_section)
            self.assertIn("舞踏会ドレスではない質素な衣装だけに戻す", post_midnight_asset_section)
            gate_road_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*馬車が待つ門前(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn(
                "特定の朝昼夕夜に固定しない中性的な参照照明",
                gate_road_section,
            )
            self.assertNotIn("深夜のみ", gate_road_section)
            self.assertNotIn("昼光なし", gate_road_section)
            midnight_stair_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*真夜中の大階段(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("ガラスの靴なし", midnight_stair_section)
            self.assertIn("物語固有の小道具", midnight_stair_section)
            self.assertIn("ロゴ、マーク、署名、ウォーターマーク", midnight_stair_section)

            scene_request_text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("[cut契約からの可視要件]", scene_request_text)
            self.assertIn("- prompt_policy_version: `image_api_prompt_v2`", scene_request_text)
            self.assertIn("```debug_prompt_source", scene_request_text)
            self.assertIn("```api_prompt", scene_request_text)
            self.assertNotIn("```text\n[参照画像の使い方]", scene_request_text)
            self.assertIn("[全体 / 不変条件]", scene_request_text)
            self.assertIn("[シーン]", scene_request_text)
            self.assertNotIn("[shot / 画角]", scene_request_text)
            self.assertNotIn("shot_role:", scene_request_text)
            self.assertNotIn("location_zone:", scene_request_text)
            self.assertNotIn("this_cut_delta:", scene_request_text)
            self.assertNotIn("[動画開始に向いた静止状態]", scene_request_text)
            self.assertNotIn("観客理解の増分:", scene_request_text)
            self.assertNotIn("因果の証明:", scene_request_text)
            self.assertNotIn("必要な役割:", scene_request_text)
            self.assertNotIn("motion_brief:", scene_request_text)
            first_scene = scene_request_text.split("## scene10_cut2", 1)[0]
            first_api_prompt = re.search(r"```api_prompt\n(?P<body>.*?)\n```", first_scene, re.DOTALL).group("body")
            self.assertIn("assets/characters/cinderella_fullbody.png", first_scene)
            self.assertIn("assets/locations/", first_scene)
            self.assertNotIn("glass_slipper", first_api_prompt)
            self.assertNotIn("event_time_position:", first_api_prompt)
            self.assertNotIn("not_yet_happened_in_still:", first_api_prompt)
            self.assertNotIn("first_frame_visual_plan", first_api_prompt)
            self.assertNotIn("source_event_contract", first_api_prompt)
            self.assertNotIn("event_context_for_cut", first_api_prompt)
            self.assertNotIn("motion_brief", first_api_prompt)
            self.assertNotIn("[小道具 / 舞台装置]", first_api_prompt)
            self.assertIn("[禁止]", first_api_prompt)
            self.assertIn("ガラスの靴", first_scene)
            self.assertNotRegex(first_api_prompt, r"^.*ガラスの靴.*$", re.MULTILINE)
            manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("scene_cut_coverage_plan:", manifest_text)
            self.assertIn("scene_shot_mix_plan:", manifest_text)
            self.assertIn("api_prompt_payload:", manifest_text)
            self.assertNotIn("prompt_deprecated:", manifest_text)
            manifest_data = yaml.safe_load(
                manifest_text.split("```yaml\n", 1)[1].rsplit("```", 1)[0]
            )
            manifest_cuts = [
                cut
                for scene in manifest_data["scenes"]
                for cut in scene["cuts"]
            ]
            semantic_cut_floor = sum(
                int(scene["scene_cut_coverage_plan"]["min_cut_count"]["selected"])
                for scene in manifest_data["scenes"]
            )
            self.assertGreaterEqual(len(manifest_cuts), semantic_cut_floor)
            for scene in manifest_data["scenes"]:
                coverage = scene["scene_cut_coverage_plan"]
                minimums = coverage["min_cut_count"]
                self.assertEqual(minimums["by_importance"], 0)
                self.assertEqual(minimums["by_duration"], 0)
                self.assertEqual(
                    minimums["selected"],
                    max(
                        minimums["by_distinct_semantic_obligations"],
                        minimums["by_event_beats"],
                    ),
                )
                self.assertGreaterEqual(
                    len(scene["cuts"]),
                    minimums["selected"],
                )
                self.assertEqual(
                    coverage["selected_cut_count"],
                    len(scene["cuts"]),
                )
            self.assertTrue(
                all("prompt" not in cut["image_generation"] for cut in manifest_cuts)
            )
            self.assertTrue(
                all(
                    cut["image_generation"]["api_prompt_payload"]["policy_version"]
                    == "image_api_prompt_v2"
                    for cut in manifest_cuts
                )
            )
            snapshot = json.loads(
                (run_dir / "image_generation_request_snapshot.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                snapshot["schema_version"],
                "toc.image_generation_request_snapshot.v1",
            )
            self.assertEqual(len(snapshot["items"]), len(manifest_cuts))
            self.assertIn("first_frame_visual_plan:", manifest_text)
            self.assertIn("schema_version: first_frame_visual_plan_v1", manifest_text)
            self.assertIn("editable: false", manifest_text)
            self.assertIn("scene_obligations:", manifest_text)
            self.assertIn("story_event_obligations:", manifest_text)
            self.assertIn("audience_knowledge_delta:", manifest_text)
            self.assertIn("causal_proof:", manifest_text)
            self.assertIn("role_coverage:", manifest_text)
            self.assertIn("visual_evidence:", manifest_text)
            self.assertIn("source_event_contract:", manifest_text)
            self.assertIn("event_context_for_cut:", manifest_text)
            self.assertIn("cut_context_packet:", manifest_text)
            self.assertIn("schema_version: cut_context_packet_v1", manifest_text)
            self.assertIn("editable: false", manifest_text)
            self.assertIn("scene_state_progression_plan:", manifest_text)
            self.assertIn("cut_state_progression:", manifest_text)
            self.assertNotIn("assigned_story_event_ids:", manifest_text)
            self.assertIn("static_first_frame_rule:", manifest_text)
            self.assertIn("must_be_static_evidence_not_motion: true", manifest_text)
            self.assertIn("coverage_obligation_id:", manifest_text)
            self.assertIn("scene10_cut04", scene_request_text)
            self.assertIn("scene10_cut05", scene_request_text)
            self.assertIn("scene30_cut06", scene_request_text)
            self.assertIn("scene70_cut08", scene_request_text)
            self.assertIn("symbolic_proof", manifest_text)
            self.assertIn("reaction_after_change", manifest_text)
            self.assertNotIn("reveal_protection", manifest_text)
            self.assertIn("time_or_deadline_pressure", manifest_text)
            scene70_text = scene_request_text.split("## scene70_cut1", 1)[1].split("## scene80_cut1", 1)[0]
            self.assertIn("ガラスの靴", scene70_text)
            self.assertIn("脱げ", scene70_text)
            self.assertIn("階段に残ったガラスの靴", scene70_text)
            self.assertIn("片方のガラスの靴を胸元で支え", scene70_text)
            self.assertIn("逃走", scene70_text)
            post_loss_scene70 = scene_request_text.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
            self.assertIn("cinderella_post_midnight_fullbody", post_loss_scene70)
            pre_loss_scene70 = scene_request_text.split("## scene70_cut4", 1)[1].split("## scene70_cut5", 1)[0]
            self.assertIn("cinderella_transformed_fullbody", pre_loss_scene70)
            self.assertIn("シンデレラの衣装は、舞踏会ドレス姿を維持し、質素な普段着には変えない。", pre_loss_scene70)
            self.assertIn("シンデレラの衣装は、魔法が解けた後の質素な衣装を維持し、舞踏会ドレスには変えない。", post_loss_scene70)
            scene70_manifest = manifest_text.split("scene_id: 70", 1)[1].split("scene_id: 80", 1)[0]
            self.assertIn("source_event_contract:", scene70_manifest)
            self.assertIn("event_context_for_cut:", scene70_manifest)
            self.assertIn("cut_contract.source_event_contract", scene70_manifest)

            transformation_scene = scene_request_text.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
            self.assertIn("reference_count: `3`", transformation_scene)
            self.assertIn("cinderella_helper_fullbody", transformation_scene)
            self.assertNotIn("glass_slipper", transformation_scene)
            transformation_threshold = scene_request_text.split("## scene30_cut2", 1)[1].split("## scene30_cut3", 1)[0]
            self.assertIn("reference_count: `3`", transformation_threshold)
            self.assertIn("cinderella_helper_fullbody", transformation_threshold)
            self.assertNotIn("glass_slipper", transformation_threshold)
            self.assertIn("魔法の助力者", transformation_threshold)
            transformation_reveal = scene_request_text.split("## scene30_cut3", 1)[1].split("## scene30_cut4", 1)[0]
            transformation_reveal_api_prompt = re.search(r"```api_prompt\n(?P<body>.*?)\n```", transformation_reveal, re.DOTALL).group("body")
            self.assertIn("reference_count: `4`", transformation_reveal)
            self.assertNotIn("cinderella_helper_fullbody", transformation_reveal)
            self.assertIn("pumpkin_carriage", transformation_reveal)
            self.assertIn("glass_slipper", transformation_reveal)
            self.assertNotIn("object_visibility:", transformation_reveal_api_prompt)
            self.assertIn("[小道具 / 舞台装置]", transformation_reveal_api_prompt)
            self.assertIn("ガラスの靴は", transformation_reveal_api_prompt)
            self.assertIn("cinderella_transformed_fullbody", transformation_reveal)
            deterministic_review = (run_dir / "image_prompt_story_review.md").read_text(encoding="utf-8")
            self.assertIn("- status: `PASS`", deterministic_review)
            self.assertIn("- hard_findings: `0`", deterministic_review)
            self.assertNotIn("足音が明確に見える", scene_request_text)

            departure_scene = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene50_cut1", 1)[0]
            self.assertIn("pumpkin_carriage", departure_scene)
            self.assertIn("馬車", departure_scene)
            self.assertNotIn("ガラスの靴はこのsceneでは見せない", departure_scene)
            scene40_manifest = manifest_text.split("scene_id: 40", 1)[1].split("scene_id: 50", 1)[0]
            self.assertIn("progression_mode: sequential_state_progression", scene40_manifest)
            self.assertIn("first_frame_temporal_role: progressed_state_after_previous_cut", scene40_manifest)
            self.assertNotIn("not_yet_happened_in_still:\n                  - scene04_event_turn", scene40_manifest)
            self.assertIn("story_meaning: 馬車", scene40_manifest)
            self.assertNotIn("story_meaning: ガラスの靴", scene40_manifest)
            departure_pressure = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene40_cut2", 1)[0]
            departure_proof = scene_request_text.split("## scene40_cut3", 1)[1].split("## scene40_cut4", 1)[0]
            departure_late = scene_request_text.split("## scene40_cut4", 1)[1].split("## scene40_cut5", 1)[0]
            self.assertNotIn("glass_slipper", departure_pressure)
            self.assertIn("pumpkin_carriage", departure_proof)
            self.assertIn("馬車", departure_late)
            self.assertIn("progressed_state", departure_late)
            self.assertNotIn("still_must_not_show: 行為完了後、後続reveal、次場面の結果。", departure_late)

            palace_stair_scene = scene_request_text.split("## scene50_cut3", 1)[1].split("## scene50_cut4", 1)[0]
            self.assertIn("宮殿の階段", palace_stair_scene)
            self.assertIn("location_05", palace_stair_scene)
            self.assertNotIn("location_01", palace_stair_scene)
            palace_pressure = scene_request_text.split("## scene50_cut1", 1)[1].split("## scene50_cut2", 1)[0]
            self.assertNotIn("glass_slipper", palace_pressure)

            ballroom_scene = scene_request_text.split("## scene60_cut3", 1)[1].split("## scene60_cut4", 1)[0]
            self.assertIn("舞踏会の大広間", ballroom_scene)
            self.assertIn("location_06", ballroom_scene)
            self.assertIn("prince_dance_partner", ballroom_scene)
            self.assertNotIn("cinderella_stepmother_fullbody", ballroom_scene)
            self.assertNotIn("cinderella_helper_fullbody", ballroom_scene)
            self.assertNotIn("location_02", ballroom_scene)
            ballroom_pressure = scene_request_text.split("## scene60_cut1", 1)[1].split("## scene60_cut2", 1)[0]
            self.assertNotIn("glass_slipper", ballroom_pressure)

            final_scene_manifest = re.split(r"\n-\s+scene_id:\s+'?80'?", manifest_text, maxsplit=1)[1]
            self.assertIn("物語を閉じる", final_scene_manifest)
            self.assertIn("終結", final_scene_manifest)
            self.assertIn("靴合わせが行われる部屋", final_scene_manifest)
            self.assertIn("ガラスの靴", final_scene_manifest)
            self.assertIn("主人公の価値を証明", final_scene_manifest)
            self.assertIn("出口ではなく主人公とガラスの靴へ収束する", final_scene_manifest)
            self.assertIn("fitted_on_foot", final_scene_manifest)
            self.assertIn("carries_to_next_scene: []", final_scene_manifest)
            self.assertNotIn("次の場所へ進む証拠が生まれる", final_scene_manifest)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_manifest)

            final_scene_requests = scene_request_text.split("## scene80_cut1", 1)[1]
            self.assertIn("cinderella_post_midnight_fullbody", final_scene_requests)
            self.assertNotIn("cinderella_transformed_fullbody", final_scene_requests)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_requests)
            self.assertIn("シンデレラの衣装は、魔法が解けた後の質素な衣装を維持し、舞踏会ドレスには変えない。", final_scene_requests)
            final_scene_api_prompts = "\n".join(re.findall(r"```api_prompt\n(.*?)\n```", final_scene_requests, re.DOTALL))
            self.assertNotIn("object_visibility:", final_scene_api_prompts)
            self.assertIn("[小道具 / 舞台装置]", final_scene_api_prompts)
            self.assertIn("ガラスの靴は", final_scene_api_prompts)
            self.assertIn("シンデレラの足に隙間なく合っている", final_scene_requests)
            self.assertIn("靴合わせが行われる部屋", final_scene_requests)
            self.assertNotIn("月光、ガラス、階段", final_scene_requests)

            video_request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("video_prompt_ir:", video_request_text)
            self.assertIn("projection_review_contract:", video_request_text)
            self.assertIn(
                "cut.cut_contract.motion_contract.motion_brief",
                video_request_text,
            )
            self.assertIn("```video_prompt", video_request_text)

            prompt_text = (run_dir / "logs/eval/asset/round_01/prompts/critic_1.prompt.md").read_text(encoding="utf-8")
            self.assertIn("You are critic_1 in the ToC Asset Eval/Improve Loop", prompt_text)
            aggregate_text = (run_dir / "logs/eval/asset/round_01/aggregated_review.md").read_text(encoding="utf-8")
            self.assertIn("## Blocking Findings", aggregate_text)
            self.assertIn("Root Cause Review", aggregate_text)

            forbidden = ("TODO", "TBD", "REPLACE_ME", "placeholder")
            for name in (
                "research.md",
                "story.md",
                "script.md",
                "asset_generation_requests.md",
                "image_generation_requests.md",
                "video_generation_requests.md",
            ):
                text = (run_dir / name).read_text(encoding="utf-8")
                self.assertFalse(any(marker in text for marker in forbidden), name)

    def test_materialize_only_uses_topic_profile_instead_of_cinderella_scaffold(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_generic_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            module.materialize_run(
                "桃太郎",
                "桃から生まれた主人公が仲間と鬼のいる島へ向かう民話。",
                run_dir,
                "p650",
            )

            request_text = "\n".join(
                [
                    (run_dir / "asset_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "image_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "video_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "video_manifest.md").read_text(encoding="utf-8"),
                ]
            )
            self.assertIn("cut_contract:", request_text)
            self.assertIn("source_event_contract:", request_text)
            self.assertIn("event_context_for_cut:", request_text)
            self.assertIn("first_frame_contract:", request_text)
            self.assertIn("motion_contract:", request_text)
            self.assertIn("story_event_obligations:", request_text)
            self.assertIn("audience_knowledge_delta:", request_text)
            self.assertIn("causal_proof:", request_text)
            self.assertIn("scene_character_state_timeline:", request_text)
            self.assertIn("scene_film_coverage_plan:", request_text)
            self.assertIn("scene_state_progression_plan:", request_text)
            self.assertIn("cut_character_emotion_transition:", request_text)
            self.assertIn("cut_film_grammar_contract:", request_text)
            self.assertIn("cut_state_progression:", request_text)
            self.assertIn("[登場人物]", request_text)
            self.assertIn("表情は、", request_text)
            self.assertIn("視線は、", request_text)
            self.assertIn("姿勢は、", request_text)
            self.assertIn("足元は、", request_text)
            self.assertNotIn("観客理解の増分:", request_text)
            self.assertNotIn("因果の証明:", request_text)
            self.assertNotIn("静止画ルール:", request_text)
            self.assertIn("桃太郎", request_text)
            self.assertNotIn("cinderella_fullbody", request_text)
            self.assertNotIn("glass_slipper", request_text)
            self.assertNotIn("シンデレラ", request_text)

            manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text.split("```yaml", 1)[1].split("```", 1)[0])
            object_scenes = []
            for scene in manifest["scenes"]:
                has_object_dependency = any(
                    ((cut.get("cut_contract") or {}).get("asset_dependency") or {}).get(
                        "object_ids_required"
                    )
                    for cut in scene.get("cuts") or []
                )
                if not has_object_dependency:
                    continue
                object_scenes.append(scene)
                required_insert = (
                    ((scene.get("scene_film_coverage_plan") or {}).get("shot_mix") or {})
                    .get("required_coverage", {})
                    .get("insert")
                )
                self.assertTrue(required_insert, f"scene {scene.get('scene_id')} object coverage")
            self.assertTrue(object_scenes)

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            # `materialize_run()` only authors the run. Grounding is the next
            # orchestration step (`prepare_grounding()`), exercised by the CLI
            # and backend create-route tests rather than this profile test.
            self.assertNotIn("stage.scene_implementation.grounding.status", state)

    def test_cinderella_asset_specs_preserve_ensemble_and_neutral_reuse_contracts(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            profile = module._story_profile("シンデレラ", "シンデレラ", variant_seed="asset-contract")

        stepsisters = next(
            item
            for item in module._supporting_character_asset_specs(profile)
            if item.get("source_character_id") == "stepsisters"
        )
        self.assertEqual(stepsisters["subject_contract"]["identity_scope"], "ensemble")
        self.assertEqual(stepsisters["subject_contract"]["subject_count"], 2)
        self.assertEqual(len(stepsisters["subject_contract"]["member_ids"]), 2)
        self.assertTrue(stepsisters["appearance_contract"]["materials"])

        forbidden_dayparts = ("朝日", "昼光", "夕日", "夜の", "真夜中", "深夜", "月光", "月明かり")
        for location in module._location_asset_specs(profile):
            self.assertEqual(location["reuse_contract"], {"mode": "neutral_anchor"})
            subject = str((location.get("visual_spec") or {}).get("subject") or "")
            self.assertFalse(any(marker in subject for marker in forbidden_dayparts), subject)

    def test_asset_plan_projection_keeps_prompt_review_contracts(self) -> None:
        module = load_frontend_run_module()
        profile = {
            "protagonist_name": "主人公",
            "artifact_name": "鍵",
            "artifact_role": "証拠",
            "artifact_visual": "古い鍵",
        }
        manifest = {
            "assets": {
                "character_bible": [
                    {
                        "character_id": "siblings",
                        "reference_images": ["assets/characters/siblings.png"],
                        "fixed_prompts": ["姉妹"],
                        "cinematic": {"role": "対立者", "visual_subject": "二人の姉妹"},
                        "subject_contract": {"identity_scope": "ensemble", "subject_count": 2, "member_ids": ["older", "younger"]},
                        "appearance_contract": {"social_position": "裕福な家の姉妹", "materials": "絹"},
                        "reuse_contract": {"mode": "neutral_anchor"},
                    }
                ],
                "object_bible": [],
                "location_bible": [],
            },
            "scenes": [{"cuts": [{"selector": "scene01_cut01", "image_generation": {"character_ids": ["siblings"]}}]}],
        }

        _inventory, plan = module._build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
        entry = plan["assets"][0]
        self.assertEqual(entry["subject_contract"]["subject_count"], 2)
        self.assertEqual(entry["appearance_contract"]["materials"], "絹")
        self.assertEqual(entry["reuse_contract"], {"mode": "neutral_anchor"})

    def test_cinderella_authored_and_exact_reviewed_story_materialize_complete_location_segments(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="reviewed-location-segments"
        )
        story = module._build_story(
            "シンデレラ",
            Path("output/reviewed-location-segments"),
            "2099-01-01T00:00:00+09:00",
            profile,
        )

        module._validate_reviewed_story_time_of_day_contract(story)
        for scene in story["script"]["scenes"]:
            route = scene["location"]["sequence"]
            if len(route) <= 1:
                continue
            self.assertEqual(
                [segment["location"] for segment in scene["location"]["segments"]],
                route,
            )

        scenes = {int(scene["scene_id"]): scene for scene in story["script"]["scenes"]}
        scene2_segments = {
            segment["location"]: segment
            for segment in scenes[2]["location"]["segments"]
        }
        self.assertIn("参加を願い出る", scene2_segments["閉ざされた扉の前"]["responsibility"])
        self.assertIn("拒み", scene2_segments["閉ざされた扉の前"]["responsibility"])
        self.assertIn("正面扉を閉じ", scene2_segments["閉ざされた扉の前"]["motion_brief"])
        self.assertIn("掛け金", scene2_segments["屋敷の裏口"]["motion_brief"])

        scene4_segments = {
            segment["location"]: segment
            for segment in scenes[4]["location"]["segments"]
        }
        gate = scene4_segments["馬車が待つ門前"]
        self.assertIn("開いた馬車扉の前", gate["visible_action"])
        self.assertFalse(any("乗せた" in item for item in gate["required_visual_evidence"]))
        stone_road = scene4_segments["宮殿へ続く石畳"]
        self.assertTrue(any("馬車" in item for item in stone_road["required_visual_evidence"]))
        self.assertIn("馬車", stone_road["motion_brief"])
        self.assertIn("石畳", stone_road["motion_end_state"])

        scene5_segments = {
            segment["location"]: segment
            for segment in scenes[5]["location"]["segments"]
        }
        ballroom = scene5_segments["舞踏会の大広間"]
        self.assertEqual(set(ballroom["required_roles"]), {"protagonist", "prince"})
        self.assertIn("シンデレラ", ballroom["visible_action"])
        self.assertTrue(any("シンデレラ" in item for item in ballroom["required_visual_evidence"]))
        self.assertIn("大階段を上り切り", scene5_segments["宮殿の階段"]["motion_brief"])

        scene8_segments = {
            segment["location"]: segment
            for segment in scenes[8]["location"]["segments"]
        }
        town_search = scene8_segments["町の家々"]
        self.assertIn("一軒ずつ巡り", town_search["responsibility"])
        self.assertIn("次の家", town_search["motion_brief"])
        self.assertEqual(town_search["required_roles"], ["royal_envoy"])

        incomplete_blueprint = module._scene_blueprint(
            profile=profile,
            idx=2,
            title=profile["scene_titles"][1],
            location_name=profile["scene_locations"][1],
            include_artifact=False,
        )
        incomplete_blueprint["beat_overrides"].pop("payoff", None)
        with self.assertRaisesRegex(RuntimeError, "no authored beat or obligation"):
            module._authored_location_segments_for_story(
                profile=profile,
                scene_index=2,
                blueprint=incomplete_blueprint,
            )

        repaired_story = deepcopy(story)
        for scene in repaired_story["script"]["scenes"]:
            if len(scene["location"]["sequence"]) > 1:
                scene["location"]["segments"] = []
        module._materialize_exact_reviewed_story_location_segments(
            repaired_story,
            profile=profile,
        )
        module._validate_reviewed_story_time_of_day_contract(repaired_story)

        arbitrary_story = deepcopy(story)
        arbitrary_story["script"]["scenes"][1]["location"]["sequence"] = [
            "閉ざされた扉の前",
            "未承認の別世界",
        ]
        arbitrary_story["script"]["scenes"][1]["location"]["segments"] = []
        module._materialize_exact_reviewed_story_location_segments(
            arbitrary_story,
            profile=profile,
        )
        with self.assertRaisesRegex(
            RuntimeError, "location.segments must cover every sequence location"
        ):
            module._validate_reviewed_story_time_of_day_contract(arbitrary_story)

    def test_exact_obligation_reveal_and_boundary_policies_do_not_leak_from_shared_roots(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(module, seed="exact-obligation-scope")
        exact_only_fields = {
            "allowed_new_reveal_elements",
            "allowed_reveal_info_ids",
            "use_next_cut_first_frame_as_last_frame",
            "first_frame_character_asset_overrides",
            "first_frame_excluded_object_ids",
        }
        for scene_index, title in enumerate(profile["scene_titles"], start=1):
            blueprint = module._scene_blueprint(
                profile=profile,
                idx=scene_index,
                title=title,
                location_name=profile["scene_locations"][scene_index - 1],
                include_artifact=module._scene_uses_artifact(profile, scene_index),
            )
            for function, function_override in blueprint[
                "beat_overrides"
            ].items():
                self.assertTrue(
                    exact_only_fields.isdisjoint(function_override),
                    f"scene {scene_index} {function}",
                )
                wildcard = (
                    function_override.get("obligation_overrides") or {}
                ).get("*") or {}
                self.assertTrue(
                    exact_only_fields.isdisjoint(wildcard),
                    f"scene {scene_index} {function} wildcard",
                )
        title, location, intent, event, include_artifact = self._scene_design_bundle(
            module, profile, 7
        )
        payoff = next(
            beat
            for beat in event["event_sequence"]
            if beat["beat_function"] == "payoff"
        )
        payoff["allowed_new_reveal_elements"] = ["ROOT_LEAK"]
        payoff["allowed_reveal_info_ids"] = ["ROOT_INFO_LEAK"]
        payoff["use_next_cut_first_frame_as_last_frame"] = True
        payoff["first_frame_character_asset_overrides"] = {
            "シンデレラ": profile["protagonist_asset_id"]
        }
        payoff["first_frame_excluded_object_ids"] = [
            profile["artifact_asset_id"]
        ]
        payoff["concrete_event"]["allowed_new_reveal_elements"] = [
            "CONCRETE_LEAK"
        ]
        payoff["concrete_event"]["allowed_reveal_info_ids"] = [
            "CONCRETE_INFO_LEAK"
        ]
        payoff["concrete_event"]["use_next_cut_first_frame_as_last_frame"] = True
        payoff["concrete_event"]["first_frame_character_asset_overrides"] = {
            "シンデレラ": profile["protagonist_asset_id"]
        }
        payoff["concrete_event"]["first_frame_excluded_object_ids"] = [
            profile["artifact_asset_id"]
        ]
        payoff["obligation_overrides"]["*"] = {
            "allowed_new_reveal_elements": ["WILDCARD_LEAK"],
            "allowed_reveal_info_ids": ["WILDCARD_INFO_LEAK"],
            "use_next_cut_first_frame_as_last_frame": True,
            "first_frame_character_asset_overrides": {
                "シンデレラ": profile["protagonist_asset_id"]
            },
            "first_frame_excluded_object_ids": [profile["artifact_asset_id"]],
        }

        result = module._scene_cut_coverage_plan(
            title=title,
            idx=7,
            scene_intent=intent,
            scene_event=event,
            location_name=str(location["name"]),
            profile=profile,
            include_artifact=include_artifact,
        )
        by_id = {cut["obligation_id"]: cut for cut in result["cuts"]}
        audience_context = by_id["audience_context"]
        self.assertEqual(
            audience_context["allowed_new_reveal_elements"],
            ["質素な普段着へ戻ったシンデレラ"],
        )
        self.assertEqual(
            audience_context["allowed_reveal_info_ids"], ["時間制限の結果"]
        )
        self.assertTrue(
            audience_context["use_next_cut_first_frame_as_last_frame"]
        )
        self.assertEqual(
            audience_context["first_frame_character_asset_overrides"],
            {
                "シンデレラ": profile["protagonist_transformed_asset_id"],
                "protagonist": profile["protagonist_transformed_asset_id"],
            },
        )
        self.assertEqual(audience_context["first_frame_excluded_object_ids"], [])
        for obligation_id, cut in by_id.items():
            if obligation_id == "audience_context":
                continue
            self.assertEqual(cut["allowed_new_reveal_elements"], [], obligation_id)
            self.assertEqual(cut["allowed_reveal_info_ids"], [], obligation_id)
            self.assertFalse(
                cut["use_next_cut_first_frame_as_last_frame"], obligation_id
            )
            self.assertEqual(
                cut["first_frame_character_asset_overrides"], {}, obligation_id
            )
            self.assertEqual(
                cut["first_frame_excluded_object_ids"], [], obligation_id
            )

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

    def test_cross_location_last_frame_carry_forward_uses_destination_and_actual_end_state(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(module, seed="cross-location-carry")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            research = module._build_research(
                "シンデレラ", "シンデレラ", "now", profile
            )
            (run_dir / "research.md").write_text(
                module._md_yaml("Research", research), encoding="utf-8"
            )
            story = module._build_story("シンデレラ", run_dir, "now", profile)
            (run_dir / "story.md").write_text(
                module._md_yaml("Story", story), encoding="utf-8"
            )
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ", run_dir, "now", profile
            )

        cuts = {
            cut["selector"]: cut
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        }
        for selector, departure, destination in (
            ("scene20_cut03", "閉ざされた扉の前", "月明かりの庭"),
            ("scene40_cut04", "馬車が待つ門前", "宮殿へ続く石畳"),
            ("scene50_cut03", "宮殿の階段", "舞踏会の大広間"),
        ):
            contract = cuts[selector]["cut_contract"]
            carry = contract["continuity_contract"][
                "carry_forward_to_next_cut"
            ]
            actual_end_state = contract["motion_contract"]["end_state"]
            next_selector = selector[:-2] + f"{int(selector[-2:]) + 1:02d}"
            next_contract = cuts[next_selector]["cut_contract"]
            self.assertNotIn(departure, carry, selector)
            self.assertIn(destination, carry, selector)
            self.assertIn(actual_end_state, carry, selector)
            self.assertIn(
                destination,
                contract["motion_contract"]["allowed_new_reveal_elements"],
                selector,
            )
            self.assertIn(
                actual_end_state,
                json.dumps(
                    next_contract["first_frame_contract"], ensure_ascii=False
                ),
                selector,
            )
            self.assertEqual(
                contract["continuity_contract"]["end_state"]["spatial_state"],
                destination,
                selector,
            )
            self.assertEqual(
                contract["continuity_contract"]["end_state"]["character_state"],
                actual_end_state,
                selector,
            )
            next_context = next_contract["event_context_for_cut"]
            primary_context_beat = next_context["primary_event_beat"]
            self.assertEqual(
                primary_context_beat["concrete_event"]["where"],
                destination,
                next_selector,
            )
            matching_source_context_beat = next(
                beat
                for beat in next_context["source_event_beats"]
                if beat["beat_id"] == primary_context_beat["beat_id"]
            )
            self.assertEqual(
                matching_source_context_beat["concrete_event"]["where"],
                destination,
                next_selector,
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

    def test_reviewed_story_manifest_enforces_adjacent_motion_and_first_frame_boundaries(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="reviewed-provider-boundaries"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            research = module._build_research(
                "シンデレラ", "シンデレラ", "now", profile
            )
            (run_dir / "research.md").write_text(
                module._md_yaml("Research", research), encoding="utf-8"
            )
            story = module._build_story("シンデレラ", run_dir, "now", profile)
            (run_dir / "story.md").write_text(
                module._md_yaml("Story", story), encoding="utf-8"
            )
            reviewed_profile = module._profile_from_reviewed_story(profile, story)
            _script, manifest, selectors = module._build_script_and_manifest(
                "シンデレラ", run_dir, "now", reviewed_profile
            )

        self.assertEqual(len(selectors), 45)
        for scene in manifest["scenes"]:
            route = list(scene["location_sequence"])
            for cut_index, cut in enumerate(scene["cuts"]):
                selector = cut["selector"]
                contract = cut["cut_contract"]
                plan = cut["image_generation"]["first_frame_visual_plan"]
                composition = plan["spatial_composition"]
                prompt_positive = str(
                    cut["image_generation"]["api_prompt_payload"].get("prompt")
                    or ""
                ).split("\n[禁止]\n", 1)[0]

                if cut_index:
                    previous = scene["cuts"][cut_index - 1]
                    previous_motion = previous["cut_contract"]["motion_contract"]
                    current_motion = contract["motion_contract"]
                    self.assertNotEqual(
                        (
                            previous_motion["motion_brief"],
                            previous_motion["subject_motion"],
                            previous_motion["end_state"],
                        ),
                        (
                            current_motion["motion_brief"],
                            current_motion["subject_motion"],
                            current_motion["end_state"],
                        ),
                        selector,
                    )
                    self.assertEqual(
                        contract["cut_state_progression"][
                            "state_after_previous_cut"
                        ],
                        previous_motion["end_state"],
                        selector,
                    )

                foreground_identities = module._character_identities_in_text(
                    reviewed_profile, composition["foreground"]
                )
                midground_identities = module._character_identities_in_text(
                    reviewed_profile, composition["midground"]
                )
                if not module._is_character_body_part_evidence(
                    composition["foreground"]
                ):
                    self.assertFalse(
                        foreground_identities.intersection(midground_identities),
                        selector,
                    )

                subject_names = [
                    plan["subject_binding"]["primary_subject"]["name"],
                    *[
                        item["name"]
                        for item in plan["subject_binding"]["secondary_subjects"]
                    ],
                ]
                seen_identities: set[str] = set()
                for subject_name in subject_names:
                    identities = module._character_identities_in_text(
                        reviewed_profile, subject_name
                    )
                    self.assertFalse(
                        identities.intersection(seen_identities), selector
                    )
                    seen_identities.update(identities)

                for other_location in route:
                    if other_location != composition["background"]:
                        self.assertNotIn(other_location, prompt_positive, selector)
                for future_reveal in contract["motion_contract"][
                    "allowed_new_reveal_elements"
                ]:
                    self.assertNotIn(future_reveal, prompt_positive, selector)

                event_context = contract["event_context_for_cut"]
                self.assertEqual(
                    event_context["primary_event_beat"]["concrete_event"]["where"],
                    composition["background"],
                    selector,
                )

    def test_first_frame_excluded_objects_are_removed_from_every_positive_still_source(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="first-frame-object-exclusions"
        )
        # Exercise the fail-closed path where the canonical location label
        # itself contains an object that is forbidden in this first frame.
        profile["scene_locations"][2] = "馬車が待つ門前"
        profile["scene_location_sequences"][2] = ["馬車が待つ門前"]
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            research = module._build_research(
                "シンデレラ", "シンデレラ", "now", profile
            )
            (run_dir / "research.md").write_text(
                module._md_yaml("Research", research), encoding="utf-8"
            )
            story = module._build_story("シンデレラ", run_dir, "now", profile)
            (run_dir / "story.md").write_text(
                module._md_yaml("Story", story), encoding="utf-8"
            )
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ", run_dir, "now", profile
            )

        cut = next(
            cut
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
            if cut["selector"] == "scene30_cut03"
        )
        excluded_ids = {
            str(profile["artifact_asset_id"]),
            str(profile["carriage_asset_id"]),
        }
        excluded_tokens = {
            *excluded_ids,
            *(module._object_name_for_asset(profile, value) for value in excluded_ids),
        }
        positive_still_sources = {
            "scene_contract": {
                key: cut["scene_contract"].get(key)
                for key in ("visual_beat", "first_frame_brief", "visual_evidence")
            },
            "first_frame_contract": cut["cut_contract"]["first_frame_contract"],
            "visual_translation": cut["image_generation"]["first_frame_visual_plan"][
                "visual_translation"
            ],
            "temporal_boundary_positive": {
                key: cut["image_generation"]["first_frame_visual_plan"][
                    "temporal_boundary"
                ].get(key)
                for key in (
                    "first_visible_moment",
                    "event_fact_visible_in_still",
                    "action_completion_state",
                )
            },
            "character_state_gate": cut["image_generation"][
                "first_frame_visual_plan"
            ]["character_state_gate"],
            "spatial_composition": cut["image_generation"][
                "first_frame_visual_plan"
            ]["spatial_composition"],
            "source_grounding": {
                key: cut["image_generation"]["first_frame_visual_plan"][
                    "source_grounding"
                ].get(key)
                for key in (
                    "what_happens",
                    "visible_action",
                    "visible_reaction",
                    "event_facts_to_preserve",
                )
            },
            "source_event_positive_review_trace": {
                key: cut["cut_contract"]["source_event_contract"].get(key)
                for key in (
                    "source_event_summary",
                    "source_visible_action",
                    "source_visible_reaction",
                    "source_required_visual_evidence",
                    "event_facts_to_preserve",
                )
            },
            "positive_start_and_composition_contracts": {
                "first_frame": cut["cut_contract"]["first_frame_contract"],
                "continuity_start": cut["cut_contract"]["continuity_contract"][
                    "start_state"
                ],
                "cinematic": cut["cut_contract"]["cinematic_contract"],
            },
            "provider_prompt_positive": str(
                cut["image_generation"]["api_prompt_payload"].get("prompt") or ""
            ).split("\n[禁止]\n", 1)[0],
        }
        positive_text = json.dumps(
            positive_still_sources, ensure_ascii=False, sort_keys=True
        )
        for token in excluded_tokens:
            self.assertNotIn(token, positive_text, token)

        motion_text = json.dumps(
            cut["cut_contract"]["motion_contract"],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertIn("ガラスの靴", motion_text)
        self.assertIn("馬車", motion_text)
        canonical_source_event_text = json.dumps(
            {
                key: cut["cut_contract"]["source_event_contract"].get(key)
                for key in (
                    "canonical_source_visible_action",
                    "canonical_source_required_visual_evidence",
                    "canonical_event_facts_to_preserve",
                )
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertIn("ガラスの靴", canonical_source_event_text)
        self.assertIn("馬車", canonical_source_event_text)
        from toc.stage_evaluator import _cut_event_ref_issue_map

        scene = next(
            scene
            for scene in manifest["scenes"]
            if cut in scene["cuts"]
        )
        self.assertNotIn(
            "source_event_preservation",
            _cut_event_ref_issue_map(scene),
        )

    def test_motion_reveals_are_explicit_first_frame_negatives_until_the_action(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="first-frame-motion-reveal-negatives"
        )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            research = module._build_research(
                "シンデレラ", "シンデレラ", "now", profile
            )
            (run_dir / "research.md").write_text(
                module._md_yaml("Research", research), encoding="utf-8"
            )
            story = module._build_story("シンデレラ", run_dir, "now", profile)
            (run_dir / "story.md").write_text(
                module._md_yaml("Story", story), encoding="utf-8"
            )
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ", run_dir, "now", profile
            )

        cuts = {
            cut["selector"]: cut
            for scene in manifest["scenes"]
            for cut in scene["cuts"]
        }
        for selector, expected_not_yet in (
            (
                "scene30_cut03",
                {
                    "変身後のシンデレラ",
                    "ガラスの靴",
                    "完成したかぼちゃの馬車",
                    "馬車",
                },
            ),
            ("scene70_cut04", {"質素な普段着へ戻ったシンデレラ"}),
        ):
            cut = cuts[selector]
            plan = cut["image_generation"]["first_frame_visual_plan"]
            not_yet = set(
                plan["temporal_boundary"]["not_yet_happened_in_still"]
            )
            self.assertLessEqual(expected_not_yet, not_yet, selector)
            prompt = cut["image_generation"]["api_prompt_payload"]["prompt"]
            self.assertIn("まだ描かないものは", prompt, selector)
            for outcome in expected_not_yet:
                self.assertIn(outcome, prompt, f"{selector}: {outcome}")
            motion_reveals = set(
                cut["cut_contract"]["motion_contract"][
                    "allowed_new_reveal_elements"
                ]
            )
            self.assertTrue(motion_reveals, selector)
            self.assertLessEqual(motion_reveals, not_yet, selector)

        self.assertNotIn(
            "変身後のシンデレラ",
            cuts["scene30_cut04"]["image_generation"][
                "first_frame_visual_plan"
            ]["temporal_boundary"]["not_yet_happened_in_still"],
        )
        self.assertNotIn(
            "質素な普段着へ戻ったシンデレラ",
            cuts["scene70_cut05"]["image_generation"][
                "first_frame_visual_plan"
            ]["temporal_boundary"]["not_yet_happened_in_still"],
        )

    def test_first_frame_excluded_object_ids_fail_closed_for_malformed_or_unknown_values(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="first-frame-object-validation"
        )
        with self.assertRaisesRegex(RuntimeError, "must be a list"):
            module._validate_first_frame_excluded_object_ids(
                profile, "glass_slipper", context="scene30.turn"
            )
        with self.assertRaisesRegex(RuntimeError, "unknown object asset id"):
            module._validate_first_frame_excluded_object_ids(
                profile, ["unknown_object"], context="scene30.turn"
            )
        with self.assertRaisesRegex(RuntimeError, "non-blank strings"):
            module._validate_first_frame_excluded_object_ids(
                profile, [""], context="scene30.turn"
            )
        with self.assertRaisesRegex(RuntimeError, "non-blank strings"):
            module._validate_first_frame_excluded_object_ids(
                profile, [123], context="scene30.turn"
            )

    def test_first_frame_character_overrides_only_accept_known_same_identity_variants(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="first-frame-character-validation"
        )
        protagonist_name = str(profile["protagonist_name"])
        base_id = str(profile["protagonist_asset_id"])
        transformed_id = str(profile["protagonist_transformed_asset_id"])
        post_midnight_id = str(profile["protagonist_post_midnight_asset_id"])
        self.assertEqual(
            module._validate_first_frame_character_asset_overrides(
                profile,
                {
                    protagonist_name: base_id,
                    "protagonist": transformed_id,
                    f"魔法が解けた後の{protagonist_name}": post_midnight_id,
                },
                context="scene30.turn",
            ),
            {
                protagonist_name: base_id,
                "protagonist": transformed_id,
                f"魔法が解けた後の{protagonist_name}": post_midnight_id,
            },
        )

        stepmother_id = next(
            str(spec["character_id"])
            for spec in module._supporting_character_asset_specs(profile)
            if str(spec.get("source_character_id") or "") == "stepmother"
        )
        with self.assertRaisesRegex(RuntimeError, "same identity"):
            module._validate_first_frame_character_asset_overrides(
                profile,
                {protagonist_name: stepmother_id},
                context="scene30.turn",
            )
        with self.assertRaisesRegex(RuntimeError, "known character asset"):
            module._validate_first_frame_character_asset_overrides(
                profile,
                {protagonist_name: "unknown_character"},
                context="scene30.turn",
            )
        with self.assertRaisesRegex(RuntimeError, "must be an object"):
            module._validate_first_frame_character_asset_overrides(
                profile, [], context="scene30.turn"
            )

        ambiguous_profile = dict(profile)
        ambiguous_profile["protagonist_name"] = "Alex"
        with patch.object(
            module,
            "_supporting_character_asset_specs",
            return_value=[
                {
                    "character_id": "rival_alex",
                    "source_character_id": "rival",
                    "name": "Alex",
                    "identity_name": "Alex",
                }
            ],
        ):
            with self.assertRaisesRegex(RuntimeError, "alias is ambiguous"):
                module._validate_first_frame_character_asset_overrides(
                    ambiguous_profile,
                    {"Alex": "rival_alex"},
                    context="scene10.setup",
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

    def test_reviewed_scene_visualizable_action_survives_only_as_scene_review_trace(self) -> None:
        module = load_frontend_run_module()
        profile = self._legacy_cinderella_profile(
            module, seed="review-only-visualizable-action"
        )
        sentinel = "REGISTRY_REVIEW_TRACE_ONLY"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            research = module._build_research(
                "シンデレラ", "シンデレラ", "now", profile
            )
            (run_dir / "research.md").write_text(
                module._md_yaml("Research", research), encoding="utf-8"
            )
            story = module._build_story("シンデレラ", run_dir, "now", profile)
            story["script"]["scenes"][0]["visualizable_action"] = sentinel
            (run_dir / "story.md").write_text(
                module._md_yaml("Story", story), encoding="utf-8"
            )
            reviewed_profile = module._profile_from_reviewed_story(profile, story)
            _script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ", run_dir, "now", reviewed_profile
            )

        scene = manifest["scenes"][0]
        self.assertEqual(
            scene["scene_intent"]["review_only_visualizable_action"], sentinel
        )
        provider_payload = json.dumps(
            [
                {
                    "scene_contract": cut["scene_contract"],
                    "first_frame_visual_plan": cut["image_generation"][
                        "first_frame_visual_plan"
                    ],
                    "api_prompt_payload": cut["image_generation"][
                        "api_prompt_payload"
                    ],
                }
                for cut in scene["cuts"]
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn(sentinel, provider_payload)

    def test_duration_expansion_preserves_canonical_routes_and_scoped_beat_overrides(self) -> None:
        module = load_frontend_run_module()
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            canonical_profile = module._story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="duration-segment",
            )
            profile = module._duration_aware_profile(
                canonical_profile,
                target_duration_seconds=1200,
            )

        def explicit_locations(value: object) -> set[str]:
            if isinstance(value, dict):
                locations = {
                    str(value.get("location") or "").strip()
                } if str(value.get("location") or "").strip() else set()
                for child in value.values():
                    locations.update(explicit_locations(child))
                return locations
            if isinstance(value, list):
                locations: set[str] = set()
                for child in value:
                    locations.update(explicit_locations(child))
                return locations
            return set()

        checked_split_scenes = 0
        seen_functions_by_canonical: dict[int, set[str]] = {}
        seen_segment_functions_by_canonical: dict[int, set[str]] = {}
        root_functions_by_segment: dict[tuple[int, str], list[str]] = {}
        scene8_event_sequences: list[tuple[int, list[dict[str, object]]]] = []
        preserved_stone_road_obligations: set[str] = set()
        for runtime_scene_index, segment_count in enumerate(profile["scene_segment_counts"], start=1):
            if segment_count <= 1:
                continue
            allowed_locations = set(profile["scene_location_sequences"][runtime_scene_index - 1])
            canonical_index = int(profile["canonical_scene_indices"][runtime_scene_index - 1])
            canonical_route = list(
                canonical_profile["scene_location_sequences"][canonical_index - 1]
            )
            self.assertEqual(
                profile["scene_location_sequences"][runtime_scene_index - 1],
                canonical_route,
                f"runtime scene {runtime_scene_index}",
            )
            blueprint = module._scene_blueprint(
                profile=profile,
                idx=runtime_scene_index,
                title=profile["scene_titles"][runtime_scene_index - 1],
                location_name=profile["scene_locations"][runtime_scene_index - 1],
                include_artifact=False,
            )
            locations = explicit_locations(blueprint["beat_overrides"])
            self.assertLessEqual(locations, allowed_locations, f"runtime scene {runtime_scene_index}")
            seen_functions = seen_functions_by_canonical.setdefault(canonical_index, set())
            duplicated_functions = seen_functions.intersection(blueprint["beat_overrides"])
            self.assertFalse(duplicated_functions, f"runtime scene {runtime_scene_index}")
            seen_functions.update(blueprint["beat_overrides"])
            seen_segment_functions = seen_segment_functions_by_canonical.setdefault(
                canonical_index, set()
            )
            for segment in profile["scene_location_segments"][runtime_scene_index - 1]:
                segment_functions = set((segment.get("beat_overrides") or {}).keys())
                self.assertFalse(
                    seen_segment_functions.intersection(segment_functions),
                    f"runtime scene {runtime_scene_index} segment overrides",
                )
                seen_segment_functions.update(segment_functions)
                root_functions_by_segment.setdefault(
                    (canonical_index, str(segment["location"])), []
                ).extend(segment.get("root_active_beat_functions") or [])
            if canonical_index == 8:
                location_spec = module._location_spec_for_scene(
                    profile, runtime_scene_index
                )
                scene_intent = module._scene_intent_for_cut_design(
                    title=profile["scene_titles"][runtime_scene_index - 1],
                    idx=runtime_scene_index,
                    location_spec=location_spec,
                    profile=profile,
                    include_artifact=True,
                )
                scene_event = module._scene_event_for_cut_design(
                    title=profile["scene_titles"][runtime_scene_index - 1],
                    idx=runtime_scene_index,
                    scene_intent=scene_intent,
                    location_name=str(location_spec["name"]),
                    location_id=str(location_spec["asset_id"]),
                    profile=profile,
                    include_artifact=True,
                )
                scene8_event_sequences.append(
                    (runtime_scene_index, scene_event["event_sequence"])
                )
            if canonical_index == 4 and "宮殿へ続く石畳" in allowed_locations:
                payoff = blueprint["beat_overrides"].get("payoff") or {}
                preserved_stone_road_obligations.update(
                    (payoff.get("obligation_overrides") or {}).keys()
                )
            checked_split_scenes += 1
        self.assertGreater(checked_split_scenes, 1)
        self.assertEqual(
            preserved_stone_road_obligations,
            {
                "audience_context",
                "spatial_transition",
                "time_or_deadline_pressure",
            },
        )
        for canonical_index, canonical_segments in enumerate(
            canonical_profile["scene_location_segments"], start=1
        ):
            expected_segment_functions = {
                function
                for segment in canonical_segments
                for function in (segment.get("beat_overrides") or {})
            }
            self.assertEqual(
                seen_segment_functions_by_canonical.get(canonical_index, set()),
                expected_segment_functions,
                f"canonical scene {canonical_index} segment override coverage",
            )
        self.assertEqual(
            root_functions_by_segment[(8, "王宮の命令の間")], ["setup"]
        )
        self.assertEqual(
            root_functions_by_segment[(8, "町の家々")], ["pressure"]
        )
        self.assertEqual(
            root_functions_by_segment[(8, "靴合わせの部屋")], ["payoff"]
        )
        for segment in canonical_profile["scene_location_segments"][7]:
            responsibility = str(segment["responsibility"])
            owners = [
                (runtime_index, str(beat["beat_function"]))
                for runtime_index, sequence in scene8_event_sequences
                for beat in sequence
                if responsibility in str(beat.get("what_happens") or "")
            ]
            self.assertEqual(len(owners), 1, responsibility)
