from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import ctypes
from dataclasses import dataclass, field
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time
import weakref
from typing import AsyncIterator, Callable, Iterator, TextIO


class FileLockUnavailable(RuntimeError):
    """Raised when a non-blocking lease or bounded slot cannot be acquired."""


class _AcquisitionCancelled(RuntimeError):
    """Internal signal used to stop a cancelled async polling worker."""


@dataclass
class FileLockLease:
    path: Path
    file: TextIO
    slot: int | None = None
    lock_offset: int = 0
    lock_offsets: tuple[int, ...] = ()
    owner_pid: int = field(default_factory=os.getpid)
    released: bool = False

    def release(self) -> None:
        with _ACTIVE_LEASES_GUARD:
            if self.released:
                return
            self.released = True
            _ACTIVE_LEASES.pop(id(self), None)
            if self.owner_pid != os.getpid() or self.file.closed:
                return
            try:
                for offset in self.lock_offsets or (self.lock_offset,):
                    _set_open_file_description_lock(
                        self.file.fileno(),
                        offset=offset,
                        lock_type=fcntl.F_UNLCK,
                    )
            finally:
                self.file.close()


_ACTIVE_LEASES: weakref.WeakValueDictionary[int, FileLockLease] = (
    weakref.WeakValueDictionary()
)
_ACTIVE_LEASES_GUARD = threading.RLock()


def _prepare_fork() -> None:
    _ACTIVE_LEASES_GUARD.acquire()


def _after_fork_parent() -> None:
    _ACTIVE_LEASES_GUARD.release()


def _after_fork_child() -> None:
    global _ACTIVE_LEASES_GUARD

    try:
        for lease in tuple(_ACTIVE_LEASES.values()):
            lease.released = True
            if not lease.file.closed:
                try:
                    lease.file.close()
                except OSError:
                    pass
    finally:
        _ACTIVE_LEASES.clear()
        _ACTIVE_LEASES_GUARD = threading.RLock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_prepare_fork,
        after_in_parent=_after_fork_parent,
        after_in_child=_after_fork_child,
    )


