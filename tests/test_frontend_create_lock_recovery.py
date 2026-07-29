from __future__ import annotations

import asyncio
import fcntl
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import image_gen_app


class FrontendCreateLockRecoveryTests(unittest.TestCase):
    @staticmethod
    async def _async_noop(*_args, **_kwargs) -> None:
        return None

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


if __name__ == "__main__":
    unittest.main()
