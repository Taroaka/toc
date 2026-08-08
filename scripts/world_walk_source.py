from __future__ import annotations

import hashlib
import os
import secrets
import stat
from pathlib import Path

from toc.atomic_exchange import atomic_exchange_names


PathIdentity = tuple[int, int]
_CLEANUP_DIRECTORY_NONCE = secrets.token_hex(16)


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _file_read_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_root_directory(
    root: Path,
    *,
    expected_identity: PathIdentity | None = None,
) -> int:
    try:
        lexical = root.lstat()
    except OSError as exc:
        raise ValueError(f"directory is unavailable: {root}") from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise ValueError(f"directory must be a real directory: {root}")
    try:
        descriptor = os.open(root, _directory_open_flags())
    except OSError as exc:
        raise ValueError(f"directory could not be opened safely: {root}") from exc
    opened = os.fstat(descriptor)
    identity = (opened.st_dev, opened.st_ino)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino)
        or (expected_identity is not None and identity != expected_identity)
    ):
        os.close(descriptor)
        raise ValueError(f"directory identity changed: {root}")
    return descriptor


def directory_identity_nofollow(root: Path) -> PathIdentity:
    descriptor = _open_root_directory(root)
    try:
        opened = os.fstat(descriptor)
        return opened.st_dev, opened.st_ino
    finally:
        os.close(descriptor)


