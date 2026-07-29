from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from toc.runtime_locks import FileLockUnavailable, async_file_lock, async_file_slot


class RuntimeLockTests(unittest.TestCase):
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
