"""Native, no-gap exchange of two filesystem names.

The ToC runtime already requires POSIX dirfd and no-follow support.  For an
existing canonical artifact we additionally require the Darwin/Linux atomic
exchange primitive so concurrent readers see either the old or the new name,
never a transient ENOENT window.
"""

from __future__ import annotations

import ctypes
import errno
import os
import sys


class AtomicExchangeUnavailableError(OSError):
    """The platform cannot safely exchange two names atomically."""


def atomic_exchange_names(
    source_dir_fd: int,
    source_name: str,
    destination_dir_fd: int,
    destination_name: str,
) -> None:
    """Atomically swap two existing leaf names without following either."""

    for name in (source_name, destination_name):
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"atomic exchange requires a leaf name: {name!r}")

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        operation = getattr(libc, "renameatx_np", None)
        exchange_flag = 0x00000002  # RENAME_SWAP
    elif sys.platform.startswith("linux"):
        operation = getattr(libc, "renameat2", None)
        exchange_flag = 0x00000002  # RENAME_EXCHANGE
    else:
        operation = None
        exchange_flag = 0
    if operation is None:
        raise AtomicExchangeUnavailableError(
            errno.ENOTSUP,
            "native atomic name exchange is unavailable",
        )

    operation.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    operation.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = operation(
        source_dir_fd,
        os.fsencode(source_name),
        destination_dir_fd,
        os.fsencode(destination_name),
        exchange_flag,
    )
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        if error_number in {
            errno.ENOSYS,
            errno.ENOTSUP,
            getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
        }:
            raise AtomicExchangeUnavailableError(
                error_number,
                "native atomic name exchange is unavailable",
            )
        raise OSError(
            error_number,
            os.strerror(error_number),
            f"{source_name} <-> {destination_name}",
        )

