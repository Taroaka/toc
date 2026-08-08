from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from toc.runtime_locks import (
    FileLockUnavailable,
    acquire_file_lock,
    async_file_lock,
    async_file_slot,
    release_file_lock,
)


class RuntimeLockTests(unittest.TestCase):
    @staticmethod
    def _unlink_replaceable_anchor_files(anchor_dir: Path) -> None:
        for candidate in anchor_dir.iterdir():
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()

    def test_file_lock_rejects_symlink_without_modifying_target(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("symlink lock path must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "outside.txt"
            target.write_text("do-not-truncate\n", encoding="utf-8")
            lock_path = root / "run.lock"
            lock_path.symlink_to(target)

            asyncio.run(run_case(lock_path))

            self.assertEqual(target.read_text(encoding="utf-8"), "do-not-truncate\n")

    def test_file_lock_rejects_symlink_parent_without_creating_outside_lock(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("symlink lock parent must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            run_dir.mkdir()
            outside.mkdir()
            (run_dir / ".locks").symlink_to(outside, target_is_directory=True)

            asyncio.run(run_case(run_dir / ".locks" / "create_resume.lock"))

            self.assertFalse((outside / "create_resume.lock").exists())

    def test_pinned_run_lock_metadata_never_mutates_public_replacement(
        self,
    ) -> None:
        async def run_case(
            lock_path: Path,
            run_descriptor: int,
            identity: tuple[int, int],
        ) -> None:
            lease = await acquire_file_lock(
                lock_path,
                wait=False,
                run_root_descriptor=run_descriptor,
                expected_run_root_identity=identity,
            )
            await release_file_lock(lease)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            run_dir.mkdir(parents=True)
            opened = run_dir.stat()
            identity = opened.st_dev, opened.st_ino
            descriptor = os.open(
                run_dir,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            original = root / "original-run"
            run_dir.rename(original)
            run_dir.mkdir()
            sentinel = run_dir / "sentinel.txt"
            sentinel.write_text("replacement\n", encoding="utf-8")
            try:
                asyncio.run(
                    run_case(
                        run_dir / ".locks" / "create_resume.lock",
                        descriptor,
                        identity,
                    )
                )
            finally:
                os.close(descriptor)

            self.assertTrue(
                (original / ".locks" / "create_resume.lock").is_file()
            )
            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                ["sentinel.txt"],
            )
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "replacement\n",
            )

    def test_file_lock_rejects_symlink_run_ancestor(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("symlink run ancestor must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            (outside / "run").mkdir(parents=True)
            (root / "output").symlink_to(outside, target_is_directory=True)

            asyncio.run(
                run_case(
                    root
                    / "output"
                    / "run"
                    / ".locks"
                    / "create_resume.lock"
                )
            )

            self.assertFalse((outside / "run" / ".locks").exists())

    def test_file_lock_rejects_non_regular_path_without_blocking(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("non-regular lock path must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            fifo = Path(tmp) / "run.lock"
            os.mkfifo(fifo)
            asyncio.run(asyncio.wait_for(run_case(fifo), timeout=1))

    def test_file_lock_rejects_hard_link_without_modifying_target(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("multiply-linked lock path must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "outside.txt"
            target.write_text("do-not-truncate\n", encoding="utf-8")
            lock_path = root / "run.lock"
            os.link(target, lock_path)

            asyncio.run(run_case(lock_path))

            self.assertEqual(target.read_text(encoding="utf-8"), "do-not-truncate\n")

    def test_nonblocking_file_lease_rejects_second_owner(self) -> None:
        async def run_case(path: Path) -> None:
            async with async_file_lock(path, wait=False):
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(path, wait=False):
                        self.fail("second lease must not enter")

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp) / "run.lock"))

    def test_temp_path_aliases_share_one_logical_lock(self) -> None:
        async def run_case(lexical_path: Path, canonical_path: Path) -> None:
            async with async_file_lock(lexical_path, wait=False):
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(canonical_path, wait=False):
                        self.fail("temp path aliases must share one lease")

        with tempfile.TemporaryDirectory() as tmp:
            lexical_run = Path(tmp) / "run"
            lexical_run.mkdir()
            canonical_run = lexical_run.resolve()
            asyncio.run(
                run_case(
                    lexical_run / ".locks" / "create_resume.lock",
                    canonical_run / ".locks" / "create_resume.lock",
                )
            )

    def test_case_aliases_share_one_logical_lock_when_supported(self) -> None:
        async def run_case(first_path: Path, alias_path: Path) -> None:
            async with async_file_lock(first_path, wait=False):
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(alias_path, wait=False):
                        self.fail("case aliases must share one lease")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "RunCase"
            run_dir.mkdir()
            alias_dir = root / "rUNcASE"
            if not alias_dir.is_dir():
                self.skipTest("filesystem is case-sensitive")
            asyncio.run(
                run_case(
                    run_dir / ".locks" / "create_resume.lock",
                    alias_dir / ".locks" / "create_resume.lock",
                )
            )

    def test_unlinked_lock_anchors_cannot_create_same_process_owner(self) -> None:
        async def run_case(run_dir: Path, anchor_dir: Path) -> None:
            lock_path = run_dir / ".locks" / "create_resume.lock"
            with mock.patch.object(tempfile, "tempdir", os.fspath(anchor_dir)):
                async with async_file_lock(lock_path, wait=False):
                    lock_path.unlink()
                    self._unlink_replaceable_anchor_files(anchor_dir)
                    with self.assertRaises(FileLockUnavailable):
                        async with async_file_lock(lock_path, wait=False):
                            self.fail("unlinked anchors must not admit a second owner")
                async with async_file_lock(lock_path, wait=False):
                    return

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            anchor_dir = root / "anchors"
            run_dir.mkdir()
            anchor_dir.mkdir()
            asyncio.run(run_case(run_dir, anchor_dir))

    def test_closing_unrelated_devnull_fd_does_not_release_lease(self) -> None:
        async def run_case(lock_path: Path) -> None:
            async with async_file_lock(lock_path, wait=False):
                with open(os.devnull, "wb"):
                    pass
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(lock_path, wait=False):
                        self.fail("an unrelated close must not release the lease")

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            asyncio.run(
                run_case(run_dir / ".locks" / "create_resume.lock")
            )

    def test_cancelled_async_acquisition_does_not_leak_later_lease(self) -> None:
        async def run_case(lock_path: Path) -> None:
            async with async_file_lock(lock_path, wait=False):
                pending = asyncio.create_task(
                    acquire_file_lock(lock_path, wait=True)
                )
                await asyncio.sleep(0.1)
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
            async with async_file_lock(lock_path, wait=False):
                return

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            asyncio.run(
                run_case(run_dir / ".locks" / "create_resume.lock")
            )

    def test_unlinked_lock_anchors_cannot_create_cross_process_owner(self) -> None:
        probe = """
import asyncio
import sys
from pathlib import Path

from toc.runtime_locks import FileLockUnavailable, async_file_lock


async def main() -> int:
    try:
        async with async_file_lock(Path(sys.argv[1]), wait=False):
            return 3
    except FileLockUnavailable:
        return 0


raise SystemExit(asyncio.run(main()))
"""

        async def run_case(run_dir: Path, anchor_dir: Path) -> None:
            lock_path = run_dir / ".locks" / "create_resume.lock"
            child_env = os.environ.copy()
            child_env.update(
                TMPDIR=os.fspath(anchor_dir),
                TMP=os.fspath(anchor_dir),
                TEMP=os.fspath(anchor_dir),
            )

            def probe_owner() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, "-c", probe, os.fspath(lock_path)],
                    cwd=Path(__file__).resolve().parents[1],
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )

            with mock.patch.object(tempfile, "tempdir", os.fspath(anchor_dir)):
                async with async_file_lock(lock_path, wait=False):
                    lock_path.unlink()
                    self._unlink_replaceable_anchor_files(anchor_dir)
                    blocked = probe_owner()
                    self.assertEqual(
                        blocked.returncode,
                        0,
                        msg=f"stdout={blocked.stdout!r} stderr={blocked.stderr!r}",
                    )

            acquired = probe_owner()
            self.assertEqual(
                acquired.returncode,
                3,
                msg=f"stdout={acquired.stdout!r} stderr={acquired.stderr!r}",
            )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            anchor_dir = root / "anchors"
            run_dir.mkdir()
            anchor_dir.mkdir()
            asyncio.run(run_case(run_dir, anchor_dir))

    def test_cross_process_identity_ignores_temp_environment(self) -> None:
        probe = """
import asyncio
import sys
from pathlib import Path

from toc.runtime_locks import FileLockUnavailable, async_file_lock


async def main() -> int:
    try:
        async with async_file_lock(Path(sys.argv[1]), wait=False):
            return 3
    except FileLockUnavailable:
        return 0


raise SystemExit(asyncio.run(main()))
"""

        async def run_case(lock_path: Path, child_temp: Path) -> None:
            child_env = os.environ.copy()
            child_env.update(
                TMPDIR=os.fspath(child_temp),
                TMP=os.fspath(child_temp),
                TEMP=os.fspath(child_temp),
            )
            async with async_file_lock(lock_path, wait=False):
                blocked = subprocess.run(
                    [sys.executable, "-c", probe, os.fspath(lock_path)],
                    cwd=Path(__file__).resolve().parents[1],
                    env=child_env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(
                    blocked.returncode,
                    0,
                    msg=f"stdout={blocked.stdout!r} stderr={blocked.stderr!r}",
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            child_temp = root / "child-temp"
            run_dir.mkdir()
            child_temp.mkdir()
            asyncio.run(
                run_case(
                    run_dir / ".locks" / "create_resume.lock",
                    child_temp,
                )
            )

    @unittest.skipUnless(hasattr(os, "fork"), "requires POSIX fork semantics")
    def test_forked_child_does_not_extend_parent_lease_lifetime(self) -> None:
        holder = """
import os
import sys
import time
from pathlib import Path

from toc.runtime_locks import sync_file_lock


with sync_file_lock(Path(sys.argv[1]), wait=False):
    child_pid = os.fork()
    if child_pid == 0:
        time.sleep(10)
        os._exit(0)
    print(child_pid, flush=True)
    os._exit(0)
"""

        async def acquire_after_owner_death(lock_path: Path) -> None:
            async with async_file_lock(lock_path, wait=False):
                return

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            lock_path = run_dir / ".locks" / "create_resume.lock"
            process = subprocess.Popen(
                [sys.executable, "-c", holder, os.fspath(lock_path)],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            child_pid: int | None = None
            try:
                assert process.stdout is not None
                child_pid = int(process.stdout.readline().strip())
                process.wait(timeout=5)
                self.assertEqual(process.returncode, 0)
                asyncio.run(acquire_after_owner_death(lock_path))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                if child_pid is not None:
                    try:
                        os.kill(child_pid, 9)
                    except ProcessLookupError:
                        pass

    def test_file_lock_output_parent_replacement_cannot_create_second_owner(
        self,
    ) -> None:
        async def run_case(root: Path, output_dir: Path, anchor_dir: Path) -> None:
            lock_path = output_dir / "run" / ".locks" / "create_resume.lock"
            with mock.patch.object(tempfile, "tempdir", os.fspath(anchor_dir)):
                async with async_file_lock(lock_path, wait=False):
                    output_dir.rename(root / "output-old")
                    (output_dir / "run").mkdir(parents=True)
                    self._unlink_replaceable_anchor_files(anchor_dir)
                    with self.assertRaises(FileLockUnavailable):
                        async with async_file_lock(lock_path, wait=False):
                            self.fail("replacement output parent must share the lock")
                async with async_file_lock(lock_path, wait=False):
                    return

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output"
            anchor_dir = root / "anchors"
            (output_dir / "run").mkdir(parents=True)
            anchor_dir.mkdir()
            asyncio.run(run_case(root, output_dir, anchor_dir))

    def test_file_lock_namespace_replacement_cannot_create_second_owner(
        self,
    ) -> None:
        async def run_case(run_dir: Path) -> None:
            lock_path = run_dir / ".locks" / "create_resume.lock"
            async with async_file_lock(lock_path, wait=False):
                (run_dir / ".locks").rename(run_dir / ".locks-old")
                (run_dir / ".locks").mkdir()
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(lock_path, wait=False):
                        self.fail("replacement namespace must share the anchor")
            async with async_file_lock(lock_path, wait=False):
                return

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            asyncio.run(run_case(run_dir))

    def test_file_lock_run_replacement_cannot_create_second_owner(self) -> None:
        async def run_case(root: Path, run_dir: Path) -> None:
            lock_path = run_dir / ".locks" / "create_resume.lock"
            async with async_file_lock(lock_path, wait=False):
                run_dir.rename(root / "run-old")
                run_dir.mkdir()
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_lock(lock_path, wait=False):
                        self.fail("replacement run must share the anchor")
            async with async_file_lock(lock_path, wait=False):
                return

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            asyncio.run(run_case(root, run_dir))

    def test_file_lock_rejects_nested_namespace_symlink(self) -> None:
        async def run_case(lock_path: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_lock(lock_path, wait=False):
                    self.fail("nested symlink lock path must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outside = root / "outside"
            (run_dir / ".locks").mkdir(parents=True)
            outside.mkdir()
            (run_dir / ".locks" / "image_generation").symlink_to(
                outside,
                target_is_directory=True,
            )

            asyncio.run(
                run_case(
                    run_dir
                    / ".locks"
                    / "image_generation"
                    / "scene.lock"
                )
            )
            self.assertFalse((outside / "scene.lock").exists())

    def test_file_slot_pool_enforces_limit_across_independent_callers(self) -> None:
        active = 0
        max_active = 0

        async def run_case(lock_dir: Path) -> None:
            nonlocal active, max_active

            async def worker() -> None:
                nonlocal active, max_active
                async with async_file_slot(lock_dir, namespace="image", slots=2, timeout_seconds=2):
                    active += 1
                    max_active = max(max_active, active)
                    await asyncio.sleep(0.04)
                    active -= 1

            await asyncio.gather(*(worker() for _ in range(6)))

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp)))

        self.assertEqual(max_active, 2)

    def test_unlinked_slot_metadata_cannot_create_second_owner(self) -> None:
        async def run_case(lock_dir: Path) -> None:
            async with async_file_slot(
                lock_dir,
                namespace="serial",
                slots=1,
                timeout_seconds=0,
            ):
                (lock_dir / "serial-00.lock").unlink()
                with self.assertRaises(FileLockUnavailable):
                    async with async_file_slot(
                        lock_dir,
                        namespace="serial",
                        slots=1,
                        timeout_seconds=0,
                    ):
                        self.fail("unlinked slot metadata must remain leased")

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp)))

    def test_file_slot_rejects_symlink_ancestor(self) -> None:
        async def run_case(lock_dir: Path) -> None:
            with self.assertRaisesRegex(FileLockUnavailable, "unsafe"):
                async with async_file_slot(
                    lock_dir,
                    namespace="serial",
                    slots=1,
                    timeout_seconds=0,
                ):
                    self.fail("symlink slot ancestor must not be entered")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            (root / "locks").symlink_to(outside, target_is_directory=True)

            asyncio.run(run_case(root / "locks" / "pool"))

            self.assertFalse((outside / "pool").exists())

    def test_file_slot_is_released_after_exception(self) -> None:
        async def run_case(lock_dir: Path) -> None:
            with self.assertRaisesRegex(RuntimeError, "boom"):
                async with async_file_slot(lock_dir, namespace="serial", slots=1, timeout_seconds=1):
                    raise RuntimeError("boom")
            async with async_file_slot(lock_dir, namespace="serial", slots=1, timeout_seconds=1):
                return

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(run_case(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
