import subprocess
import sys
import tempfile
import unittest
import re
import json
import importlib.util
import os
from pathlib import Path
from unittest.mock import Mock, patch

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
            self.assertEqual(state["runtime.duration_plan.minimum_cut_count"], "75")
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

        def fake_materialize(*args, **kwargs) -> None:
            calls.append({"args": args, "kwargs": kwargs})

        with (
            patch.object(module, "materialize_run", fake_materialize),
            patch.object(module, "prepare_grounding", Mock()),
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

        self.assertEqual(p100["state_keys"]["slot.p130.status"], "done")
        self.assertEqual(p200["state_keys"]["slot.p230.status"], "done")

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

        self.assertEqual(research_profile["events"], [reviewed_event])
        self.assertIn(reviewed_event, story["script"]["scenes"][0]["purpose"])
        self.assertIn("research.story_materials.chronological_events[E99]", story["script"]["scenes"][0]["research_refs"])
        self.assertIn("research.source_passages[P99]", story["script"]["scenes"][0]["research_refs"])

        reviewed_turn = "審査で修正された不可逆な転換を画面上の事実にする。"
        story["script"]["scenes"][0]["purpose"] = "審査で修正されたscene目的"
        story["script"]["scenes"][0]["turn"] = reviewed_turn
        cut_profile = module._profile_from_reviewed_story(research_profile, story)
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

    def test_reviewed_research_duration_contract_requires_requested_plan(self) -> None:
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
        research["metadata"]["duration_plan"].pop("minimum_cut_count")

        with self.assertRaisesRegex(RuntimeError, "metadata.duration_plan.minimum_cut_count"):
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

    def test_duration_aware_profile_expands_canonical_beats_without_losing_order(self) -> None:
        module = load_frontend_run_module()
        profile = module._story_profile("シンデレラ", "シンデレラ", variant_seed="duration-test")

        five_minutes = module._duration_aware_profile(profile, target_duration_seconds=300)
        twenty_minutes = module._duration_aware_profile(profile, target_duration_seconds=1200)

        self.assertEqual(len(five_minutes["scene_titles"]), 8)
        self.assertEqual(five_minutes["canonical_scene_indices"], list(range(1, 9)))
        self.assertEqual(len(twenty_minutes["scene_titles"]), 30)
        self.assertEqual(len(twenty_minutes["scene_locations"]), 30)
        self.assertEqual(len(twenty_minutes["canonical_scene_indices"]), 30)
        self.assertEqual(twenty_minutes["canonical_scene_indices"][0], 1)
        self.assertEqual(twenty_minutes["canonical_scene_indices"][-1], 8)
        self.assertEqual(sorted(twenty_minutes["canonical_scene_indices"]), twenty_minutes["canonical_scene_indices"])
        self.assertEqual(twenty_minutes["duration_plan"]["target_seconds"], 1200)
        self.assertEqual(twenty_minutes["duration_plan"]["minimum_scene_count"], 30)
        self.assertEqual(twenty_minutes["duration_plan"]["minimum_cut_count"], 100)
        self.assertEqual(twenty_minutes["duration_plan"]["minimum_narration_seconds"], 840)
        self.assertEqual(sum(twenty_minutes["scene_target_durations"]), 1200)

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
        self.assertGreaterEqual(len(selectors), 100)
        self.assertEqual(manifest["video_metadata"]["target_duration_seconds"], 1200)
        self.assertEqual(manifest["video_metadata"]["minimum_duration_seconds"], 960)
        self.assertGreaterEqual(sum(scene["target_duration_seconds"] for scene in manifest["scenes"]), 1200)

    def test_scene_cut_coverage_meets_duration_floor_with_distinct_obligations(self) -> None:
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
        required_floor = (profile["scene_target_durations"][idx - 1] + 7) // 8

        self.assertGreaterEqual(len(cuts), required_floor)
        self.assertEqual(coverage["min_cut_count"]["by_duration"], required_floor)
        self.assertGreaterEqual(coverage["min_cut_count"]["selected"], required_floor)
        self.assertEqual(coverage["selected_cut_count"], len(cuts))
        self.assertEqual(len(coverage["cut_assignments"]), len(cuts))
        self.assertEqual(len({cut["obligation_id"] for cut in cuts}), len(cuts))
        self.assertTrue(all(cut.get("primary_event_beat_id") for cut in cuts))

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
                    "must_be_drawn_as": "人物を囲む配置",
                },
                {
                    "source_field": "viewer_contract.visual_evidence",
                    "must_be_drawn_as": "舞踏会の知らせ",
                },
            ],
        )

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
        self.assertIn("灰と家事に縛られたシンデレラは、舞踏会の知らせへ顔を上げられるか", combined)
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
        scene70_cut1 = request_a.split("## scene70_cut1", 1)[1].split("## scene70_cut2", 1)[0]
        scene70_cut3 = request_a.split("## scene70_cut3", 1)[1].split("## scene70_cut4", 1)[0]
        scene70_cut5 = request_a.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
        self.assertNotRegex(scene30_cut1, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
        self.assertRegex(scene30_cut3, r"assets/objects/[a-z0-9_]+_signature_artifact\.png")
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
            self.assertEqual(state["slot.p650.status"], "done")
            self.assertNotIn("slot.p660.status", state)
            self.assertNotIn("slot.p680.status", state)
            self.assertEqual(state["review.image.status"], "pending")
            self.assertEqual(state["gate.image_review"], "required")
            self.assertEqual(state["review.image_prompt.judgment.status"], "pending")
            self.assertEqual(state["review.semantic.asset_plan.entry_count"], "14")
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
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `location_04_location_04_78c27f`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("深夜のみ", gate_road_section)
            self.assertIn("昼光なし", gate_road_section)
            self.assertIn("太陽なし", gate_road_section)
            self.assertIn("明るい青空", gate_road_section)
            midnight_stair_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `location_07_location_07_def6a5`(?:(?!\n## scene).)*",
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
            duration_cut_floor = sum(
                (int(scene["target_duration_seconds"]) + 7) // 8
                for scene in manifest_data["scenes"]
            )
            self.assertGreaterEqual(len(manifest_cuts), duration_cut_floor)
            for scene in manifest_data["scenes"]:
                self.assertGreaterEqual(
                    len(scene["cuts"]),
                    (int(scene["target_duration_seconds"]) + 7) // 8,
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
            post_loss_scene70 = scene_request_text.split("## scene70_cut8", 1)[1].split("## scene80_cut1", 1)[0]
            self.assertIn("ガラスの靴", scene70_text)
            self.assertIn("脱げ", scene70_text)
            self.assertIn("階段に残ったガラスの靴", scene70_text)
            self.assertIn("証拠", scene70_text)
            self.assertIn("逃走", scene70_text)
            self.assertIn("cinderella_post_midnight_fullbody", post_loss_scene70)
            pre_loss_scene70 = scene_request_text.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
            self.assertIn("cinderella_transformed_fullbody", pre_loss_scene70)
            self.assertIn("衣装は、舞踏会ドレス姿を維持し、質素な普段着へ戻さない。", pre_loss_scene70)
            self.assertIn("衣装は、魔法が解けた後の質素な衣装を維持し、舞踏会ドレスへ戻さない。", post_loss_scene70)
            scene70_manifest = manifest_text.split("scene_id: 70", 1)[1].split("scene_id: 80", 1)[0]
            self.assertIn("source_event_contract:", scene70_manifest)
            self.assertIn("event_context_for_cut:", scene70_manifest)
            self.assertIn("cut_contract.source_event_contract", scene70_manifest)

            transformation_scene = scene_request_text.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
            self.assertIn("reference_count: `2`", transformation_scene)
            self.assertNotIn("glass_slipper", transformation_scene)
            transformation_reveal = scene_request_text.split("## scene30_cut3", 1)[1].split("## scene30_cut4", 1)[0]
            transformation_reveal_api_prompt = re.search(r"```api_prompt\n(?P<body>.*?)\n```", transformation_reveal, re.DOTALL).group("body")
            self.assertIn("glass_slipper", transformation_reveal)
            self.assertNotIn("object_visibility:", transformation_reveal_api_prompt)
            self.assertIn("[小道具 / 舞台装置]", transformation_reveal_api_prompt)
            self.assertIn("ガラスの靴は", transformation_reveal_api_prompt)
            self.assertIn("cinderella_transformed_fullbody", transformation_reveal)

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
            self.assertIn("衣装は、魔法が解けた後の質素な衣装を維持し、舞踏会ドレスへ戻さない。", final_scene_requests)
            final_scene_api_prompts = "\n".join(re.findall(r"```api_prompt\n(.*?)\n```", final_scene_requests, re.DOTALL))
            self.assertNotIn("object_visibility:", final_scene_api_prompts)
            self.assertIn("[小道具 / 舞台装置]", final_scene_api_prompts)
            self.assertIn("ガラスの靴は", final_scene_api_prompts)
            self.assertIn("シンデレラの足に隙間なく合っている", final_scene_requests)
            self.assertIn("靴合わせが行われる部屋", final_scene_requests)
            self.assertNotIn("月光、ガラス、階段", final_scene_requests)

            video_request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("cut_contract:", video_request_text)
            self.assertIn("motion_brief:", video_request_text)

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
            self.assertIn("[人物の見える演技]", request_text)
            self.assertIn("表情は、", request_text)
            self.assertIn("視線は、", request_text)
            self.assertIn("姿勢は、", request_text)
            self.assertIn("人物と圧力源の距離は、", request_text)
            self.assertNotIn("観客理解の増分:", request_text)
            self.assertNotIn("因果の証明:", request_text)
            self.assertNotIn("静止画ルール:", request_text)
            self.assertIn("桃太郎", request_text)
            self.assertNotIn("cinderella_fullbody", request_text)
            self.assertNotIn("glass_slipper", request_text)
            self.assertNotIn("シンデレラ", request_text)

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["stage.scene_implementation.grounding.status"], "ready")
