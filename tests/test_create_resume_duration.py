import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from server import image_gen_app


def _write_manifest(run_dir: Path, target: object | None) -> None:
    target_line = [] if target is None else [f"  target_duration_seconds: {target}"]
    (run_dir / "video_manifest.md").write_text(
        "\n".join(
            [
                "# Manifest",
                "",
                "```yaml",
                "video_metadata:",
                *target_line,
                "scenes: []",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


class CreateResumeDurationTests(unittest.TestCase):
    def test_resume_restores_manifest_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_duration_") as td:
            run_dir = Path(td)
            _write_manifest(run_dir, 1200)
            (run_dir / "state.txt").write_text("runtime.target_video_seconds=300\n---\n", encoding="utf-8")

            target = image_gen_app._target_duration_seconds_for_run(run_dir)

        self.assertEqual(target, 1200)

    def test_resume_falls_back_to_state_then_default(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_duration_") as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text("runtime.target_video_seconds=900\n---\n", encoding="utf-8")
            self.assertEqual(image_gen_app._target_duration_seconds_for_run(run_dir), 900)

            (run_dir / "state.txt").write_text("topic=test\n---\n", encoding="utf-8")
            self.assertEqual(image_gen_app._target_duration_seconds_for_run(run_dir), 300)

    def test_resume_rejects_invalid_persisted_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_duration_") as td:
            run_dir = Path(td)
            _write_manifest(run_dir, 1201)

            with self.assertRaisesRegex(ValueError, "between 300 and 1200"):
                image_gen_app._target_duration_seconds_for_run(run_dir)

    def test_resume_schedules_create_job_with_persisted_target(self) -> None:
        scheduled: list[dict[str, object]] = []

        async def noop_job():
            return None

        def fake_run_create_job(job_id: str, **kwargs):
            scheduled.append({"job_id": job_id, **kwargs})
            return noop_job()

        def fake_create_task(coro):
            coro.close()
            return object()

        with tempfile.TemporaryDirectory(prefix="toc_resume_duration_") as td:
            root = Path(td)
            run_id = "story_20990101_0000"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 1200)
            (run_dir / "state.txt").write_text("runtime.target_video_seconds=1200\n---\n", encoding="utf-8")
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._current_process_number_for_run", return_value=650),
                patch("server.image_gen_app.process_store.get_process_run", return_value=None),
                patch("server.image_gen_app._acquire_run_execution_lease", AsyncMock()),
                patch("server.image_gen_app._create_process_record_best_effort", return_value=None),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    return_value={"preservedCount": 0},
                ),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
                patch("server.image_gen_app._run_create_job", fake_run_create_job),
                patch("server.image_gen_app.asyncio.create_task", fake_create_task),
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
            ):
                payload = asyncio.run(
                    image_gen_app.api_resume_run(run_id, image_gen_app.ResumeRunRequest(stop_target="p680"))
                )

        self.assertEqual(payload["targetDurationSeconds"], 1200)
        self.assertEqual(scheduled[0]["target_duration_seconds"], 1200)


if __name__ == "__main__":
    unittest.main()
