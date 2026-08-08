import asyncio
import json
import os
import signal
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

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


def _write_p680_regeneration_plan(run_dir: Path, *, action: str) -> None:
    scene_output = "assets/scenes/scene01.png"
    asset_output = "assets/characters/hero.png"
    (run_dir / "image_generation_requests.md").write_text(
        f"""# Image Generation Requests

## scene01

- output: `{scene_output}`
- references:
  - `character`: `{asset_output}`

```text
scene
```
""",
        encoding="utf-8",
    )
    (run_dir / "asset_generation_requests.md").write_text(
        f"""# Asset Generation Requests

## hero

- output: `{asset_output}`

```text
hero
```
""",
        encoding="utf-8",
    )
    references = [asset_output] if action == "regenerate_p500_reference_first" else []
    (run_dir / "eval_report.json").write_text(
        json.dumps(
            {
                "run_dir": str(run_dir.resolve()),
                "stage_target": "p680",
                "stages": {
                    "image": {
                        "passed": False,
                        "details": {
                            "image_regeneration_plan": [
                                {
                                    "selector": "scene01",
                                    "output": scene_output,
                                    "action": action,
                                    "vector_like_references": references,
                                }
                            ]
                        },
                    }
                },
            }
        )
        + "\n",
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

    def test_resume_with_strict_p650_schedules_image_only_job_with_persisted_target(self) -> None:
        scheduled: list[dict[str, object]] = []
        scheduled_task = Mock()

        async def noop_job():
            return None

        def fake_run_image_resume_job(job_id: str, **kwargs):
            scheduled.append({"job_id": job_id, **kwargs})
            return noop_job()

        def fake_create_task(coro):
            coro.close()
            return scheduled_task

        with tempfile.TemporaryDirectory(prefix="toc_resume_duration_") as td:
            root = Path(td)
            run_id = "story_20990101_0000"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 1200)
            (run_dir / "state.txt").write_text("runtime.target_video_seconds=1200\n---\n", encoding="utf-8")
            _write_p680_regeneration_plan(
                run_dir,
                action="regenerate_p600_scene",
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._current_process_number_for_run", return_value=650),
                patch("server.image_gen_app.process_store.get_process_run", return_value=None),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=RuntimeError("p680 incomplete"),
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch("server.image_gen_app._acquire_run_execution_lease", AsyncMock()),
                patch("server.image_gen_app._create_process_record_best_effort", return_value=None),
                patch("server.image_gen_app.write_app_server_debug_log"),
                patch("server.image_gen_app._run_image_only_resume_job", fake_run_image_resume_job),
                patch("server.image_gen_app._run_create_job") as fresh_create,
                patch("server.image_gen_app.asyncio.create_task", fake_create_task),
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
                patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            ):
                payload = asyncio.run(
                    image_gen_app.api_resume_run(run_id, image_gen_app.ResumeRunRequest(stop_target="p680"))
                )
                self.assertIs(
                    image_gen_app._resume_tasks[payload["jobId"]],
                    scheduled_task,
                )

        self.assertEqual(payload["targetDurationSeconds"], 1200)
        self.assertEqual(payload["resumeMode"], "image_only")
        self.assertEqual(scheduled[0]["run_id"], run_id)
        self.assertIsInstance(
            scheduled[0]["retained_run"],
            image_gen_app._FrontendCreateRunReservation,
        )
        fresh_create.assert_not_called()

    def test_resume_with_strict_p650_and_asset_repair_plan_schedules_canonical_p500_job(
        self,
    ) -> None:
        scheduled: list[dict[str, object]] = []

        async def noop_job():
            return None

        def fake_run_p500_resume_job(job_id: str, **kwargs):
            scheduled.append({"job_id": job_id, **kwargs})
            return noop_job()

        def fake_create_task(coro):
            coro.close()
            return Mock()

        with tempfile.TemporaryDirectory(prefix="toc_resume_asset_repair_") as td:
            root = Path(td)
            run_id = "story_20990101_0004"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 600)
            (run_dir / "state.txt").write_text(
                "runtime.target_video_seconds=600\n---\n",
                encoding="utf-8",
            )
            _write_p680_regeneration_plan(
                run_dir,
                action="regenerate_p500_reference_first",
            )
            acquire_lease = AsyncMock()
            run_image_only = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._current_process_number_for_run",
                    return_value=650,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=RuntimeError("p680 incomplete"),
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    acquire_lease,
                ),
                patch(
                    "server.image_gen_app._create_process_record_best_effort",
                    return_value=None,
                ),
                patch("server.image_gen_app.write_app_server_debug_log"),
                patch(
                    "server.image_gen_app._run_p500_resume_job",
                    fake_run_p500_resume_job,
                ),
                patch(
                    "server.image_gen_app._run_image_only_resume_job",
                    run_image_only,
                ),
                patch("server.image_gen_app.asyncio.create_task", fake_create_task),
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
                patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            ):
                payload = asyncio.run(
                    image_gen_app.api_resume_run(
                        run_id,
                        image_gen_app.ResumeRunRequest(stop_target="p680"),
                    )
                )

        self.assertEqual(payload["resumeMode"], "p500_subprocess")
        self.assertEqual(scheduled[0]["run_id"], run_id)
        self.assertIsInstance(
            scheduled[0]["retained_run"],
            image_gen_app._FrontendCreateRunReservation,
        )
        acquire_lease.assert_awaited_once()
        self.assertIsNotNone(
            acquire_lease.await_args.kwargs["run_descriptor"]
        )
        run_image_only.assert_not_called()

    def test_resume_with_strict_p650_rejects_malformed_asset_plan_before_scheduling(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_bad_asset_plan_") as td:
            root = Path(td)
            run_id = "story_20990101_0005"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 600)
            (run_dir / "state.txt").write_text(
                "runtime.target_video_seconds=600\n---\n",
                encoding="utf-8",
            )
            _write_p680_regeneration_plan(
                run_dir,
                action="regenerate_p500_reference_first",
            )
            report_path = run_dir / "eval_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["stages"]["image"]["details"]["image_regeneration_plan"][0][
                "vector_like_references"
            ] = "assets/characters/hero.png"
            report_path.write_text(
                json.dumps(report) + "\n",
                encoding="utf-8",
            )
            acquire_lease = AsyncMock()
            create_task = Mock()
            run_image_only = Mock()
            run_p500 = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._current_process_number_for_run",
                    return_value=650,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=RuntimeError("p680 incomplete"),
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    acquire_lease,
                ),
                patch(
                    "server.image_gen_app._run_image_only_resume_job",
                    run_image_only,
                ),
                patch("server.image_gen_app._run_p500_resume_job", run_p500),
                patch("server.image_gen_app.asyncio.create_task", create_task),
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
                patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            ):
                with self.assertRaises(image_gen_app.HTTPException) as raised:
                    asyncio.run(
                        image_gen_app.api_resume_run(
                            run_id,
                            image_gen_app.ResumeRunRequest(stop_target="p680"),
                        )
                    )

                self.assertEqual(image_gen_app._create_jobs, {})

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("p500 reference targets", str(raised.exception.detail))
        acquire_lease.assert_awaited_once()
        create_task.assert_not_called()
        run_image_only.assert_not_called()
        run_p500.assert_not_called()

    def test_resume_rejects_strictly_complete_p680_even_when_progress_is_stale(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_complete_") as td:
            root = Path(td)
            run_id = "story_20990101_0001"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 300)
            (run_dir / "state.txt").write_text("slot.p110.status=done\n---\n", encoding="utf-8")
            acquire_lease = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._current_process_number_for_run", return_value=110),
                patch("server.image_gen_app.process_store.get_process_run", return_value=None),
                patch("server.image_gen_app._validate_frontend_create_run") as validate_p680,
                patch("server.image_gen_app._validate_p650_run") as validate_p650,
                patch(
                    "server.image_gen_app._acquire_run_execution_lease",
                    acquire_lease,
                ),
                patch("server.image_gen_app.asyncio.create_task") as create_task,
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
            ):
                with self.assertRaises(image_gen_app.HTTPException) as raised:
                    asyncio.run(
                        image_gen_app.api_resume_run(
                            run_id,
                            image_gen_app.ResumeRunRequest(stop_target="p680"),
                        )
                    )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("p680", str(raised.exception.detail))
        acquire_lease.assert_awaited_once()
        validate_p680.assert_called_once_with(run_id, strict_visual_quality=True)
        validate_p650.assert_not_called()
        create_task.assert_not_called()

    def test_resume_before_p650_schedules_subprocess_job_with_retained_parent_lease(self) -> None:
        scheduled: list[dict[str, object]] = []

        async def noop_job():
            return None

        def fake_run_p500_resume_job(job_id: str, **kwargs):
            scheduled.append({"job_id": job_id, **kwargs})
            return noop_job()

        def fake_create_task(coro):
            coro.close()
            return Mock()

        with tempfile.TemporaryDirectory(prefix="toc_resume_p500_") as td:
            root = Path(td)
            run_id = "story_20990101_0002"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 600)
            (run_dir / "state.txt").write_text("topic=story\n---\n", encoding="utf-8")
            acquire_lease = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._current_process_number_for_run", return_value=430),
                patch("server.image_gen_app.process_store.get_process_run", return_value=None),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=RuntimeError("p680 incomplete"),
                ),
                patch(
                    "server.image_gen_app._validate_p650_run",
                    side_effect=RuntimeError("p650 incomplete"),
                ),
                patch("server.image_gen_app._acquire_run_execution_lease", acquire_lease),
                patch("server.image_gen_app._create_process_record_best_effort", return_value=None),
                patch("server.image_gen_app.write_app_server_debug_log"),
                patch("server.image_gen_app._run_p500_resume_job", fake_run_p500_resume_job),
                patch("server.image_gen_app._run_create_job") as fresh_create,
                patch("server.image_gen_app.asyncio.create_task", fake_create_task),
                patch.dict(image_gen_app._create_jobs, {}, clear=True),
                patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            ):
                payload = asyncio.run(
                    image_gen_app.api_resume_run(
                        run_id,
                        image_gen_app.ResumeRunRequest(stop_target="p680"),
                    )
                )

        self.assertEqual(payload["resumeMode"], "p500_subprocess")
        self.assertEqual(scheduled[0]["run_id"], run_id)
        acquire_lease.assert_awaited_once()
        self.assertIsNotNone(scheduled[0]["retained_run"])
        fresh_create.assert_not_called()

    def test_resume_rejects_an_existing_running_job_for_the_same_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_resume_concurrent_") as td:
            root = Path(td)
            run_id = "story_20990101_0003"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            _write_manifest(run_dir, 300)
            (run_dir / "state.txt").write_text("topic=story\n---\n", encoding="utf-8")
            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app._current_process_number_for_run", return_value=430),
                patch("server.image_gen_app.process_store.get_process_run", return_value=None),
                patch(
                    "server.image_gen_app._validate_frontend_create_run",
                    side_effect=RuntimeError("p680 incomplete"),
                ),
                patch(
                    "server.image_gen_app._validate_p650_run",
                    side_effect=RuntimeError("p650 incomplete"),
                ),
                patch("server.image_gen_app.asyncio.create_task") as create_task,
                patch.dict(
                    image_gen_app._create_jobs,
                    {
                        "existing": {
                            "jobId": "existing",
                            "runId": run_id,
                            "status": "running",
                        }
                    },
                    clear=True,
                ),
            ):
                with self.assertRaises(image_gen_app.HTTPException) as raised:
                    asyncio.run(
                        image_gen_app.api_resume_run(
                            run_id,
                            image_gen_app.ResumeRunRequest(stop_target="p680"),
                        )
                    )

                self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("already active", str(raised.exception.detail))
        create_task.assert_not_called()