def _safe_namespace(namespace: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", namespace).strip("._") or "lock"


def _unsafe_lock_path(path: Path, reason: str) -> FileLockUnavailable:
    return FileLockUnavailable(f"unsafe file lock path: {path} ({reason})")


def _run_lock_scope(path: Path) -> tuple[Path, tuple[str, ...]] | None:
    """Return the lexical run root and lock-relative parts for `.locks`."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    indices = [
        index
        for index, part in enumerate(absolute.parts)
        if part == ".locks"
    ]
    if not indices:
        return None
    index = indices[0]
    run_root = Path(*absolute.parts[:index])
    relative_parts = absolute.parts[index + 1 :]
    if (
        not relative_parts
        or any(part in {"", ".", ".."} for part in relative_parts)
    ):
        raise _unsafe_lock_path(path, "lock must name a file below .locks")
    return run_root, relative_parts


def _trusted_system_path(path: Path) -> Path:
    """Normalize only immutable Darwin root aliases before no-follow walking."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    if sys.platform != "darwin":
        return absolute
    for lexical, canonical in (
        (Path("/etc"), Path("/private/etc")),
        (Path("/tmp"), Path("/private/tmp")),
        (Path("/var"), Path("/private/var")),
    ):
        try:
            return canonical / absolute.relative_to(lexical)
        except ValueError:
            continue
    return absolute


def _open_directory_path_nofollow(
    path: Path,
    *,
    create: bool = False,
    create_mode: int = 0o777,
) -> int:
    """Open a directory by dirfd without following any mutable ancestor."""

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not directory:
        raise _unsafe_lock_path(path, "platform lacks no-follow directory opens")

    absolute = _trusted_system_path(path)
    current_fd = -1
    try:
        current_fd = os.open(
            absolute.anchor,
            os.O_RDONLY | directory | cloexec | nofollow,
        )
        for component in absolute.parts[1:]:
            child_fd = -1
            try:
                try:
                    child_fd = os.open(
                        component,
                        os.O_RDONLY | directory | cloexec | nofollow,
                        dir_fd=current_fd,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(
                            component,
                            create_mode,
                            dir_fd=current_fd,
                        )
                    except FileExistsError:
                        pass
                    child_fd = os.open(
                        component,
                        os.O_RDONLY | directory | cloexec | nofollow,
                        dir_fd=current_fd,
                    )
                named_child = os.stat(
                    component,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                opened_child = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(named_child.st_mode)
                    or (named_child.st_dev, named_child.st_ino)
                    != (opened_child.st_dev, opened_child.st_ino)
                ):
                    raise _unsafe_lock_path(
                        path,
                        f"directory ancestor identity changed: {component}",
                    )
                os.close(current_fd)
                current_fd = child_fd
                child_fd = -1
            finally:
                if child_fd >= 0:
                    os.close(child_fd)
        opened_fd = current_fd
        current_fd = -1
        return opened_fd
    except FileLockUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise _unsafe_lock_path(path, str(exc)) from exc
    finally:
        if current_fd >= 0:
            os.close(current_fd)


def _open_run_lock_metadata_nofollow(
    path: Path,
    *,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> None:
    """Create and validate the caller-visible `.locks/...` entry by dirfd."""

    scope = _run_lock_scope(path)
    if scope is None:
        return
    run_root, relative_parts = scope
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow or not directory:
        raise _unsafe_lock_path(path, "platform lacks no-follow directory opens")

    if (run_root_descriptor is None) != (
        expected_run_root_identity is None
    ):
        raise _unsafe_lock_path(
            path,
            "pinned run descriptor and expected identity must be supplied together",
        )

    root_fd = -1
    current_fd = -1
    lock_fd = -1
    try:
        if run_root_descriptor is None:
            root_fd = _open_directory_path_nofollow(run_root)
        else:
            root_fd = os.dup(run_root_descriptor)
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or (
                expected_run_root_identity is not None
                and (opened_root.st_dev, opened_root.st_ino)
                != expected_run_root_identity
            )
        ):
            raise _unsafe_lock_path(path, "pinned run root identity changed")
        current_fd = os.dup(root_fd)
        for component in (".locks", *relative_parts[:-1]):
            child_fd = -1
            try:
                try:
                    child_fd = os.open(
                        component,
                        os.O_RDONLY | directory | cloexec | nofollow,
                        dir_fd=current_fd,
                    )
                except FileNotFoundError:
                    try:
                        os.mkdir(component, 0o700, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    child_fd = os.open(
                        component,
                        os.O_RDONLY | directory | cloexec | nofollow,
                        dir_fd=current_fd,
                    )
                child_entry = os.stat(
                    component,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
                opened_child = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(child_entry.st_mode)
                    or (child_entry.st_dev, child_entry.st_ino)
                    != (opened_child.st_dev, opened_child.st_ino)
                ):
                    raise _unsafe_lock_path(
                        path,
                        f"lock ancestor identity changed: {component}",
                    )
                os.close(current_fd)
                current_fd = child_fd
                child_fd = -1
            finally:
                if child_fd >= 0:
                    os.close(child_fd)

        leaf = relative_parts[-1]
        try:
            created_fd = os.open(
                leaf,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | cloexec | nofollow,
                0o600,
                dir_fd=current_fd,
            )
        except FileExistsError:
            pass
        else:
            os.close(created_fd)
        lock_fd = os.open(
            leaf,
            os.O_RDONLY | cloexec | nofollow | nonblock,
            dir_fd=current_fd,
        )
        opened_lock = os.fstat(lock_fd)
        named_lock = os.stat(
            leaf,
            dir_fd=current_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened_lock.st_mode)
            or opened_lock.st_nlink != 1
            or (opened_lock.st_dev, opened_lock.st_ino)
            != (named_lock.st_dev, named_lock.st_ino)
        ):
            raise _unsafe_lock_path(path, "lock target is not a private regular file")

        if run_root_descriptor is None:
            final_root_fd = _open_directory_path_nofollow(run_root)
            try:
                final_root = os.fstat(final_root_fd)
                if (final_root.st_dev, final_root.st_ino) != (
                    opened_root.st_dev,
                    opened_root.st_ino,
                ):
                    raise _unsafe_lock_path(path, "run root identity changed")
            finally:
                os.close(final_root_fd)
        else:
            final_root = os.fstat(run_root_descriptor)
            if (
                not stat.S_ISDIR(final_root.st_mode)
                or (final_root.st_dev, final_root.st_ino)
                != (opened_root.st_dev, opened_root.st_ino)
            ):
                raise _unsafe_lock_path(
                    path,
                    "pinned run root identity changed",
                )
    except FileLockUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise _unsafe_lock_path(path, str(exc)) from exc
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if current_fd >= 0:
            os.close(current_fd)
        if root_fd >= 0:
            os.close(root_fd)


class _DarwinFlock(ctypes.Structure):
    _fields_ = [
        ("l_start", ctypes.c_longlong),
        ("l_len", ctypes.c_longlong),
        ("l_pid", ctypes.c_int),
        ("l_type", ctypes.c_short),
        ("l_whence", ctypes.c_short),
    ]


class _LinuxFlock(ctypes.Structure):
    _fields_ = [
        ("l_type", ctypes.c_short),
        ("l_whence", ctypes.c_short),
        ("l_start", ctypes.c_longlong),
        ("l_len", ctypes.c_longlong),
        ("l_pid", ctypes.c_int),
    ]


_MACHINE = os.uname().machine.lower()
if (
    sys.platform == "darwin"
    and ctypes.sizeof(ctypes.c_void_p) == 8
    and ctypes.sizeof(_DarwinFlock) == 24
    and _MACHINE in {"arm64", "x86_64"}
):
    _F_OFD_SETLK = 90
elif (
    sys.platform.startswith("linux")
    and ctypes.sizeof(ctypes.c_void_p) == 8
    and ctypes.sizeof(_LinuxFlock) == 32
    and _MACHINE in {"aarch64", "arm64", "amd64", "x86_64"}
):
    _F_OFD_SETLK = getattr(fcntl, "F_OFD_SETLK", 37)
else:
    _F_OFD_SETLK = None

_SYSTEM_LOCK_CARRIER_IDENTITY: tuple[int, int, int] | None = None


def _lock_identities(
    path: Path,
    *,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> tuple[bytes, ...]:
    scope = _run_lock_scope(path)
    if scope is None:
        absolute = Path(os.path.abspath(os.fspath(path)))
        identities = {os.fsencode(absolute)}
        try:
            identities.add(os.fsencode(absolute.resolve(strict=True)))
            opened = absolute.stat()
            identities.add(
                b"\x01inode\0"
                + f"{opened.st_dev}:{opened.st_ino}".encode("ascii")
            )
        except OSError:
            pass
        return tuple(sorted(identities))
    run_root, relative_parts = scope
    suffix = b"\0" + os.fsencode("/".join(relative_parts))
    identities = {
        os.fsencode(Path(os.path.abspath(os.fspath(run_root)))) + suffix
    }
    if expected_run_root_identity is not None:
        identities.add(
            b"\x01inode\0"
            + (
                f"{expected_run_root_identity[0]}:"
                f"{expected_run_root_identity[1]}"
            ).encode("ascii")
            + suffix
        )
        return tuple(sorted(identities))
    try:
        identities.add(os.fsencode(run_root.resolve(strict=True)) + suffix)
        opened_root = run_root.stat()
        identities.add(
            b"\x01inode\0"
            + f"{opened_root.st_dev}:{opened_root.st_ino}".encode("ascii")
            + suffix
        )
    except OSError:
        pass
    return tuple(sorted(identities))


def _lock_offsets(
    path: Path,
    *,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> tuple[int, ...]:
    offsets = {
        int.from_bytes(
            hashlib.sha256(b"toc-runtime-lock-v2\0" + identity).digest()[:8],
            "big",
        )
        & ((1 << 62) - 1)
        for identity in _lock_identities(
            path,
            expected_run_root_identity=expected_run_root_identity,
        )
    }
    return tuple(sorted(offsets))


def _ofd_lock_buffer(*, offset: int, lock_type: int) -> bytes:
    if sys.platform == "darwin":
        lock = _DarwinFlock(
            l_start=offset,
            l_len=1,
            l_pid=0,
            l_type=lock_type,
            l_whence=os.SEEK_SET,
        )
    elif sys.platform.startswith("linux"):
        lock = _LinuxFlock(
            l_type=lock_type,
            l_whence=os.SEEK_SET,
            l_start=offset,
            l_len=1,
            l_pid=0,
        )
    else:
        raise OSError("open-file-description locks are unavailable")
    return bytes(lock)


def _set_open_file_description_lock(
    file_descriptor: int,
    *,
    offset: int,
    lock_type: int,
) -> None:
    if _F_OFD_SETLK is None:
        raise OSError("open-file-description locks are unavailable")
    lock_buffer = _ofd_lock_buffer(offset=offset, lock_type=lock_type)
    while True:
        try:
            fcntl.fcntl(file_descriptor, _F_OFD_SETLK, lock_buffer)
            return
        except InterruptedError:
            continue


def _open_system_lock_file(path: Path) -> TextIO:
    """Open a fresh description for the stable kernel lock inode."""

    global _SYSTEM_LOCK_CARRIER_IDENTITY

    if _F_OFD_SETLK is None:
        raise _unsafe_lock_path(
            path,
            "platform lacks open-file-description locks",
        )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow:
        raise _unsafe_lock_path(path, "platform lacks no-follow opens")

    system_path = Path(os.devnull)
    lock_fd = -1
    try:
        lock_fd = os.open(
            system_path,
            os.O_RDWR | cloexec | nonblock | nofollow,
        )
        opened = os.fstat(lock_fd)
        named = system_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISCHR(opened.st_mode)
            or not stat.S_ISCHR(named.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_rdev)
            != (named.st_dev, named.st_ino, named.st_rdev)
        ):
            raise _unsafe_lock_path(
                path,
                "stable system lock inode identity changed",
            )
        carrier_identity = (opened.st_dev, opened.st_ino, opened.st_rdev)
        if _SYSTEM_LOCK_CARRIER_IDENTITY is None:
            _SYSTEM_LOCK_CARRIER_IDENTITY = carrier_identity
        elif carrier_identity != _SYSTEM_LOCK_CARRIER_IDENTITY:
            raise _unsafe_lock_path(
                path,
                "stable system lock inode was replaced",
            )
        lock_file = os.fdopen(lock_fd, "r", encoding="utf-8")
        lock_fd = -1
        return lock_file
    except FileLockUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise _unsafe_lock_path(
            path,
            f"stable system lock unavailable: {exc}",
        ) from exc
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)


def _open_lock_file_nofollow(path: Path) -> TextIO:
    """Open a regular, single-link lock file without following its parent or leaf."""

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if not nofollow:
        raise _unsafe_lock_path(path, "platform lacks no-follow opens")

    parent_fd = -1
    lock_fd = -1
    try:
        parent_fd = _open_directory_path_nofollow(
            path.parent,
            create=True,
        )
        opened_parent = os.fstat(parent_fd)
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
        named = os.stat(
            path.name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(opened.st_mode):
            raise _unsafe_lock_path(path, "lock target is not a regular file")
        if opened.st_nlink != 1:
            raise _unsafe_lock_path(path, "lock target has multiple hard links")
        if (
            opened.st_dev,
            opened.st_ino,
        ) != (
            named.st_dev,
            named.st_ino,
        ):
            raise _unsafe_lock_path(path, "lock target identity changed")

        final_parent_fd = _open_directory_path_nofollow(path.parent)
        try:
            final_parent = os.fstat(final_parent_fd)
            if (final_parent.st_dev, final_parent.st_ino) != (
                opened_parent.st_dev,
                opened_parent.st_ino,
            ):
                raise _unsafe_lock_path(path, "lock parent identity changed")
        finally:
            os.close(final_parent_fd)
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


def _validate_lock_metadata(
    path: Path,
    *,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> None:
    if _run_lock_scope(path) is not None:
        _open_run_lock_metadata_nofollow(
            path,
            run_root_descriptor=run_root_descriptor,
            expected_run_root_identity=expected_run_root_identity,
        )
        return
    if run_root_descriptor is not None or expected_run_root_identity is not None:
        raise _unsafe_lock_path(
            path,
            "pinned run descriptor requires a run-scoped .locks path",
        )
    lock_file = _open_lock_file_nofollow(path)
    lock_file.close()


def _try_lock(
    path: Path,
    *,
    slot: int | None = None,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> FileLockLease | None:
    _validate_lock_metadata(
        path,
        run_root_descriptor=run_root_descriptor,
        expected_run_root_identity=expected_run_root_identity,
    )
    lock_offsets = _lock_offsets(
        path,
        expected_run_root_identity=expected_run_root_identity,
    )
    with _ACTIVE_LEASES_GUARD:
        lock_file = _open_system_lock_file(path)
        try:
            for lock_offset in lock_offsets:
                _set_open_file_description_lock(
                    lock_file.fileno(),
                    offset=lock_offset,
                    lock_type=fcntl.F_WRLCK,
                )
        except OSError as exc:
            lock_file.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return None
            raise _unsafe_lock_path(
                path,
                f"stable system lock unavailable: {exc}",
            ) from exc
        except BaseException:
            lock_file.close()
            raise
        lease = FileLockLease(
            path=path,
            file=lock_file,
            slot=slot,
            lock_offset=lock_offsets[0],
            lock_offsets=lock_offsets,
            owner_pid=os.getpid(),
        )
        _ACTIVE_LEASES[id(lease)] = lease
    try:
        _validate_lock_metadata(
            path,
            run_root_descriptor=run_root_descriptor,
            expected_run_root_identity=expected_run_root_identity,
        )
    except BaseException:
        lease.release()
        raise
    return lease


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise _AcquisitionCancelled


def _wait_before_retry(cancel_event: threading.Event | None) -> None:
    if cancel_event is None:
        time.sleep(0.05)
    elif cancel_event.wait(0.05):
        raise _AcquisitionCancelled


def _acquire_file_lock(
    path: Path,
    *,
    wait: bool,
    timeout_seconds: float | None,
    cancel_event: threading.Event | None = None,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> FileLockLease:
    deadline = (
        None
        if timeout_seconds is None
        else time.monotonic() + max(0.0, timeout_seconds)
    )
    while True:
        _raise_if_cancelled(cancel_event)
        held = _try_lock(
            path,
            run_root_descriptor=run_root_descriptor,
            expected_run_root_identity=expected_run_root_identity,
        )
        if held is not None:
            if cancel_event is not None and cancel_event.is_set():
                held.release()
                raise _AcquisitionCancelled
            return held
        if not wait or (deadline is not None and time.monotonic() >= deadline):
            raise FileLockUnavailable(f"file lock is already held: {path}")
        _wait_before_retry(cancel_event)


@contextmanager
def sync_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> Iterator[Path]:
    """Hold the same advisory lock used by async server artifact writers."""

    held = _acquire_file_lock(
        path,
        wait=wait,
        timeout_seconds=timeout_seconds,
        run_root_descriptor=run_root_descriptor,
        expected_run_root_identity=expected_run_root_identity,
    )
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
    cancel_event: threading.Event | None = None,
) -> FileLockLease:
    slot_count = max(1, int(slots))
    safe_namespace = _safe_namespace(namespace)
    deadline = (
        None
        if timeout_seconds is None
        else time.monotonic() + max(0.0, timeout_seconds)
    )
    while True:
        _raise_if_cancelled(cancel_event)
        for slot in range(slot_count):
            held = _try_lock(
                lock_dir / f"{safe_namespace}-{slot:02d}.lock",
                slot=slot,
            )
            if held is not None:
                if cancel_event is not None and cancel_event.is_set():
                    held.release()
                    raise _AcquisitionCancelled
                return held
        if deadline is not None and time.monotonic() >= deadline:
            raise FileLockUnavailable(
                f"no {safe_namespace} slot became available within {timeout_seconds} seconds"
            )
        _wait_before_retry(cancel_event)


async def _cancellable_thread_acquire(
    acquire: Callable[..., FileLockLease],
    /,
    *args: object,
    **kwargs: object,
) -> FileLockLease:
    cancel_event = threading.Event()
    kwargs["cancel_event"] = cancel_event
    worker = asyncio.create_task(
        asyncio.to_thread(acquire, *args, **kwargs)
    )
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel_event.set()
        try:
            orphaned = await asyncio.shield(worker)
        except _AcquisitionCancelled:
            pass
        except BaseException:
            pass
        else:
            await asyncio.to_thread(orphaned.release)
        raise


@asynccontextmanager
async def async_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> AsyncIterator[Path]:
    held = await acquire_file_lock(
        path,
        wait=wait,
        timeout_seconds=timeout_seconds,
        run_root_descriptor=run_root_descriptor,
        expected_run_root_identity=expected_run_root_identity,
    )
    try:
        yield held.path
    finally:
        await asyncio.to_thread(held.release)


async def acquire_file_lock(
    path: Path,
    *,
    wait: bool = True,
    timeout_seconds: float | None = None,
    run_root_descriptor: int | None = None,
    expected_run_root_identity: tuple[int, int] | None = None,
) -> FileLockLease:
    return await _cancellable_thread_acquire(
        _acquire_file_lock,
        path,
        wait=wait,
        timeout_seconds=timeout_seconds,
        run_root_descriptor=run_root_descriptor,
        expected_run_root_identity=expected_run_root_identity,
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
    held = await _cancellable_thread_acquire(
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
