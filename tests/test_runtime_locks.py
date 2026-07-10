from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from toc.runtime_locks import FileLockUnavailable, async_file_lock, async_file_slot


class RuntimeLockTests(unittest.TestCase):
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
