from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from toc.harness import parse_state_file
from toc.review_loop import (
    MAX_REVIEW_LOOP_ROUNDS,
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SPECS,
    aggregator_prompt_relpath,
    aggregated_review_relpath,
    critic_prompt_relpath,
    critic_relpath,
    loop_state_updates,
    render_aggregated_review,
    render_critic_prompt,
    stage_for_slot,
)
from toc.run_index import SLOT_BY_CODE, build_run_index_markdown, classify_run_file


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-review-loop-round.py"
SPEC = importlib.util.spec_from_file_location("build_review_loop_round", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class TestReviewLoop(unittest.TestCase):
    def test_review_slots_are_improvement_loops(self) -> None:
        expected_slots = {
            "p130",
            "p230",
            "p320",
            "p430",
            "p540",
            "p630",
            "p640",
            "p720",
            "p820",
            "p850",
            "p930",
        }
        for code in expected_slots:
            with self.subTest(code=code):
                slot = SLOT_BY_CODE[code]
                self.assertIn("Eval/Improve Loop", slot.title)
                self.assertIn("5", slot.purpose)
                self.assertIn("5 independent critics", slot.purpose)
                self.assertIn("1 aggregator", slot.purpose)

    def test_review_loop_paths_and_state_contract(self) -> None:
        self.assertEqual(MAX_REVIEW_LOOP_ROUNDS, 5)
        self.assertEqual(REVIEW_LOOP_CRITIC_COUNT, 5)
        self.assertEqual(critic_relpath("story", 1, 1).as_posix(), "logs/eval/story/round_01/critic_1.md")
        self.assertEqual(critic_prompt_relpath("story", 1, 1).as_posix(), "logs/eval/story/round_01/prompts/critic_1.prompt.md")
        self.assertEqual(aggregator_prompt_relpath("story", 1).as_posix(), "logs/eval/story/round_01/prompts/aggregator.prompt.md")
        self.assertEqual(aggregated_review_relpath("story", 1).as_posix(), "logs/eval/story/round_01/aggregated_review.md")

        updates = loop_state_updates(stage="story", status="running", current_round=1)
        self.assertEqual(updates["eval.story.loop.status"], "running")
        self.assertEqual(updates["eval.story.loop.current_round"], "1")
        self.assertEqual(updates["eval.story.loop.max_rounds"], "5")
        self.assertEqual(updates["eval.story.loop.final_report"], "story_review.md")
        self.assertEqual(stage_for_slot("p640"), "scene_implementation_judgment")
        self.assertEqual(stage_for_slot("850"), "video_generation_review")
        self.assertEqual(stage_for_slot("p410b"), "scene_set")
        self.assertEqual(stage_for_slot("410c"), "scene_detail")
        self.assertEqual(stage_for_slot("p435"), "production_readiness")
        self.assertIn("scene_set", REVIEW_LOOP_SPECS)
        self.assertIn("scene_detail", REVIEW_LOOP_SPECS)
        self.assertIn("cut_blueprint", REVIEW_LOOP_SPECS)
        self.assertIn("production_readiness", REVIEW_LOOP_SPECS)
        self.assertIn("scene_intent", REVIEW_LOOP_SPECS)
        self.assertEqual(REVIEW_LOOP_SPECS["scene_set"].final_report, "scene_set_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["scene_detail"].final_report, "scene_detail_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["cut_blueprint"].final_report, "cut_blueprint_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["production_readiness"].final_report, "production_readiness_review.md")

    def test_aggregated_review_requires_five_critics(self) -> None:
        reports = [f"- status: changes_requested\n- note: critic {idx}" for idx in range(1, 6)]
        review = render_aggregated_review(stage="script", round_number=2, critic_reports=reports)
        self.assertIn("# Script Eval/Improve Loop", review)
        self.assertIn("- round: 2/5", review)
        self.assertIn("## Generator Patch Brief", review)
        self.assertIn("root cause", review)
        self.assertIn("fix plan", review)
        self.assertIn("acceptance condition", review)
        self.assertIn("## Critic 5 Input", review)

        with self.assertRaises(ValueError):
            render_aggregated_review(stage="script", round_number=2, critic_reports=reports[:4])

    def test_build_review_loop_round_materializes_prompts_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["story"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)

            for idx in range(1, 6):
                report_path = run_dir / critic_relpath("story", 1, idx)
                prompt_path = run_dir / critic_prompt_relpath("story", 1, idx)
                self.assertFalse(report_path.exists(), report_path)
                self.assertTrue(prompt_path.exists(), prompt_path)
                prompt_text = prompt_path.read_text(encoding="utf-8")
                self.assertIn(f"critic_{idx}", prompt_text)
                self.assertIn("root_cause", prompt_text)
                self.assertIn("fix_direction", prompt_text)
            aggregate_prompt = run_dir / aggregator_prompt_relpath("story", 1)
            self.assertTrue(aggregate_prompt.exists())
            aggregate_text = aggregate_prompt.read_text(encoding="utf-8")
            self.assertIn("Wait until all 5 critic reports exist", aggregate_text)
            self.assertIn("essential cause", aggregate_text)
            self.assertIn("adopted_fix_plan", aggregate_text)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.story.loop.status"], "running")
            self.assertEqual(state["eval.story.loop.round_01.critic_5"], "logs/eval/story/round_01/critic_5.md")
            self.assertEqual(
                state["eval.story.loop.round_01.critic_5_prompt"],
                "logs/eval/story/round_01/prompts/critic_5.prompt.md",
            )

    def test_p400_scene_and_cut_review_surfaces_materialize_by_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p400_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["scene_set"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            MODULE.write_review_loop_round(run_dir=run_dir, stage="scene_set", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="scene_detail", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="cut_blueprint", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="production_readiness", round_number=1)

            self.assertTrue((run_dir / critic_prompt_relpath("scene_set", 1, 1)).exists())
            scene_prompt = (run_dir / critic_prompt_relpath("scene_set", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("visual_value.md", scene_prompt)
            self.assertTrue((run_dir / critic_prompt_relpath("scene_detail", 1, 1)).exists())
            detail_prompt = (run_dir / critic_prompt_relpath("scene_detail", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("5-10 minute video", detail_prompt)
            self.assertIn("4-15 seconds", detail_prompt)
            self.assertIn("next scene", detail_prompt)
            self.assertTrue((run_dir / critic_prompt_relpath("cut_blueprint", 1, 1)).exists())
            self.assertTrue((run_dir / critic_prompt_relpath("production_readiness", 1, 1)).exists())
            readiness_prompt = (run_dir / critic_prompt_relpath("production_readiness", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("Structure Auditor", readiness_prompt)
            self.assertIn("Duration Auditor", readiness_prompt)
            self.assertIn("Quality Auditor", readiness_prompt)
            self.assertIn("Orchestrator", readiness_prompt)
            self.assertIn("Design Owner", readiness_prompt)
            self.assertIn("only agent allowed to edit downstream design artifacts", readiness_prompt)
            readiness_aggregate_prompt = (run_dir / aggregator_prompt_relpath("production_readiness", 1)).read_text(encoding="utf-8")
            self.assertIn("Design Owner-facing brief", readiness_aggregate_prompt)
            self.assertIn("design_owner_patch_brief", readiness_aggregate_prompt)
            self.assertIn("do not route edits to", readiness_aggregate_prompt)
            readiness_review = render_aggregated_review(
                stage="production_readiness",
                round_number=1,
                critic_reports=["- status: passed"] * REVIEW_LOOP_CRITIC_COUNT,
                status="passed",
            )
            self.assertIn("## Design Owner Patch Brief", readiness_review)
            self.assertNotIn("## Generator Patch Brief", readiness_review)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.scene_set.loop.status"], "running")
            self.assertEqual(state["eval.scene_detail.loop.status"], "running")
            self.assertEqual(state["eval.cut_blueprint.loop.status"], "running")
            self.assertEqual(state["eval.production_readiness.loop.status"], "running")
            self.assertEqual(classify_run_file("logs/eval/scene_set/round_01/aggregated_review.md").slot, "p410")
            self.assertEqual(classify_run_file("logs/eval/scene_detail/round_01/aggregated_review.md").slot, "p410")
            self.assertEqual(classify_run_file("logs/eval/cut_blueprint/round_01/aggregated_review.md").slot, "p420")
            self.assertEqual(classify_run_file("logs/eval/production_readiness/round_01/aggregated_review.md").slot, "p435")
            self.assertEqual(classify_run_file("production_readiness_review.md").slot, "p435")

    def test_asset_review_prompt_includes_p500_coverage_criteria(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_asset_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["asset"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            prompt = render_critic_prompt(run_dir=run_dir, stage="asset", round_number=1, critic_number=1)

            self.assertIn("Treat p520 coverage as the first gate", prompt)
            self.assertIn("asset_inventory.md", prompt)
            self.assertIn("characters, story-specific items, used locations, setpieces", prompt)
            self.assertIn("full-body front / side / back", prompt)
            self.assertIn("source_script_selectors[]", prompt)
            self.assertIn("execution_lane=bootstrap_builtin", prompt)
            self.assertIn("canonical output path", prompt)
            self.assertIn("reference count/input consistency", prompt)
            self.assertIn("generation/review status readiness", prompt)
            self.assertIn("Hard review", prompt)
            self.assertIn("Judgment review", prompt)
            self.assertIn("物語「<topic>」の scene10", prompt)

    def test_build_review_loop_round_rejects_missing_sources_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_missing_") as td:
            run_dir = Path(td)

            with self.assertRaises(FileNotFoundError):
                MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)

            self.assertFalse((run_dir / "state.txt").exists())

    def test_running_prompt_only_loop_is_not_marked_done(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_index_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["story"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)
            index_text = build_run_index_markdown(run_dir)
            p230_start = index_text.index("#### p230 Story Eval/Improve Loop")
            p300_start = index_text.index("### p300 Visual Planning", p230_start)
            p230_section = index_text[p230_start:p300_start]

            self.assertIn("- status: `in_progress`", p230_section)
            self.assertNotIn("- status: `done`", p230_section)

    def test_paired_review_surfaces_have_distinct_loop_artifacts(self) -> None:
        self.assertEqual(critic_relpath("scene_implementation_hard", 1, 1).as_posix(), "logs/eval/scene_implementation_hard/round_01/critic_1.md")
        self.assertEqual(critic_relpath("scene_implementation_judgment", 1, 1).as_posix(), "logs/eval/scene_implementation_judgment/round_01/critic_1.md")
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_hard/round_01/aggregated_review.md").slot, "p630")
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_judgment/round_01/aggregated_review.md").slot, "p640")
        self.assertEqual(classify_run_file("logs/eval/video_generation_motion/round_01/aggregated_review.md").slot, "p820")
        self.assertEqual(classify_run_file("logs/eval/video_generation_review/round_01/aggregated_review.md").slot, "p850")

    def test_run_index_classifies_review_loop_artifacts(self) -> None:
        entry = classify_run_file("logs/eval/story/round_01/aggregated_review.md")
        self.assertEqual(entry.slot, "p230")
        self.assertEqual(entry.role, "log")
        self.assertIn("evaluator-improvement loop", entry.note)

        index_text = build_run_index_markdown(Path("/tmp/nonexistent-review-loop"), state={})
        self.assertIn("p230` | Story | `optional` | Story Eval/Improve Loop", index_text)
        self.assertIn("p930` | Render / QA / Runtime | `optional` | QA Eval/Improve Loop", index_text)


if __name__ == "__main__":
    unittest.main()