def directory_identity_relative_nofollow(
    root: Path,
    relative_path: str | Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> PathIdentity:
    relative = Path(relative_path)
    parts = _safe_relative_parts(root, root / relative)
    root_descriptor = _open_root_directory(
        root,
        expected_identity=expected_root_identity,
    )
    directory_descriptor: int | None = None
    try:
        directory_descriptor = _open_parent_directory(
            root_descriptor,
            parts,
            create=False,
        )
        opened = os.fstat(directory_descriptor)
        return opened.st_dev, opened.st_ino
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        os.close(root_descriptor)


def open_directory_nofollow(
    root: Path,
    *,
    expected_identity: PathIdentity | None = None,
) -> int:
    """Open and pin a real directory; the caller owns the returned fd."""

    return _open_root_directory(
        root,
        expected_identity=expected_identity,
    )


def ensure_directory_relative_nofollow(
    root: Path,
    relative_path: str | Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> PathIdentity:
    relative = Path(relative_path)
    parts = _safe_relative_parts(root, root / relative)
    root_descriptor = _open_root_directory(
        root,
        expected_identity=expected_root_identity,
    )
    directory_descriptor: int | None = None
    try:
        directory_descriptor = _open_parent_directory(
            root_descriptor,
            parts,
            create=True,
        )
        opened = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValueError(
                f"destination must be a directory: "
                f"{relative.as_posix()}"
            )
        return opened.st_dev, opened.st_ino
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        os.close(root_descriptor)


def _safe_relative_parts(root: Path, path: Path) -> tuple[str, ...]:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes its root: {path}") from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} or "/" in part for part in relative.parts)
    ):
        raise ValueError(f"path is not a safe rooted file path: {path}")
    return relative.parts


def _open_parent_directory(
    root_descriptor: int,
    parent_parts: tuple[str, ...],
    *,
    create: bool,
) -> int:
    current = os.dup(root_descriptor)
    try:
        for part in parent_parts:
            try:
                child = os.open(
                    part,
                    _directory_open_flags(),
                    dir_fd=current,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, 0o755, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(
                    part,
                    _directory_open_flags(),
                    dir_fd=current,
                )
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _open_regular_file(
    root: Path,
    relative_path: Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> tuple[
    int,
    os.stat_result,
    int,
    PathIdentity,
    PathIdentity,
]:
    parts = _safe_relative_parts(root, root / relative_path)
    root_descriptor = _open_root_directory(
        root,
        expected_identity=expected_root_identity,
    )
    root_stat = os.fstat(root_descriptor)
    root_identity = root_stat.st_dev, root_stat.st_ino
    try:
        parent_descriptor = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=False,
        )
    finally:
        os.close(root_descriptor)
    parent_stat = os.fstat(parent_descriptor)
    parent_identity = parent_stat.st_dev, parent_stat.st_ino
    descriptor: int | None = None
    try:
        lexical = os.stat(
            parts[-1],
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(lexical.st_mode):
            raise ValueError(
                f"source must be a regular file: {relative_path.as_posix()}"
            )
        descriptor = os.open(
            parts[-1],
            _file_read_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(lexical):
            raise ValueError(
                f"source identity changed: {relative_path.as_posix()}"
            )
        return (
            descriptor,
            opened,
            parent_descriptor,
            parent_identity,
            root_identity,
        )
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_descriptor)
        raise


def _verify_opened_regular_path_identity(
    *,
    root: Path,
    relative_path: Path,
    opened_file: os.stat_result,
    expected_root_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    operation: str,
) -> None:
    parts = _safe_relative_parts(root, root / relative_path)
    root_descriptor = _open_root_directory(
        root,
        expected_identity=expected_root_identity,
    )
    verification_parent: int | None = None
    try:
        verification_parent = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=False,
        )
        parent_stat = os.fstat(verification_parent)
        if (
            parent_stat.st_dev,
            parent_stat.st_ino,
        ) != expected_parent_identity:
            raise ValueError(
                f"source parent identity changed after {operation}: "
                f"{relative_path.as_posix()}"
            )
        current = os.stat(
            parts[-1],
            dir_fd=verification_parent,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(current.st_mode)
            or (
                current.st_dev,
                current.st_ino,
                stat.S_IFMT(current.st_mode),
            )
            != (
                opened_file.st_dev,
                opened_file.st_ino,
                stat.S_IFMT(opened_file.st_mode),
            )
        ):
            raise ValueError(
                f"source path identity changed after {operation}: "
                f"{relative_path.as_posix()}"
            )
    finally:
        if verification_parent is not None:
            os.close(verification_parent)
        os.close(root_descriptor)


def read_regular_file_nofollow(
    root: Path,
    relative_path: str | Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> bytes:
    relative = Path(relative_path)
    (
        descriptor,
        opened,
        parent_descriptor,
        parent_identity,
        root_identity,
    ) = _open_regular_file(
        root,
        relative,
        expected_root_identity=expected_root_identity,
    )
    chunks: list[bytes] = []
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(opened):
            raise ValueError(f"source changed while reading: {relative.as_posix()}")
        _verify_opened_regular_path_identity(
            root=root,
            relative_path=relative,
            opened_file=opened,
            expected_root_identity=root_identity,
            expected_parent_identity=parent_identity,
            operation="reading",
        )
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)
    return b"".join(chunks)


def sha256_regular_file_nofollow(
    root: Path,
    relative_path: str | Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> str:
    relative = Path(relative_path)
    (
        descriptor,
        opened,
        parent_descriptor,
        parent_identity,
        root_identity,
    ) = _open_regular_file(
        root,
        relative,
        expected_root_identity=expected_root_identity,
    )
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(opened):
            raise ValueError(
                f"source changed while hashing: {relative.as_posix()}"
            )
        _verify_opened_regular_path_identity(
            root=root,
            relative_path=relative,
            opened_file=opened,
            expected_root_identity=root_identity,
            expected_parent_identity=parent_identity,
            operation="hashing",
        )
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)
    return digest.hexdigest()


def _entry_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
    )


def _open_cleanup_directory_nofollow(parent_descriptor: int) -> int | None:
    """Open an owner-only-by-mode cleanup namespace.

    Mode 0700 excludes other UIDs. Portable POSIX operations cannot isolate
    this namespace from a hostile peer running under the same UID.
    """

    directory_name = (
        f".toc-cleanup-{os.getpid()}-{_CLEANUP_DIRECTORY_NONCE}"
    )
    created = False
    try:
        os.mkdir(directory_name, 0o700, dir_fd=parent_descriptor)
        created = True
    except FileExistsError:
        pass
    except OSError:
        return None

    try:
        descriptor = os.open(
            directory_name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
    except OSError:
        return None

    try:
        opened = os.fstat(descriptor)
        named = os.stat(
            directory_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _entry_identity(named) != _entry_identity(opened)
            or opened.st_uid != os.geteuid()
        ):
            raise OSError("cleanup directory is unsafe")
        if created:
            os.fchmod(descriptor, 0o700)
            opened = os.fstat(descriptor)
        if stat.S_IMODE(opened.st_mode) != 0o700:
            raise OSError("cleanup directory is writable by peers")
    except OSError:
        os.close(descriptor)
        return None
    return descriptor


def _link_protected_entry_without_clobber(
    *,
    cleanup_descriptor: int,
    cleanup_name: str,
    parent_descriptor: int,
    destination_name: str,
) -> tuple[bool, bool]:
    try:
        os.link(
            cleanup_name,
            destination_name,
            src_dir_fd=cleanup_descriptor,
            dst_dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False, False
    try:
        os.unlink(cleanup_name, dir_fd=cleanup_descriptor)
    except OSError:
        return True, False
    return True, True


def _restore_quarantined_entry_nofollow(
    *,
    parent_descriptor: int,
    quarantine_name: str,
    original_name: str,
    quarantined_identity: tuple[int, int, int],
) -> bool:
    try:
        current = os.stat(
            quarantine_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return False
    if _entry_identity(current) != quarantined_identity:
        return False

    cleanup_descriptor = _open_cleanup_directory_nofollow(
        parent_descriptor
    )
    if cleanup_descriptor is None:
        return False
    cleanup_name = f"entry-{secrets.token_hex(16)}"
    try:
        try:
            os.rename(
                quarantine_name,
                cleanup_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=cleanup_descriptor,
            )
        except FileNotFoundError:
            return False
        try:
            staged = os.stat(
                cleanup_name,
                dir_fd=cleanup_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        if _entry_identity(staged) != quarantined_identity:
            _link_protected_entry_without_clobber(
                cleanup_descriptor=cleanup_descriptor,
                cleanup_name=cleanup_name,
                parent_descriptor=parent_descriptor,
                destination_name=quarantine_name,
            )
            return False
        restored, alias_cleaned = _link_protected_entry_without_clobber(
            cleanup_descriptor=cleanup_descriptor,
            cleanup_name=cleanup_name,
            parent_descriptor=parent_descriptor,
            destination_name=original_name,
        )
        if restored:
            return alias_cleaned
        _link_protected_entry_without_clobber(
            cleanup_descriptor=cleanup_descriptor,
            cleanup_name=cleanup_name,
            parent_descriptor=parent_descriptor,
            destination_name=quarantine_name,
        )
        return False
    finally:
        os.close(cleanup_descriptor)


def _cleanup_name_nofollow(
    *,
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int, int],
    dispose: bool,
) -> bool:
    """Detach a matching entry through a protected cleanup directory.

    A source-name replacement is restored without clobbering, and its
    protected alias is removed only after the public link succeeds. Entries
    explicitly classified as ambiguous can instead remain quarantined.
    """

    try:
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return True
    if _entry_identity(current) != expected_identity:
        return False

    cleanup_descriptor = _open_cleanup_directory_nofollow(
        parent_descriptor
    )
    if cleanup_descriptor is None:
        return False
    cleanup_name = f"entry-{secrets.token_hex(16)}"
    try:
        try:
            os.rename(
                name,
                cleanup_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=cleanup_descriptor,
            )
        except FileNotFoundError:
            return False

        try:
            quarantined = os.stat(
                cleanup_name,
                dir_fd=cleanup_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        if _entry_identity(quarantined) != expected_identity:
            _link_protected_entry_without_clobber(
                cleanup_descriptor=cleanup_descriptor,
                cleanup_name=cleanup_name,
                parent_descriptor=parent_descriptor,
                destination_name=name,
            )
            return False
        if not dispose:
            return True
        try:
            os.unlink(cleanup_name, dir_fd=cleanup_descriptor)
        except OSError:
            _link_protected_entry_without_clobber(
                cleanup_descriptor=cleanup_descriptor,
                cleanup_name=cleanup_name,
                parent_descriptor=parent_descriptor,
                destination_name=name,
            )
            return False
        return True
    finally:
        os.close(cleanup_descriptor)


def _remove_owned_name_nofollow(
    *,
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    return _cleanup_name_nofollow(
        parent_descriptor=parent_descriptor,
        name=name,
        expected_identity=expected_identity,
        dispose=True,
    )


def _quarantine_ambiguous_name_nofollow(
    *,
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    return _cleanup_name_nofollow(
        parent_descriptor=parent_descriptor,
        name=name,
        expected_identity=expected_identity,
        dispose=False,
    )


def _fsync_rollback_namespaces(parent_descriptor: int) -> str:
    """Persist both sides of rollback namespace mutations.

    The cleanup directory participates in cross-directory renames, while the
    caller's parent directory contains the canonical destination.  Both must
    be synced before a rollback can be reported as durable.
    """

    failures: list[str] = []
    cleanup_descriptor = _open_cleanup_directory_nofollow(
        parent_descriptor
    )
    if cleanup_descriptor is None:
        failures.append("protected cleanup namespace is unavailable")
    try:
        os.fsync(parent_descriptor)
    except OSError as exc:
        failures.append(f"destination parent fsync failed: {exc}")
    if cleanup_descriptor is not None:
        try:
            os.fsync(cleanup_descriptor)
        except OSError as exc:
            failures.append(f"protected cleanup namespace fsync failed: {exc}")
        finally:
            os.close(cleanup_descriptor)
    return "; ".join(failures)


def write_regular_file_nofollow(
    *,
    destination_root: Path,
    destination_relative: str | Path,
    data: bytes,
    expected_destination_root_identity: PathIdentity | None = None,
    exclusive: bool = False,
) -> str:
    destination_rel = Path(destination_relative)
    parts = _safe_relative_parts(
        destination_root,
        destination_root / destination_rel,
    )
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    temporary_descriptor: int | None = None
    verification_parent: int | None = None
    verification_file: int | None = None
    temporary_name = ""
    temporary_identity: tuple[int, int, int] | None = None
    temporary_named_identity: tuple[int, int, int] | None = None
    previous_identity: tuple[int, int, int] | None = None
    destination_published = False
    exchange_completed = False
    publication_committed = False
    preserve_temporary = False
    rollback_attempted = False
    unexpected_published_identity: tuple[int, int, int] | None = None
    unexpected_temporary_identity: tuple[int, int, int] | None = None
    try:
        root_descriptor = _open_root_directory(
            destination_root,
            expected_identity=expected_destination_root_identity,
        )
        root_stat = os.fstat(root_descriptor)
        root_identity = root_stat.st_dev, root_stat.st_ino
        parent_descriptor = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=True,
        )
        opened_parent = os.fstat(parent_descriptor)
        destination_name = parts[-1]
        try:
            previous = os.stat(
                destination_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            previous = None
        if previous is not None:
            if exclusive:
                raise FileExistsError(
                    f"destination already exists: "
                    f"{destination_rel.as_posix()}"
                )
            if not stat.S_ISREG(previous.st_mode):
                raise ValueError(
                    f"destination must be a regular file, not a symlink "
                    f"or special file: {destination_rel.as_posix()}"
                )
            previous_identity = _entry_identity(previous)

        temporary_name = (
            f".{destination_name}.write-{os.getpid()}-"
            f"{secrets.token_hex(16)}"
        )
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        opened_temporary = os.fstat(temporary_descriptor)
        temporary_identity = _entry_identity(opened_temporary)
        temporary_named_identity = temporary_identity
        if (
            not stat.S_ISREG(opened_temporary.st_mode)
            or opened_temporary.st_nlink != 1
        ):
            raise ValueError(
                f"destination temporary file is unsafe: "
                f"{destination_rel.as_posix()}"
            )
        remaining = memoryview(data)
        while remaining:
            written = os.write(temporary_descriptor, remaining)
            if written <= 0:
                raise OSError("destination write made no progress")
            remaining = remaining[written:]
        os.fsync(temporary_descriptor)
        written_temporary = os.fstat(temporary_descriptor)
        if (
            not stat.S_ISREG(written_temporary.st_mode)
            or written_temporary.st_nlink != 1
            or _entry_identity(written_temporary) != temporary_identity
        ):
            raise ValueError(
                f"destination temporary file identity changed: "
                f"{destination_rel.as_posix()}"
            )
        expected_digest = hashlib.sha256(data).hexdigest()
        os.lseek(temporary_descriptor, 0, os.SEEK_SET)
        temporary_digest = hashlib.sha256()
        while True:
            chunk = os.read(temporary_descriptor, 1024 * 1024)
            if not chunk:
                break
            temporary_digest.update(chunk)
        if (
            temporary_digest.hexdigest() != expected_digest
            or _stat_identity(os.fstat(temporary_descriptor))
            != _stat_identity(written_temporary)
        ):
            raise ValueError(
                f"destination temporary sha256 mismatch: "
                f"{destination_rel.as_posix()}"
            )
        named_temporary = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _entry_identity(named_temporary) != temporary_identity
            or named_temporary.st_nlink != 1
        ):
            raise ValueError(
                f"destination temporary path identity changed: "
                f"{destination_rel.as_posix()}"
            )

        verification_parent = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=False,
        )
        verified_parent = os.fstat(verification_parent)
        if (
            verified_parent.st_dev,
            verified_parent.st_ino,
        ) != (
            opened_parent.st_dev,
            opened_parent.st_ino,
        ):
            raise ValueError(
                f"destination parent identity changed: "
                f"{destination_rel.as_posix()}"
            )
        verified_root_descriptor = _open_root_directory(
            destination_root,
            expected_identity=root_identity,
        )
        os.close(verified_root_descriptor)

        try:
            current_destination = os.stat(
                destination_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            current_destination = None
        if previous_identity is None:
            if current_destination is not None:
                raise ValueError(
                    f"destination appeared before publishing: "
                    f"{destination_rel.as_posix()}"
                )
        elif (
            current_destination is None
            or _entry_identity(current_destination) != previous_identity
        ):
            raise ValueError(
                f"destination changed before publishing: "
                f"{destination_rel.as_posix()}"
            )
        if previous_identity is not None:
            try:
                atomic_exchange_names(
                    parent_descriptor,
                    temporary_name,
                    parent_descriptor,
                    destination_name,
                )
            except BaseException:
                try:
                    exchanged_destination = os.stat(
                        destination_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    exchanged_temporary = os.stat(
                        temporary_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    exchanged_destination = None
                    exchanged_temporary = None
                if (
                    exchanged_destination is not None
                    and exchanged_temporary is not None
                    and _entry_identity(exchanged_destination)
                    == temporary_identity
                    and _entry_identity(exchanged_temporary)
                    == previous_identity
                ):
                    exchange_completed = True
                    destination_published = True
                    temporary_named_identity = previous_identity
                raise
            exchange_completed = True
            destination_published = True
            temporary_named_identity = previous_identity
        else:
            try:
                os.link(
                    temporary_name,
                    destination_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ValueError(
                    f"destination appeared while publishing: "
                    f"{destination_rel.as_posix()}"
                ) from exc
            destination_published = True

        published = os.stat(
            destination_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _entry_identity(published) != temporary_identity:
            held_temporary = os.fstat(temporary_descriptor)
            named_temporary = None
            if temporary_name:
                try:
                    named_temporary = os.stat(
                        temporary_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    named_temporary = None
            if held_temporary.st_nlink == 0:
                unexpected_published_identity = _entry_identity(published)
                if (
                    named_temporary is not None
                    and _entry_identity(named_temporary)
                    == unexpected_published_identity
                ):
                    unexpected_temporary_identity = _entry_identity(
                        named_temporary
                    )
            raise ValueError(
                f"destination identity changed while publishing: "
                f"{destination_rel.as_posix()}"
            )
        if previous_identity is not None:
            exchanged_temporary = os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if _entry_identity(exchanged_temporary) != previous_identity:
                unexpected_temporary_identity = _entry_identity(
                    exchanged_temporary
                )
                raise ValueError(
                    f"destination rollback name changed while publishing: "
                    f"{destination_rel.as_posix()}"
                )
        else:
            linked_temporary = os.fstat(temporary_descriptor)
            if linked_temporary.st_nlink != 2:
                raise ValueError(
                    f"destination temporary link count changed: "
                    f"{destination_rel.as_posix()}"
                )
            if not _remove_owned_name_nofollow(
                parent_descriptor=parent_descriptor,
                name=temporary_name,
                expected_identity=temporary_identity,
            ):
                raise ValueError(
                    f"destination temporary path changed while publishing: "
                    f"{destination_rel.as_posix()}"
                )
            temporary_name = ""
            temporary_named_identity = None

        verification_file = os.open(
            destination_name,
            _file_read_flags(),
            dir_fd=parent_descriptor,
        )
        verified_file = os.fstat(verification_file)
        if _entry_identity(verified_file) != temporary_identity:
            raise ValueError(
                f"destination identity changed after publishing: "
                f"{destination_rel.as_posix()}"
            )
        published_digest = hashlib.sha256()
        while True:
            chunk = os.read(verification_file, 1024 * 1024)
            if not chunk:
                break
            published_digest.update(chunk)
        if (
            published_digest.hexdigest() != expected_digest
            or _stat_identity(os.fstat(verification_file))
            != _stat_identity(verified_file)
        ):
            raise ValueError(
                f"destination sha256 mismatch after publishing: "
                f"{destination_rel.as_posix()}"
            )
        _verify_opened_regular_path_identity(
            root=destination_root,
            relative_path=destination_rel,
            opened_file=verified_file,
            expected_root_identity=root_identity,
            expected_parent_identity=(
                opened_parent.st_dev,
                opened_parent.st_ino,
            ),
            operation="writing",
        )
        os.fsync(parent_descriptor)
        publication_committed = True
        if (
            previous_identity is not None
            and temporary_name
            and temporary_named_identity is not None
        ):
            try:
                old_destination_removed = _remove_owned_name_nofollow(
                    parent_descriptor=parent_descriptor,
                    name=temporary_name,
                    expected_identity=temporary_named_identity,
                )
            except OSError:
                old_destination_removed = False
            if old_destination_removed:
                temporary_name = ""
                temporary_named_identity = None
            else:
                preserve_temporary = True
        return expected_digest
    except BaseException as exc:
        rollback_failure = ""
        rollback_durability_failure = ""
        if (
            destination_published
            and not publication_committed
            and parent_descriptor is not None
            and temporary_identity is not None
        ):
            rollback_attempted = True
            try:
                try:
                    current_destination = os.stat(
                        parts[-1],
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    current_destination = None
                if previous_identity is not None and exchange_completed:
                    try:
                        current_temporary = os.stat(
                            temporary_name,
                            dir_fd=parent_descriptor,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        current_temporary = None
                    destination_identity = (
                        _entry_identity(current_destination)
                        if current_destination is not None
                        else None
                    )
                    named_temporary_identity = (
                        _entry_identity(current_temporary)
                        if current_temporary is not None
                        else None
                    )
                    cleanup_after_rollback_identity = None
                    quarantine_after_rollback_identity = None
                    rollback_restored = (
                        destination_identity == previous_identity
                        and named_temporary_identity == temporary_identity
                    )
                    if rollback_restored:
                        cleanup_after_rollback_identity = temporary_identity
                    if (
                        not rollback_restored
                        and current_destination is not None
                        and current_temporary is not None
                        and stat.S_ISREG(current_destination.st_mode)
                        and stat.S_ISREG(current_temporary.st_mode)
                    ):
                        before_rollback_destination = destination_identity
                        before_rollback_temporary = named_temporary_identity
                        rollback_exchange_error: BaseException | None = None
                        try:
                            atomic_exchange_names(
                                parent_descriptor,
                                temporary_name,
                                parent_descriptor,
                                parts[-1],
                            )
                        except BaseException as exchange_exc:
                            rollback_exchange_error = exchange_exc
                        try:
                            restored_destination = os.stat(
                                parts[-1],
                                dir_fd=parent_descriptor,
                                follow_symlinks=False,
                            )
                            restored_temporary = os.stat(
                                temporary_name,
                                dir_fd=parent_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            restored_destination = None
                            restored_temporary = None
                        rollback_restored = (
                            restored_destination is not None
                            and restored_temporary is not None
                            and _entry_identity(restored_destination)
                            == before_rollback_temporary
                            and _entry_identity(restored_temporary)
                            == before_rollback_destination
                        )
                        if (
                            rollback_restored
                            and before_rollback_destination
                            == temporary_identity
                        ):
                            cleanup_after_rollback_identity = (
                                temporary_identity
                            )
                        elif rollback_restored:
                            quarantine_after_rollback_identity = (
                                before_rollback_destination
                            )
                        if rollback_exchange_error and not rollback_restored:
                            rollback_failure = (
                                "atomic rollback exchange failed "
                                f"({rollback_exchange_error})"
                            )
                    if rollback_restored:
                        destination_published = False
                        temporary_named_identity = (
                            cleanup_after_rollback_identity
                        )
                        if cleanup_after_rollback_identity is not None:
                            try:
                                removed_temporary = (
                                    _remove_owned_name_nofollow(
                                        parent_descriptor=parent_descriptor,
                                        name=temporary_name,
                                        expected_identity=(
                                            cleanup_after_rollback_identity
                                        ),
                                    )
                                )
                            except OSError:
                                removed_temporary = False
                            if removed_temporary:
                                temporary_name = ""
                                temporary_named_identity = None
                            elif not rollback_failure:
                                preserve_temporary = True
                                rollback_failure = (
                                    "rollback temporary cleanup failed"
                                )
                        else:
                            quarantined_temporary = False
                            if quarantine_after_rollback_identity is not None:
                                try:
                                    quarantined_temporary = (
                                        _quarantine_ambiguous_name_nofollow(
                                            parent_descriptor=(
                                                parent_descriptor
                                            ),
                                            name=temporary_name,
                                            expected_identity=(
                                                quarantine_after_rollback_identity
                                            ),
                                        )
                                    )
                                except OSError:
                                    quarantined_temporary = False
                            if quarantined_temporary:
                                temporary_name = ""
                                temporary_named_identity = None
                            else:
                                preserve_temporary = True
                    else:
                        preserve_temporary = True
                        try:
                            stranded_temporary = os.stat(
                                temporary_name,
                                dir_fd=parent_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            stranded_temporary = None
                        if (
                            stranded_temporary is not None
                            and _entry_identity(stranded_temporary)
                            == previous_identity
                            and _quarantine_ambiguous_name_nofollow(
                                parent_descriptor=parent_descriptor,
                                name=temporary_name,
                                expected_identity=previous_identity,
                            )
                        ):
                            temporary_name = ""
                            temporary_named_identity = None
                        if not rollback_failure:
                            rollback_failure = (
                                "destination changed before safe rollback"
                            )
                elif previous_identity is None and current_destination is not None:
                    removed_destination = _remove_owned_name_nofollow(
                        parent_descriptor=parent_descriptor,
                        name=parts[-1],
                        expected_identity=temporary_identity,
                    )
                    if (
                        not removed_destination
                        and unexpected_published_identity is not None
                    ):
                        removed_destination = (
                            _quarantine_ambiguous_name_nofollow(
                                parent_descriptor=parent_descriptor,
                                name=parts[-1],
                                expected_identity=unexpected_published_identity,
                            )
                        )
                    if not removed_destination:
                        rollback_failure = (
                            "destination changed before safe rollback"
                        )
                if previous_identity is None and temporary_name:
                    try:
                        removed_temporary = _remove_owned_name_nofollow(
                            parent_descriptor=parent_descriptor,
                            name=temporary_name,
                            expected_identity=temporary_identity,
                        )
                    except OSError:
                        removed_temporary = False
                    if (
                        not removed_temporary
                        and unexpected_temporary_identity is not None
                    ):
                        removed_temporary = (
                            _quarantine_ambiguous_name_nofollow(
                                parent_descriptor=parent_descriptor,
                                name=temporary_name,
                                expected_identity=(
                                    unexpected_temporary_identity
                                ),
                            )
                        )
                    if removed_temporary:
                        temporary_name = ""
            except Exception as rollback_exc:
                preserve_temporary = True
                rollback_failure = (
                    "rollback namespace mutation failed "
                    f"({rollback_exc})"
                )
            finally:
                try:
                    rollback_durability_failure = (
                        _fsync_rollback_namespaces(parent_descriptor)
                    )
                except Exception as rollback_fsync_exc:
                    rollback_durability_failure = (
                        "rollback namespace fsync could not complete: "
                        f"{rollback_fsync_exc}"
                    )
        if rollback_durability_failure:
            preserve_temporary = True
            raise ValueError(
                f"{exc}; rollback durability could not be proved "
                f"({rollback_durability_failure}): "
                f"{destination_rel.as_posix()}"
            ) from exc
        if rollback_failure:
            raise ValueError(
                f"{exc}; {rollback_failure}: "
                f"{destination_rel.as_posix()}"
            ) from exc
        raise
    finally:
        if verification_file is not None:
            os.close(verification_file)
        if verification_parent is not None:
            os.close(verification_parent)
        if (
            temporary_name
            and parent_descriptor is not None
            and not rollback_attempted
            and not preserve_temporary
        ):
            removed_temporary = (
                temporary_named_identity is not None
                and _remove_owned_name_nofollow(
                    parent_descriptor=parent_descriptor,
                    name=temporary_name,
                    expected_identity=temporary_named_identity,
                )
            )
            if (
                not removed_temporary
                and unexpected_temporary_identity is not None
            ):
                _quarantine_ambiguous_name_nofollow(
                    parent_descriptor=parent_descriptor,
                    name=temporary_name,
                    expected_identity=unexpected_temporary_identity,
                )
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def write_regular_file_exclusive_nofollow(
    *,
    destination_root: Path,
    destination_relative: str | Path,
    data: bytes,
    expected_destination_root_identity: PathIdentity | None = None,
) -> str:
    return write_regular_file_nofollow(
        destination_root=destination_root,
        destination_relative=destination_relative,
        data=data,
        expected_destination_root_identity=(
            expected_destination_root_identity
        ),
        exclusive=True,
    )


def unlink_regular_file_verified_nofollow(
    *,
    root: Path,
    relative_path: str | Path,
    expected_root_identity: PathIdentity,
    expected_sha256: str,
) -> bool:
    relative = Path(relative_path)
    parts = _safe_relative_parts(root, root / relative)
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    file_descriptor: int | None = None
    try:
        root_descriptor = _open_root_directory(
            root,
            expected_identity=expected_root_identity,
        )
        parent_descriptor = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=False,
        )
        lexical = os.stat(
            parts[-1],
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(lexical.st_mode):
            return False
        file_descriptor = os.open(
            parts[-1],
            _file_read_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(file_descriptor)
        if _stat_identity(opened) != _stat_identity(lexical):
            return False
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if (
            digest.hexdigest() != expected_sha256
            or _stat_identity(os.fstat(file_descriptor))
            != _stat_identity(opened)
        ):
            return False
        if not _remove_owned_name_nofollow(
            parent_descriptor=parent_descriptor,
            name=parts[-1],
            expected_identity=_entry_identity(opened),
        ):
            return False
        os.fsync(parent_descriptor)
        return True
    except FileNotFoundError:
        return True
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def copy_regular_file_atomic_nofollow(
    *,
    source_root: Path,
    source_relative: str | Path,
    destination_root: Path,
    destination_relative: str | Path,
    expected_source_root_identity: PathIdentity | None = None,
    expected_destination_root_identity: PathIdentity | None = None,
    expected_sha256: str | None = None,
) -> str:
    source_rel = Path(source_relative)
    destination_rel = Path(destination_relative)
    destination_parts = _safe_relative_parts(
        destination_root,
        destination_root / destination_rel,
    )
    source_descriptor: int | None = None
    source_parent: int | None = None
    destination_root_descriptor: int | None = None
    destination_parent: int | None = None
    destination_descriptor: int | None = None
    published_parent: int | None = None
    published_descriptor: int | None = None
    linked_identity: tuple[int, int, int] | None = None
    temporary_identity: tuple[int, int, int] | None = None
    unexpected_linked_identity: tuple[int, int, int] | None = None
    unexpected_temporary_identity: tuple[int, int, int] | None = None
    publication_committed = False
    temporary_name = ""
    temporary_present = False
    try:
        (
            source_descriptor,
            source_stat,
            source_parent,
            source_parent_identity,
            source_root_identity,
        ) = _open_regular_file(
            source_root,
            source_rel,
            expected_root_identity=expected_source_root_identity,
        )
        destination_root_descriptor = _open_root_directory(
            destination_root,
            expected_identity=expected_destination_root_identity,
        )
        destination_root_stat = os.fstat(destination_root_descriptor)
        destination_root_identity = (
            destination_root_stat.st_dev,
            destination_root_stat.st_ino,
        )
        destination_parent = _open_parent_directory(
            destination_root_descriptor,
            destination_parts[:-1],
            create=True,
        )
        destination_parent_stat = os.fstat(destination_parent)
        destination_name = destination_parts[-1]
        try:
            os.stat(
                destination_name,
                dir_fd=destination_parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise ValueError(
                f"destination already exists: "
                f"{destination_rel.as_posix()}"
            )

        temporary_name = (
            f".{destination_name}.tmp-{os.getpid()}-"
            f"{secrets.token_hex(8)}"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        destination_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=destination_parent,
        )
        temporary_present = True
        opened_temporary = os.fstat(destination_descriptor)
        temporary_identity = _entry_identity(opened_temporary)
        if (
            not stat.S_ISREG(opened_temporary.st_mode)
            or opened_temporary.st_nlink != 1
        ):
            raise ValueError(
                f"destination temporary file is unsafe: "
                f"{destination_rel.as_posix()}"
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(destination_descriptor, remaining)
                if written <= 0:
                    raise OSError("atomic destination write made no progress")
                remaining = remaining[written:]
        actual_sha256 = digest.hexdigest()
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise ValueError(
                f"source sha256 mismatch: {source_rel.as_posix()}"
            )
        if _stat_identity(os.fstat(source_descriptor)) != _stat_identity(
            source_stat
        ):
            raise ValueError(
                f"source changed while copying: {source_rel.as_posix()}"
            )
        _verify_opened_regular_path_identity(
            root=source_root,
            relative_path=source_rel,
            opened_file=source_stat,
            expected_root_identity=source_root_identity,
            expected_parent_identity=source_parent_identity,
            operation="copying",
        )
        os.fsync(destination_descriptor)
        try:
            os.stat(
                destination_name,
                dir_fd=destination_parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise ValueError(
                f"destination appeared while copying: "
                f"{destination_rel.as_posix()}"
            )
        verification_parent = _open_parent_directory(
            destination_root_descriptor,
            destination_parts[:-1],
            create=False,
        )
        try:
            verified_parent_stat = os.fstat(verification_parent)
            if (
                verified_parent_stat.st_dev,
                verified_parent_stat.st_ino,
            ) != (
                destination_parent_stat.st_dev,
                destination_parent_stat.st_ino,
            ):
                raise ValueError(
                    f"destination parent identity changed: "
                    f"{destination_rel.as_posix()}"
                )
        finally:
            os.close(verification_parent)
        try:
            named_temporary = os.stat(
                temporary_name,
                dir_fd=destination_parent,
                follow_symlinks=False,
            )
            if (
                _entry_identity(named_temporary) != temporary_identity
                or named_temporary.st_nlink != 1
            ):
                raise ValueError(
                    f"destination temporary path identity changed: "
                    f"{destination_rel.as_posix()}"
                )
            linked_identity = temporary_identity
            os.link(
                temporary_name,
                destination_name,
                src_dir_fd=destination_parent,
                dst_dir_fd=destination_parent,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise ValueError(
                f"destination appeared while copying: "
                f"{destination_rel.as_posix()}"
            ) from exc
        linked_stat = os.stat(
            destination_name,
            dir_fd=destination_parent,
            follow_symlinks=False,
        )
        if _entry_identity(linked_stat) != linked_identity:
            held_temporary = os.fstat(destination_descriptor)
            try:
                named_after_link = os.stat(
                    temporary_name,
                    dir_fd=destination_parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                named_after_link = None
            if (
                held_temporary.st_nlink == 0
                and named_after_link is not None
                and _entry_identity(named_after_link)
                == _entry_identity(linked_stat)
            ):
                unexpected_linked_identity = _entry_identity(linked_stat)
                unexpected_temporary_identity = _entry_identity(
                    named_after_link
                )
            raise ValueError(
                f"published destination identity mismatch: "
                f"{destination_rel.as_posix()}"
            )
        published_parent = _open_parent_directory(
            destination_root_descriptor,
            destination_parts[:-1],
            create=False,
        )
        published_parent_stat = os.fstat(published_parent)
        if (
            published_parent_stat.st_dev,
            published_parent_stat.st_ino,
        ) != (
            destination_parent_stat.st_dev,
            destination_parent_stat.st_ino,
        ):
            raise ValueError(
                f"destination parent identity changed after publish: "
                f"{destination_rel.as_posix()}"
            )
        published_descriptor = os.open(
            destination_name,
            _file_read_flags(),
            dir_fd=published_parent,
        )
        published_stat = os.fstat(published_descriptor)
        held_temporary_stat = os.fstat(destination_descriptor)
        if (
            published_stat.st_dev,
            published_stat.st_ino,
            stat.S_IFMT(published_stat.st_mode),
        ) != (
            held_temporary_stat.st_dev,
            held_temporary_stat.st_ino,
            stat.S_IFMT(held_temporary_stat.st_mode),
        ):
            raise ValueError(
                f"published destination identity mismatch: "
                f"{destination_rel.as_posix()}"
            )
        published_digest = hashlib.sha256()
        while True:
            chunk = os.read(published_descriptor, 1024 * 1024)
            if not chunk:
                break
            published_digest.update(chunk)
        if published_digest.hexdigest() != actual_sha256:
            raise ValueError(
                f"published destination sha256 mismatch: "
                f"{destination_rel.as_posix()}"
            )
        _verify_opened_regular_path_identity(
            root=destination_root,
            relative_path=destination_rel,
            opened_file=published_stat,
            expected_root_identity=destination_root_identity,
            expected_parent_identity=(
                destination_parent_stat.st_dev,
                destination_parent_stat.st_ino,
            ),
            operation="publishing",
        )
        if not _remove_owned_name_nofollow(
            parent_descriptor=destination_parent,
            name=temporary_name,
            expected_identity=temporary_identity,
        ):
            raise ValueError(
                f"destination temporary path changed after publish: "
                f"{destination_rel.as_posix()}"
            )
        temporary_present = False
        os.fsync(destination_parent)
        publication_committed = True
        return actual_sha256
    finally:
        if published_descriptor is not None:
            os.close(published_descriptor)
        if published_parent is not None:
            os.close(published_parent)
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        if (
            linked_identity is not None
            and not publication_committed
            and destination_parent is not None
        ):
            try:
                removed_publication = _remove_owned_name_nofollow(
                    parent_descriptor=destination_parent,
                    name=destination_parts[-1],
                    expected_identity=linked_identity,
                )
                if (
                    not removed_publication
                    and unexpected_linked_identity is not None
                ):
                    _quarantine_ambiguous_name_nofollow(
                        parent_descriptor=destination_parent,
                        name=destination_parts[-1],
                        expected_identity=unexpected_linked_identity,
                    )
            except OSError:
                pass
        if (
            temporary_present
            and temporary_name
            and destination_parent is not None
        ):
            try:
                if temporary_identity is not None:
                    removed_temporary = _remove_owned_name_nofollow(
                        parent_descriptor=destination_parent,
                        name=temporary_name,
                        expected_identity=temporary_identity,
                    )
                    if (
                        not removed_temporary
                        and unexpected_temporary_identity is not None
                    ):
                        _quarantine_ambiguous_name_nofollow(
                            parent_descriptor=destination_parent,
                            name=temporary_name,
                            expected_identity=unexpected_temporary_identity,
                        )
            except OSError:
                pass
        if destination_parent is not None:
            os.close(destination_parent)
        if destination_root_descriptor is not None:
            os.close(destination_root_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        if source_parent is not None:
            os.close(source_parent)


def validate_world_walk_source_contract_path(
    repo_root: Path,
    source_run: str | Path,
    *,
    allow_missing: bool,
) -> tuple[Path, str]:
    root = repo_root.resolve()
    output_path = root / "output"
    if output_path.is_symlink():
        raise ValueError("output directory must not be a symlink")
    output_dir = output_path.resolve(strict=True)
    candidate = Path(source_run)
    if ".." in candidate.parts:
        raise ValueError("world-walk source run must not contain path traversal")
    if not candidate.is_absolute():
        if len(candidate.parts) != 2 or candidate.parts[0] != "output":
            raise ValueError(
                "world-walk source run must be output/<direct-child>"
            )
        candidate = root / candidate
    if candidate.is_symlink():
        raise ValueError("world-walk source run must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError:
        if not allow_missing:
            raise
        parent = candidate.parent.resolve(strict=True)
        if parent != output_dir or not candidate.name:
            raise ValueError(
                "world-walk source run must be a direct child of output/"
            )
        missing = parent / candidate.name
        return missing, missing.relative_to(root).as_posix()
    if resolved.parent != output_dir:
        raise ValueError("world-walk source run must be a direct child of output/")
    return resolved, resolved.relative_to(root).as_posix()


def validate_world_walk_source_path(repo_root: Path, source_run: str | Path) -> tuple[Path, str]:
    """Return a confined source directory and its canonical repo-relative path."""
    resolved, relative = validate_world_walk_source_contract_path(
        repo_root,
        source_run,
        allow_missing=False,
    )

    story_path = resolved / "story.md"
    assets_path = resolved / "assets"
    if not story_path.is_file() or not assets_path.is_dir():
        raise ValueError("world-walk source run requires story.md and assets/")
    for required_root in (story_path, assets_path):
        paths = (required_root, *required_root.rglob("*")) if required_root.is_dir() else (required_root,)
        for path in paths:
            if path.is_symlink():
                raise ValueError(f"world-walk source contains a symlink: {path.relative_to(resolved)}")
            path.resolve(strict=True).relative_to(resolved)

    return resolved, relative
