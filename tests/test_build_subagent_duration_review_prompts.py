import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENE_SCRIPT_PATH = REPO_ROOT / "scripts" / "build-subagent-duration-scene-review-prompt.py"
NARRATION_SCRIPT_PATH = REPO_ROOT / "scripts" / "build-subagent-duration-narration-review-prompt.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCENE_MODULE = _load_module(SCENE_SCRIPT_PATH, "build_subagent_duration_scene_review_prompt")
NARRATION_MODULE = _load_module(NARRATION_SCRIPT_PATH, "build_subagent_duration_narration_review_prompt")


class TestBuildSubagentDurationReviewPrompts(unittest.TestCase):
    def test_scene_prompt_builder_includes_thresholds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_duration_scene_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt = SCENE_MODULE.build_duration_scene_review_prompt(
                run_dir=run_dir,
                minimum_seconds=300,
                actual_seconds=133,
                flow="immersive",
            )

            self.assertIn("scene-duration expansion review", prompt)
            self.assertIn("Actual runtime after audio sync: `133` seconds.", prompt)
            self.assertIn("Required minimum runtime: `300` seconds.", prompt)
            self.assertIn(str((run_dir / "story.md").resolve()), prompt)
            self.assertIn("scene_expansion_plan: [...]", prompt)

    def test_narration_prompt_builder_includes_thresholds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_duration_narration_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt = NARRATION_MODULE.build_duration_narration_review_prompt(
                run_dir=run_dir,
                minimum_seconds=300,
                actual_seconds=133,
                flow="immersive",
            )

            self.assertIn("narration-duration expansion review", prompt)
            self.assertIn("Actual runtime after audio sync: `133` seconds.", prompt)
            self.assertIn("Required minimum runtime: `300` seconds.", prompt)
            self.assertIn(str((run_dir / "script.md").resolve()), prompt)
            self.assertIn("silent_cuts_to_keep: [...]", prompt)

    def test_cli_writes_prompt_artifacts_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_duration_prompt_cli_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)

            scene_result = subprocess.run(
                [
                    sys.executable,
                    str(SCENE_SCRIPT_PATH),
                    "--run-dir",
                    str(run_dir),
                    "--min-seconds",
                    "300",
                    "--actual-seconds",
                    "133",
                    "--flow",
                    "immersive",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            narration_result = subprocess.run(
                [
                    sys.executable,
                    str(NARRATION_SCRIPT_PATH),
                    "--run-dir",
                    str(run_dir),
                    "--min-seconds",
                    "300",
                    "--actual-seconds",
                    "133",
                    "--flow",
                    "immersive",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(scene_result.returncode, 0, msg=scene_result.stderr)
            self.assertEqual(narration_result.returncode, 0, msg=narration_result.stderr)

            scene_path = run_dir / "logs" / "review" / "duration_scene.subagent_prompt.md"
            narration_path = run_dir / "logs" / "review" / "duration_narration.subagent_prompt.md"
            self.assertTrue(scene_path.exists())
            self.assertTrue(narration_path.exists())
            self.assertEqual(scene_path.read_text(encoding="utf-8").strip(), scene_result.stdout.strip())
            self.assertEqual(narration_path.read_text(encoding="utf-8").strip(), narration_result.stdout.strip())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.duration_fit.scene_prompt"), "logs/review/duration_scene.subagent_prompt.md")
            self.assertEqual(state.get("review.duration_fit.narration_prompt"), "logs/review/duration_narration.subagent_prompt.md")
            self.assertTrue(state.get("review.duration_fit.scene_prompt.generated_at"))
            self.assertTrue(state.get("review.duration_fit.narration_prompt.generated_at"))


if __name__ == "__main__":
    unittest.main()
