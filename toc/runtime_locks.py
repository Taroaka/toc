from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import re
import stat
import time
from typing import AsyncIterator, Iterator, TextIO


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


def _unsafe_lock_path(path: Path, reason: str) -> FileLockUnavailable:
    return FileLockUnavailable(f"unsafe file lock path: {path} ({reason})")


def _open_lock_file_nofollow(path: Path) -> TextIO:
    """Open a regular, single-link lock file without following its parent or leaf."""

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow or not directory:
        raise _unsafe_lock_path(path, "platform lacks no-follow directory opens")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _unsafe_lock_path(path, f"lock directory unavailable: {exc}") from exc

    parent_fd = -1
    lock_fd = -1
    try:
        # Opening the immediate parent with O_NOFOLLOW prevents a malicious
        # `.locks` symlink from redirecting creation outside the run.
        parent_fd = os.open(
            path.parent,
            os.O_RDONLY | directory | cloexec | nofollow,
        )
        try:
            created_fd = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | cloexec | nofollow,
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            pass
        else:
            os.close(created_fd)
        lock_fd = os.open(
            path.name,
            os.O_RDONLY | cloexec | nofollow | nonblock,
            dir_fd=parent_fd,
        )
        opened = os.fstat(lock_fd)
        if not stat.S_ISREG(opened.st_mode):
            raise _unsafe_lock_path(path, "lock target is not a regular file")
        if opened.st_nlink != 1:
            raise _unsafe_lock_path(path, "lock target has multiple hard links")
        lock_file = os.fdopen(lock_fd, "r", encoding="utf-8")
        lock_fd = -1
        return lock_file
    except FileLockUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise _unsafe_lock_path(path, str(exc)) from exc
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _try_lock(path: Path, *, slot: int | None = None) -> FileLockLease | None:
    lock_file = _open_lock_file_nofollow(path)
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    except BaseException:
        lock_file.close()
        raise
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


@contextmanager
def sync_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
) -> Iterator[Path]:
    """Hold the same advisory lock used by async server artifact writers."""

    held = _acquire_file_lock(path, wait=wait, timeout_seconds=timeout_seconds)
    try:
        yield held.path
    finally:
        held.release()


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
