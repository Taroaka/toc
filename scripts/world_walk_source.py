from __future__ import annotations

import hashlib
import os
import secrets
import stat
from pathlib import Path


PathIdentity = tuple[int, int]


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
    file_descriptor: int | None = None
    verification_parent: int | None = None
    verification_file: int | None = None
    try:
        root_descriptor = _open_root_directory(
            destination_root,
            expected_identity=expected_destination_root_identity,
        )
        parent_descriptor = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=True,
        )
        flags = os.O_WRONLY | os.O_CREAT
        flags |= os.O_EXCL if exclusive else os.O_TRUNC
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(
            parts[-1],
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        opened_file = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened_file.st_mode):
            raise ValueError(
                f"destination must be a regular file: "
                f"{destination_rel.as_posix()}"
            )
        remaining = memoryview(data)
        while remaining:
            written = os.write(file_descriptor, remaining)
            if written <= 0:
                raise OSError("exclusive destination write made no progress")
            remaining = remaining[written:]
        os.fsync(file_descriptor)
        opened_parent = os.fstat(parent_descriptor)
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
        verification_file = os.open(
            parts[-1],
            _file_read_flags(),
            dir_fd=verification_parent,
        )
        verified_file = os.fstat(verification_file)
        if (
            verified_file.st_dev,
            verified_file.st_ino,
            stat.S_IFMT(verified_file.st_mode),
        ) != (
            opened_file.st_dev,
            opened_file.st_ino,
            stat.S_IFMT(opened_file.st_mode),
        ):
            raise ValueError(
                f"destination identity changed: "
                f"{destination_rel.as_posix()}"
            )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(verification_file, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        expected_digest = hashlib.sha256(data).hexdigest()
        if digest.hexdigest() != expected_digest:
            raise ValueError(
                f"destination sha256 mismatch: "
                f"{destination_rel.as_posix()}"
            )
        os.fsync(parent_descriptor)
        return expected_digest
    finally:
        if verification_file is not None:
            os.close(verification_file)
        if verification_parent is not None:
            os.close(verification_parent)
        if file_descriptor is not None:
            os.close(file_descriptor)
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
        current = os.stat(
            parts[-1],
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            current.st_dev,
            current.st_ino,
        ) != (
            opened.st_dev,
            opened.st_ino,
        ):
            return False
        os.unlink(parts[-1], dir_fd=parent_descriptor)
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
    linked_identity: tuple[int, int] | None = None
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
        linked_identity = linked_stat.st_dev, linked_stat.st_ino
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
        os.unlink(temporary_name, dir_fd=destination_parent)
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
                current_link = os.stat(
                    destination_parts[-1],
                    dir_fd=destination_parent,
                    follow_symlinks=False,
                )
                if (
                    current_link.st_dev,
                    current_link.st_ino,
                ) == linked_identity:
                    os.unlink(
                        destination_parts[-1],
                        dir_fd=destination_parent,
                    )
            except OSError:
                pass
        if (
            temporary_present
            and temporary_name
            and destination_parent is not None
        ):
            try:
                os.unlink(temporary_name, dir_fd=destination_parent)
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
