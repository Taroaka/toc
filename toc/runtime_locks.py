from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import time
from typing import AsyncIterator, TextIO


class FileLockUnavailable(RuntimeError):
    """Raised when a non-blocking lease or bounded slot cannot be acquired."""


@dataclass
class FileLockLease:
    path: Path
    file: TextIO
    slot: int | None = None

    def release(self) -> None:
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()


def _safe_namespace(namespace: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", namespace).strip("._") or "lock"


def _try_lock(path: Path, *, slot: int | None = None) -> FileLockLease | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"pid={os.getpid()}\nacquired_at={time.time():.6f}\n")
    lock_file.flush()
    return FileLockLease(path=path, file=lock_file, slot=slot)


def _acquire_file_lock(path: Path, *, wait: bool, timeout_seconds: float | None) -> FileLockLease:
    deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
    while True:
        held = _try_lock(path)
        if held is not None:
            return held
        if not wait or (deadline is not None and time.monotonic() >= deadline):
            raise FileLockUnavailable(f"file lock is already held: {path}")
        time.sleep(0.05)


def _acquire_file_slot(
    lock_dir: Path,
    *,
    namespace: str,
    slots: int,
    timeout_seconds: float | None,
) -> FileLockLease:
    slot_count = max(1, int(slots))
    safe_namespace = _safe_namespace(namespace)
    deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
    while True:
        for slot in range(slot_count):
            held = _try_lock(lock_dir / f"{safe_namespace}-{slot:02d}.lock", slot=slot)
            if held is not None:
                return held
        if deadline is not None and time.monotonic() >= deadline:
            raise FileLockUnavailable(
                f"no {safe_namespace} slot became available within {timeout_seconds} seconds"
            )
        time.sleep(0.05)


@asynccontextmanager
async def async_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
) -> AsyncIterator[Path]:
    held = await acquire_file_lock(path, wait=wait, timeout_seconds=timeout_seconds)
    try:
        yield held.path
    finally:
        await asyncio.to_thread(held.release)


async def acquire_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
) -> FileLockLease:
    return await asyncio.to_thread(
        _acquire_file_lock,
        path,
        wait=wait,
        timeout_seconds=timeout_seconds,
    )


async def release_file_lock(lease: FileLockLease) -> None:
    await asyncio.to_thread(lease.release)


@asynccontextmanager
async def async_file_slot(
    lock_dir: Path,
    *,
    namespace: str,
    slots: int,
    timeout_seconds: float | None = None,
) -> AsyncIterator[int]:
    held = await asyncio.to_thread(
        _acquire_file_slot,
        lock_dir,
        namespace=namespace,
        slots=slots,
        timeout_seconds=timeout_seconds,
    )
    try:
        yield int(held.slot or 0)
    finally:
        await asyncio.to_thread(held.release)
