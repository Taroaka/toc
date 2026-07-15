import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toc.harness import parse_state_file


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-final-video-duration-gate.py"


def _write_manifest(
    run_dir: Path,
    *,
    target_seconds: int | None = 300,
    minimum_seconds: int | None = None,
) -> None:
    duration_lines: list[str] = []
    if target_seconds is not None:
        duration_lines.append(f"  target_duration_seconds: {target_seconds}")
    if minimum_seconds is not None:
        duration_lines.append(f"  minimum_duration_seconds: {minimum_seconds}")
    (run_dir / "video_manifest.md").write_text(
        "\n".join(
            [
                "# Manifest",
                "",
                "```yaml",
                "video_metadata:",
                *duration_lines,
                "scenes: []",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_fake_ffprobe(bin_dir: Path, *, duration_seconds: float) -> None:
    ffprobe = bin_dir / "ffprobe"
    ffprobe.write_text(
        "#!/bin/sh\n" f"echo '{duration_seconds}'\n",
        encoding="utf-8",
    )
    ffprobe.chmod(0o755)


class FinalVideoDurationGateTests(unittest.TestCase):
    def test_immersive_cli_runs_final_gate_before_marking_done(self) -> None:
        script = (REPO_ROOT / "scripts" / "toc-immersive-ride-generate.sh").read_text(encoding="utf-8")

        gate_index = script.index("check-final-video-duration-gate.py")
        done_index = script.index('stage="done"')

        self.assertLess(gate_index, done_index)

    def _run_gate(
        self,
        *,
        actual_seconds: float,
        target_seconds: int | None = 300,
        minimum_seconds: int | None = None,
        state_target_seconds: int | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        with tempfile.TemporaryDirectory(prefix="toc_final_duration_") as td:
            run_dir = Path(td) / "output" / "topic_20990101_0000"
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, target_seconds=target_seconds, minimum_seconds=minimum_seconds)
            state_lines = ["topic=テスト"]
            if state_target_seconds is not None:
                state_lines.append(f"runtime.target_video_seconds={state_target_seconds}")
            (run_dir / "state.txt").write_text("\n".join(state_lines) + "\n---\n", encoding="utf-8")
            final_video = run_dir / "video.mp4"
            final_video.write_bytes(b"test-video")
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            _write_fake_ffprobe(bin_dir, duration_seconds=actual_seconds)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--run-dir",
                    str(run_dir),
                    "--video",
                    str(final_video),
                ],
                cwd=REPO_ROOT,
                env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"},
                capture_output=True,
                text=True,
                check=False,
            )
            return result, parse_state_file(run_dir / "state.txt")

    def test_final_video_below_eighty_percent_fails(self) -> None:
        result, state = self._run_gate(actual_seconds=239.7)

        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
        self.assertEqual(state["review.final.duration_fit.status"], "changes_requested")
        self.assertEqual(state["slot.p920.status"], "failed")
        self.assertEqual(state["slot.p930.status"], "blocked")

    def test_final_video_at_eighty_percent_passes(self) -> None:
        result, state = self._run_gate(actual_seconds=240.0)

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(state["review.final.duration_fit.status"], "passed")
        self.assertEqual(state["slot.p920.status"], "done")
        self.assertEqual(state["slot.p930.status"], "awaiting_approval")

    def test_final_video_over_target_has_no_upper_failure(self) -> None:
        result, state = self._run_gate(actual_seconds=450.0)

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(state["review.final.duration_fit.status"], "passed")
        self.assertEqual(state["review.final.duration_fit.actual_seconds"], "450")

    def test_final_video_target_falls_back_to_run_state(self) -> None:
        result, state = self._run_gate(
            actual_seconds=480,
            target_seconds=None,
            state_target_seconds=600,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(state["review.final.duration_fit.target_seconds"], "600")
        self.assertEqual(state["review.final.duration_fit.minimum_seconds"], "480")

    def test_final_video_legacy_minimum_recovers_original_target(self) -> None:
        result, state = self._run_gate(
            actual_seconds=240,
            target_seconds=None,
            minimum_seconds=240,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertEqual(state["review.final.duration_fit.target_seconds"], "300")


if __name__ == "__main__":
    unittest.main()
