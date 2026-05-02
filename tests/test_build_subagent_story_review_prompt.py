import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-subagent-story-review-prompt.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file

SPEC = importlib.util.spec_from_file_location("build_subagent_story_review_prompt", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestBuildSubagentStoryReviewPrompt(unittest.TestCase):
    def test_prompt_includes_story_research_readset_and_scoring_instructions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_story_prompt_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt = MODULE.build_subagent_story_review_prompt(run_dir=run_dir, flow="immersive")

            self.assertIn(str((run_dir / "story.md").resolve()), prompt)
            self.assertIn(str((run_dir / "research.md").resolve()), prompt)
            self.assertIn(str((run_dir / "logs" / "grounding" / "story.readset.json").resolve()), prompt)
            self.assertIn("Score selection candidates yourself", prompt)
            self.assertIn("purpose, conflict, turn, affect, visualizable_action, grounding_note", prompt)
            self.assertIn("candidate_scores", prompt)
            self.assertIn("Scene Findings", prompt)

    def test_cli_writes_prompt_artifact_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_story_prompt_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            prompt_path = run_dir / "logs" / "review" / "story.subagent_prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertEqual(prompt_path.read_text(encoding="utf-8").strip(), result.stdout.strip())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.story.subagent.prompt"), "logs/review/story.subagent_prompt.md")
            self.assertTrue(state.get("review.story.subagent.prompt.generated_at"))


if __name__ == "__main__":
    unittest.main()
