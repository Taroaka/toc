import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-subagent-image-review-prompt.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


SPEC = importlib.util.spec_from_file_location("build_subagent_image_review_prompt", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestBuildSubagentImageReviewPrompt(unittest.TestCase):
    def test_build_prompt_includes_review_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_image_review_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt = MODULE.build_subagent_image_review_prompt(run_dir=run_dir, flow="immersive")

            self.assertIn("You are a contextless, judgment-only subagent for ToC image prompt quality review.", prompt)
            self.assertIn(f"Review the image prompt quality for run dir `{run_dir.resolve()}`.", prompt)
            self.assertIn("python scripts/export-image-prompt-collection.py --manifest", prompt)
            self.assertIn("python scripts/review-image-prompt-story-consistency.py --manifest", prompt)
            self.assertIn(str((run_dir / "video_manifest.md").resolve()), prompt)
            self.assertIn(str((run_dir / "image_prompt_story_review.md").resolve()), prompt)
            self.assertIn("hard_blockers: [...]", prompt)
            self.assertIn("revision_suggestions: [...]", prompt)

    def test_cli_writes_prompt_artifact_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_image_review_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
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

            prompt_path = run_dir / "logs" / "review" / "image_prompt.subagent_prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertEqual(prompt_path.read_text(encoding="utf-8").strip(), result.stdout.strip())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(
                state.get("review.image_prompt.subagent.prompt"),
                "logs/review/image_prompt.subagent_prompt.md",
            )
            self.assertTrue(state.get("review.image_prompt.subagent.prompt.generated_at"))


if __name__ == "__main__":
    unittest.main()
