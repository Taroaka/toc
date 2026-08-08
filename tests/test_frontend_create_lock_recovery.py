from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from server import image_gen_app


class FrontendCreateLockRecoveryTests(unittest.TestCase):
    def test_create_job_binding_rejects_reserved_run_replacement_before_body(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "job-binding_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            original = root / "original-run"
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("must survive\n", encoding="utf-8")
            run_dir.rename(original)
            run_dir.symlink_to(outside, target_is_directory=True)
            job_updates: list[dict[str, object]] = []

            async def record_job(_job_id, update, **_kwargs):
                job_updates.append(dict(update))

            inner = AsyncMock()
            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_run_create_job_bound",
                    inner,
                ),
                patch.object(
                    image_gen_app,
                    "_set_create_job",
                    side_effect=record_job,
                ),
                patch.object(
                    image_gen_app,
                    "_release_run_execution_lease",
                    new=AsyncMock(),
                ),
            ):
                asyncio.run(
                    image_gen_app._run_create_job(
                        "job-1",
                        title="binding",
                        source="binding",
                        run_id=run_id,
                        expected_run_identity=expected_identity,
                    )
                )

            inner.assert_not_awaited()
            self.assertEqual(
                job_updates[-1]["errorCode"],
                "RunRootBindingError",
            )
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "must survive\n",
            )
            self.assertFalse((outside / "logs").exists())

    @staticmethod
    async def _async_noop(*_args, **_kwargs) -> None:
        return None

    @staticmethod
    def _directory_identity(path: Path) -> tuple[int, int]:
        entry = os.stat(path, follow_symlinks=False)
        return entry.st_dev, entry.st_ino

    def test_cli_helper_ignores_inert_legacy_marker_without_removing_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "stale-marker_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            marker = run_dir / ".toc_frontend_create.lock"
            marker.write_text("pid=999999999\n", encoding="utf-8")
            subprocess_started = False

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"ok\n", b""

            async def fake_create_subprocess_exec(*_args, **_kwargs):
                nonlocal subprocess_started
                subprocess_started = True
                return FakeProcess()

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.asyncio,
                    "create_subprocess_exec",
                    fake_create_subprocess_exec,
                ),
            ):
                stdout = asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="stale marker recovery",
                        run_id=run_id,
                    )
                )

            self.assertTrue(subprocess_started)
            self.assertEqual(stdout, "ok")
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "pid=999999999\n",
            )

    def test_cli_helper_rejects_live_directory_lock_before_spawning(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "live-lock_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            marker = run_dir / ".toc_frontend_create.lock"
            marker.write_text("pid=999999999\n", encoding="utf-8")
            subprocess_started = False
            owner_descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            fcntl.flock(
                owner_descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            async def fake_create_subprocess_exec(*_args, **_kwargs):
                nonlocal subprocess_started
                subprocess_started = True
                self.fail("live lock must be rejected before subprocess spawn")

            try:
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.object(
                        image_gen_app.asyncio,
                        "create_subprocess_exec",
                        fake_create_subprocess_exec,
                    ),
                    self.assertRaisesRegex(
                        RuntimeError,
                        "another frontend-create process owns this run",
                    ),
                ):
                    asyncio.run(
                        image_gen_app._run_toc_immersive_frontend_cli_helper(
                            topic="live lock",
                            run_id=run_id,
                        )
                    )
            finally:
                fcntl.flock(owner_descriptor, fcntl.LOCK_UN)
                os.close(owner_descriptor)

            self.assertFalse(subprocess_started)
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "pid=999999999\n",
            )

    def test_cli_helper_classifies_runner_lock_race_without_writing_logs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "runner-lock-race_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)

            class FakeProcess:
                returncode = 1

                async def communicate(self):
                    return (
                        b"",
                        (
                            "another frontend-create process owns this run: "
                            f"{run_dir}\n"
                        ).encode(),
                    )

            async def fake_create_subprocess_exec(*_args, **_kwargs):
                return FakeProcess()

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.asyncio,
                    "create_subprocess_exec",
                    fake_create_subprocess_exec,
                ),
                self.assertRaises(
                    image_gen_app.FrontendCreateLockOwnedError,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="runner lock race",
                        run_id=run_id,
                    )
                )

            self.assertFalse(
                (run_dir / "logs" / "frontend_create_cli").exists()
            )

    def test_cli_helper_binds_child_to_probed_run_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "identity-bound_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected = run_dir.stat()
            captured: tuple[object, ...] = ()

            class FakeProcess:
                returncode = 0

                async def communicate(self):
                    return b"ok\n", b""

            async def fake_create_subprocess_exec(*args, **_kwargs):
                nonlocal captured
                captured = args
                return FakeProcess()

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.asyncio,
                    "create_subprocess_exec",
                    fake_create_subprocess_exec,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="identity bound",
                        run_id=run_id,
                    )
                )

            device_index = captured.index("--expected-run-device")
            inode_index = captured.index("--expected-run-inode")
            self.assertEqual(
                captured[device_index + 1],
                str(expected.st_dev),
            )
            self.assertEqual(
                captured[inode_index + 1],
                str(expected.st_ino),
            )

    def test_cli_helper_identity_failure_never_writes_replacement_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "identity-race_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            displaced = root / "displaced-run"

            class FakeProcess:
                returncode = 1

                async def communicate(self):
                    run_dir.rename(displaced)
                    run_dir.mkdir()
                    (run_dir / "sentinel.txt").write_text(
                        "replacement\n",
                        encoding="utf-8",
                    )
                    return (
                        b"",
                        b"destination run identity changed after server reservation\n",
                    )

            async def fake_create_subprocess_exec(*_args, **_kwargs):
                return FakeProcess()

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.asyncio,
                    "create_subprocess_exec",
                    fake_create_subprocess_exec,
                ),
                self.assertRaises(
                    image_gen_app.FrontendCreateLockError,
                ),
            ):
                asyncio.run(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="identity race",
                        run_id=run_id,
                    )
                )

            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                ["sentinel.txt"],
            )
            self.assertFalse((run_dir / "logs").exists())

    def test_cli_helper_cancellation_reaps_child_before_returning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cancel-child_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            communicate_started: asyncio.Event | None = None
            cleanup_finished = False

            class FakeProcess:
                pid = 424242
                returncode = None

                async def communicate(self):
                    assert communicate_started is not None
                    communicate_started.set()
                    await asyncio.Event().wait()
                    raise AssertionError("unreachable")

            async def fake_create_subprocess_exec(*_args, **_kwargs):
                return FakeProcess()

            async def fake_cleanup(_proc, communicate_task):
                nonlocal cleanup_finished
                communicate_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await communicate_task
                cleanup_finished = True
                return b"", b""

            async def run_case() -> None:
                nonlocal communicate_started
                communicate_started = asyncio.Event()
                task = asyncio.create_task(
                    image_gen_app._run_toc_immersive_frontend_cli_helper(
                        topic="cancel child",
                        run_id=run_id,
                    )
                )
                await communicate_started.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.asyncio,
                    "create_subprocess_exec",
                    fake_create_subprocess_exec,
                ),
                patch.object(
                    image_gen_app,
                    "_await_resume_process_cleanup",
                    side_effect=fake_cleanup,
                ) as cleanup,
            ):
                asyncio.run(run_case())

            cleanup.assert_awaited_once()
            self.assertTrue(cleanup_finished)

    def test_frontend_runner_rejects_reserved_run_inode_replacement(
        self,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = repo_root / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_identity_binding_",
            dir=output_root,
        ) as td:
            parent = Path(td)
            run_dir = parent / "run"
            run_dir.mkdir()
            expected = run_dir.stat()
            original_run = parent / "run-original"
            run_dir.rename(original_run)
            run_dir.mkdir()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        repo_root
                        / "scripts"
                        / "toc-immersive-frontend-run.py"
                    ),
                    "--topic",
                    "identity replacement",
                    "--source",
                    "identity replacement",
                    "--run-dir",
                    str(run_dir),
                    "--materialize-only",
                    "--skip-validation",
                    "--expected-run-device",
                    str(expected.st_dev),
                    "--expected-run-inode",
                    str(expected.st_ino),
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "destination run identity changed after server reservation",
                completed.stderr,
            )
            self.assertEqual(list(run_dir.iterdir()), [])
            self.assertEqual(list(original_run.iterdir()), [])

    def test_frontend_runner_expected_identity_never_recreates_missing_run(
        self,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        output_root = repo_root / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="frontend_missing_identity_",
            dir=output_root,
        ) as td:
            run_dir = Path(td) / "missing-run"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        repo_root
                        / "scripts"
                        / "toc-immersive-frontend-run.py"
                    ),
                    "--topic",
                    "missing reservation",
                    "--source",
                    "missing reservation",
                    "--run-dir",
                    str(run_dir),
                    "--materialize-only",
                    "--skip-validation",
                    "--expected-run-device",
                    "1",
                    "--expected-run-inode",
                    "1",
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(run_dir.exists())

    def test_directory_lock_probe_releases_its_advisory_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            image_gen_app._probe_frontend_create_directory_lock(run_dir)

            descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                fcntl.flock(
                    descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def test_directory_lock_probe_rejects_path_replacement_before_locking(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            run_dir = parent / "run"
            run_dir.mkdir()
            original_run = parent / "run-original"
            original_open = os.open
            replaced = False

            def replace_before_open(path, flags, *args, **kwargs):
                nonlocal replaced
                if not replaced:
                    replaced = True
                    run_dir.rename(original_run)
                    run_dir.mkdir()
                return original_open(path, flags, *args, **kwargs)

            with (
                patch.object(
                    image_gen_app.os,
                    "open",
                    side_effect=replace_before_open,
                ),
                self.assertRaisesRegex(
                    RuntimeError,
                    "run directory identity changed",
                ),
            ):
                image_gen_app._probe_frontend_create_directory_lock(run_dir)

            self.assertTrue(original_run.is_dir())
            self.assertTrue(run_dir.is_dir())

    def test_atomic_reservation_never_adopts_post_publish_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            original_rename = (
                image_gen_app._frontend_create_rename_noreplace
            )
            displaced_name = "displaced-reservation"

            def replace_after_publish(**kwargs):
                original_rename(**kwargs)
                destination_name = kwargs["destination_name"]
                parent_descriptor = kwargs[
                    "destination_parent_descriptor"
                ]
                os.rename(
                    destination_name,
                    displaced_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                os.mkdir(destination_name, dir_fd=parent_descriptor)
                replacement_descriptor = os.open(
                    destination_name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=parent_descriptor,
                )
                try:
                    sentinel_descriptor = os.open(
                        "sentinel.txt",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=replacement_descriptor,
                    )
                    try:
                        os.write(sentinel_descriptor, b"replacement\n")
                    finally:
                        os.close(sentinel_descriptor)
                finally:
                    os.close(replacement_descriptor)

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_frontend_create_rename_noreplace",
                    side_effect=replace_after_publish,
                ),
                self.assertRaisesRegex(
                    image_gen_app.FrontendCreateLockError,
                    "published run identity changed",
                ),
            ):
                image_gen_app._reserve_frontend_create_run_dir(
                    "replacement race"
                )

            public_runs = [
                path
                for path in output_dir.iterdir()
                if not path.name.startswith(".")
                and path.name != displaced_name
            ]
            self.assertEqual(len(public_runs), 1)
            self.assertEqual(
                (public_runs[0] / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "replacement\n",
            )
            self.assertTrue((output_dir / displaced_name).is_dir())

    def test_atomic_reservation_returns_original_identity_and_cleans_stage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(image_gen_app, "ROOT", root):
                (
                    run_id,
                    run_dir,
                    expected_identity,
                ) = image_gen_app._reserve_frontend_create_run_dir(
                    "atomic reservation"
                )

            self.assertEqual(run_dir.name, run_id)
            self.assertEqual(
                self._directory_identity(run_dir),
                expected_identity,
            )
            self.assertEqual(
                list(
                    (root / "output").glob(
                        ".toc-reservation-*.private"
                    )
                ),
                [],
            )

    def test_atomic_reservation_retains_descriptors_until_explicit_close(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(image_gen_app, "ROOT", root):
                reservation = image_gen_app._reserve_frontend_create_run_dir(
                    "retained descriptor"
                )
                try:
                    self.assertEqual(
                        self._directory_identity(reservation.run_dir),
                        reservation.identity,
                    )
                    self.assertEqual(
                        self._directory_identity(reservation.run_dir),
                        image_gen_app._frontend_create_entry_identity(
                            os.fstat(reservation.descriptor)
                        ),
                    )
                    os.fstat(reservation.parent_descriptor)
                finally:
                    reservation.close()

            with self.assertRaises(OSError):
                os.fstat(reservation.descriptor)
            with self.assertRaises(OSError):
                os.fstat(reservation.parent_descriptor)

    def test_atomic_reservation_bounds_multibyte_public_name_by_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(image_gen_app, "ROOT", root):
                reservation = image_gen_app._reserve_frontend_create_run_dir(
                    "界" * 500
                )
                try:
                    name_max = os.pathconf(
                        root / "output",
                        "PC_NAME_MAX",
                    )
                    self.assertLessEqual(
                        len(os.fsencode(reservation.run_id)),
                        name_max,
                    )
                finally:
                    reservation.close()

    def test_reservation_publication_error_quarantines_private_stage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original_rename = (
                image_gen_app._frontend_create_rename_noreplace
            )

            def fail_publication(**kwargs):
                if kwargs["source_name"].startswith(
                    ".toc-reservation-"
                ) and not kwargs["destination_name"].startswith(
                    ".toc-reservation-failed-"
                ):
                    raise OSError(
                        getattr(os, "ENAMETOOLONG", 63),
                        "name too long",
                    )
                return original_rename(**kwargs)

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_frontend_create_rename_noreplace",
                    side_effect=fail_publication,
                ),
                self.assertRaises(image_gen_app.FrontendCreateLockError),
            ):
                image_gen_app._reserve_frontend_create_run_dir(
                    "publication failure"
                )

            self.assertEqual(
                list(
                    (root / "output").glob(
                        ".toc-reservation-*.private"
                    )
                ),
                [],
            )

    def test_reservation_post_publication_failure_quarantines_owned_inode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.os,
                    "fchmod",
                    side_effect=OSError("injected fchmod failure"),
                ),
                self.assertRaises(image_gen_app.FrontendCreateLockError),
            ):
                image_gen_app._reserve_frontend_create_run_dir(
                    "post publication failure"
                )

            output_dir = root / "output"
            self.assertEqual(
                [
                    path
                    for path in output_dir.iterdir()
                    if not path.name.startswith(".")
                ],
                [],
            )
            self.assertEqual(
                list(output_dir.glob(".toc-reservation-*.private")),
                [],
            )
            self.assertEqual(
                len(
                    list(
                        output_dir.glob(
                            ".toc-reservation-failed-*.quarantine"
                        )
                    )
                ),
                1,
            )

    def _assert_endpoint_propagates_reserved_identity(
        self,
        *,
        endpoint,
        request,
        scheduled_job_name: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "reserved_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            reservation = image_gen_app._FrontendCreateRunReservation(
                run_id=run_id,
                run_dir=run_dir,
                identity=expected_identity,
                descriptor=os.open(
                    run_dir,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                ),
                parent_descriptor=os.open(
                    run_dir.parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                ),
            )
            scheduled_token = object()
            scheduled_job = MagicMock(return_value=scheduled_token)

            try:
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.dict(image_gen_app._create_jobs, {}, clear=True),
                    patch.dict(image_gen_app._create_tasks, {}, clear=True),
                    patch.object(
                        image_gen_app,
                        "_reserve_frontend_create_run_dir",
                        return_value=reservation,
                    ),
                    patch.object(
                        image_gen_app,
                        "_probe_frontend_create_directory_lock",
                        side_effect=AssertionError(
                            "endpoint must not re-probe a reserved pathname"
                        ),
                    ),
                    patch.object(
                        image_gen_app,
                        "_require_world_walk_source_run",
                        return_value=root / "output" / "source",
                    ),
                    patch.object(
                        image_gen_app,
                        "_acquire_run_execution_lease",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_create_process_record_best_effort",
                        return_value=None,
                    ),
                    patch.object(
                        image_gen_app,
                        "write_app_server_debug_log",
                    ),
                    patch.object(
                        image_gen_app.asyncio,
                        "create_task",
                    ) as create_task,
                    patch.object(
                        image_gen_app,
                        scheduled_job_name,
                        new=scheduled_job,
                    ),
                ):
                    result = asyncio.run(endpoint(request))
            finally:
                reservation.close()

            self.assertEqual(result["runId"], run_id)
            scheduled_job.assert_called_once()
            self.assertIs(
                scheduled_job.call_args.kwargs["reservation"],
                reservation,
            )
            create_task.assert_called_once_with(scheduled_token)

    def test_create_endpoint_propagates_atomic_reservation_identity(
        self,
    ) -> None:
        self._assert_endpoint_propagates_reserved_identity(
            endpoint=image_gen_app.api_create_run,
            request=image_gen_app.CreateRunRequest(title="normal"),
            scheduled_job_name="_run_create_job",
        )

    def test_storyboard_endpoint_propagates_atomic_reservation_identity(
        self,
    ) -> None:
        self._assert_endpoint_propagates_reserved_identity(
            endpoint=image_gen_app.api_create_storyboard_run,
            request=image_gen_app.CreateStoryboardRunRequest(
                title="storyboard"
            ),
            scheduled_job_name="_run_create_job",
        )

    def test_world_walk_endpoint_propagates_atomic_reservation_identity(
        self,
    ) -> None:
        self._assert_endpoint_propagates_reserved_identity(
            endpoint=image_gen_app.api_create_world_walk_run,
            request=image_gen_app.CreateWorldWalkRunRequest(
                source_run_id="source_20260801_1200",
                title="world walk",
            ),
            scheduled_job_name="_run_world_walk_create_job",
        )

    def test_all_create_endpoints_leave_post_reservation_replacement_untouched(
        self,
    ) -> None:
        cases = (
            (
                "normal",
                image_gen_app.api_create_run,
                image_gen_app.CreateRunRequest(title="normal swap"),
                RuntimeError("normal handoff failure"),
            ),
            (
                "storyboard",
                image_gen_app.api_create_storyboard_run,
                image_gen_app.CreateStoryboardRunRequest(
                    title="storyboard swap"
                ),
                asyncio.CancelledError(),
            ),
            (
                "world-walk",
                image_gen_app.api_create_world_walk_run,
                image_gen_app.CreateWorldWalkRunRequest(
                    source_run_id="source_20260801_1200",
                    title="world walk swap",
                ),
                RuntimeError("world-walk handoff failure"),
            ),
        )
        for label, endpoint, request, injected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                real_reserve = image_gen_app._reserve_frontend_create_run_dir
                real_acquire = image_gen_app._acquire_run_execution_lease
                captured: list[
                    image_gen_app._FrontendCreateRunReservation
                ] = []

                def capture_reservation(title: str):
                    reservation = real_reserve(title)
                    captured.append(reservation)
                    return reservation

                async def swap_then_fail(
                    job_id: str,
                    run_dir: Path,
                    **kwargs,
                ) -> None:
                    displaced = run_dir.with_name(
                        f"{run_dir.name}-reserved-original"
                    )
                    run_dir.rename(displaced)
                    run_dir.mkdir()
                    (run_dir / "sentinel.txt").write_text(
                        "replacement untouched\n",
                        encoding="utf-8",
                    )
                    await real_acquire(job_id, run_dir, **kwargs)
                    raise injected

                async def invoke() -> None:
                    with self.assertRaises(BaseException):
                        await endpoint(request)

                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.dict(image_gen_app._create_jobs, {}, clear=True),
                    patch.dict(image_gen_app._create_tasks, {}, clear=True),
                    patch.dict(
                        image_gen_app._run_execution_leases,
                        {},
                        clear=True,
                    ),
                    patch.object(
                        image_gen_app,
                        "_reserve_frontend_create_run_dir",
                        side_effect=capture_reservation,
                    ),
                    patch.object(
                        image_gen_app,
                        "_require_world_walk_source_run",
                        return_value=root / "output" / "source",
                    ),
                    patch.object(
                        image_gen_app,
                        "_acquire_run_execution_lease",
                        side_effect=swap_then_fail,
                    ),
                ):
                    asyncio.run(invoke())

                    self.assertEqual(image_gen_app._create_jobs, {})
                    self.assertEqual(image_gen_app._create_tasks, {})
                    self.assertEqual(
                        image_gen_app._run_execution_leases,
                        {},
                    )

                self.assertEqual(len(captured), 1)
                reservation = captured[0]
                self.assertEqual(reservation.descriptor, -1)
                self.assertEqual(
                    sorted(
                        path.name
                        for path in reservation.run_dir.iterdir()
                    ),
                    ["sentinel.txt"],
                )
                self.assertEqual(
                    (reservation.run_dir / "sentinel.txt").read_text(
                        encoding="utf-8"
                    ),
                    "replacement untouched\n",
                )

    def test_background_cancellation_releases_and_cleans_all_create_modes(
        self,
    ) -> None:
        cases = (
            ("normal", image_gen_app.CREATE_MODE_NORMAL, False),
            (
                "storyboard",
                image_gen_app.CREATE_MODE_SCENE_STORYBOARD,
                False,
            ),
            ("world-walk", image_gen_app.CREATE_MODE_WORLD_WALK, True),
        )
        for label, create_mode, world_walk in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with patch.object(image_gen_app, "ROOT", root):
                    reservation = (
                        image_gen_app._reserve_frontend_create_run_dir(label)
                    )
                started: asyncio.Event | None = None

                async def block_bound(*_args, **_kwargs) -> None:
                    assert started is not None
                    started.set()
                    await asyncio.Event().wait()

                async def run_case() -> None:
                    nonlocal started
                    started = asyncio.Event()
                    await image_gen_app._acquire_run_execution_lease(
                        "cancel-job",
                        reservation.run_dir,
                        run_descriptor=reservation.descriptor,
                        expected_run_identity=reservation.identity,
                    )
                    if world_walk:
                        coroutine = image_gen_app._run_world_walk_create_job(
                            "cancel-job",
                            title=label,
                            source_run_id="source",
                            run_id=reservation.run_id,
                            reservation=reservation,
                        )
                    else:
                        coroutine = image_gen_app._run_create_job(
                            "cancel-job",
                            title=label,
                            source=label,
                            run_id=reservation.run_id,
                            create_mode=create_mode,
                            reservation=reservation,
                        )
                    task = asyncio.create_task(coroutine)
                    await started.wait()
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task

                target = (
                    "_run_world_walk_create_job_bound"
                    if world_walk
                    else "_run_create_job_bound"
                )
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.dict(
                        image_gen_app._run_execution_leases,
                        {},
                        clear=True,
                    ),
                    patch.object(
                        image_gen_app,
                        target,
                        side_effect=block_bound,
                    ),
                    patch.object(
                        image_gen_app,
                        "_set_create_job",
                        new=AsyncMock(),
                    ),
                ):
                    asyncio.run(run_case())
                    self.assertEqual(
                        image_gen_app._run_execution_leases,
                        {},
                    )

                self.assertEqual(reservation.descriptor, -1)
                self.assertFalse(reservation.run_dir.exists())
                self.assertEqual(
                    len(
                        list(
                            (root / "output").glob(
                                ".toc-cleanup-*.quarantine"
                            )
                        )
                    ),
                    1,
                )

    def test_shutdown_cancels_and_awaits_tracked_create_tasks(self) -> None:
        finalized = asyncio.Event()

        async def worker() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                finalized.set()

        async def run_case() -> None:
            task = asyncio.create_task(worker())
            image_gen_app._create_tasks["create-job"] = task
            await asyncio.sleep(0)
            await image_gen_app.shutdown_codex_client()
            self.assertTrue(task.cancelled())

        with (
            patch.dict(image_gen_app._create_tasks, {}, clear=True),
            patch.dict(image_gen_app._resume_tasks, {}, clear=True),
            patch.dict(image_gen_app._bulk_generation_tasks, {}, clear=True),
            patch.object(image_gen_app, "_codex_client", None),
        ):
            asyncio.run(run_case())
            self.assertTrue(finalized.is_set())
            self.assertEqual(image_gen_app._create_tasks, {})

    def test_shutdown_releases_lease_for_task_cancelled_before_first_step(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "prestart-shutdown_20260801_1200"
            run_dir.mkdir(parents=True)
            leased_descriptor = -1
            worker_started = False

            async def worker() -> None:
                nonlocal worker_started
                worker_started = True
                try:
                    await asyncio.Event().wait()
                finally:
                    await image_gen_app._release_run_execution_lease(
                        "prestart-job"
                    )

            async def run_case() -> None:
                nonlocal leased_descriptor
                lease = await image_gen_app._acquire_run_execution_lease(
                    "prestart-job",
                    run_dir,
                )
                leased_descriptor = lease.run_descriptor
                task = asyncio.create_task(worker())
                image_gen_app._create_tasks["prestart-job"] = task
                # Do not yield: shutdown cancels the task before worker() can
                # enter its own finally block.
                await image_gen_app.shutdown_codex_client()
                self.assertTrue(task.cancelled())

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.dict(image_gen_app._create_tasks, {}, clear=True),
                patch.dict(image_gen_app._resume_tasks, {}, clear=True),
                patch.dict(
                    image_gen_app._bulk_generation_tasks,
                    {},
                    clear=True,
                ),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {},
                    clear=True,
                ),
                patch.object(image_gen_app, "_codex_client", None),
            ):
                asyncio.run(run_case())

            self.assertFalse(worker_started)
            self.assertEqual(image_gen_app._run_execution_leases, {})
            with self.assertRaises(OSError):
                os.fstat(leased_descriptor)

    def test_create_job_lock_conflict_does_not_delete_live_owner_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "live-owner_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            marker = run_dir / ".toc_frontend_create.lock"
            marker.write_text("legacy marker\n", encoding="utf-8")
            descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.object(
                        image_gen_app,
                        "_acquire_run_execution_lease",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_release_run_execution_lease",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_set_create_job",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_sync_process_current_process",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_invalidate_published_image_generation_review_handoff",
                    ),
                    patch.object(
                        image_gen_app,
                        "write_app_server_debug_log",
                    ),
                ):
                    asyncio.run(
                        image_gen_app._run_create_job(
                            "live-owner-job",
                            title="live owner",
                            source="live owner",
                            run_id=run_id,
                        )
                    )
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

            self.assertTrue(run_dir.is_dir())
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "legacy marker\n",
            )

    def test_create_job_lock_conflict_does_not_mutate_live_owner_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "live-state_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            state_path = run_dir / "state.txt"
            owner_state = "status=RUNNING\nowner=frontend\n---\n"
            state_path.write_text(owner_state, encoding="utf-8")
            descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.object(
                        image_gen_app,
                        "_acquire_run_execution_lease",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_release_run_execution_lease",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_set_create_job",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_sync_process_current_process",
                        self._async_noop,
                    ),
                    patch.object(
                        image_gen_app,
                        "_invalidate_published_image_generation_review_handoff",
                    ),
                    patch.object(
                        image_gen_app,
                        "write_app_server_debug_log",
                    ),
                ):
                    asyncio.run(
                        image_gen_app._run_create_job(
                            "live-state-job",
                            title="live state",
                            source="live state",
                            run_id=run_id,
                        )
                    )
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

            self.assertEqual(
                state_path.read_text(encoding="utf-8"),
                owner_state,
            )

    def test_world_walk_failure_cleanup_never_recreates_public_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "world-walk-failure_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            job_updates: list[tuple[tuple[object, ...], dict[str, object]]] = []

            async def fail_helper(**_kwargs) -> str:
                raise RuntimeError("frontend helper failed")

            async def record_job_update(*args, **kwargs) -> None:
                job_updates.append((args, kwargs))

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {},
                    clear=True,
                ),
                patch.object(
                    image_gen_app,
                    "_require_world_walk_source_run",
                    return_value=root / "output" / "source",
                ),
                patch.object(
                    image_gen_app,
                    "_acquire_run_execution_lease",
                    self._async_noop,
                ),
                patch.object(
                    image_gen_app,
                    "_release_run_execution_lease",
                    self._async_noop,
                ),
                patch.object(
                    image_gen_app,
                    "_set_create_job",
                    record_job_update,
                ),
                patch.object(
                    image_gen_app,
                    "_sync_process_current_process",
                    self._async_noop,
                ),
                patch.object(
                    image_gen_app,
                    "_run_toc_immersive_frontend_cli_helper",
                    fail_helper,
                ),
                patch.object(
                    image_gen_app,
                    "write_app_server_debug_log",
                ) as debug_log,
            ):
                asyncio.run(
                    image_gen_app._run_world_walk_create_job(
                        "world-walk-failure-job",
                        title="world walk failure",
                        source_run_id="source_20260801_1200",
                        run_id=run_id,
                        expected_run_identity=expected_identity,
                    )
                )

            self.assertFalse(run_dir.exists())
            residues = list(
                (root / "output").glob(".toc-cleanup-*.quarantine")
            )
            self.assertEqual(len(residues), 1)
            self.assertEqual(debug_log.call_count, 1)
            self.assertEqual(
                debug_log.call_args.kwargs["status"],
                "started",
            )
            self.assertEqual(
                job_updates[-1][1].get("write_run_log"),
                False,
            )

    def test_direct_generation_providers_run_inside_retained_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "provider-binding_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            observed: list[tuple[int, int]] = []

            async def fake_generate_one(
                actual_run_dir: Path,
                _request,
                index: int,
            ) -> dict[str, object]:
                binding = image_gen_app.current_run_root_binding()
                self.assertIsNotNone(binding)
                assert binding is not None
                self.assertEqual(actual_run_dir.name, run_dir.name)
                self.assertEqual(binding.identity, expected_identity)
                self.assertEqual(
                    self._directory_identity(Path(binding.lexical_root)),
                    expected_identity,
                )
                observed.append(binding.identity)
                return {
                    "index": index,
                    "status": "completed",
                    "path": "candidate.png",
                }

            single_request = image_gen_app.GenerateRequest(
                run_id=run_id,
                kind="asset",
                item_id="hero",
                prompt="hero",
                candidate_count=1,
            )
            bulk_request = image_gen_app.BulkGenerateRequest(
                run_id=run_id,
                kind="asset",
                items=[single_request],
                concurrency=1,
                background=False,
            )

            async def run_case() -> None:
                await image_gen_app.api_generate(single_request)
                await image_gen_app.api_generate_bulk(bulk_request)

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {},
                    clear=True,
                ),
                patch.object(
                    image_gen_app,
                    "_generate_one",
                    side_effect=fake_generate_one,
                ),
            ):
                asyncio.run(run_case())

            self.assertEqual(observed, [expected_identity, expected_identity])
            self.assertEqual(image_gen_app._run_execution_leases, {})

    def test_background_generation_provider_runs_inside_retained_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "background-provider-binding_20260801_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            request = image_gen_app.GenerateRequest(
                run_id=run_id,
                kind="asset",
                item_id="hero",
                prompt="hero",
                candidate_count=1,
            )
            bulk_request = image_gen_app.BulkGenerateRequest(
                run_id=run_id,
                kind="asset",
                items=[request],
                concurrency=1,
                background=True,
            )
            plan = image_gen_app._BulkGenerationPlanItem(
                id=request.item_id,
                output="assets/characters/hero.png",
                references=[],
                dependency_references=[],
                request=request,
            )
            groups = [[plan]]
            job = image_gen_app._initial_bulk_generation_job(
                req=bulk_request,
                groups=groups,
                fingerprint="binding-fingerprint",
            )
            job_id = str(job["jobId"])
            observed: list[tuple[int, int]] = []

            async def fake_generate_one(
                actual_run_dir: Path,
                _request,
                index: int,
            ) -> dict[str, object]:
                binding = image_gen_app.current_run_root_binding()
                self.assertIsNotNone(binding)
                assert binding is not None
                self.assertEqual(actual_run_dir.name, run_dir.name)
                self.assertEqual(binding.identity, expected_identity)
                observed.append(binding.identity)
                return {
                    "index": index,
                    "status": "failed",
                    "path": None,
                    "error": "synthetic failure",
                }

            async def run_case() -> None:
                lease = await image_gen_app._acquire_run_execution_lease(
                    job_id,
                    run_dir,
                )
                await image_gen_app._run_bulk_generation_job(
                    job_id=job_id,
                    run_dir=run_dir,
                    groups=groups,
                    requested_concurrency=1,
                    run_descriptor=lease.run_descriptor,
                    expected_run_identity=lease.identity,
                )

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.dict(
                    image_gen_app._bulk_generation_jobs,
                    {job_id: job},
                    clear=True,
                ),
                patch.dict(
                    image_gen_app._bulk_generation_tasks,
                    {},
                    clear=True,
                ),
                patch.dict(
                    image_gen_app._run_execution_leases,
                    {},
                    clear=True,
                ),
                patch.object(
                    image_gen_app,
                    "_generate_one",
                    side_effect=fake_generate_one,
                ),
            ):
                asyncio.run(run_case())

            self.assertEqual(observed, [expected_identity])
            self.assertEqual(image_gen_app._run_execution_leases, {})

    def test_orphaned_child_directory_lease_blocks_restarted_mutator(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "orphan-lease_20260801_1200"
            run_dir.mkdir(parents=True)
            child: subprocess.Popen[str] | None = None

            async def run_case() -> None:
                nonlocal child
                lease = await image_gen_app._acquire_run_execution_lease(
                    "original-server",
                    run_dir,
                )
                child = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import os,sys,time; "
                            "os.fstat(int(sys.argv[1])); "
                            "print('ready', flush=True); "
                            "time.sleep(60)"
                        ),
                        str(lease.run_descriptor),
                    ],
                    pass_fds=(lease.run_descriptor,),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                assert child.stdout is not None
                self.assertEqual(child.stdout.readline().strip(), "ready")

                # Model abrupt server death: close its copies without issuing
                # LOCK_UN on the shared open-file description retained by the
                # child.  A restarted server can reacquire the metadata lock,
                # but the directory flock must still reject mutation.
                async with image_gen_app._run_execution_leases_guard:
                    self.assertIs(
                        image_gen_app._run_execution_leases.pop(
                            "original-server"
                        ),
                        lease,
                    )
                os.close(lease.run_descriptor)
                await image_gen_app.release_file_lock(
                    lease.runtime_lease
                )

                with self.assertRaises(image_gen_app.FileLockUnavailable):
                    await image_gen_app._acquire_run_execution_lease(
                        "restarted-server",
                        run_dir,
                    )

                child.terminate()
                child.wait(timeout=5)
                child = None
                restarted = (
                    await image_gen_app._acquire_run_execution_lease(
                        "restarted-server",
                        run_dir,
                    )
                )
                self.assertEqual(
                    restarted.identity,
                    self._directory_identity(run_dir),
                )
                await image_gen_app._release_run_execution_lease(
                    "restarted-server"
                )

            try:
                with (
                    patch.object(image_gen_app, "ROOT", root),
                    patch.dict(
                        image_gen_app._run_execution_leases,
                        {},
                        clear=True,
                    ),
                ):
                    asyncio.run(run_case())
            finally:
                if child is not None:
                    child.kill()
                    child.wait(timeout=5)

            self.assertEqual(image_gen_app._run_execution_leases, {})

    def test_directory_fd_exec_helper_closes_fd_after_fchdir(self) -> None:
        script_path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "run-from-directory-fd.py"
        )
        spec = importlib.util.spec_from_file_location(
            "run_from_directory_fd_test",
            script_path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class ExecIntercept(RuntimeError):
            pass

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            directory_descriptor = os.open(
                run_dir,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            original_directory = os.open(
                ".",
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            real_fstat = os.fstat

            def intercept_exec(*_args, **_kwargs):
                with self.assertRaises(OSError):
                    real_fstat(directory_descriptor)
                self.assertTrue(Path.cwd().samefile(run_dir))
                raise ExecIntercept("exec intercepted")

            try:
                with (
                    patch.object(
                        sys,
                        "argv",
                        [
                            str(script_path),
                            "--fd",
                            str(directory_descriptor),
                            "--",
                            "synthetic-command",
                        ],
                    ),
                    patch.object(
                        module.os,
                        "execvpe",
                        side_effect=intercept_exec,
                    ),
                    self.assertRaises(ExecIntercept),
                ):
                    module.main()
            finally:
                os.fchdir(original_directory)
                os.close(original_directory)

    def test_unscaffolded_cleanup_does_not_delete_live_locked_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-live_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            sentinel = run_dir / "owner.txt"
            sentinel.write_text("active\n", encoding="utf-8")
            expected_identity = self._directory_identity(run_dir)
            descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

            try:
                with patch.object(image_gen_app, "ROOT", root):
                    image_gen_app._cleanup_unscaffolded_run(
                        run_id,
                        expected_run_identity=expected_identity,
                    )
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "active\n",
            )

    def test_unscaffolded_cleanup_quarantines_run_with_available_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-stale_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "stale.txt").write_text("stale\n", encoding="utf-8")
            expected_identity = self._directory_identity(run_dir)

            with patch.object(image_gen_app, "ROOT", root):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertFalse(run_dir.exists())
            residues = list(
                (root / "output").glob(
                    ".toc-cleanup-*.quarantine"
                )
            )
            self.assertEqual(len(residues), 1)
            self.assertEqual(
                (residues[0] / "stale.txt").read_text(encoding="utf-8"),
                "stale\n",
            )

    def test_unscaffolded_cleanup_does_not_delete_run_swapped_after_lock(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-swap_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "stale.txt").write_text(
                "stale\n",
                encoding="utf-8",
            )
            expected_identity = self._directory_identity(run_dir)
            displaced = root / "locked-original"
            replacement_sentinel = root / "replacement-sentinel.txt"
            replacement_sentinel.write_text(
                "must survive\n",
                encoding="utf-8",
            )
            original_lock = image_gen_app._frontend_create_directory_lock

            @contextmanager
            def swap_after_lock(path: Path, **kwargs):
                with original_lock(path, **kwargs) as lease:
                    path.rename(displaced)
                    path.mkdir()
                    replacement_sentinel.rename(path / "sentinel.txt")
                    yield lease

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_frontend_create_directory_lock",
                    swap_after_lock,
                ),
            ):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertEqual(
                (run_dir / "sentinel.txt").read_text(encoding="utf-8"),
                "must survive\n",
            )
            self.assertEqual(
                (displaced / "stale.txt").read_text(encoding="utf-8"),
                "stale\n",
            )

    def test_unscaffolded_cleanup_rejects_final_symlink_to_victim_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            output_dir.mkdir()
            run_id = "cleanup-link_20260729_1200"
            run_dir = output_dir / run_id
            run_dir.mkdir()
            expected_identity = self._directory_identity(run_dir)
            displaced = root / "original-run"
            run_dir.rename(displaced)
            victim_dir = output_dir / "victim_20260729_1200"
            victim_dir.mkdir()
            victim_sentinel = victim_dir / "sentinel.txt"
            victim_sentinel.write_text(
                "must survive\n",
                encoding="utf-8",
            )
            run_dir.symlink_to(victim_dir.name, target_is_directory=True)

            with patch.object(image_gen_app, "ROOT", root):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertTrue(run_dir.is_symlink())
            self.assertEqual(
                victim_sentinel.read_text(encoding="utf-8"),
                "must survive\n",
            )

    def test_unscaffolded_cleanup_preserves_broken_scaffold_symlink(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-scaffold-link_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            state_path = run_dir / "state.txt"
            state_path.symlink_to("missing-state-target.txt")

            with patch.object(image_gen_app, "ROOT", root):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertTrue(run_dir.is_dir())
            self.assertTrue(state_path.is_symlink())

    def test_unscaffolded_cleanup_never_path_deletes_private_quarantine(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-entry-race_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "stale.txt").write_text(
                "stale\n",
                encoding="utf-8",
            )
            expected_identity = self._directory_identity(run_dir)
            victim = root / "victim.txt"
            victim.write_text("must survive\n", encoding="utf-8")
            original_unlink = os.unlink
            original_rmdir = os.rmdir
            private_deletions: list[str] = []

            def record_private_unlink(path, *args, **kwargs):
                if str(path).startswith(".toc-"):
                    private_deletions.append(f"unlink:{path}")
                return original_unlink(path, *args, **kwargs)

            def record_private_rmdir(path, *args, **kwargs):
                if str(path).startswith(".toc-"):
                    private_deletions.append(f"rmdir:{path}")
                return original_rmdir(path, *args, **kwargs)

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app.os,
                    "unlink",
                    side_effect=record_private_unlink,
                ),
                patch.object(
                    image_gen_app.os,
                    "rmdir",
                    side_effect=record_private_rmdir,
                ),
            ):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertEqual(private_deletions, [])
            self.assertFalse(run_dir.exists())
            self.assertEqual(
                victim.read_text(encoding="utf-8"),
                "must survive\n",
            )

    def test_unscaffolded_cleanup_rejects_prelock_run_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-prelock-swap_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            displaced = root / "reserved-original"
            run_dir.rename(displaced)
            run_dir.mkdir()
            replacement = run_dir / "sentinel.txt"
            replacement.write_text("must survive\n", encoding="utf-8")

            with patch.object(image_gen_app, "ROOT", root):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertEqual(
                replacement.read_text(encoding="utf-8"),
                "must survive\n",
            )
            self.assertTrue(displaced.is_dir())

    def test_unscaffolded_cleanup_commit_swap_only_moves_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            run_id = "cleanup-commit-swap_20260729_1200"
            run_dir = output_dir / run_id
            run_dir.mkdir(parents=True)
            (run_dir / "stale.txt").write_text(
                "stale\n",
                encoding="utf-8",
            )
            expected_identity = self._directory_identity(run_dir)
            original_rename_noreplace = (
                image_gen_app._frontend_create_rename_noreplace
            )
            raced = False

            def swap_at_atomic_move(**kwargs):
                nonlocal raced
                if not raced:
                    raced = True
                    parent_descriptor = kwargs[
                        "source_parent_descriptor"
                    ]
                    os.rename(
                        run_id,
                        "displaced-at-commit",
                        src_dir_fd=parent_descriptor,
                        dst_dir_fd=parent_descriptor,
                    )
                    os.mkdir(run_id, dir_fd=parent_descriptor)
                    replacement_descriptor = os.open(
                        run_id,
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=parent_descriptor,
                    )
                    try:
                        sentinel_descriptor = os.open(
                            "sentinel.txt",
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=replacement_descriptor,
                        )
                        try:
                            os.write(sentinel_descriptor, b"must survive\n")
                        finally:
                            os.close(sentinel_descriptor)
                    finally:
                        os.close(replacement_descriptor)
                return original_rename_noreplace(**kwargs)

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_frontend_create_rename_noreplace",
                    side_effect=swap_at_atomic_move,
                ),
            ):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertTrue(raced)
            self.assertEqual(
                (output_dir / "displaced-at-commit" / "stale.txt")
                .read_text(encoding="utf-8"),
                "stale\n",
            )
            residues = list(
                output_dir.glob(".toc-cleanup-*.quarantine")
            )
            self.assertEqual(len(residues), 1)
            self.assertEqual(
                (residues[0] / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "must survive\n",
            )

    def test_unscaffolded_cleanup_without_reserved_identity_is_noop(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "cleanup-no-identity_20260729_1200"
            run_dir = root / "output" / run_id
            run_dir.mkdir(parents=True)
            sentinel = run_dir / "sentinel.txt"
            sentinel.write_text("must survive\n", encoding="utf-8")

            with patch.object(image_gen_app, "ROOT", root):
                image_gen_app._cleanup_unscaffolded_run(run_id)

            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "must survive\n",
            )

    def test_unscaffolded_cleanup_never_clobbers_quarantine_collision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            run_id = "cleanup-collision_20260729_1200"
            run_dir = output_dir / run_id
            run_dir.mkdir(parents=True)
            expected_identity = self._directory_identity(run_dir)
            (run_dir / "stale.txt").write_text(
                "stale\n",
                encoding="utf-8",
            )
            collision = output_dir / ".reserved-quarantine"
            collision.mkdir()
            collision_sentinel = collision / "sentinel.txt"
            collision_sentinel.write_text(
                "must survive\n",
                encoding="utf-8",
            )

            with (
                patch.object(image_gen_app, "ROOT", root),
                patch.object(
                    image_gen_app,
                    "_frontend_create_private_name",
                    return_value=collision.name,
                ),
            ):
                image_gen_app._cleanup_unscaffolded_run(
                    run_id,
                    expected_run_identity=expected_identity,
                )

            self.assertTrue(run_dir.is_dir())
            self.assertEqual(
                collision_sentinel.read_text(encoding="utf-8"),
                "must survive\n",
            )


if __name__ == "__main__":
    unittest.main()
