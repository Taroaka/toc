from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from toc.atomic_exchange import atomic_exchange_names
from toc.review_projection import (
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    ReviewProjectionError,
    review_source_fingerprint,
)
from toc.run_root_binding import (
    current_run_root_binding,
    require_bound_run_root,
)


IMAGE_PROMPT_JUDGMENT_COLLECTION = Path("logs/review/image_prompt.review_collection.md")
IMAGE_PROMPT_JUDGMENT_SCOPE = Path("logs/review/image_prompt.review_scope.json")
IMAGE_PROMPT_JUDGMENT_PROMPT = Path("logs/review/image_prompt.judgment_prompt.md")
IMAGE_PROMPT_JUDGMENT_REPORT = Path("logs/review/image_prompt.judgment.md")
PASSING_JUDGMENT_STATUSES = {"passed"}
SEMANTIC_REVIEW_INPUT_SCHEMA = "semantic_review_input_v1"
LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA = "semantic_review_input_legacy_mtime_v1"
_SEMANTIC_REVIEW_DIGEST_FIELDS = {
    "semantic_review_input_schema",
    "source_artifact_digests",
    "collection_sha256",
    "prompt_sha256",
    "scope_binding_sha256",
    "semantic_review_input_digest",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEMANTIC_CLEANUP_DIRECTORY_NONCE = uuid.uuid4().hex
SEMANTIC_REVIEW_STAGES = {
    "research",
    "story",
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "asset_plan",
    "image_prompt",
    "narration",
    "video_motion",
}
FOUNDATION_SEMANTIC_REVIEW_STAGES = {"research", "story"}
FOUNDATION_SEMANTIC_CRITERIA = {
    "research": (
        "baseline",
        "chronology",
        "principal_characters",
        "central_conflict_resolution",
        "downstream_handoff",
    ),
    "story": (
        "research_event_allocation",
        "chronology_causality",
        "character_continuity",
        "conflict_resolution",
        "historical_time_context",
        "scene_time_of_day_continuity",
        "scene_location_route_continuity",
        "duration_scene_readiness",
    ),
}


class SemanticWriteIndeterminateError(ValueError):
    """The writer could not prove that a failed publication rolled back."""


def semantic_review_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_review_input_digest(
    *,
    stage: str,
    entry_ids: Sequence[str],
    collection_sha256: str,
    prompt_sha256: str,
    source_artifact_digests: Sequence[Mapping[str, str]],
    request_revision: str | None = None,
    scope_binding_sha256: str = "",
) -> str:
    """Return the canonical identity of every input visible to a reviewer."""

    source_records: list[dict[str, str]] = []
    for record in source_artifact_digests:
        normalized_record = {
            "path": str(record.get("path") or ""),
            "sha256": str(record.get("sha256") or ""),
        }
        policy = record.get(REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD)
        if policy is not None:
            normalized_record[
                REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
            ] = str(policy)
        source_records.append(normalized_record)

    payload = {
        "schema_version": SEMANTIC_REVIEW_INPUT_SCHEMA,
        "stage": str(stage),
        "entry_ids": [str(entry_id) for entry_id in entry_ids],
        "collection_sha256": str(collection_sha256),
        "prompt_sha256": str(prompt_sha256),
        "source_artifacts": source_records,
        "request_revision": str(request_revision or ""),
        "scope_binding_sha256": str(scope_binding_sha256),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def semantic_review_scope_binding(scope: Mapping[str, Any]) -> dict[str, Any]:
    """Return the scope fields whose mutation invalidates a review verdict."""

    binding: dict[str, Any] = {
        "review_scope": str(scope.get("review_scope") or "all_entries"),
        "artifacts": scope.get("artifacts") if isinstance(scope.get("artifacts"), dict) else {},
    }
    for key in ("shard_id", "scene_id", "canonical_scope", "canonical_report"):
        value = scope.get(key)
        if value is not None:
            binding[key] = value
    if "coverage" in scope:
        binding["coverage"] = scope.get("coverage")
    if "shards" in scope:
        binding["shards"] = scope.get("shards")
    return binding


def semantic_review_scope_binding_sha256(scope: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        semantic_review_scope_binding(scope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_entry_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
    )


def _semantic_file_snapshot(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _semantic_directory_open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise ValueError(
            "semantic artifact writes require no-follow directory operations"
        )
    return (
        os.O_RDONLY
        | nofollow
        | directory
        | getattr(os, "O_CLOEXEC", 0)
    )


def _verify_semantic_directory_chain(
    *,
    run_root: Path,
    root_fd: int,
    links: Sequence[tuple[int, str, int]],
) -> None:
    """Verify every caller-visible name still identifies its retained FD."""

    try:
        root_entry = os.stat(run_root, follow_symlinks=False)
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_entry.st_mode)
            or _semantic_entry_identity(root_entry)
            != _semantic_entry_identity(opened_root)
        ):
            raise ValueError(
                "semantic artifact run directory identity changed"
            )
        for parent_fd, name, child_fd in links:
            entry = os.stat(
                name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            opened = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(entry.st_mode)
                or _semantic_entry_identity(entry)
                != _semantic_entry_identity(opened)
            ):
                raise ValueError(
                    "semantic artifact ancestor identity changed: "
                    f"{name}"
                )
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(
            "semantic artifact ancestry became unsafe"
        ) from exc


def _semantic_named_stat(
    parent_fd: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(
            name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None


def _semantic_open_cleanup_directory(parent_fd: int) -> int:
    """Open an owner-only-by-mode cleanup namespace.

    Mode 0700 excludes other UIDs. Portable POSIX operations cannot isolate
    this namespace from a hostile peer running under the same UID.
    """

    directory_name = (
        f".semantic-cleanup-{os.getpid()}-"
        f"{_SEMANTIC_CLEANUP_DIRECTORY_NONCE}"
    )
    created = False
    try:
        os.mkdir(directory_name, 0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError:
        return -1

    try:
        directory_fd = os.open(
            directory_name,
            _semantic_directory_open_flags(),
            dir_fd=parent_fd,
        )
    except OSError:
        return -1

    try:
        opened = os.fstat(directory_fd)
        named = _semantic_named_stat(parent_fd, directory_name)
        if (
            named is None
            or not stat.S_ISDIR(opened.st_mode)
            or _semantic_entry_identity(named)
            != _semantic_entry_identity(opened)
            or opened.st_uid != os.geteuid()
        ):
            raise OSError("semantic cleanup directory is unsafe")
        if created:
            os.fchmod(directory_fd, 0o700)
            opened = os.fstat(directory_fd)
        if stat.S_IMODE(opened.st_mode) != 0o700:
            raise OSError("semantic cleanup directory is writable by peers")
    except OSError:
        os.close(directory_fd)
        return -1
    return directory_fd


def _semantic_cleanup_if_identity(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
    *,
    dispose: bool,
    cleanup_fd: int | None = None,
) -> bool:
    """Detach a matching name through a protected cleanup directory.

    The shared parent is never the namespace used for physical deletion.
    A source-name replacement moved during the rename is restored with a
    no-clobber link and its protected alias is then safely removed.  If that
    restoration cannot be proven, the ambiguous entry remains quarantined.
    """

    current = _semantic_named_stat(parent_fd, name)
    if (
        current is None
        or _semantic_entry_identity(current) != expected_identity
    ):
        return current is None
    retained_cleanup_fd = cleanup_fd
    close_cleanup_fd = retained_cleanup_fd is None
    if retained_cleanup_fd is None:
        retained_cleanup_fd = _semantic_open_cleanup_directory(parent_fd)
    if retained_cleanup_fd < 0:
        return False
    quarantine_name = f"entry-{uuid.uuid4().hex}"
    try:
        try:
            os.rename(
                name,
                quarantine_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=retained_cleanup_fd,
            )
        except FileNotFoundError:
            return False
        quarantined = _semantic_named_stat(
            retained_cleanup_fd,
            quarantine_name,
        )
        if quarantined is None:
            return False
        if _semantic_entry_identity(quarantined) != expected_identity:
            if _semantic_named_stat(parent_fd, name) is not None:
                return False
            try:
                os.link(
                    quarantine_name,
                    name,
                    src_dir_fd=retained_cleanup_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                os.unlink(quarantine_name, dir_fd=retained_cleanup_fd)
            except OSError:
                return False
            return False
        if not dispose:
            return True
        try:
            os.unlink(quarantine_name, dir_fd=retained_cleanup_fd)
        except OSError:
            return False
        return True
    finally:
        if close_cleanup_fd:
            os.close(retained_cleanup_fd)


def _semantic_unlink_if_identity(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
    *,
    cleanup_fd: int | None = None,
) -> bool:
    return _semantic_cleanup_if_identity(
        parent_fd,
        name,
        expected_identity,
        dispose=True,
        cleanup_fd=cleanup_fd,
    )


def _semantic_quarantine_if_identity(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
    *,
    cleanup_fd: int | None = None,
) -> bool:
    return _semantic_cleanup_if_identity(
        parent_fd,
        name,
        expected_identity,
        dispose=False,
        cleanup_fd=cleanup_fd,
    )


def _semantic_unlink_protected_if_identity(
    directory_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    """Unlink a known entry inside the writer-only cleanup namespace."""

    current = _semantic_named_stat(directory_fd, name)
    if (
        current is None
        or _semantic_entry_identity(current) != expected_identity
    ):
        return current is None
    try:
        os.unlink(name, dir_fd=directory_fd)
    except OSError:
        return False
    return True


def _semantic_link_without_clobber(
    parent_fd: int,
    source_name: str,
    destination_name: str,
) -> None:
    os.link(
        source_name,
        destination_name,
        src_dir_fd=parent_fd,
        dst_dir_fd=parent_fd,
        follow_symlinks=False,
    )


def safe_semantic_write_text(
    run_dir: Path,
    path: Path,
    text: str,
    *,
    expected_root_identity: tuple[int, int] | None = None,
) -> Path:
    """Atomically write a run-local artifact through retained directory FDs."""

    binding = current_run_root_binding()
    if binding is not None:
        if os.path.abspath(os.fspath(run_dir)) != binding.lexical_root:
            raise ValueError(
                "semantic artifact escaped the active bound run root"
            )
        require_bound_run_root(Path(binding.lexical_root))
        if (
            expected_root_identity is not None
            and expected_root_identity != binding.identity
        ):
            raise ValueError(
                "semantic artifact root identity conflicts with active binding"
            )
        expected_root_identity = binding.identity

    run_root = (
        Path(os.path.abspath(os.fspath(run_dir)))
        if expected_root_identity is not None
        else run_dir.resolve(strict=True)
    )
    raw_candidate = path if path.is_absolute() else run_root / path
    raw_candidate = Path(os.path.abspath(raw_candidate))
    candidate = (
        raw_candidate
        if expected_root_identity is not None
        else raw_candidate.resolve(strict=False)
    )
    try:
        relative = candidate.relative_to(run_root)
    except ValueError as exc:
        raise ValueError(f"semantic artifact escapes run directory: {path}") from exc
    if not relative.parts:
        raise ValueError("semantic artifact path must name a file")

    # Inspect only the caller-visible path below the canonical run root. This
    # rejects run-local symlinks while allowing platform aliases such as
    # macOS's /var -> /private/var before the run root.
    raw_cursor = raw_candidate
    while (
        Path(os.path.abspath(os.fspath(raw_cursor)))
        if expected_root_identity is not None
        else raw_cursor.resolve(strict=False)
    ) != run_root:
        if raw_cursor.is_symlink():
            raise ValueError(f"semantic artifact path traverses a symlink: {raw_cursor}")
        parent = raw_cursor.parent
        if parent == raw_cursor:
            raise ValueError(f"semantic artifact escapes run directory: {path}")
        raw_cursor = parent

    directory_flags = _semantic_directory_open_flags()
    file_nofollow = getattr(os, "O_NOFOLLOW")
    cloexec = getattr(os, "O_CLOEXEC", 0)
    encoded = text.encode("utf-8")
    opened_directories: list[int] = []
    directory_links: list[tuple[int, str, int]] = []
    root_fd = -1
    parent_fd = -1
    target_fd = -1
    temporary_fd = -1
    backup_cleanup_fd = -1
    temporary_name = (
        f".semantic-write-{candidate.name}-{uuid.uuid4().hex}.tmp"
    )
    temporary_identity: tuple[int, int, int] | None = None
    temporary_present = False
    backup_name = (
        f".semantic-write-backup-{candidate.name}-{uuid.uuid4().hex}.tmp"
    )
    backup_identity: tuple[int, int, int] | None = None
    rollback_cleanup_identity: tuple[int, int, int] | None = None
    backup_role = ""
    backup_present = False
    published = False
    exchange_pending = False
    committed = False
    unexpected_published_identity: tuple[int, int, int] | None = None
    unexpected_temporary_identity: tuple[int, int, int] | None = None
    target_initial_snapshot: tuple[int, int, int, int, int, int, int] | None = (
        None
    )

    def restore_backup_without_clobber(*, keep_backup: bool = False) -> bool:
        nonlocal backup_present
        if (
            not backup_present
            or backup_identity is None
            or parent_fd < 0
            or backup_cleanup_fd < 0
        ):
            return False
        current_backup = _semantic_named_stat(
            backup_cleanup_fd,
            backup_name,
        )
        if (
            current_backup is None
            or _semantic_entry_identity(current_backup) != backup_identity
            or not stat.S_ISREG(current_backup.st_mode)
        ):
            return False
        current_target = _semantic_named_stat(parent_fd, relative.parts[-1])
        if current_target is None:
            try:
                os.link(
                    backup_name,
                    relative.parts[-1],
                    src_dir_fd=backup_cleanup_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                return False
            current_target = _semantic_named_stat(
                parent_fd,
                relative.parts[-1],
            )
        restored = (
            current_target is not None
            and stat.S_ISREG(current_target.st_mode)
            and _semantic_entry_identity(current_target) == backup_identity
        )
        if (
            restored
            and not keep_backup
            and _semantic_unlink_protected_if_identity(
            backup_cleanup_fd,
            backup_name,
            backup_identity,
            )
        ):
            backup_present = False
        return restored

    try:
        try:
            root_entry = os.stat(run_root, follow_symlinks=False)
            root_fd = os.open(run_root, directory_flags)
            opened_directories.append(root_fd)
            opened_root = os.fstat(root_fd)
        except OSError as exc:
            raise ValueError(
                f"semantic artifact run directory is unsafe: {run_root}"
            ) from exc
        if (
            not stat.S_ISDIR(root_entry.st_mode)
            or _semantic_entry_identity(root_entry)
            != _semantic_entry_identity(opened_root)
            or (
                expected_root_identity is not None
                and (opened_root.st_dev, opened_root.st_ino)
                != expected_root_identity
            )
        ):
            raise ValueError(
                "semantic artifact run directory identity changed"
            )

        parent_fd = root_fd
        for part in relative.parts[:-1]:
            try:
                child_fd = os.open(
                    part,
                    directory_flags,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o755, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                try:
                    child_fd = os.open(
                        part,
                        directory_flags,
                        dir_fd=parent_fd,
                    )
                except OSError as exc:
                    raise ValueError(
                        "semantic artifact ancestor became unsafe: "
                        f"{part}"
                    ) from exc
            except OSError as exc:
                raise ValueError(
                    f"semantic artifact ancestor is unsafe: {part}"
                ) from exc

            opened_directories.append(child_fd)
            directory_links.append((parent_fd, part, child_fd))
            child_entry = _semantic_named_stat(parent_fd, part)
            opened_child = os.fstat(child_fd)
            if (
                child_entry is None
                or not stat.S_ISDIR(child_entry.st_mode)
                or _semantic_entry_identity(child_entry)
                != _semantic_entry_identity(opened_child)
            ):
                raise ValueError(
                    "semantic artifact ancestor identity changed: "
                    f"{part}"
                )
            parent_fd = child_fd

        _verify_semantic_directory_chain(
            run_root=run_root,
            root_fd=root_fd,
            links=directory_links,
        )
        target_name = relative.parts[-1]
        target_entry = _semantic_named_stat(parent_fd, target_name)
        if target_entry is not None:
            if not stat.S_ISREG(target_entry.st_mode):
                raise ValueError(
                    "semantic artifact target is not a safe regular file: "
                    f"{candidate}"
                )
            if target_entry.st_nlink != 1:
                raise ValueError(
                    "semantic artifact target has multiple hard links: "
                    f"{candidate}"
                )
            try:
                target_fd = os.open(
                    target_name,
                    os.O_RDONLY
                    | file_nofollow
                    | cloexec
                    | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise ValueError(
                    f"semantic artifact target became unsafe: {candidate}"
                ) from exc
            opened_target = os.fstat(target_fd)
            current_target = _semantic_named_stat(parent_fd, target_name)
            if (
                current_target is None
                or not stat.S_ISREG(opened_target.st_mode)
                or _semantic_file_snapshot(opened_target)
                != _semantic_file_snapshot(current_target)
            ):
                raise ValueError(
                    "semantic artifact target identity changed before write"
                )
            target_initial_snapshot = _semantic_file_snapshot(opened_target)

        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | file_nofollow
            | cloexec,
            0o600,
            dir_fd=parent_fd,
        )
        temporary_stat = os.fstat(temporary_fd)
        if (
            not stat.S_ISREG(temporary_stat.st_mode)
            or temporary_stat.st_nlink != 1
        ):
            raise ValueError(
                "semantic artifact temporary file is not a safe regular file"
            )
        temporary_identity = _semantic_entry_identity(temporary_stat)
        temporary_present = True

        remaining = memoryview(encoded)
        while remaining:
            written = os.write(temporary_fd, remaining)
            if written <= 0:
                raise OSError(
                    "semantic artifact write made no progress"
                )
            remaining = remaining[written:]
        os.fsync(temporary_fd)

        _verify_semantic_directory_chain(
            run_root=run_root,
            root_fd=root_fd,
            links=directory_links,
        )
        held_temporary = os.fstat(temporary_fd)
        named_temporary = _semantic_named_stat(parent_fd, temporary_name)
        if (
            named_temporary is None
            or not stat.S_ISREG(named_temporary.st_mode)
            or held_temporary.st_nlink != 1
            or named_temporary.st_nlink != 1
            or _semantic_entry_identity(held_temporary)
            != temporary_identity
            or _semantic_entry_identity(named_temporary)
            != temporary_identity
        ):
            raise ValueError(
                "semantic artifact temporary name identity changed"
            )

        if target_fd >= 0:
            current_opened_target = os.fstat(target_fd)
            current_named_target = _semantic_named_stat(
                parent_fd,
                target_name,
            )
            if (
                current_named_target is None
                or current_named_target.st_nlink != 1
                or current_opened_target.st_nlink != 1
                or _semantic_file_snapshot(current_opened_target)
                != target_initial_snapshot
                or _semantic_file_snapshot(current_named_target)
                != target_initial_snapshot
            ):
                raise ValueError(
                    "semantic artifact target identity changed during write"
                )

            backup_cleanup_fd = _semantic_open_cleanup_directory(
                parent_fd
            )
            if backup_cleanup_fd < 0:
                raise ValueError(
                    "semantic artifact cleanup directory is unsafe"
                )
            backup_name = f"backup-{uuid.uuid4().hex}"
            opened_target_before_exchange = os.fstat(target_fd)
            backup_identity = _semantic_entry_identity(
                opened_target_before_exchange
            )
            # Swap the two existing names in one kernel operation. Concurrent
            # readers therefore observe either the complete old artifact or
            # the complete new artifact, never a missing canonical leaf.
            try:
                atomic_exchange_names(
                    parent_fd,
                    temporary_name,
                    parent_fd,
                    target_name,
                )
            except BaseException:
                reconciled_target = _semantic_named_stat(
                    parent_fd,
                    target_name,
                )
                reconciled_backup = _semantic_named_stat(
                    parent_fd,
                    temporary_name,
                )
                if (
                    reconciled_target is not None
                    and reconciled_backup is not None
                    and _semantic_entry_identity(reconciled_target)
                    == temporary_identity
                    and _semantic_entry_identity(reconciled_backup)
                    == backup_identity
                ):
                    published = True
                    exchange_pending = True
                raise
            published = True
            exchange_pending = True
            exchanged_target = _semantic_named_stat(parent_fd, target_name)
            exchanged_backup = _semantic_named_stat(
                parent_fd,
                temporary_name,
            )
            if (
                exchanged_target is None
                or exchanged_backup is None
                or not stat.S_ISREG(exchanged_target.st_mode)
                or not stat.S_ISREG(exchanged_backup.st_mode)
                or exchanged_target.st_nlink != 1
                or exchanged_backup.st_nlink != 1
                or _semantic_entry_identity(exchanged_target)
                != temporary_identity
                or _semantic_entry_identity(exchanged_backup)
                != backup_identity
            ):
                if (
                    exchanged_target is not None
                    and exchanged_backup is not None
                    and _semantic_entry_identity(exchanged_target)
                    == temporary_identity
                ):
                    raced_identity = _semantic_entry_identity(
                        exchanged_backup
                    )
                    try:
                        atomic_exchange_names(
                            parent_fd,
                            target_name,
                            parent_fd,
                            temporary_name,
                        )
                    except OSError:
                        pass
                    else:
                        restored_raced_target = _semantic_named_stat(
                            parent_fd,
                            target_name,
                        )
                        restored_new_temporary = _semantic_named_stat(
                            parent_fd,
                            temporary_name,
                        )
                        if (
                            restored_raced_target is not None
                            and restored_new_temporary is not None
                            and _semantic_entry_identity(
                                restored_raced_target
                            )
                            == raced_identity
                            and _semantic_entry_identity(
                                restored_new_temporary
                            )
                            == temporary_identity
                        ):
                            published = False
                            exchange_pending = False
                            temporary_present = True
                raise ValueError(
                    "semantic artifact identity changed during atomic exchange"
                )

            try:
                os.rename(
                    temporary_name,
                    backup_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=backup_cleanup_fd,
                )
            except BaseException:
                reconciled_backup = _semantic_named_stat(
                    backup_cleanup_fd,
                    backup_name,
                )
                reconciled_temporary = _semantic_named_stat(
                    parent_fd,
                    temporary_name,
                )
                if (
                    reconciled_backup is not None
                    and _semantic_entry_identity(reconciled_backup)
                    == backup_identity
                ):
                    backup_present = True
                    backup_role = "expected"
                    exchange_pending = False
                    temporary_present = False
                elif (
                    reconciled_temporary is None
                    or _semantic_entry_identity(reconciled_temporary)
                    != backup_identity
                ):
                    backup_role = "unknown"
                raise

            try:
                moved_target = _semantic_named_stat(
                    backup_cleanup_fd,
                    backup_name,
                )
            except BaseException:
                # The rename may already be complete even when a following
                # inspection fails. Reconcile ownership so the common
                # rollback path can restore the old canonical inode.
                reconciled_backup = _semantic_named_stat(
                    backup_cleanup_fd,
                    backup_name,
                )
                if (
                    reconciled_backup is not None
                    and _semantic_entry_identity(reconciled_backup)
                    == backup_identity
                ):
                    backup_present = True
                    backup_role = "expected"
                    exchange_pending = False
                    temporary_present = False
                else:
                    backup_role = "unknown"
                raise
            if (
                moved_target is None
                or not stat.S_ISREG(moved_target.st_mode)
                or moved_target.st_nlink != 1
                or _semantic_entry_identity(moved_target) != backup_identity
                or _semantic_entry_identity(os.fstat(target_fd))
                != backup_identity
            ):
                backup_role = "unknown"
                raise ValueError(
                    "semantic artifact backup identity changed after exchange"
                )
            backup_present = True
            backup_role = "expected"
            exchange_pending = False
            temporary_present = False

            # Preserve the existing post-publication invariant: the new inode
            # remains held by its fd and by both canonical and temporary names
            # until the parent-directory commit fsync succeeds.
            try:
                _semantic_link_without_clobber(
                    parent_fd,
                    target_name,
                    temporary_name,
                )
            except BaseException:
                reconciled_temporary = _semantic_named_stat(
                    parent_fd,
                    temporary_name,
                )
                if (
                    reconciled_temporary is not None
                    and _semantic_entry_identity(reconciled_temporary)
                    == temporary_identity
                ):
                    temporary_present = True
                raise
            temporary_present = True
            _verify_semantic_directory_chain(
                run_root=run_root,
                root_fd=root_fd,
                links=directory_links,
            )
        elif _semantic_named_stat(parent_fd, target_name) is not None:
            raise ValueError(
                "semantic artifact target appeared during write"
            )

        if target_fd < 0:
            try:
                # The absent-target path remains no-clobber: a leaf that
                # appears after the checks wins and is never overwritten.
                _semantic_link_without_clobber(
                    parent_fd,
                    temporary_name,
                    target_name,
                )
            except BaseException as exc:
                reconciled_publication = _semantic_named_stat(
                    parent_fd,
                    target_name,
                )
                if (
                    reconciled_publication is not None
                    and _semantic_entry_identity(reconciled_publication)
                    == temporary_identity
                ):
                    published = True
                if isinstance(exc, FileExistsError):
                    raise ValueError(
                        "semantic artifact target appeared during publish"
                    ) from exc
                raise
            published = True

        published_stat = _semantic_named_stat(parent_fd, target_name)
        if (
            published_stat is None
            or not stat.S_ISREG(published_stat.st_mode)
            or _semantic_entry_identity(published_stat)
            != temporary_identity
        ):
            named_after_publish = _semantic_named_stat(
                parent_fd,
                temporary_name,
            )
            if (
                published_stat is not None
                and named_after_publish is not None
                and stat.S_ISREG(published_stat.st_mode)
                and stat.S_ISREG(named_after_publish.st_mode)
                and _semantic_entry_identity(published_stat)
                == _semantic_entry_identity(named_after_publish)
            ):
                unexpected_published_identity = (
                    _semantic_entry_identity(published_stat)
                )
                unexpected_temporary_identity = (
                    _semantic_entry_identity(named_after_publish)
                )
            raise ValueError(
                "semantic artifact target identity changed after publish"
            )
        _verify_semantic_directory_chain(
            run_root=run_root,
            root_fd=root_fd,
            links=directory_links,
        )

        # Keep both the temporary link and previous-version backup until the
        # new canonical name has been durably recorded. If this fsync fails,
        # the rollback path can still restore the exact previous artifact.
        os.fsync(parent_fd)

        _verify_semantic_directory_chain(
            run_root=run_root,
            root_fd=root_fd,
            links=directory_links,
        )
        final_target = _semantic_named_stat(parent_fd, target_name)
        final_temporary = os.fstat(temporary_fd)
        if (
            final_target is None
            or not stat.S_ISREG(final_target.st_mode)
            or final_target.st_nlink != 2
            or _semantic_entry_identity(final_target)
            != temporary_identity
            or _semantic_entry_identity(final_temporary)
            != temporary_identity
        ):
            raise ValueError(
                "semantic artifact target identity changed after commit"
            )
        committed = True
        try:
            removed_temporary = _semantic_unlink_if_identity(
                parent_fd,
                temporary_name,
                temporary_identity,
                cleanup_fd=(
                    backup_cleanup_fd if backup_cleanup_fd >= 0 else None
                ),
            )
        except OSError:
            removed_temporary = False
        if removed_temporary:
            temporary_present = False
        if backup_role == "expected" and backup_identity is not None:
            if _semantic_unlink_protected_if_identity(
                backup_cleanup_fd,
                backup_name,
                backup_identity,
            ):
                backup_present = False
        # Publication is already durable. Cleanup is hygiene only: a caller
        # must not receive failure while the committed bytes remain canonical.
        for cleanup_descriptor in (backup_cleanup_fd, parent_fd):
            if cleanup_descriptor < 0:
                continue
            try:
                os.fsync(cleanup_descriptor)
            except OSError:
                pass
    except ValueError:
        if not committed:
            raise
    except OSError as exc:
        if not committed:
            raise ValueError(
                f"semantic artifact write became unsafe: {candidate}"
            ) from exc
    finally:
        rollback_required = (
            not committed
            and parent_fd >= 0
            and (published or backup_role == "expected")
        )
        rollback_canonical_proven = True
        rollback_durability_proven = True
        if rollback_required and backup_cleanup_fd < 0:
            backup_cleanup_fd = _semantic_open_cleanup_directory(parent_fd)
            if backup_cleanup_fd < 0:
                rollback_durability_proven = False
        if not committed and parent_fd >= 0:
            if exchange_pending and temporary_identity is not None:
                exchanged_target = _semantic_named_stat(
                    parent_fd,
                    relative.parts[-1],
                )
                exchanged_backup = _semantic_named_stat(
                    parent_fd,
                    temporary_name,
                )
                if (
                    exchanged_target is not None
                    and exchanged_backup is not None
                    and _semantic_entry_identity(exchanged_target)
                    == temporary_identity
                    and backup_identity is not None
                    and _semantic_entry_identity(exchanged_backup)
                    == backup_identity
                ):
                    try:
                        atomic_exchange_names(
                            parent_fd,
                            relative.parts[-1],
                            parent_fd,
                            temporary_name,
                        )
                    except OSError:
                        rollback_canonical_proven = False
                    else:
                        restored_target = _semantic_named_stat(
                            parent_fd,
                            relative.parts[-1],
                        )
                        restored_temporary = _semantic_named_stat(
                            parent_fd,
                            temporary_name,
                        )
                        rollback_canonical_proven = (
                            restored_target is not None
                            and restored_temporary is not None
                            and _semantic_entry_identity(restored_target)
                            == backup_identity
                            and _semantic_entry_identity(restored_temporary)
                            == temporary_identity
                        )
                        if rollback_canonical_proven:
                            exchange_pending = False
                            published = False
                            temporary_present = True
                            backup_role = "restored_exchange"
                else:
                    rollback_canonical_proven = False
            if (
                published
                and backup_role == "expected"
                and backup_present
                and backup_identity is not None
                and temporary_identity is not None
                and backup_cleanup_fd >= 0
            ):
                # Restore an overwritten canonical name with one native
                # exchange.  Unlinking the new name before relinking the old
                # backup would expose a transient ENOENT to concurrent
                # readers on every failed write after publication.
                try:
                    atomic_exchange_names(
                        parent_fd,
                        relative.parts[-1],
                        backup_cleanup_fd,
                        backup_name,
                    )
                except OSError:
                    restored_target = _semantic_named_stat(
                        parent_fd,
                        relative.parts[-1],
                    )
                    relocated_new = _semantic_named_stat(
                        backup_cleanup_fd,
                        backup_name,
                    )
                    if (
                        restored_target is None
                        or relocated_new is None
                        or _semantic_entry_identity(restored_target)
                        != backup_identity
                        or _semantic_entry_identity(relocated_new)
                        != temporary_identity
                    ):
                        rollback_canonical_proven = False
                    else:
                        published = False
                        backup_role = "restored_atomic"
                        rollback_cleanup_identity = temporary_identity
                else:
                    restored_target = _semantic_named_stat(
                        parent_fd,
                        relative.parts[-1],
                    )
                    relocated_new = _semantic_named_stat(
                        backup_cleanup_fd,
                        backup_name,
                    )
                    rollback_canonical_proven = (
                        restored_target is not None
                        and relocated_new is not None
                        and _semantic_entry_identity(restored_target)
                        == backup_identity
                        and _semantic_entry_identity(relocated_new)
                        == temporary_identity
                    )
                    if rollback_canonical_proven:
                        published = False
                        backup_role = "restored_atomic"
                        rollback_cleanup_identity = temporary_identity
            if (
                published
                and temporary_identity is not None
                and target_fd < 0
            ):
                try:
                    removed_publication = _semantic_unlink_if_identity(
                        parent_fd,
                        relative.parts[-1],
                        temporary_identity,
                        cleanup_fd=(
                            backup_cleanup_fd
                            if backup_cleanup_fd >= 0
                            else None
                        ),
                    )
                except OSError:
                    removed_publication = False
                if (
                    not removed_publication
                    and unexpected_published_identity is not None
                ):
                    try:
                        removed_publication = (
                            _semantic_quarantine_if_identity(
                                parent_fd,
                                relative.parts[-1],
                                unexpected_published_identity,
                                cleanup_fd=(
                                    backup_cleanup_fd
                                    if backup_cleanup_fd >= 0
                                    else None
                                ),
                            )
                        )
                    except OSError:
                        removed_publication = False
                published = not removed_publication
            if backup_role == "expected" and not published:
                try:
                    rollback_canonical_proven = (
                        restore_backup_without_clobber(keep_backup=True)
                    )
                except OSError:
                    rollback_canonical_proven = False
            elif backup_role == "unrelated":
                try:
                    restore_backup_without_clobber()
                except OSError:
                    pass
        if (
            temporary_present
            and temporary_identity is not None
            and parent_fd >= 0
        ):
            try:
                removed_temporary = _semantic_unlink_if_identity(
                    parent_fd,
                    temporary_name,
                    temporary_identity,
                    cleanup_fd=(
                        backup_cleanup_fd
                        if backup_cleanup_fd >= 0
                        else None
                    ),
                )
            except OSError:
                removed_temporary = False
            if (
                not removed_temporary
                and unexpected_temporary_identity is not None
            ):
                try:
                    _semantic_quarantine_if_identity(
                        parent_fd,
                        temporary_name,
                        unexpected_temporary_identity,
                        cleanup_fd=(
                            backup_cleanup_fd
                            if backup_cleanup_fd >= 0
                            else None
                        ),
                    )
                except OSError:
                    pass
        if rollback_required:
            rollback_target_inspected = True
            try:
                rolled_back_target = _semantic_named_stat(
                    parent_fd,
                    relative.parts[-1],
                )
            except OSError:
                rolled_back_target = None
                rollback_target_inspected = False
                rollback_canonical_proven = False
            if backup_role in {
                "expected",
                "restored_exchange",
                "restored_atomic",
            } and backup_identity is not None:
                rollback_canonical_proven = (
                    rollback_canonical_proven
                    and rolled_back_target is not None
                    and stat.S_ISREG(rolled_back_target.st_mode)
                    and _semantic_entry_identity(rolled_back_target)
                    == backup_identity
                )
            else:
                rollback_canonical_proven = (
                    rollback_canonical_proven
                    and rollback_target_inspected
                    and rolled_back_target is None
                )
            parent_rollback_synced = False
            try:
                os.fsync(parent_fd)
            except OSError:
                rollback_durability_proven = False
            else:
                parent_rollback_synced = True
            if (
                parent_rollback_synced
                and backup_role == "expected"
                and rollback_canonical_proven
                and backup_present
                and backup_identity is not None
                and _semantic_unlink_protected_if_identity(
                    backup_cleanup_fd,
                    backup_name,
                    backup_identity,
                )
            ):
                backup_present = False
            if (
                parent_rollback_synced
                and backup_role == "restored_atomic"
                and rollback_canonical_proven
                and backup_present
                and rollback_cleanup_identity is not None
                and _semantic_unlink_protected_if_identity(
                    backup_cleanup_fd,
                    backup_name,
                    rollback_cleanup_identity,
                )
            ):
                backup_present = False
            if backup_cleanup_fd < 0:
                rollback_durability_proven = False
            else:
                try:
                    os.fsync(backup_cleanup_fd)
                except OSError:
                    rollback_durability_proven = False
        if backup_cleanup_fd >= 0:
            try:
                os.close(backup_cleanup_fd)
            except OSError:
                pass
        if temporary_fd >= 0:
            try:
                os.close(temporary_fd)
            except OSError:
                pass
        if target_fd >= 0:
            try:
                os.close(target_fd)
            except OSError:
                pass
        for directory_fd in reversed(opened_directories):
            try:
                os.close(directory_fd)
            except OSError:
                pass
        if rollback_required and (
            not rollback_canonical_proven
            or not rollback_durability_proven
        ):
            raise SemanticWriteIndeterminateError(
                "semantic artifact rollback durability is indeterminate: "
                f"{candidate}"
            )
    return candidate


def semantic_review_relpaths(stage: str) -> dict[str, Path]:
    normalized = stage.strip()
    if normalized not in SEMANTIC_REVIEW_STAGES:
        raise ValueError(f"unknown semantic review stage: {stage}")
    base = Path("logs/review/semantic")
    return {
        "collection": base / f"{normalized}.collection.md",
        "scope": base / f"{normalized}.scope.json",
        "prompt": base / f"{normalized}.prompt.md",
        "report": base / f"{normalized}.report.md",
    }


def semantic_state_updates(
    stage: str,
    *,
    status: str,
    entry_count: int | None,
    error_count: int | None = None,
    generated_at: str | None = None,
) -> dict[str, str]:
    relpaths = semantic_review_relpaths(stage)
    updates = {
        f"review.semantic.{stage}.collection": relpaths["collection"].as_posix(),
        f"review.semantic.{stage}.scope": relpaths["scope"].as_posix(),
        f"review.semantic.{stage}.prompt": relpaths["prompt"].as_posix(),
        f"review.semantic.{stage}.report": relpaths["report"].as_posix(),
        f"review.semantic.{stage}.status": status,
    }
    if entry_count is not None:
        updates[f"review.semantic.{stage}.entry_count"] = str(entry_count)
    if error_count is not None:
        updates[f"review.semantic.{stage}.error_count"] = str(error_count)
    if generated_at:
        updates[f"review.semantic.{stage}.generated_at"] = generated_at
    return updates


@dataclass(frozen=True)
class SemanticReviewStatus:
    status: str
    entry_count: int | None
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors and self.status in PASSING_JUDGMENT_STATUSES


def parse_judgment_report_status(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^-?\s*status\s*:\s*`?([A-Za-z_ -]+)`?\s*$", line)
        if match:
            return match.group(1).strip().lower().replace(" ", "_")
    return ""


def semantic_report_field_occurrences(text: str, key: str) -> int:
    pattern = re.compile(rf"^-?\s*{re.escape(key)}\s*:", re.IGNORECASE)
    return sum(1 for raw in text.splitlines() if pattern.match(raw.strip()))


def semantic_report_required_field_issues(
    text: str,
    *,
    require_digest: bool,
) -> tuple[str, ...]:
    required = ["status", "reviewed_entries", "blocked_entries", "failed_selectors"]
    if require_digest:
        required.append("semantic_review_input_digest")
    errors: list[str] = []
    for key in required:
        count = semantic_report_field_occurrences(text, key)
        if count != 1:
            errors.append(
                f"semantic review report must contain exactly one {key} field (found={count})"
            )
    return tuple(errors)


def _report_scalar_values(text: str, key: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(rf"^-?\s*{re.escape(key)}\s*:\s*(.*?)\s*$")
    for raw in text.splitlines():
        match = pattern.match(raw.strip())
        if not match:
            continue
        value = match.group(1).strip().strip("`").strip()
        values.append(value)
    return values


def _safe_run_relative_file(
    run_dir: Path,
    raw_path: object,
    *,
    field: str,
) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None, f"{field} must be a safe run-relative path"
    value = raw_path.strip()
    relative = PurePosixPath(value)
    if (
        "\\" in value
        or relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(char in value for char in "*?[")
    ):
        return None, f"{field} must be a safe run-relative path: {value}"

    try:
        run_root = run_dir.resolve(strict=True)
    except OSError as exc:
        return None, f"cannot resolve semantic review run directory: {exc}"
    candidate = run_root.joinpath(*relative.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, f"{field} does not exist: {value}"
    try:
        resolved.relative_to(run_root)
    except ValueError:
        return None, f"{field} escapes the semantic review run directory: {value}"
    if not resolved.is_file():
        return None, f"{field} is not a file: {value}"
    if Path(os.path.abspath(candidate)) != resolved:
        return None, f"{field} must not traverse a symlink: {value}"
    return resolved, None


def _contained_artifact_file(
    run_dir: Path,
    path: Path,
    *,
    field: str,
) -> tuple[Path | None, str | None]:
    try:
        run_root = run_dir.resolve(strict=True)
    except OSError as exc:
        return None, f"cannot resolve semantic review run directory: {exc}"
    candidate = path if path.is_absolute() else run_root / path
    candidate = Path(os.path.abspath(candidate))
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, f"missing semantic review {field}: {path.as_posix()}"
    try:
        resolved.relative_to(run_root)
    except ValueError:
        return None, f"semantic review {field} escapes the run directory: {path.as_posix()}"
    if not resolved.is_file():
        return None, f"semantic review {field} is not a file: {path.as_posix()}"
    if candidate != resolved:
        return None, f"semantic review {field} must not traverse a symlink: {path.as_posix()}"
    return resolved, None


def _load_scope_object(scope_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw_scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"cannot read semantic review scope: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid semantic review scope JSON: {exc}"
    if not isinstance(raw_scope, dict):
        return None, "semantic review scope JSON must be an object"
    return raw_scope, None


def _scope_has_digest_metadata(scope: Mapping[str, Any]) -> bool:
    return any(field in scope for field in _SEMANTIC_REVIEW_DIGEST_FIELDS)


def _semantic_review_artifact_currentness_issues(
    run_dir: Path,
    *,
    scope_path: Path,
    report_path: Path,
    expected_stage: str | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    resolved_scope, scope_path_error = _contained_artifact_file(
        run_dir,
        scope_path,
        field="scope",
    )
    resolved_report, report_path_error = _contained_artifact_file(
        run_dir,
        report_path,
        field="report",
    )
    if scope_path_error:
        errors.append(scope_path_error)
    if report_path_error:
        errors.append(report_path_error)
    if resolved_scope is None or resolved_report is None:
        return tuple(errors)

    scope, scope_error = _load_scope_object(resolved_scope)
    if scope_error or scope is None:
        return tuple([*errors, scope_error or "invalid semantic review scope"])

    stage = str(scope.get("stage") or expected_stage or "").strip()
    if expected_stage and stage != expected_stage:
        errors.append(
            "semantic review scope stage does not match requested stage "
            f"(expected={expected_stage}, got={stage or '(missing)'})"
        )

    source_artifacts = scope.get("source_artifacts")
    if not isinstance(source_artifacts, list):
        return tuple([*errors, "semantic review scope is missing source_artifacts"])

    if scope.get("semantic_review_input_schema") == LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA:
        if not source_artifacts:
            return tuple([*errors, "legacy semantic review scope has no source_artifacts"])
        report_mtime_ns = resolved_report.stat().st_mtime_ns
        for index, raw_path in enumerate(source_artifacts):
            source_path, path_error = _safe_run_relative_file(
                run_dir,
                raw_path,
                field=f"source_artifacts[{index}]",
            )
            if path_error:
                errors.append(path_error)
                continue
            assert source_path is not None
            if source_path.stat().st_mtime_ns > report_mtime_ns:
                errors.append(f"legacy semantic review source is newer than report: {raw_path}")
        return tuple(errors)

    missing_digest_fields = sorted(_SEMANTIC_REVIEW_DIGEST_FIELDS - set(scope))
    if missing_digest_fields:
        errors.append(
            "semantic review scope has incomplete digest metadata: "
            + ", ".join(missing_digest_fields)
        )
        return tuple(errors)
    if scope.get("semantic_review_input_schema") != SEMANTIC_REVIEW_INPUT_SCHEMA:
        errors.append(
            "unsupported semantic review input schema: "
            f"{scope.get('semantic_review_input_schema') or '(missing)'}"
        )

    entry_ids = scope.get("entry_ids")
    if not isinstance(entry_ids, list) or any(
        not isinstance(entry_id, str) or not entry_id.strip() for entry_id in entry_ids
    ):
        errors.append("semantic review scope has invalid entry_ids for input digest")
        entry_ids = []

    raw_records = scope.get("source_artifact_digests")
    records: list[dict[str, str]] = []
    if not isinstance(raw_records, list):
        errors.append("semantic review scope source_artifact_digests must be an array")
        raw_records = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            errors.append(f"source_artifact_digests[{index}] must be an object")
            continue
        raw_path = raw_record.get("path")
        raw_sha256 = raw_record.get("sha256")
        raw_policy = raw_record.get(
            REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
        )
        source_path, path_error = _safe_run_relative_file(
            run_dir,
            raw_path,
            field=f"source_artifact_digests[{index}].path",
        )
        if path_error:
            errors.append(path_error)
        if not isinstance(raw_sha256, str) or _SHA256_RE.fullmatch(raw_sha256) is None:
            errors.append(f"source_artifact_digests[{index}].sha256 must be a lowercase SHA-256")
        if source_path is not None and isinstance(raw_sha256, str):
            try:
                fingerprint = review_source_fingerprint(
                    source_path,
                    artifact_relpath=(
                        raw_path if isinstance(raw_path, str) else ""
                    ),
                    review_kind="semantic",
                    stage=stage,
                )
            except ReviewProjectionError as exc:
                errors.append(
                    "semantic review source projection is invalid: "
                    f"{raw_path}: {exc}"
                )
            else:
                if raw_policy is None:
                    # semantic_review_input_v1 originally stored raw file
                    # hashes without an explicit policy. Keep that evidence
                    # valid only while the exact legacy bytes still match.
                    current_sha256 = semantic_review_file_sha256(
                        source_path
                    )
                elif (
                    not isinstance(raw_policy, str)
                    or not raw_policy
                    or raw_policy != fingerprint.policy
                ):
                    errors.append(
                        "semantic review source fingerprint policy mismatch: "
                        f"{raw_path}"
                    )
                    current_sha256 = ""
                else:
                    current_sha256 = fingerprint.sha256
                if current_sha256 != raw_sha256:
                    errors.append(
                        f"semantic review source SHA-256 mismatch: {raw_path}"
                    )
        if isinstance(raw_path, str) and isinstance(raw_sha256, str):
            record = {"path": raw_path, "sha256": raw_sha256}
            if raw_policy is not None:
                record[REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD] = str(
                    raw_policy
                )
            records.append(record)

    normalized_sources = [
        raw_path.strip()
        for raw_path in source_artifacts
        if isinstance(raw_path, str) and raw_path.strip()
    ]
    record_paths = [record["path"] for record in records]
    if len(normalized_sources) != len(source_artifacts):
        errors.append("semantic review source_artifacts contains invalid paths")
    if len(set(normalized_sources)) != len(normalized_sources):
        errors.append("semantic review source_artifacts contains duplicate paths")
    if record_paths != normalized_sources:
        errors.append(
            "semantic review source_artifact_digests paths must exactly match source_artifacts"
        )

    artifacts = scope.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("semantic review scope is missing artifacts")
        artifacts = {}
    resolved_inputs: dict[str, Path] = {}
    for key in ("collection", "prompt"):
        artifact_path, artifact_error = _safe_run_relative_file(
            run_dir,
            artifacts.get(key),
            field=f"artifacts.{key}",
        )
        if artifact_error:
            errors.append(artifact_error)
        elif artifact_path is not None:
            resolved_inputs[key] = artifact_path
    for key, actual_path in (("scope", resolved_scope), ("report", resolved_report)):
        artifact_path, artifact_error = _safe_run_relative_file(
            run_dir,
            artifacts.get(key),
            field=f"artifacts.{key}",
        )
        if artifact_error:
            errors.append(artifact_error)
        elif artifact_path != actual_path:
            errors.append(f"semantic review artifacts.{key} does not match the checked {key}")

    stored_collection_sha256 = scope.get("collection_sha256")
    stored_prompt_sha256 = scope.get("prompt_sha256")
    stored_scope_binding_sha256 = scope.get("scope_binding_sha256")
    for key, stored_sha256 in (
        ("collection", stored_collection_sha256),
        ("prompt", stored_prompt_sha256),
    ):
        if not isinstance(stored_sha256, str) or _SHA256_RE.fullmatch(stored_sha256) is None:
            errors.append(f"semantic review {key}_sha256 must be a lowercase SHA-256")
            continue
        input_path = resolved_inputs.get(key)
        if input_path is not None and semantic_review_file_sha256(input_path) != stored_sha256:
            errors.append(f"semantic review {key} SHA-256 mismatch")
    expected_scope_binding_sha256 = semantic_review_scope_binding_sha256(scope)
    if (
        not isinstance(stored_scope_binding_sha256, str)
        or _SHA256_RE.fullmatch(stored_scope_binding_sha256) is None
    ):
        errors.append("semantic review scope_binding_sha256 must be a lowercase SHA-256")
    elif stored_scope_binding_sha256 != expected_scope_binding_sha256:
        errors.append("semantic review scope binding SHA-256 mismatch")

    request_revision = scope.get("request_revision")
    if request_revision is not None and (
        not isinstance(request_revision, str) or not request_revision.strip()
    ):
        errors.append("semantic review request_revision must be a non-empty string when present")
        request_revision = None

    stored_digest = scope.get("semantic_review_input_digest")
    if not isinstance(stored_digest, str) or _SHA256_DIGEST_RE.fullmatch(stored_digest) is None:
        errors.append("semantic_review_input_digest must be a sha256: digest")
    if (
        stage
        and isinstance(stored_collection_sha256, str)
        and isinstance(stored_prompt_sha256, str)
    ):
        expected_digest = semantic_review_input_digest(
            stage=stage,
            entry_ids=entry_ids,
            collection_sha256=stored_collection_sha256,
            prompt_sha256=stored_prompt_sha256,
            source_artifact_digests=records,
            request_revision=request_revision if isinstance(request_revision, str) else None,
            scope_binding_sha256=(
                stored_scope_binding_sha256
                if isinstance(stored_scope_binding_sha256, str)
                else ""
            ),
        )
        if stored_digest != expected_digest:
            errors.append("semantic_review_input_digest does not match canonical review inputs")

    try:
        report_text = resolved_report.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot read semantic review report: {exc}")
    else:
        report_digests = _report_scalar_values(report_text, "semantic_review_input_digest")
        if len(report_digests) != 1:
            errors.append("semantic review report must contain exactly one semantic_review_input_digest")
        elif report_digests[0] != stored_digest:
            errors.append("report semantic_review_input_digest does not match scope")
    return tuple(errors)


def semantic_review_currentness_issues(run_dir: Path, stage: str) -> tuple[str, ...]:
    """Return fail-closed currentness issues for a canonical stage and its emitted shards."""

    paths = semantic_review_relpaths(stage)
    errors = list(
        _semantic_review_artifact_currentness_issues(
            run_dir,
            scope_path=paths["scope"],
            report_path=paths["report"],
            expected_stage=stage,
        )
    )
    scope_path, _scope_path_error = _contained_artifact_file(
        run_dir,
        paths["scope"],
        field="scope",
    )
    if scope_path is None:
        return tuple(errors)
    scope, _scope_error = _load_scope_object(scope_path)
    if scope is None:
        return tuple(errors)
    review_scope = str(scope.get("review_scope") or "all_entries").strip()
    shards = scope.get("shards")
    if review_scope == "per_scene_shards" and (not isinstance(shards, list) or not shards):
        errors.append("per_scene_shards semantic review scope requires non-empty shards")
        return tuple(errors)
    if shards is None:
        return tuple(errors)
    if not isinstance(shards, list):
        errors.append("semantic review shards must be an array")
        return tuple(errors)

    canonical_entry_ids = scope.get("entry_ids")
    expected_entry_ids = (
        [str(value).strip() for value in canonical_entry_ids]
        if isinstance(canonical_entry_ids, list)
        else []
    )
    canonical_scope_rel = semantic_review_relpaths(stage)["scope"].as_posix()
    canonical_report_rel = semantic_review_relpaths(stage)["report"].as_posix()
    seen_shard_ids: set[str] = set()
    seen_artifact_paths: set[str] = set()
    assigned_entry_ids: list[str] = []
    for index, shard in enumerate(shards):
        if not isinstance(shard, dict):
            errors.append(f"semantic review shard {index + 1} must be an object")
            continue
        shard_id = str(shard.get("shard_id") or "").strip()
        scene_id = str(shard.get("scene_id") or "").strip()
        raw_shard_entry_ids = shard.get("entry_ids")
        shard_entry_ids = (
            [str(value).strip() for value in raw_shard_entry_ids]
            if isinstance(raw_shard_entry_ids, list)
            else []
        )
        if not shard_id:
            errors.append(f"semantic review shard {index + 1} is missing shard_id")
        elif shard_id in seen_shard_ids:
            errors.append(f"semantic review has duplicate shard_id: {shard_id}")
        else:
            seen_shard_ids.add(shard_id)
        if not scene_id:
            errors.append(f"semantic review shard {shard_id or index + 1} is missing scene_id")
        if (
            not isinstance(raw_shard_entry_ids, list)
            or not shard_entry_ids
            or any(not value for value in shard_entry_ids)
            or len(set(shard_entry_ids)) != len(shard_entry_ids)
        ):
            errors.append(
                f"semantic review shard {shard_id or index + 1} has invalid entry_ids"
            )
        if shard.get("entry_count") != len(shard_entry_ids):
            errors.append(
                f"semantic review shard {shard_id or index + 1} entry_count mismatch"
            )
        assigned_entry_ids.extend(shard_entry_ids)
        artifacts = shard.get("artifacts")
        if not isinstance(artifacts, dict):
            errors.append(f"semantic review shard {index + 1} is missing artifacts")
            continue
        for artifact_key in ("collection", "scope", "prompt", "report"):
            artifact_value = artifacts.get(artifact_key)
            if not isinstance(artifact_value, str) or not artifact_value.strip():
                errors.append(
                    f"semantic review shard {shard_id or index + 1} is missing {artifact_key} path"
                )
                continue
            if artifact_value in seen_artifact_paths:
                errors.append(
                    f"semantic review shard artifact path is reused: {artifact_value}"
                )
            seen_artifact_paths.add(artifact_value)
        shard_scope = artifacts.get("scope")
        shard_report = artifacts.get("report")
        if not isinstance(shard_scope, str) or not isinstance(shard_report, str):
            errors.append(f"semantic review shard {shard_id} is missing scope/report paths")
            continue
        errors.extend(
            f"semantic review shard {shard_id}: {issue}"
            for issue in _semantic_review_artifact_currentness_issues(
                run_dir,
                scope_path=Path(shard_scope),
                report_path=Path(shard_report),
                expected_stage=stage,
            )
        )
        resolved_shard_scope, shard_scope_error = _contained_artifact_file(
            run_dir,
            Path(shard_scope),
            field=f"shard {shard_id or index + 1} scope",
        )
        if shard_scope_error or resolved_shard_scope is None:
            continue
        shard_scope_data, shard_scope_load_error = _load_scope_object(resolved_shard_scope)
        if shard_scope_load_error or shard_scope_data is None:
            errors.append(
                f"semantic review shard {shard_id or index + 1}: "
                f"{shard_scope_load_error or 'invalid shard scope'}"
            )
            continue
        expected_links = {
            "shard_id": shard_id,
            "scene_id": scene_id,
            "entry_ids": shard_entry_ids,
            "canonical_scope": canonical_scope_rel,
            "canonical_report": canonical_report_rel,
        }
        for key, expected in expected_links.items():
            actual = shard_scope_data.get(key)
            if actual != expected:
                errors.append(
                    f"semantic review shard {shard_id or index + 1} {key} "
                    f"does not match canonical scope"
                )
        if shard_scope_data.get("artifacts") != artifacts:
            errors.append(
                f"semantic review shard {shard_id or index + 1} artifacts "
                "do not match canonical scope"
            )

    if review_scope == "per_scene_shards":
        if (
            len(assigned_entry_ids) != len(expected_entry_ids)
            or len(set(assigned_entry_ids)) != len(assigned_entry_ids)
            or set(assigned_entry_ids) != set(expected_entry_ids)
        ):
            errors.append(
                "per_scene_shards assigned entry_ids must exactly cover canonical entry_ids "
                f"(expected={expected_entry_ids}, got={assigned_entry_ids})"
            )
        coverage = scope.get("coverage")
        if not isinstance(coverage, dict):
            errors.append("per_scene_shards semantic review scope is missing coverage")
        else:
            expected_coverage = {
                "status": "valid",
                "expected_entry_count": len(expected_entry_ids),
                "assigned_entry_count": len(assigned_entry_ids),
                "expected_entry_ids": expected_entry_ids,
                "assigned_entry_ids": assigned_entry_ids,
                "missing_entry_ids": [],
                "duplicate_entry_ids": [],
            }
            for key, expected in expected_coverage.items():
                if coverage.get(key) != expected:
                    errors.append(
                        f"per_scene_shards coverage.{key} does not match canonical assignment"
                    )
    return tuple(errors)


def semantic_review_sources_are_current(run_dir: Path, stage: str) -> bool:
    return not semantic_review_currentness_issues(run_dir, stage)


def _scope_entry_count(scope_path: Path, *, rel_scope: Path | None = None) -> tuple[int | None, str | None]:
    if not scope_path.exists():
        rel = rel_scope or scope_path
        return None, f"missing semantic review scope: {rel.as_posix()}"
    try:
        data = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid semantic review scope JSON: {exc}"
    raw = data.get("entry_count")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw, None
    return None, "semantic review scope is missing integer entry_count"


def _scope_entry_ids(scope_path: Path) -> tuple[list[str], str | None]:
    if not scope_path.exists():
        return [], f"missing semantic review scope: {scope_path.as_posix()}"
    try:
        data = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"invalid semantic review scope JSON: {exc}"
    raw = data.get("entry_ids")
    if raw is None:
        raw = data.get("selectors")
    if not isinstance(raw, list):
        return [], "semantic review scope is missing entry_ids"
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        entry_ids = [value.strip() for value in raw if isinstance(value, str) and value.strip()]
        return entry_ids, "semantic review scope contains blank entry_ids"
    entry_ids = [value.strip() for value in raw]
    if len(set(entry_ids)) != len(entry_ids):
        return entry_ids, "semantic review scope contains duplicate entry_ids"
    return entry_ids, None


def _report_list_values(text: str, key: str) -> list[str]:
    values: list[str] = []
    collecting = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(f"{key}:") or stripped.startswith(f"- {key}:"):
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                body = inline[1:-1].strip()
                return [
                    value.strip().strip("`\"'")
                    for value in body.split(",")
                    if value.strip().strip("`\"'")
                ]
            if inline:
                scalar = inline.strip("`\"'")
                return [] if scalar in {"[]", "..."} else [scalar]
            collecting = True
            continue
        if collecting:
            if not stripped:
                continue
            if not stripped.startswith("-"):
                break
            value = stripped[1:].strip().strip("`\"'")
            if value and value not in {"[]", "..."}:
                values.append(value)
    return values


def _report_has_list_field(text: str, key: str) -> bool:
    return re.search(rf"(?m)^-?\s*{re.escape(key)}\s*:", text) is not None


def _report_json_value(text: str, key: str) -> tuple[Any | None, str | None]:
    matches = list(re.finditer(rf"(?m)^-?\s*{re.escape(key)}\s*:\s*", text))
    if len(matches) != 1:
        return None, (
            f"semantic review report must contain exactly one {key} field "
            f"(found={len(matches)})"
        )
    match = matches[0]
    remainder = text[match.end() :].lstrip()
    try:
        value, _end = json.JSONDecoder().raw_decode(remainder)
    except json.JSONDecodeError as exc:
        return None, f"semantic review report has invalid {key} JSON: {exc}"
    return value, None


def _foundation_criteria_errors(report_text: str, stage: str, overall_status: str) -> list[str]:
    expected_ids = list(FOUNDATION_SEMANTIC_CRITERIA[stage])
    raw_results, parse_error = _report_json_value(report_text, "criteria_results_json")
    if parse_error:
        return [parse_error]
    if not isinstance(raw_results, list):
        return ["semantic review criteria_results_json must be a JSON array"]

    errors: list[str] = []
    result_ids: list[str] = []
    statuses: dict[str, str] = {}
    for index, raw_result in enumerate(raw_results, start=1):
        if not isinstance(raw_result, dict):
            errors.append(f"semantic review criterion result {index} must be an object")
            continue
        criterion_id = str(raw_result.get("criterion_id") or "").strip()
        result_ids.append(criterion_id)
        status = str(raw_result.get("status") or "").strip().lower()
        if status not in {"passed", "failed"}:
            errors.append(
                f"semantic review criterion {criterion_id or index} status must be passed or failed"
            )
        elif criterion_id:
            statuses[criterion_id] = status
        evidence = raw_result.get("evidence")
        if isinstance(evidence, list):
            evidence_values = [str(value).strip() for value in evidence if str(value).strip()]
        else:
            evidence_values = [str(evidence).strip()] if evidence is not None and str(evidence).strip() else []
        if not evidence_values or any(value in {"...", "pending"} for value in evidence_values):
            errors.append(
                f"semantic review criterion {criterion_id or index} requires non-empty evidence"
            )

    if result_ids != expected_ids:
        errors.append(
            "semantic review criterion_ids must exactly match the required ordered criteria "
            f"(expected={expected_ids}, got={result_ids})"
        )
    if overall_status in PASSING_JUDGMENT_STATUSES and any(
        statuses.get(criterion_id) != "passed" for criterion_id in expected_ids
    ):
        errors.append("passed foundation semantic review requires every criterion status to be passed")
    return errors


def _check_review_artifacts(
    run_dir: Path,
    *,
    artifacts: dict[str, Path],
    require_entries: bool,
    require_exact_entry_coverage: bool = False,
    require_digest: bool = False,
) -> SemanticReviewStatus:
    errors: list[str] = []
    for rel in artifacts.values():
        if not (run_dir / rel).exists():
            errors.append(f"missing semantic review artifact: {rel.as_posix()}")

    entry_count, scope_error = _scope_entry_count(run_dir / artifacts["scope"], rel_scope=artifacts["scope"])
    if scope_error:
        errors.append(scope_error)
    if require_entries and entry_count == 0:
        errors.append("semantic review scope has zero entries")

    report_path = run_dir / artifacts["report"]
    status = ""
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        errors.extend(
            semantic_report_required_field_issues(
                report_text,
                require_digest=require_digest,
            )
        )
        status = parse_judgment_report_status(report_text)
        if "`...`" in report_text or "- `...`" in report_text:
            errors.append("semantic review report still contains template placeholder entries")
        if status not in PASSING_JUDGMENT_STATUSES:
            errors.append(f"semantic review status must be passed, got {status or '(missing)'}")
        if require_exact_entry_coverage:
            expected_entry_ids, entry_ids_error = _scope_entry_ids(run_dir / artifacts["scope"])
            if entry_ids_error:
                errors.append(entry_ids_error)
            if entry_count is not None and entry_count != len(expected_entry_ids):
                errors.append(
                    "semantic review scope entry_count must match entry_ids length "
                    f"(entry_count={entry_count}, entry_ids={len(expected_entry_ids)})"
                )
            if not _report_has_list_field(report_text, "reviewed_entries"):
                errors.append("semantic review report is missing reviewed_entries")
            reviewed_entries = _report_list_values(report_text, "reviewed_entries")
            if reviewed_entries != expected_entry_ids:
                errors.append(
                    "semantic review reviewed_entries coverage must exactly match scope entry_ids "
                    f"(expected={expected_entry_ids}, got={reviewed_entries})"
                )
            if not _report_has_list_field(report_text, "blocked_entries"):
                errors.append("semantic review report is missing blocked_entries")
            if not _report_has_list_field(report_text, "failed_selectors"):
                errors.append("semantic review report is missing failed_selectors")
            blocked_entries = _report_list_values(report_text, "blocked_entries")
            failed_selectors = _report_list_values(report_text, "failed_selectors")
            if status in PASSING_JUDGMENT_STATUSES and blocked_entries:
                errors.append("passed semantic review must have empty blocked_entries")
            if status in PASSING_JUDGMENT_STATUSES and failed_selectors:
                errors.append("passed semantic review must have empty failed_selectors")
            stage = artifacts["report"].name.split(".", 1)[0]
            if stage in FOUNDATION_SEMANTIC_REVIEW_STAGES:
                errors.extend(_foundation_criteria_errors(report_text, stage, status))

    return SemanticReviewStatus(status=status, entry_count=entry_count, errors=tuple(errors))


def check_semantic_review(run_dir: Path, stage: str, *, require_entries: bool = True) -> SemanticReviewStatus:
    scope_path = run_dir / semantic_review_relpaths(stage)["scope"]
    scope, _scope_error = _load_scope_object(scope_path) if scope_path.exists() else (None, None)
    explicit_legacy = (
        isinstance(scope, dict)
        and scope.get("semantic_review_input_schema") == LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA
    )
    result = _check_review_artifacts(
        run_dir,
        artifacts=semantic_review_relpaths(stage),
        require_entries=require_entries,
        require_exact_entry_coverage=True,
        require_digest=not explicit_legacy,
    )
    currentness_errors = semantic_review_currentness_issues(run_dir, stage)
    if currentness_errors:
        result = SemanticReviewStatus(
            status=result.status,
            entry_count=result.entry_count,
            errors=tuple([*result.errors, *currentness_errors]),
        )
    return result


def check_image_prompt_judgment(run_dir: Path, *, require_entries: bool = True) -> SemanticReviewStatus:
    generic_paths = semantic_review_relpaths("image_prompt")
    legacy_status = _check_review_artifacts(
        run_dir,
        artifacts={
            "collection": IMAGE_PROMPT_JUDGMENT_COLLECTION,
            "scope": IMAGE_PROMPT_JUDGMENT_SCOPE,
            "prompt": IMAGE_PROMPT_JUDGMENT_PROMPT,
            "report": IMAGE_PROMPT_JUDGMENT_REPORT,
        },
        require_entries=require_entries,
        require_exact_entry_coverage=True,
        require_digest=False,
    )
    if any((run_dir / rel).exists() for rel in generic_paths.values()):
        # Once the canonical generic artifact set exists it is authoritative.
        # Falling back to an older passing judgment here can mask a pending or
        # failed current review revision.
        return check_semantic_review(run_dir, "image_prompt", require_entries=require_entries)
    return legacy_status


def review_status_to_state(stage: str, result: SemanticReviewStatus) -> dict[str, str]:
    return semantic_state_updates(
        stage,
        status=result.status or "failed",
        entry_count=result.entry_count,
        error_count=len(result.errors),
    )