class _FakeResumeProcess:
    def __init__(
        self,
        stdout: bytes,
        stderr: bytes = b"",
        returncode: int | None = 0,
        *,
        pid: int = 4321,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = pid
        self.kill = Mock()

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


class _HangingResumeProcess(_FakeResumeProcess):
    def __init__(self) -> None:
        super().__init__(b"", returncode=None, pid=9876)
        self.communicate_started = asyncio.Event()
        self.exit_event = asyncio.Event()
        self.communicate_calls = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        self.communicate_calls += 1
        self.communicate_started.set()
        await self.exit_event.wait()
        self.returncode = -signal.SIGKILL
        return b"", b""


class ResumeSubprocessContractTests(unittest.TestCase):
    def test_dry_run_json_token_is_forwarded_to_exact_apply_command(self) -> None:
        token = "a" * 64
        exact_source = "first line\n\nsecond line\n"
        job_id = "job123"
        checkpoint_id = f"api-{job_id}"
        dry_run = _FakeResumeProcess(
            json.dumps(
                {
                    "checkpoint_id": checkpoint_id,
                    "plan_token": token,
                    "downstream_files": [],
                }
            ).encode("utf-8")
        )
        apply_run = _FakeResumeProcess(b"Run dir: done\n")

        with tempfile.TemporaryDirectory(prefix="toc_resume_subprocess_") as td:
            root = Path(td)
            run_dir = root / "output" / "story"
            run_dir.mkdir(parents=True)
            create_subprocess = AsyncMock(side_effect=[dry_run, apply_run])
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.asyncio.create_subprocess_exec",
                    create_subprocess,
                ),
                patch("server.image_gen_app.write_app_server_debug_log") as debug_log,
                patch("server.image_gen_app.append_state_snapshot") as append_state,
            ):
                result = asyncio.run(
                    image_gen_app._run_p500_resume_subprocess(
                        job_id=job_id,
                        run_dir=run_dir,
                        source=exact_source,
                    )
                )

        base = (
            image_gen_app.sys.executable,
            str(root / "scripts" / "resume-from-p500.py"),
            "--run-dir",
            str(run_dir),
            "--checkpoint-id",
            checkpoint_id,
            "--source",
            exact_source,
        )
        self.assertEqual(
            create_subprocess.await_args_list,
            [
                call(
                    *base,
                    cwd=str(root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                ),
                call(
                    *base,
                    "--plan-token",
                    token,
                    "--apply",
                    "--continue-to",
                    "p680",
                    cwd=str(root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    start_new_session=True,
                ),
            ],
        )
        self.assertEqual(result["checkpointId"], checkpoint_id)
        self.assertEqual(result["planToken"], token)
        debug_log.assert_not_called()
        append_state.assert_not_called()

    def test_malformed_dry_run_token_fails_closed_without_apply(self) -> None:
        job_id = "job456"
        dry_run = _FakeResumeProcess(
            json.dumps(
                {
                    "checkpoint_id": f"api-{job_id}",
                    "plan_token": "not-a-sha256-token",
                }
            ).encode("utf-8")
        )

        with tempfile.TemporaryDirectory(prefix="toc_resume_bad_token_") as td:
            root = Path(td)
            run_dir = root / "output" / "story"
            run_dir.mkdir(parents=True)
            create_subprocess = AsyncMock(return_value=dry_run)
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.asyncio.create_subprocess_exec",
                    create_subprocess,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "plan_token"):
                    asyncio.run(
                        image_gen_app._run_p500_resume_subprocess(
                            job_id=job_id,
                            run_dir=run_dir,
                        )
                    )

        self.assertEqual(create_subprocess.await_count, 1)

    def test_resume_helper_timeout_kills_process_group_and_reaps_direct_child(
        self,
    ) -> None:
        proc = _HangingResumeProcess()
        killpg = Mock(
            side_effect=lambda _pid, sig: (
                proc.exit_event.set() if sig == signal.SIGKILL else None
            )
        )
        with (
            patch(
                "server.image_gen_app.asyncio.create_subprocess_exec",
                AsyncMock(return_value=proc),
            ) as create_subprocess,
            patch(
                "server.image_gen_app.FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS",
                0.01,
            ),
            patch(
                "server.image_gen_app.RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS",
                0.01,
            ),
            patch("server.image_gen_app.os.killpg", killpg),
        ):
            with self.assertRaisesRegex(
                TimeoutError,
                "resume-from-p500 subprocess timed out",
            ):
                asyncio.run(
                    image_gen_app._run_resume_subprocess_command(
                        ["resume-helper", "--apply"]
                    )
                )

        create_subprocess.assert_awaited_once_with(
            "resume-helper",
            "--apply",
            cwd=str(image_gen_app.ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self.assertEqual(
            [
                invoked.args[1]
                for invoked in killpg.call_args_list
                if invoked.args[1] != 0
            ],
            [signal.SIGTERM, signal.SIGKILL],
        )
        self.assertIn(call(proc.pid, 0), killpg.call_args_list)
        self.assertEqual(proc.communicate_calls, 1)
        proc.kill.assert_not_called()

    def test_resume_helper_task_cancellation_kills_process_group_and_reaps_direct_child(
        self,
    ) -> None:
        proc = _HangingResumeProcess()
        killpg = Mock(
            side_effect=lambda _pid, sig: (
                proc.exit_event.set() if sig == signal.SIGKILL else None
            )
        )

        async def run_and_cancel() -> None:
            task = asyncio.create_task(
                image_gen_app._run_resume_subprocess_command(
                    ["resume-helper", "--continue-to", "p680"]
                )
            )
            await proc.communicate_started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with (
            patch(
                "server.image_gen_app.asyncio.create_subprocess_exec",
                AsyncMock(return_value=proc),
            ),
            patch(
                "server.image_gen_app.RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS",
                0.01,
            ),
            patch("server.image_gen_app.os.killpg", killpg),
        ):
            asyncio.run(run_and_cancel())

        self.assertEqual(
            [
                invoked.args[1]
                for invoked in killpg.call_args_list
                if invoked.args[1] != 0
            ],
            [signal.SIGTERM, signal.SIGKILL],
        )
        self.assertIn(call(proc.pid, 0), killpg.call_args_list)
        self.assertEqual(proc.communicate_calls, 1)
        proc.kill.assert_not_called()

    def test_resume_helper_timeout_stops_a_term_ignoring_grandchild(self) -> None:
        parent_code = """
import subprocess
import sys
import time

child_code = '''
import signal
import sys
import time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(sys.argv[1], "ab", buffering=0) as heartbeat:
    while True:
        heartbeat.write(b"x")
        time.sleep(0.02)
'''
child = subprocess.Popen(
    [sys.executable, "-c", child_code, sys.argv[2]],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
with open(sys.argv[1], "w", encoding="utf-8") as pid_file:
    pid_file.write(str(child.pid))
while True:
    time.sleep(1)
"""
        with tempfile.TemporaryDirectory(prefix="toc_resume_process_group_") as td:
            root = Path(td)
            pid_path = root / "grandchild.pid"
            heartbeat_path = root / "heartbeat.bin"
            with (
                patch(
                    "server.image_gen_app.FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS",
                    0.5,
                ),
                patch(
                    "server.image_gen_app.RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS",
                    0.1,
                ),
            ):
                with self.assertRaisesRegex(
                    TimeoutError,
                    "resume-from-p500 subprocess timed out",
                ):
                    asyncio.run(
                        image_gen_app._run_resume_subprocess_command(
                            [
                                sys.executable,
                                "-c",
                                parent_code,
                                str(pid_path),
                                str(heartbeat_path),
                            ]
                        )
                    )

            self.assertTrue(pid_path.is_file())
            grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
            heartbeat_size = heartbeat_path.stat().st_size
            time.sleep(0.15)
            self.assertEqual(heartbeat_path.stat().st_size, heartbeat_size)
            with self.assertRaises(ProcessLookupError):
                os.kill(grandchild_pid, 0)

    def test_shutdown_cancels_and_awaits_tracked_resume_tasks(self) -> None:
        started = asyncio.Event()
        finalized = asyncio.Event()

        async def resume_worker() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finalized.set()

        async def run_case() -> None:
            task = asyncio.create_task(resume_worker())
            image_gen_app._resume_tasks["resume-job"] = task
            await started.wait()
            await image_gen_app.shutdown_codex_client()
            self.assertTrue(task.done())
            self.assertTrue(task.cancelled())

        with (
            patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            patch.dict(image_gen_app._bulk_generation_tasks, {}, clear=True),
            patch.object(image_gen_app, "_codex_client", None),
        ):
            asyncio.run(run_case())
            self.assertTrue(finalized.is_set())
            self.assertEqual(image_gen_app._resume_tasks, {})


class ResumeJobWorkerTests(unittest.TestCase):
    def test_p500_worker_forwards_refetched_legacy_normal_source_without_logging_it(
        self,
    ) -> None:
        job_id = "p500-legacy-source-job"
        exact_source = "first line\n\nsecond line\n"
        with tempfile.TemporaryDirectory(prefix="toc_resume_legacy_source_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=normal\n---\n",
                encoding="utf-8",
            )
            run_subprocess = AsyncMock(
                return_value={
                    "checkpointId": "api-p500-legacy-source-job",
                    "planToken": "a" * 64,
                    "stdout": "done",
                }
            )
            debug_log = Mock()
            record = SimpleNamespace(
                create_mode=image_gen_app.CREATE_MODE_NORMAL,
                source=exact_source,
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    run_subprocess,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=record,
                ),
                patch("server.image_gen_app._validate_current_p680_run"),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch(
                    "server.image_gen_app.write_app_server_debug_log",
                    debug_log,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        run_subprocess.assert_awaited_once_with(
            job_id=job_id,
            run_dir=run_dir.resolve(),
            source=exact_source,
        )
        self.assertNotIn(
            exact_source,
            "\n".join(str(entry) for entry in debug_log.call_args_list),
        )

    def test_p500_worker_rejects_legacy_resume_without_record_source(self) -> None:
        job_id = "p500-missing-source-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_missing_source_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=normal\n---\n",
                encoding="utf-8",
            )
            run_subprocess = AsyncMock()
            set_job = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    run_subprocess,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", set_job),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        run_subprocess.assert_not_awaited()
        self.assertEqual(set_job.await_args_list[-1].args[1]["status"], "failed")
        self.assertIn(
            "exact source",
            set_job.await_args_list[-1].args[1]["error"],
        )

    def test_p500_worker_rejects_legacy_world_walk_record_path_as_source(
        self,
    ) -> None:
        job_id = "p500-legacy-world-walk-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_legacy_world_") as td:
            root = Path(td)
            run_id = "walk"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=normal\n"
                "immersive.experience=world_walk\n"
                "---\n",
                encoding="utf-8",
            )
            run_subprocess = AsyncMock()
            record = SimpleNamespace(
                create_mode=image_gen_app.CREATE_MODE_WORLD_WALK,
                source="output/source_run",
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    run_subprocess,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=record,
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        run_subprocess.assert_not_awaited()

    def test_p500_worker_allows_world_walk_with_canonical_create_input(
        self,
    ) -> None:
        job_id = "p500-canonical-world-walk-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_canonical_world_") as td:
            root = Path(td)
            run_id = "walk"
            run_dir = root / "output" / run_id
            create_input = run_dir / "logs/orchestration/create_input.json"
            create_input.parent.mkdir(parents=True)
            create_input.write_text("{}\n", encoding="utf-8")
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=world_walk\n"
                "immersive.experience=world_walk\n"
                "---\n",
                encoding="utf-8",
            )
            run_subprocess = AsyncMock(
                return_value={
                    "checkpointId": "api-p500-canonical-world-walk-job",
                    "planToken": "a" * 64,
                    "stdout": "done",
                }
            )
            record = SimpleNamespace(
                create_mode=image_gen_app.CREATE_MODE_WORLD_WALK,
                source="output/source_run",
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    run_subprocess,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=record,
                ),
                patch("server.image_gen_app._validate_current_p680_run"),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        run_subprocess.assert_awaited_once_with(
            job_id=job_id,
            run_dir=run_dir.resolve(),
            source=None,
        )

    def test_p500_worker_re_resolves_create_mode_after_subprocess_before_strict_validation(
        self,
    ) -> None:
        job_id = "p500-mode-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_p500_mode_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=scene_storyboard\n---\n",
                encoding="utf-8",
            )
            create_input = run_dir / "logs/orchestration/create_input.json"
            create_input.parent.mkdir(parents=True)
            create_input.write_text("{}\n", encoding="utf-8")
            validate_p680 = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    AsyncMock(
                        return_value={
                            "checkpointId": "api-p500-mode-job",
                            "planToken": "a" * 64,
                            "stdout": "done",
                        }
                    ),
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch(
                    "server.image_gen_app._validate_current_p680_run",
                    validate_p680,
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        validate_p680.assert_called_once_with(
            run_id,
            create_mode=image_gen_app.CREATE_MODE_SCENE_STORYBOARD,
        )

    def test_image_only_worker_re_resolves_create_mode_after_lease_acquisition(
        self,
    ) -> None:
        job_id = "image-mode-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_mode_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=scene_storyboard\n---\n",
                encoding="utf-8",
            )
            events: list[str] = []
            finalize_storyboard = Mock(
                side_effect=lambda _run_id: events.append(
                    "storyboard_finalizer"
                )
            )
            validate_p680 = Mock(
                side_effect=lambda *_args, **_kwargs: events.append(
                    "final_validation"
                )
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    return_value={"deletedCount": 0, "preservedCount": 0},
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    AsyncMock(
                        side_effect=lambda *_args, **_kwargs: events.append(
                            "generate_images"
                        )
                    ),
                ),
                patch(
                    "server.image_gen_app._finalize_scene_storyboard_p680",
                    finalize_storyboard,
                ),
                patch(
                    "server.image_gen_app._validate_current_p680_run",
                    validate_p680,
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app._release_run_execution_lease", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_image_only_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        finalize_storyboard.assert_called_once_with(run_id)
        validate_p680.assert_called_once_with(
            run_id,
            create_mode=image_gen_app.CREATE_MODE_SCENE_STORYBOARD,
        )
        self.assertEqual(
            events,
            [
                "generate_images",
                "storyboard_finalizer",
                "final_validation",
            ],
        )

    def test_image_only_worker_uses_current_scene_helper_and_releases_reserved_lease(self) -> None:
        job_id = "image-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_image_worker_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text("slot.p650.status=done\n---\n", encoding="utf-8")
            generate_scenes = AsyncMock()
            release_lease = AsyncMock()
            validate_p650 = Mock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    return_value={
                        "deletedCount": 1,
                        "preservedCount": 2,
                    },
                ),
                patch(
                    "server.image_gen_app._validate_p650_run",
                    validate_p650,
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    generate_scenes,
                ),
                patch("server.image_gen_app._validate_current_p680_run"),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app._acquire_run_execution_lease", AsyncMock()) as acquire_lease,
                patch("server.image_gen_app._release_run_execution_lease", release_lease),
                patch("server.image_gen_app._run_create_job") as fresh_create,
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_image_only_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        acquire_lease.assert_not_awaited()
        validate_p650.assert_called_once_with(run_id)
        generate_scenes.assert_awaited_once_with(
            job_id,
            run_id=run_id,
            run_dir=run_dir.resolve(),
            scene_revision_lock_held=True,
        )
        fresh_create.assert_not_called()
        release_lease.assert_awaited_once_with(job_id)

    def test_image_only_worker_revalidates_p650_before_deleting_outputs(self) -> None:
        job_id = "image-job"
        calls: list[str] = []
        with tempfile.TemporaryDirectory(prefix="toc_resume_image_revalidate_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)

            def validate_p650(_run_id: str) -> None:
                calls.append("validate")

            def delete_outputs(_run_dir: Path) -> dict[str, int]:
                calls.append("delete")
                return {"deletedCount": 0, "preservedCount": 0}

            async def generate_scenes(*_args, **_kwargs) -> None:
                calls.append("generate")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch("server.image_gen_app._validate_p650_run", validate_p650),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    delete_outputs,
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    generate_scenes,
                ),
                patch("server.image_gen_app._validate_current_p680_run"),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app._release_run_execution_lease", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_image_only_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        self.assertEqual(calls[:3], ["validate", "delete", "generate"])

    def test_image_only_worker_holds_request_revision_locks_from_delete_through_handoff(
        self,
    ) -> None:
        job_id = "image-revision-lock-job"
        delete_started = threading.Event()
        allow_delete_to_finish = threading.Event()

        def slow_delete(_run_dir: Path) -> dict[str, int]:
            delete_started.set()
            if not allow_delete_to_finish.wait(timeout=2):
                raise TimeoutError("test did not release deletion thread")
            return {"deletedCount": 0, "preservedCount": 0}

        async def run_case(run_dir: Path, run_id: str) -> bool:
            mutation_entered = asyncio.Event()

            async def mutate_current_requests() -> None:
                async with image_gen_app._serialized_run_write(
                    run_dir,
                    "run_artifacts",
                ):
                    async with image_gen_app._serialized_run_write(
                        run_dir,
                        "asset_request_revision",
                    ):
                        async with image_gen_app._serialized_run_write(
                            run_dir,
                            "scene_request_revision",
                        ):
                            mutation_entered.set()

            worker = asyncio.create_task(
                image_gen_app._run_image_only_resume_job(
                    job_id,
                    run_id=run_id,
                    create_mode=image_gen_app.CREATE_MODE_NORMAL,
                )
            )
            started = await asyncio.to_thread(delete_started.wait, 1)
            self.assertTrue(started)
            mutation = asyncio.create_task(mutate_current_requests())
            await asyncio.sleep(0.05)
            entered_before_delete_finished = mutation_entered.is_set()
            allow_delete_to_finish.set()
            await worker
            await mutation
            return entered_before_delete_finished

        with tempfile.TemporaryDirectory(prefix="toc_resume_revision_lock_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "slot.p650.status=done\n---\n",
                encoding="utf-8",
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_write_locks,
                    {},
                    clear=True,
                ),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    slow_delete,
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    AsyncMock(),
                ),
                patch("server.image_gen_app._validate_current_p680_run"),
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    AsyncMock(),
                ),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    AsyncMock(),
                ),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                entered_early = asyncio.run(run_case(run_dir, run_id))

        self.assertFalse(entered_early)

    def test_image_only_worker_rechecks_changed_plan_and_requires_canonical_p500_before_delete(
        self,
    ) -> None:
        job_id = "image-plan-changed-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_plan_changed_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "slot.p650.status=done\n---\n",
                encoding="utf-8",
            )
            _write_p680_regeneration_plan(
                run_dir,
                action="regenerate_p500_reference_first",
            )
            delete_outputs = Mock()
            generate_scenes = AsyncMock()
            set_job = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    delete_outputs,
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    generate_scenes,
                ),
                patch(
                    "server.image_gen_app._sync_process_current_process",
                    AsyncMock(),
                ),
                patch("server.image_gen_app._set_create_job", set_job),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    AsyncMock(),
                ),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_image_only_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

        delete_outputs.assert_not_called()
        generate_scenes.assert_not_awaited()
        failure = set_job.await_args_list[-1].args[1]
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(failure["errorCode"], "canonical_p500_required")
        self.assertIn("canonical p500", failure["error"].lower())

    def test_image_only_worker_waits_for_delete_thread_before_releasing_lease_on_cancel(self) -> None:
        job_id = "image-job"
        delete_started = threading.Event()
        allow_delete_to_finish = threading.Event()
        release_lease = AsyncMock()

        def slow_delete(_run_dir: Path) -> dict[str, int]:
            delete_started.set()
            if not allow_delete_to_finish.wait(timeout=2):
                raise TimeoutError("test did not release deletion thread")
            return {"deletedCount": 0, "preservedCount": 0}

        async def run_case(root: Path, run_id: str) -> None:
            task = asyncio.create_task(
                image_gen_app._run_image_only_resume_job(
                    job_id,
                    run_id=run_id,
                    create_mode=image_gen_app.CREATE_MODE_NORMAL,
                )
            )
            started = await asyncio.to_thread(delete_started.wait, 1)
            self.assertTrue(started)
            task.cancel()
            await asyncio.sleep(0.05)
            release_lease.assert_not_awaited()
            allow_delete_to_finish.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with tempfile.TemporaryDirectory(prefix="toc_resume_image_cancel_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    slow_delete,
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    AsyncMock(),
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    release_lease,
                ),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(run_case(root, run_id))

        release_lease.assert_awaited_once_with(job_id)

    def test_image_only_worker_waits_for_storyboard_finalizer_before_releasing_lease_on_cancel(
        self,
    ) -> None:
        job_id = "storyboard-image-job"
        finalizer_started = threading.Event()
        allow_finalizer_to_finish = threading.Event()
        release_lease = AsyncMock()

        def slow_finalize(_run_id: str) -> dict[str, bool]:
            finalizer_started.set()
            if not allow_finalizer_to_finish.wait(timeout=2):
                raise TimeoutError("test did not release storyboard finalizer thread")
            return {"alreadyCurrent": False}

        async def run_case(run_id: str) -> None:
            task = asyncio.create_task(
                image_gen_app._run_image_only_resume_job(
                    job_id,
                    run_id=run_id,
                    create_mode=image_gen_app.CREATE_MODE_SCENE_STORYBOARD,
                )
            )
            started = await asyncio.to_thread(finalizer_started.wait, 1)
            self.assertTrue(started)
            task.cancel()
            await asyncio.sleep(0.05)
            release_lease.assert_not_awaited()
            allow_finalizer_to_finish.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with tempfile.TemporaryDirectory(
            prefix="toc_resume_storyboard_cancel_"
        ) as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=scene_storyboard\n---\n",
                encoding="utf-8",
            )
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch(
                    "server.image_gen_app.process_store.get_process_run",
                    return_value=None,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._delete_existing_images_for_image_resume",
                    return_value={"deletedCount": 0, "preservedCount": 0},
                ),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._finalize_scene_storyboard_p680",
                    slow_finalize,
                ),
                patch(
                    "server.image_gen_app._release_run_execution_lease",
                    release_lease,
                ),
                patch("server.image_gen_app._set_create_job", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(run_case(run_id))

        release_lease.assert_awaited_once_with(job_id)

    def test_image_only_worker_blocks_provider_when_request_output_is_symlink(self) -> None:
        job_id = "image-job"
        with tempfile.TemporaryDirectory(prefix="toc_resume_image_symlink_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            upload = run_dir / "assets/uploads/user.png"
            output = run_dir / "assets/scenes/cut.png"
            safe_output = run_dir / "assets/scenes/safe.png"
            upload.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            upload.write_bytes(b"user-upload")
            output.symlink_to(upload)
            safe_output.write_bytes(b"safe-generated-image")
            (run_dir / "image_generation_requests.md").write_text(
                """# Image Generation Requests

## safe

- output: `assets/scenes/safe.png`
- references: `[]`

```text
safe
```

## cut

- output: `assets/scenes/cut.png`
- references: `[]`

```text
cut
```
""",
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps(
                    {
                        "run_dir": str(run_dir.resolve()),
                        "stage_target": "p680",
                        "stages": {
                            "image": {
                                "passed": False,
                                "details": {
                                    "image_regeneration_plan": [
                                        {
                                            "output": "assets/scenes/safe.png",
                                            "action": "regenerate_p600_scene",
                                        },
                                        {
                                            "output": "assets/scenes/cut.png",
                                            "action": "regenerate_p600_scene",
                                        }
                                    ]
                                },
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            generate_scenes = AsyncMock()
            set_job = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {job_id: object()},
                    clear=True,
                ),
                patch("server.image_gen_app._validate_p650_run"),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    generate_scenes,
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", set_job),
                patch("server.image_gen_app._release_run_execution_lease", AsyncMock()),
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_image_only_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )

            self.assertEqual(upload.read_bytes(), b"user-upload")
            self.assertEqual(safe_output.read_bytes(), b"safe-generated-image")
            self.assertTrue(output.is_symlink())

        generate_scenes.assert_not_awaited()
        self.assertEqual(set_job.await_args_list[-1].args[1]["status"], "failed")

    def test_p500_worker_preserves_subprocess_failure_state_and_never_owns_parent_lease(self) -> None:
        job_id = "p500-job"
        original_state = (
            "runtime.resume.p500.checkpoint=logs/resume/p500/api-p500-job\n"
            "runtime.resume.p500.status=prepared\n"
            "runtime.stage=semantic_review_failed_before_media_generation\n"
            "---\n"
        )
        with tempfile.TemporaryDirectory(prefix="toc_resume_p500_worker_") as td:
            root = Path(td)
            run_id = "story"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            state_path = run_dir / "state.txt"
            state_path.write_text(original_state, encoding="utf-8")
            set_job = AsyncMock()
            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._run_p500_resume_subprocess",
                    AsyncMock(side_effect=RuntimeError("semantic resume failed")),
                ),
                patch("server.image_gen_app._sync_process_current_process", AsyncMock()),
                patch("server.image_gen_app._set_create_job", set_job),
                patch("server.image_gen_app._acquire_run_execution_lease", AsyncMock()) as acquire_lease,
                patch("server.image_gen_app._release_run_execution_lease", AsyncMock()) as release_lease,
                patch("server.image_gen_app.append_state_snapshot") as append_state,
                patch("server.image_gen_app.write_app_server_debug_log"),
            ):
                asyncio.run(
                    image_gen_app._run_p500_resume_job(
                        job_id,
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )
            final_state = state_path.read_text(encoding="utf-8")

        self.assertEqual(final_state, original_state)
        self.assertEqual(set_job.await_args_list[-1].args[1]["status"], "failed")
        append_state.assert_not_called()
        acquire_lease.assert_not_awaited()
        release_lease.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
