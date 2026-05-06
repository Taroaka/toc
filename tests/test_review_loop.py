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
            "p520",
            "p640",
            "p730",
            "p740",
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
        self.assertEqual(stage_for_slot("p740"), "scene_implementation_judgment")
        self.assertEqual(stage_for_slot("850"), "video_generation_review")

    def test_aggregated_review_requires_five_critics(self) -> None:
        reports = [f"- status: changes_requested\n- note: critic {idx}" for idx in range(1, 6)]
        review = render_aggregated_review(stage="script", round_number=2, critic_reports=reports)
        self.assertIn("# Script Eval/Improve Loop", review)
        self.assertIn("- round: 2/5", review)
        self.assertIn("## Generator Patch Brief", review)
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
                self.assertIn(f"critic_{idx}", prompt_path.read_text(encoding="utf-8"))
            aggregate_prompt = run_dir / aggregator_prompt_relpath("story", 1)
            self.assertTrue(aggregate_prompt.exists())
            self.assertIn("Wait until all 5 critic reports exist", aggregate_prompt.read_text(encoding="utf-8"))

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.story.loop.status"], "running")
            self.assertEqual(state["eval.story.loop.round_01.critic_5"], "logs/eval/story/round_01/critic_5.md")
            self.assertEqual(
                state["eval.story.loop.round_01.critic_5_prompt"],
                "logs/eval/story/round_01/prompts/critic_5.prompt.md",
            )

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
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_hard/round_01/aggregated_review.md").slot, "p730")
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_judgment/round_01/aggregated_review.md").slot, "p740")
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
