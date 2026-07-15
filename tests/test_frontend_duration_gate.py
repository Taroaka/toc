import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import image_gen_app
from toc.harness import parse_state_file


def _write_manifest(run_dir: Path, *, video_seconds: float, with_audio: bool = True) -> None:
    audio_output = "assets/audio/scene10_cut1.mp3" if with_audio else ""
    (run_dir / "video_manifest.md").write_text(
        "\n".join(
            [
                "# Manifest",
                "",
                "```yaml",
                "video_metadata:",
                "  target_duration_seconds: 300",
                "scenes:",
                "  - scene_id: 10",
                "    cuts:",
                "      - cut_id: 1",
                "        selector: scene10_cut1",
                "        video_generation:",
                f"          duration_seconds: {video_seconds}",
                "        audio:",
                "          narration:",
                "            tool: elevenlabs",
                "            status: audio_ready",
                f"            output: {audio_output}",
                "            review:",
                "              status: approved",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "state.txt").write_text("topic=テスト\n---\n", encoding="utf-8")
    if with_audio:
        audio_path = run_dir / audio_output
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio-fixture")


class FrontendDurationGateTests(unittest.TestCase):
    def _audit(self, *, actual_seconds: float, video_seconds: float | None = None):
        context = tempfile.TemporaryDirectory(prefix="toc_frontend_duration_")
        self.addCleanup(context.cleanup)
        run_dir = Path(context.name) / "run"
        run_dir.mkdir()
        _write_manifest(run_dir, video_seconds=video_seconds or actual_seconds)
        with patch("server.image_gen_app._probe_media_duration_seconds", return_value=actual_seconds):
            result = image_gen_app._append_narration_review_approved_if_ready(run_dir)
        return run_dir, result

    def test_frontend_p740_rejects_seventy_nine_point_nine_percent(self) -> None:
        run_dir, result = self._audit(actual_seconds=239.7, video_seconds=240)
        state = parse_state_file(run_dir / "state.txt")

        self.assertTrue(result["audioReady"])
        self.assertFalse(result["durationPassed"])
        self.assertFalse(result["ready"])
        self.assertEqual(state["review.duration_fit.status"], "changes_requested")
        self.assertEqual(state["slot.p740.status"], "failed")
        self.assertEqual(state["slot.p750.status"], "blocked")

    def test_frontend_p740_accepts_eighty_percent(self) -> None:
        run_dir, result = self._audit(actual_seconds=240.0)
        state = parse_state_file(run_dir / "state.txt")

        self.assertTrue(result["durationPassed"])
        self.assertTrue(result["ready"])
        self.assertEqual(state["review.duration_fit.status"], "passed")
        self.assertEqual(state["slot.p740.status"], "done")
        self.assertEqual(state["slot.p750.status"], "awaiting_approval")
        self.assertEqual(state["stage.narration.status"], "awaiting_approval")
        self.assertEqual(state["review.narration.status"], "pending")
        self.assertEqual(state["gate.narration_review"], "required")
        self.assertEqual(state["review.duration_fit.measurement_complete"], "true")
        self.assertNotIn("review.duration_fit.complete", state)
        self.assertEqual(json.loads(state["review.duration_fit.missing_items"]), [])
        self.assertEqual(json.loads(state["review.duration_fit.invalid_items"]), [])

    def test_frontend_p740_has_no_upper_duration_failure(self) -> None:
        run_dir, result = self._audit(actual_seconds=450.0)
        state = parse_state_file(run_dir / "state.txt")

        self.assertTrue(result["ready"])
        self.assertEqual(state["review.duration_fit.actual_seconds"], "450")
        self.assertEqual(state["review.duration_fit.minimum_seconds"], "240")

    def test_frontend_p740_requires_every_audio_item(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_frontend_duration_") as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            _write_manifest(run_dir, video_seconds=300, with_audio=False)
            result = image_gen_app._append_narration_review_approved_if_ready(run_dir)
            state = parse_state_file(run_dir / "state.txt")

        self.assertFalse(result["audioReady"])
        self.assertFalse(result["ready"])
        self.assertNotEqual(state.get("slot.p740.status"), "done")

    def test_video_readiness_rejects_duration_failure(self) -> None:
        run_dir, _result = self._audit(actual_seconds=239.7, video_seconds=240)

        with patch("server.image_gen_app._probe_media_duration_seconds", return_value=239.7):
            with self.assertRaisesRegex(ValueError, "80%|duration"):
                image_gen_app._require_narration_ready_for_video(run_dir)

    def test_frontend_final_video_rejects_below_eighty_percent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_frontend_final_") as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            run_dir = run_dir.resolve()
            _write_manifest(run_dir, video_seconds=300)
            final_video = run_dir / "video.mp4"
            final_video.write_bytes(b"video-fixture")
            with patch("server.image_gen_app._probe_media_duration_seconds", return_value=239.7):
                with self.assertRaisesRegex(ValueError, "80%"):
                    image_gen_app._apply_final_video_duration_gate(run_dir, final_video)
            state = parse_state_file(run_dir / "state.txt")

        self.assertEqual(state["review.final.duration_fit.status"], "changes_requested")
        self.assertEqual(state["slot.p920.status"], "failed")
        self.assertEqual(state["slot.p930.status"], "blocked")

    def test_frontend_final_video_accepts_eighty_percent_and_over_target(self) -> None:
        for actual_seconds in (240.0, 450.0):
            with self.subTest(actual_seconds=actual_seconds):
                with tempfile.TemporaryDirectory(prefix="toc_frontend_final_") as td:
                    run_dir = Path(td) / "run"
                    run_dir.mkdir()
                    _write_manifest(run_dir, video_seconds=300)
                    final_video = run_dir / "video.mp4"
                    final_video.write_bytes(b"video-fixture")
                    with patch("server.image_gen_app._probe_media_duration_seconds", return_value=actual_seconds):
                        result = image_gen_app._apply_final_video_duration_gate(run_dir, final_video)
                    state = parse_state_file(run_dir / "state.txt")

                self.assertTrue(result["passed"])
                self.assertEqual(state["review.final.duration_fit.status"], "passed")
                self.assertEqual(state["slot.p920.status"], "done")
                self.assertEqual(state["slot.p930.status"], "awaiting_approval")

    def test_final_render_runs_duration_gate_before_p930(self) -> None:
        class FakeProcess:
            returncode = 0

            async def communicate(self):
                return b"rendered", b""

        async def fake_create_subprocess_exec(*_args, **_kwargs):
            return FakeProcess()

        with tempfile.TemporaryDirectory(prefix="toc_frontend_final_") as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            run_dir = run_dir.resolve()
            _write_manifest(run_dir, video_seconds=300)
            (run_dir / "video.mp4").write_bytes(b"video-fixture")
            req = image_gen_app.FinalRenderRequest(
                run_id="run",
                items=[
                    {
                        "item_id": "scene10_cut1",
                        "video_path": "assets/scenes/scene10_cut1.mp4",
                        "narration_path": "assets/audio/scene10_cut1.mp3",
                        "video_duration_seconds": 240,
                    }
                ],
                output="video.mp4",
            )
            with (
                patch("server.image_gen_app.ROOT", Path(td)),
                patch("server.image_gen_app.asyncio.create_subprocess_exec", fake_create_subprocess_exec),
                patch("server.image_gen_app._probe_media_duration_seconds", return_value=240.0),
            ):
                result = asyncio.run(
                    image_gen_app._run_final_render(
                        run_dir,
                        req,
                        {"clipList": "video_clips.txt", "narrationList": "video_narration_list.txt"},
                    )
                )
            state = parse_state_file(run_dir / "state.txt")

        self.assertTrue(result["durationAudit"]["passed"])
        self.assertEqual(state["review.final.duration_fit.status"], "passed")
        self.assertEqual(state["slot.p930.status"], "awaiting_approval")


if __name__ == "__main__":
    unittest.main()
