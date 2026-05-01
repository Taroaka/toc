import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check-audio-duration-gate.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


def _write_markdown_yaml(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(["# Doc", "", "```yaml", *lines, "```", ""]) + "\n", encoding="utf-8")


class TestAudioDurationGate(unittest.TestCase):
    def test_gate_fails_and_writes_review_prompts_when_runtime_is_short(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audio_duration_gate_") as td:
            run_dir = Path(td) / "output" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_markdown_yaml(
                run_dir / "video_manifest.md",
                [
                    "video_metadata:",
                    '  topic: "テスト"',
                    "  duration_seconds: 133",
                    "  experience: cinematic_story",
                    "scenes: []",
                ],
            )
            _write_markdown_yaml(
                run_dir / "script.md",
                [
                    "script_metadata:",
                    "  target_duration: 300",
                    "scenes: []",
                ],
            )
            (run_dir / "state.txt").write_text("topic=テスト\n---\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--manifest", str(run_dir / "video_manifest.md"), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertIn("below minimum 300s", result.stdout)
            self.assertTrue((run_dir / "logs" / "review" / "duration_scene.subagent_prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "review" / "duration_narration.subagent_prompt.md").exists())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.duration_fit.status"), "changes_requested")
            self.assertEqual(state.get("review.duration_fit.actual_seconds"), "133")
            self.assertEqual(state.get("review.duration_fit.minimum_seconds"), "300")
            self.assertEqual(state.get("slot.p540.status"), "failed")
            self.assertEqual(state.get("slot.p550.status"), "pending")
            self.assertEqual(state.get("slot.p560.status"), "pending")
            self.assertEqual(state.get("slot.p570.status"), "blocked")

    def test_gate_passes_when_runtime_meets_threshold(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audio_duration_gate_") as td:
            run_dir = Path(td) / "output" / "topic_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_markdown_yaml(
                run_dir / "video_manifest.md",
                [
                    "video_metadata:",
                    '  topic: "テスト"',
                    "  duration_seconds: 305",
                    "  experience: cinematic_story",
                    "scenes: []",
                ],
            )
            _write_markdown_yaml(
                run_dir / "script.md",
                [
                    "script_metadata:",
                    "  target_duration: 300",
                    "scenes: []",
                ],
            )
            (run_dir / "state.txt").write_text("topic=テスト\n---\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--manifest", str(run_dir / "video_manifest.md"), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("meets minimum 300s", result.stdout)
            self.assertFalse((run_dir / "logs" / "review" / "duration_scene.subagent_prompt.md").exists())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.duration_fit.status"), "passed")
            self.assertEqual(state.get("slot.p540.status"), "done")
            self.assertEqual(state.get("slot.p550.status"), "skipped")
            self.assertEqual(state.get("slot.p560.status"), "skipped")
            self.assertEqual(state.get("slot.p570.status"), "pending")


if __name__ == "__main__":
    unittest.main()
