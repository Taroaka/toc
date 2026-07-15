import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check-audio-duration-gate.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE_MODULE = _load_module(SCRIPT_PATH, "check_audio_duration_gate")


def _write_markdown_yaml(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(["# Doc", "", "```yaml", *lines, "```", ""]) + "\n", encoding="utf-8")


def _write_run(run_dir: Path, *, include_scene: bool = True) -> Path:
    manifest_lines = [
        "video_metadata:",
        '  topic: "テスト"',
        "  target_duration_seconds: 300",
        "  duration_seconds: 999",
        "  experience: cinematic_story",
    ]
    if include_scene:
        manifest_lines.extend(
            [
                "scenes:",
                "  - scene_id: 1",
                "    cuts:",
                "      - cut_id: 1",
                "        video_generation:",
                "          duration_seconds: 600",
                "        audio:",
                "          narration:",
                "            tool: elevenlabs",
                "            output: assets/audio/scene1_cut1.wav",
            ]
        )
    else:
        manifest_lines.append("scenes: []")

    manifest_path = run_dir / "video_manifest.md"
    _write_markdown_yaml(manifest_path, manifest_lines)
    _write_markdown_yaml(
        run_dir / "script.md",
        ["script_metadata:", "  target_duration: 300", "scenes: []"],
    )
    (run_dir / "state.txt").write_text("topic=テスト\n---\n", encoding="utf-8")
    if include_scene:
        audio_path = run_dir / "assets" / "audio" / "scene1_cut1.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"probe-is-injected")
    return manifest_path


def _run_gate(run_dir: Path, *, probed_seconds: float | None) -> tuple[int, str]:
    manifest_path = run_dir / "video_manifest.md"
    argv = [
        str(SCRIPT_PATH),
        "--manifest",
        str(manifest_path),
        "--run-dir",
        str(run_dir),
        "--flow",
        "immersive",
    ]
    output = io.StringIO()
    with (
        patch.object(sys, "argv", argv),
        patch.object(GATE_MODULE, "_ffprobe_duration_seconds", return_value=probed_seconds),
        contextlib.redirect_stdout(output),
    ):
        return GATE_MODULE.main(), output.getvalue()


class TestAudioDurationGate(unittest.TestCase):
    def test_legacy_minimum_duration_fallback_recovers_the_original_target(self) -> None:
        self.assertEqual(
            GATE_MODULE._resolve_target_seconds(
                state={},
                manifest_data={"video_metadata": {"minimum_duration_seconds": 240}},
                script_data={},
                explicit=None,
            ),
            300,
        )
        self.assertEqual(
            GATE_MODULE._resolve_target_seconds(
                state={"runtime.duration_gate.minimum_seconds": "480"},
                manifest_data={"video_metadata": {}},
                script_data={},
                explicit=None,
            ),
            600,
        )

    def test_canonical_target_beats_legacy_minimum_fallback(self) -> None:
        self.assertEqual(
            GATE_MODULE._resolve_target_seconds(
                state={"runtime.target_video_seconds": "900"},
                manifest_data={"video_metadata": {"minimum_duration_seconds": 240}},
                script_data={},
                explicit=None,
            ),
            900,
        )

    def test_ffprobe_adapter_returns_real_duration_and_rejects_missing_input(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audio_duration_probe_") as td:
            audio_path = Path(td) / "audio.wav"
            audio_path.write_bytes(b"fake")
            completed = SimpleNamespace(stdout="12.5\n")

            with (
                patch.object(GATE_MODULE.shutil, "which", return_value="/usr/bin/ffprobe"),
                patch.object(GATE_MODULE.subprocess, "run", return_value=completed) as run,
            ):
                duration = GATE_MODULE._ffprobe_duration_seconds(audio_path)

            self.assertEqual(duration, 12.5)
            self.assertIn(str(audio_path), run.call_args.args[0])
            self.assertIsNone(GATE_MODULE._ffprobe_duration_seconds(Path(td) / "missing.wav"))

    def test_gate_ignores_spoofed_metadata_and_fails_at_79_9_percent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audio_duration_gate_") as td:
            run_dir = Path(td) / "output" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_run(run_dir)

            returncode, output = _run_gate(run_dir, probed_seconds=239.7)

            self.assertEqual(returncode, 2)
            self.assertIn("below minimum 240", output)
            self.assertTrue((run_dir / "logs" / "review" / "duration_scene.subagent_prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "review" / "duration_narration.subagent_prompt.md").exists())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.duration_fit.status"), "changes_requested")
            self.assertEqual(state.get("review.duration_fit.target_seconds"), "300")
            self.assertEqual(state.get("review.duration_fit.minimum_seconds"), "240")
            self.assertEqual(state.get("review.duration_fit.actual_seconds"), "239.7")
            self.assertAlmostEqual(float(state.get("review.duration_fit.ratio") or "0"), 0.799)
            self.assertEqual(state.get("review.duration_fit.measurement_complete"), "true")
            self.assertEqual(state.get("review.duration_fit.audio_timeline_seconds"), "239.7")
            self.assertEqual(state.get("review.duration_fit.video_timeline_seconds"), "600")
            self.assertEqual(state.get("slot.p740.status"), "failed")
            self.assertEqual(state.get("slot.p750.status"), "blocked")

    def test_gate_passes_at_80_percent_and_has_no_upper_bound(self) -> None:
        for suffix, actual in (("boundary", 240.0), ("over", 450.0)):
            with self.subTest(actual=actual), tempfile.TemporaryDirectory(prefix="toc_audio_duration_gate_") as td:
                run_dir = Path(td) / "output" / f"topic_{suffix}"
                run_dir.mkdir(parents=True, exist_ok=True)
                _write_run(run_dir)

                returncode, output = _run_gate(run_dir, probed_seconds=actual)

                self.assertEqual(returncode, 0)
                self.assertIn("meets minimum 240", output)
                state = parse_state_file(run_dir / "state.txt")
                self.assertEqual(state.get("review.duration_fit.status"), "passed")
                self.assertEqual(state.get("slot.p740.status"), "done")
                self.assertEqual(state.get("slot.p750.status"), "pending")
                self.assertAlmostEqual(float(state.get("review.duration_fit.ratio") or "0"), actual / 300)

    def test_incomplete_measurement_fails_even_when_metadata_claims_long_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audio_duration_gate_") as td:
            run_dir = Path(td) / "output" / "topic_incomplete"
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_run(run_dir, include_scene=False)

            returncode, output = _run_gate(run_dir, probed_seconds=None)

            self.assertEqual(returncode, 2)
            self.assertIn("measurement is incomplete", output)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("review.duration_fit.measurement_complete"), "false")
            self.assertEqual(state.get("review.duration_fit.actual_seconds"), "0")
            self.assertIn("manifest:scenes", state.get("review.duration_fit.missing_items") or "")
            self.assertEqual(state.get("slot.p740.status"), "failed")


if __name__ == "__main__":
    unittest.main()
