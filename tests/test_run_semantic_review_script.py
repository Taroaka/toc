from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.harness import parse_state_file
from toc.semantic_review import SemanticReviewStatus


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run-semantic-review.py"


def load_run_semantic_review_module():
    spec = importlib.util.spec_from_file_location("run_semantic_review_script", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load run-semantic-review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunSemanticReviewScriptTests(unittest.TestCase):
    def test_progress_resets_no_progress_watchdog(self) -> None:
        module = load_run_semantic_review_module()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            paths = module.semantic_review_relpaths(stage)
            (run_dir / paths["report"]).parent.mkdir(parents=True, exist_ok=True)

            async def progressing_review(*_args, **_kwargs):
                for index in range(4):
                    (run_dir / paths["report"]).write_text(f"status: pending\nprogress: {index}\n", encoding="utf-8")
                    if index < 3:
                        await asyncio.sleep(0.015)
                return SemanticReviewStatus(status="passed", entry_count=1, errors=())

            with (
                patch.object(module, "_run_review_once", progressing_review),
                patch.object(module, "SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.005),
            ):
                code = asyncio.run(
                    module.run_review(
                        run_dir,
                        stage,
                        timeout_seconds=0.03,
                        max_attempts=1,
                    )
                )

            state = parse_state_file(run_dir / "state.txt")

        self.assertEqual(code, 0)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.watchdog.status"], "completed")

    def test_repair_no_progress_timeout_rereviews_when_source_changed(self) -> None:
        module = load_run_semantic_review_module()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            stage = "scene_set"
            paths = module.semantic_review_relpaths(stage)
            (run_dir / paths["scope"]).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / paths["scope"]).write_text(
                json.dumps({"entry_count": 1, "source_artifacts": ["script.md"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text("# Script\n\nold scene meaning\n", encoding="utf-8")
            review_turns = 0
            repair_turns = 0

            async def fake_review_once(*_args, **_kwargs):
                nonlocal review_turns
                review_turns += 1
                if review_turns == 1:
                    return SemanticReviewStatus(status="failed", entry_count=1, errors=("wrong meaning",))
                return SemanticReviewStatus(status="passed", entry_count=1, errors=())

            async def slow_repair(*_args, **_kwargs):
                nonlocal repair_turns
                repair_turns += 1
                (run_dir / "script.md").write_text("# Script\n\nrepaired scene meaning\n", encoding="utf-8")
                await asyncio.Event().wait()

            with (
                patch.object(module, "_run_review_once", fake_review_once),
                patch.object(module, "_run_producer_repair", slow_repair),
                patch.object(module, "SEMANTIC_TURN_ARTIFACT_POLL_SECONDS", 0.005),
            ):
                code = asyncio.run(
                    module.run_review(
                        run_dir,
                        stage,
                        timeout_seconds=0.03,
                        repair_timeout_seconds=0.01,
                        max_attempts=2,
                    )
                )

            state = parse_state_file(run_dir / "state.txt")

        self.assertEqual(code, 0)
        self.assertEqual(review_turns, 2)
        self.assertEqual(repair_turns, 1)
        self.assertEqual(state["review.semantic.scene_set.loop.status"], "passed")
        self.assertEqual(state["review.semantic.scene_set.repair.transport.status"], "salvaged_after_source_artifact_change")
        self.assertEqual(state["review.semantic.scene_set.repair.changed_artifacts_detected"], "script.md")


if __name__ == "__main__":
    unittest.main()
