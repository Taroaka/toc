"""Typed, deterministic contracts for image-generation request snapshots.

The Markdown request files are review projections.  This module provides the
versioned JSON contract that runtime code can freeze, validate, and bind to
request-bound output provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.world_walk_source import (
    directory_identity_nofollow,
    open_directory_nofollow,
    read_regular_file_nofollow,
    sha256_regular_file_nofollow,
)
from toc.atomic_exchange import atomic_exchange_names
from toc.run_root_binding import (
    PathIdentity,
    RunRootBindingError,
    current_run_root_binding,
    require_bound_run_root,
)


SNAPSHOT_SCHEMA_VERSION = "toc.image_generation_request_snapshot.v1"
DEFAULT_SNAPSHOT_FILENAME = "image_generation_request_snapshot.json"
_SHA256_LENGTH = 64
_SUCCESS_STATUSES = {"completed", "success", "succeeded"}
_SNAPSHOT_CLEANUP_DIRECTORY_NONCE = secrets.token_hex(16)


class ImageRequestSnapshotError(ValueError):
    """Raised when a request snapshot is malformed, stale, or unsafe."""


@dataclass(frozen=True)
class ImageRequestReference:
    path: str
    sha256: str | None
    deferred: bool = False
    producer_item_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "deferred": self.deferred,
            "producer_item_id": self.producer_item_id,
        }


@dataclass(frozen=True)
class ImageRequestSnapshotItem:
    item_id: str
    kind: str
    destination: str
    prompt: str
    prompt_sha256: str
    prompt_policy_version: str
    compiler_version: str
    source_digest: str
    references: tuple[ImageRequestReference, ...]
    request_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **_item_digest_payload(self),
            "request_digest": self.request_digest,
        }


@dataclass(frozen=True)
class ImageRequestSnapshot:
    schema_version: str
    request_revision: str
    kind: str
    created_at: str
    source_artifact: str | None
    source_artifact_sha256: str | None
    items: tuple[ImageRequestSnapshotItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_revision": self.request_revision,
            "kind": self.kind,
            "created_at": self.created_at,
            "source_artifact": self.source_artifact,
            "source_artifact_sha256": self.source_artifact_sha256,
            "items": [item.to_dict() for item in self.items],
        }

    def item(self, item_id: str) -> ImageRequestSnapshotItem:
        for item in self.items:
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)


@dataclass(frozen=True)
class OutputProvenanceMatch:
    matches: bool
    reasons: tuple[str, ...]

    def __bool__(self) -> bool:
        return self.matches


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes suitable for hashing."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_canonical_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    binding = current_run_root_binding()
    if binding is not None:
        lexical_path = Path(os.path.abspath(os.fspath(path)))
        try:
            relative = lexical_path.relative_to(binding.lexical_root)
        except ValueError:
            relative = None
        if relative is not None:
            require_bound_run_root(Path(binding.lexical_root))
            return sha256_regular_file_nofollow(
                Path(binding.lexical_root),
                relative,
                expected_root_identity=binding.identity,
            )
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_root(
    run_dir: Path,
    *,
    expected_root_identity: PathIdentity | None = None,
) -> tuple[Path, PathIdentity]:
    """Return a lexical real-directory root and its pinned identity.

    An ambient binding is authoritative.  Unbound callers are still pinned to
    the directory inode observed at entry so later reads and publication never
    fall back to a replacement pathname.
    """

    lexical = Path(os.path.abspath(os.fspath(run_dir)))
    binding = current_run_root_binding()
    if binding is not None:
        if os.fspath(lexical) != binding.lexical_root:
            raise RunRootBindingError(
                "snapshot operation escaped the active bound run root: "
                f"{lexical} != {binding.lexical_root}"
            )
        if (
            expected_root_identity is not None
            and expected_root_identity != binding.identity
        ):
            raise RunRootBindingError(
                "snapshot root identity conflicts with the active binding"
            )
        require_bound_run_root(lexical)
        return lexical, binding.identity

    try:
        identity = directory_identity_nofollow(lexical)
    except (OSError, ValueError) as exc:
        raise ImageRequestSnapshotError(
            f"snapshot run directory is unsafe: {lexical}"
        ) from exc
    if expected_root_identity is not None and identity != expected_root_identity:
        raise ImageRequestSnapshotError(
            f"snapshot run directory identity changed: {lexical}"
        )
    return lexical, identity


def _snapshot_file_sha256(
    run_dir: Path,
    relative_path: str | Path,
    *,
    expected_root_identity: PathIdentity,
) -> str:
    return sha256_regular_file_nofollow(
        run_dir,
        relative_path,
        expected_root_identity=expected_root_identity,
    )


def materialize_request_snapshot(
    run_dir: Path,
    *,
    kind: str,
    items: Iterable[Mapping[str, Any]],
    compiler_version: str | None = None,
    source_artifact: str | None = None,
    created_at: str | None = None,
    defer_missing_references: bool = False,
    expected_root_identity: PathIdentity | None = None,
) -> ImageRequestSnapshot:
    """Freeze normalized generic request dictionaries into a v1 snapshot.

    Existing reference files are content-hashed immediately.  A missing
    reference is allowed only when another item in the same snapshot produces
    that exact destination; such a reference is marked deferred and must be
    resolved before provider submission.
    """

    base, root_identity = _snapshot_root(
        run_dir,
        expected_root_identity=expected_root_identity,
    )
    normalized_kind = _required_text(kind, field="kind")
    raw_items = list(items)
    if not raw_items:
        raise ImageRequestSnapshotError("snapshot must contain at least one item")
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise ImageRequestSnapshotError("snapshot items must be mappings")

    identities: list[tuple[Mapping[str, Any], str, str, str]] = []
    seen_ids: set[str] = set()
    producer_by_destination: dict[str, str] = {}
    for raw in raw_items:
        item_id = _required_mapping_text(raw, "item_id", "id", "selector", field="item_id")
        if item_id in seen_ids:
            raise ImageRequestSnapshotError(f"duplicate item id: {item_id}")
        seen_ids.add(item_id)
        item_kind = _optional_mapping_text(raw, "kind") or normalized_kind
        if item_kind != normalized_kind:
            raise ImageRequestSnapshotError(
                f"item kind mismatch for {item_id}: expected {normalized_kind}, got {item_kind}"
            )
        destination_raw = _required_mapping_text(raw, "destination", "output", field="destination")
        destination = _normalize_run_relative_path(base, destination_raw, field="destination")
        previous_producer = producer_by_destination.get(destination)
        if previous_producer is not None:
            raise ImageRequestSnapshotError(
                f"duplicate destination: {destination} ({previous_producer}, {item_id})"
            )
        producer_by_destination[destination] = item_id
        identities.append((raw, item_id, item_kind, destination))

    materialized_items: list[ImageRequestSnapshotItem] = []
    for raw, item_id, item_kind, destination in identities:
        api_payload = raw.get("api_prompt_payload")
        payload = api_payload if isinstance(api_payload, Mapping) else {}
        prompt = _first_nonempty_text(raw.get("prompt"), payload.get("prompt"))
        if not prompt:
            raise ImageRequestSnapshotError(f"prompt is required for {item_id}")
        prompt_sha256 = sha256_text(prompt)
        declared_prompt_sha256 = _first_nonempty_text(
            raw.get("prompt_sha256"),
            raw.get("promptSha256"),
            payload.get("sha256"),
        )
        if declared_prompt_sha256 and declared_prompt_sha256 != prompt_sha256:
            raise ImageRequestSnapshotError(f"prompt_sha256 mismatch for {item_id}")

        prompt_policy_version = _first_nonempty_text(
            raw.get("prompt_policy_version"),
            raw.get("promptPolicyVersion"),
            payload.get("policy_version"),
        )
        if not prompt_policy_version:
            raise ImageRequestSnapshotError(f"prompt_policy_version is required for {item_id}")
        item_compiler_version = _first_nonempty_text(
            raw.get("compiler_version"),
            raw.get("compilerVersion"),
            payload.get("compiler_version"),
            compiler_version,
        )
        if not item_compiler_version:
            raise ImageRequestSnapshotError(f"compiler_version is required for {item_id}")
        source_digest = _first_nonempty_text(
            raw.get("source_digest"),
            raw.get("sourceDigest"),
            raw.get("source_sha256"),
            payload.get("source_digest"),
        )
        _require_sha256(source_digest, field=f"source_digest for {item_id}")

        raw_references = raw.get("references") or []
        if not isinstance(raw_references, (list, tuple)):
            raise ImageRequestSnapshotError(f"references must be a list for {item_id}")
        references: list[ImageRequestReference] = []
        for raw_reference in raw_references:
            declared_reference_sha256: str | None = None
            declared_producer: str | None = None
            if isinstance(raw_reference, Mapping):
                reference_raw = _required_mapping_text(raw_reference, "path", field="reference path")
                declared_reference_sha256 = _optional_mapping_text(raw_reference, "sha256")
                declared_producer = _optional_mapping_text(
                    raw_reference,
                    "producer_item_id",
                    "producerItemId",
                )
            else:
                reference_raw = _required_text(raw_reference, field="reference path")
            reference_path = _normalize_run_relative_path(base, reference_raw, field="reference")
            producer_item_id = producer_by_destination.get(reference_path)
            if producer_item_id is not None:
                if producer_item_id == item_id:
                    try:
                        actual_sha256 = _snapshot_file_sha256(
                            base,
                            reference_path,
                            expected_root_identity=root_identity,
                        )
                    except (OSError, ValueError) as exc:
                        raise ImageRequestSnapshotError(
                            f"self-reference does not exist for {item_id}: {reference_path}"
                        ) from exc
                    if declared_reference_sha256 and declared_reference_sha256 != actual_sha256:
                        raise ImageRequestSnapshotError(
                            f"reference sha256 mismatch for {item_id}: {reference_path}"
                        )
                    references.append(
                        ImageRequestReference(
                            path=reference_path,
                            sha256=actual_sha256,
                        )
                    )
                    continue
                if declared_producer and declared_producer != producer_item_id:
                    raise ImageRequestSnapshotError(
                        f"reference producer mismatch for {item_id}: {reference_path}"
                    )
                references.append(
                    ImageRequestReference(
                        path=reference_path,
                        sha256=None,
                        deferred=True,
                        producer_item_id=producer_item_id,
                    )
                )
                continue
            try:
                actual_sha256 = _snapshot_file_sha256(
                    base,
                    reference_path,
                    expected_root_identity=root_identity,
                )
            except FileNotFoundError:
                actual_sha256 = None
            except (OSError, ValueError) as exc:
                raise ImageRequestSnapshotError(
                    f"reference is unsafe for {item_id}: {reference_path}"
                ) from exc
            if actual_sha256 is not None:
                if declared_reference_sha256 and declared_reference_sha256 != actual_sha256:
                    raise ImageRequestSnapshotError(
                        f"reference sha256 mismatch for {item_id}: {reference_path}"
                    )
                references.append(
                    ImageRequestReference(
                        path=reference_path,
                        sha256=actual_sha256,
                    )
                )
                continue
            if defer_missing_references:
                references.append(
                    ImageRequestReference(
                        path=reference_path,
                        sha256=None,
                        deferred=True,
                        producer_item_id=f"external:{reference_path}",
                    )
                )
                continue
            raise ImageRequestSnapshotError(
                f"reference does not exist and has no snapshot producer for {item_id}: {reference_path}"
            )

        item_without_digest = ImageRequestSnapshotItem(
            item_id=item_id,
            kind=item_kind,
            destination=destination,
            prompt=prompt,
            prompt_sha256=prompt_sha256,
            prompt_policy_version=prompt_policy_version,
            compiler_version=item_compiler_version,
            source_digest=source_digest,
            references=tuple(references),
            request_digest="",
        )
        materialized_items.append(
            replace(
                item_without_digest,
                request_digest=sha256_canonical_json(_item_digest_payload(item_without_digest)),
            )
        )

    materialized_items.sort(key=lambda item: item.item_id)
    source_path: str | None = None
    source_sha256: str | None = None
    if source_artifact:
        source_path = _normalize_run_relative_path(base, source_artifact, field="source_artifact")
        try:
            source_sha256 = _snapshot_file_sha256(
                base,
                source_path,
                expected_root_identity=root_identity,
            )
        except (OSError, ValueError) as exc:
            raise ImageRequestSnapshotError(
                f"source_artifact does not exist: {source_path}"
            ) from exc

    snapshot_without_revision = ImageRequestSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        request_revision="",
        kind=normalized_kind,
        created_at=created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        source_artifact=source_path,
        source_artifact_sha256=source_sha256,
        items=tuple(materialized_items),
    )
    return replace(
        snapshot_without_revision,
        request_revision=_expected_request_revision(snapshot_without_revision),
    )


def _snapshot_entry_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
    )


def _snapshot_file_state(
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


def _snapshot_directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise ImageRequestSnapshotError(
            "snapshot publication requires no-follow directory operations"
        )
    return (
        os.O_RDONLY
        | nofollow
        | directory
        | getattr(os, "O_CLOEXEC", 0)
    )


def _snapshot_named_stat(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _snapshot_verify_directory_chain(
    *,
    run_root: Path,
    root_fd: int,
    root_identity: PathIdentity,
    links: list[tuple[int, str, int]],
) -> None:
    try:
        named_root = os.stat(run_root, follow_symlinks=False)
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(named_root.st_mode)
            or not stat.S_ISDIR(opened_root.st_mode)
            or (opened_root.st_dev, opened_root.st_ino) != root_identity
            or _snapshot_entry_identity(named_root)
            != _snapshot_entry_identity(opened_root)
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication root identity changed"
            )
        for parent_fd, name, child_fd in links:
            named_child = os.stat(
                name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            opened_child = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(named_child.st_mode)
                or not stat.S_ISDIR(opened_child.st_mode)
                or _snapshot_entry_identity(named_child)
                != _snapshot_entry_identity(opened_child)
            ):
                raise ImageRequestSnapshotError(
                    f"snapshot publication ancestor identity changed: {name}"
                )
    except ImageRequestSnapshotError:
        raise
    except OSError as exc:
        raise ImageRequestSnapshotError(
            "snapshot publication ancestry became unsafe"
        ) from exc


def _snapshot_open_parent_chain(
    *,
    root_fd: int,
    parent_parts: tuple[str, ...],
) -> tuple[int, list[int], list[tuple[int, str, int]]]:
    current = root_fd
    opened: list[int] = []
    links: list[tuple[int, str, int]] = []
    flags = _snapshot_directory_flags()
    try:
        for part in parent_parts:
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o755, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(part, flags, dir_fd=current)
                os.fsync(current)
            named = os.stat(part, dir_fd=current, follow_symlinks=False)
            opened_child = os.fstat(child)
            if (
                not stat.S_ISDIR(named.st_mode)
                or _snapshot_entry_identity(named)
                != _snapshot_entry_identity(opened_child)
            ):
                os.close(child)
                raise ImageRequestSnapshotError(
                    f"snapshot publication ancestor is unsafe: {part}"
                )
            links.append((current, part, child))
            opened.append(child)
            current = child
    except Exception:
        for descriptor in reversed(opened):
            os.close(descriptor)
        raise
    return current, opened, links


def _snapshot_open_cleanup_directory(parent_fd: int) -> int:
    name = (
        f".toc-snapshot-cleanup-{os.getpid()}-"
        f"{_SNAPSHOT_CLEANUP_DIRECTORY_NONCE}"
    )
    created = False
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    try:
        descriptor = os.open(
            name,
            _snapshot_directory_flags(),
            dir_fd=parent_fd,
        )
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _snapshot_entry_identity(named)
            != _snapshot_entry_identity(opened)
            or opened.st_uid != os.geteuid()
        ):
            raise OSError("snapshot cleanup directory identity is unsafe")
        if created:
            os.fchmod(descriptor, 0o700)
            opened = os.fstat(descriptor)
        if stat.S_IMODE(opened.st_mode) != 0o700:
            raise OSError("snapshot cleanup directory is not owner-only")
        return descriptor
    except Exception:
        if "descriptor" in locals():
            os.close(descriptor)
        raise


def _snapshot_restore_protected_entry(
    *,
    cleanup_fd: int,
    cleanup_name: str,
    parent_fd: int,
    destination_name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    protected = _snapshot_named_stat(cleanup_fd, cleanup_name)
    if (
        protected is None
        or _snapshot_entry_identity(protected) != expected_identity
        or not stat.S_ISREG(protected.st_mode)
    ):
        return False
    if _snapshot_named_stat(parent_fd, destination_name) is not None:
        return False
    try:
        os.link(
            cleanup_name,
            destination_name,
            src_dir_fd=cleanup_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError:
        return False
    restored = _snapshot_named_stat(parent_fd, destination_name)
    if (
        restored is None
        or _snapshot_entry_identity(restored) != expected_identity
    ):
        return False
    try:
        os.unlink(cleanup_name, dir_fd=cleanup_fd)
    except OSError:
        return False
    final = _snapshot_named_stat(parent_fd, destination_name)
    return (
        final is not None
        and stat.S_ISREG(final.st_mode)
        and final.st_nlink == 1
        and _snapshot_entry_identity(final) == expected_identity
    )


def _snapshot_cleanup_public_name(
    *,
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
    cleanup_fd: int,
    dispose: bool,
) -> bool:
    current = _snapshot_named_stat(parent_fd, name)
    if current is None:
        return True
    if _snapshot_entry_identity(current) != expected_identity:
        return False
    quarantine_name = f"entry-{secrets.token_hex(16)}"
    try:
        os.rename(
            name,
            quarantine_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=cleanup_fd,
        )
    except OSError:
        return False
    quarantined = _snapshot_named_stat(cleanup_fd, quarantine_name)
    if (
        quarantined is None
        or _snapshot_entry_identity(quarantined) != expected_identity
    ):
        _snapshot_restore_protected_entry(
            cleanup_fd=cleanup_fd,
            cleanup_name=quarantine_name,
            parent_fd=parent_fd,
            destination_name=name,
            expected_identity=(
                _snapshot_entry_identity(quarantined)
                if quarantined is not None
                else expected_identity
            ),
        )
        return False
    if not dispose:
        return True
    try:
        os.unlink(quarantine_name, dir_fd=cleanup_fd)
    except OSError:
        return False
    return True


def _snapshot_unlink_protected(
    cleanup_fd: int,
    name: str,
    expected_identity: tuple[int, int, int],
) -> bool:
    current = _snapshot_named_stat(cleanup_fd, name)
    if current is None:
        return True
    if _snapshot_entry_identity(current) != expected_identity:
        return False
    try:
        os.unlink(name, dir_fd=cleanup_fd)
    except OSError:
        return False
    return True


def write_run_file_atomic_nofollow(
    path: Path,
    data: bytes,
    *,
    run_dir: Path | None = None,
    expected_root_identity: PathIdentity | None = None,
) -> Path:
    """Publish one run-local private regular file through retained dirfds.

    The old leaf remains available for rollback until both the new file and
    its parent-directory entry have been fsynced.  Publication is no-clobber:
    a leaf that races into place wins and is never overwritten.
    """

    base, root_identity = _snapshot_root(
        run_dir or path.parent,
        expected_root_identity=expected_root_identity,
    )
    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise ImageRequestSnapshotError(
            f"snapshot publication path escapes run directory: {path}"
        ) from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ImageRequestSnapshotError(
            f"snapshot publication path is unsafe: {path}"
        )

    root_fd = -1
    parent_fd = -1
    target_fd = -1
    temporary_fd = -1
    cleanup_fd = -1
    opened_directories: list[int] = []
    directory_links: list[tuple[int, str, int]] = []
    temporary_name = (
        f".{relative.name}.snapshot-{os.getpid()}-{secrets.token_hex(16)}.tmp"
    )
    temporary_identity: tuple[int, int, int] | None = None
    temporary_present = False
    target_initial_state: tuple[int, int, int, int, int, int, int] | None = None
    backup_identity: tuple[int, int, int] | None = None
    published = False
    exchange_attempted = False
    exchange_pending = False
    exchange_resolved = False
    committed = False
    rollback_failure = ""
    rollback_fsync_failure = ""

    try:
        binding = current_run_root_binding()
        if binding is not None:
            require_bound_run_root(base)
            root_fd = os.dup(binding.descriptor)
        else:
            root_fd = open_directory_nofollow(
                base,
                expected_identity=root_identity,
            )
        opened_root = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or (opened_root.st_dev, opened_root.st_ino) != root_identity
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication root descriptor is unsafe"
            )
        parent_fd, opened_directories, directory_links = (
            _snapshot_open_parent_chain(
                root_fd=root_fd,
                parent_parts=relative.parts[:-1],
            )
        )
        _snapshot_verify_directory_chain(
            run_root=base,
            root_fd=root_fd,
            root_identity=root_identity,
            links=directory_links,
        )
        destination_name = relative.parts[-1]
        target_entry = _snapshot_named_stat(parent_fd, destination_name)
        if target_entry is not None:
            if not stat.S_ISREG(target_entry.st_mode):
                raise ImageRequestSnapshotError(
                    "snapshot publication target is not a safe regular file"
                )
            if target_entry.st_nlink != 1:
                raise ImageRequestSnapshotError(
                    "snapshot publication target has multiple hard links"
                )
            target_fd = os.open(
                destination_name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_fd,
            )
            opened_target = os.fstat(target_fd)
            current_target = _snapshot_named_stat(parent_fd, destination_name)
            if (
                current_target is None
                or not stat.S_ISREG(opened_target.st_mode)
                or _snapshot_file_state(opened_target)
                != _snapshot_file_state(current_target)
            ):
                raise ImageRequestSnapshotError(
                    "snapshot publication target identity changed before write"
                )
            target_initial_state = _snapshot_file_state(opened_target)

        cleanup_fd = _snapshot_open_cleanup_directory(parent_fd)
        temporary_fd = os.open(
            temporary_name,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_fd,
        )
        temporary_stat = os.fstat(temporary_fd)
        if (
            not stat.S_ISREG(temporary_stat.st_mode)
            or temporary_stat.st_nlink != 1
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication temporary is not a private regular file"
            )
        temporary_identity = _snapshot_entry_identity(temporary_stat)
        temporary_present = True
        remaining = memoryview(data)
        while remaining:
            written = os.write(temporary_fd, remaining)
            if written <= 0:
                raise OSError("snapshot publication write made no progress")
            remaining = remaining[written:]
        os.fsync(temporary_fd)
        os.lseek(temporary_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(temporary_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        held_temporary = os.fstat(temporary_fd)
        named_temporary = _snapshot_named_stat(parent_fd, temporary_name)
        if (
            digest.digest() != hashlib.sha256(data).digest()
            or named_temporary is None
            or not stat.S_ISREG(named_temporary.st_mode)
            or held_temporary.st_nlink != 1
            or named_temporary.st_nlink != 1
            or _snapshot_entry_identity(held_temporary) != temporary_identity
            or _snapshot_entry_identity(named_temporary) != temporary_identity
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication temporary identity changed"
            )

        _snapshot_verify_directory_chain(
            run_root=base,
            root_fd=root_fd,
            root_identity=root_identity,
            links=directory_links,
        )
        if target_fd >= 0:
            current_opened_target = os.fstat(target_fd)
            current_named_target = _snapshot_named_stat(
                parent_fd,
                destination_name,
            )
            if (
                current_named_target is None
                or current_named_target.st_nlink != 1
                or current_opened_target.st_nlink != 1
                or _snapshot_file_state(current_opened_target)
                != target_initial_state
                or _snapshot_file_state(current_named_target)
                != target_initial_state
            ):
                raise ImageRequestSnapshotError(
                    "snapshot publication target identity changed during write"
                )
            backup_identity = _snapshot_entry_identity(current_opened_target)
            # Existing canonical leaves are replaced with one native exchange.
            # The old inode remains under ``temporary_name`` until the new
            # canonical entry is durably committed, so readers can observe old
            # or new bytes but never a transient missing name.
            exchange_attempted = True
            try:
                atomic_exchange_names(
                    parent_fd,
                    temporary_name,
                    parent_fd,
                    destination_name,
                )
            except BaseException:
                reconciled_target = _snapshot_named_stat(
                    parent_fd,
                    destination_name,
                )
                reconciled_old = _snapshot_named_stat(
                    parent_fd,
                    temporary_name,
                )
                if (
                    reconciled_target is not None
                    and reconciled_old is not None
                    and _snapshot_entry_identity(reconciled_target)
                    == temporary_identity
                    and _snapshot_entry_identity(reconciled_old)
                    == backup_identity
                ):
                    published = True
                    exchange_pending = True
                    temporary_present = False
                elif (
                    reconciled_target is not None
                    and reconciled_old is not None
                    and _snapshot_entry_identity(reconciled_target)
                    == backup_identity
                    and _snapshot_entry_identity(reconciled_old)
                    == temporary_identity
                ):
                    exchange_resolved = True
                raise
            published = True
            exchange_pending = True
            temporary_present = False

            exchanged_target = _snapshot_named_stat(
                parent_fd,
                destination_name,
            )
            exchanged_old = _snapshot_named_stat(
                parent_fd,
                temporary_name,
            )
            if (
                exchanged_target is None
                or exchanged_old is None
                or not stat.S_ISREG(exchanged_target.st_mode)
                or not stat.S_ISREG(exchanged_old.st_mode)
                or exchanged_target.st_nlink != 1
                or exchanged_old.st_nlink != 1
                or _snapshot_entry_identity(exchanged_target)
                != temporary_identity
                or _snapshot_entry_identity(exchanged_old)
                != backup_identity
                or _snapshot_entry_identity(os.fstat(target_fd))
                != backup_identity
            ):
                # A name may have raced between validation and exchange. If
                # the new inode is still canonical, exchange it back without
                # clobbering the racing leaf, then fail closed.
                if (
                    exchanged_target is not None
                    and exchanged_old is not None
                    and _snapshot_entry_identity(exchanged_target)
                    == temporary_identity
                ):
                    raced_identity = _snapshot_entry_identity(exchanged_old)
                    try:
                        atomic_exchange_names(
                            parent_fd,
                            destination_name,
                            parent_fd,
                            temporary_name,
                        )
                    except OSError:
                        pass
                    else:
                        restored_target = _snapshot_named_stat(
                            parent_fd,
                            destination_name,
                        )
                        restored_temporary = _snapshot_named_stat(
                            parent_fd,
                            temporary_name,
                        )
                        if (
                            restored_target is not None
                            and restored_temporary is not None
                            and _snapshot_entry_identity(restored_target)
                            == raced_identity
                            and _snapshot_entry_identity(restored_temporary)
                            == temporary_identity
                        ):
                            published = False
                            exchange_pending = False
                            exchange_resolved = True
                            temporary_present = True
                raise ImageRequestSnapshotError(
                    "snapshot publication identity changed during atomic exchange"
                )
        elif _snapshot_named_stat(parent_fd, destination_name) is not None:
            raise ImageRequestSnapshotError(
                "snapshot publication target appeared during write"
            )

        if target_fd < 0:
            try:
                os.link(
                    temporary_name,
                    destination_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise ImageRequestSnapshotError(
                    "snapshot publication target appeared during publish"
                ) from exc
            published = True
        published_stat = _snapshot_named_stat(parent_fd, destination_name)
        held_temporary = os.fstat(temporary_fd)
        expected_link_count = 1 if exchange_pending else 2
        if (
            published_stat is None
            or not stat.S_ISREG(published_stat.st_mode)
            or _snapshot_entry_identity(published_stat) != temporary_identity
            or held_temporary.st_nlink != expected_link_count
            or published_stat.st_nlink != expected_link_count
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication target identity changed after publish"
            )
        _snapshot_verify_directory_chain(
            run_root=base,
            root_fd=root_fd,
            root_identity=root_identity,
            links=directory_links,
        )
        os.fsync(parent_fd)

        _snapshot_verify_directory_chain(
            run_root=base,
            root_fd=root_fd,
            root_identity=root_identity,
            links=directory_links,
        )
        if exchange_pending:
            final_target = _snapshot_named_stat(parent_fd, destination_name)
            retained_old = _snapshot_named_stat(parent_fd, temporary_name)
            final_opened = os.fstat(temporary_fd)
            if (
                final_target is None
                or retained_old is None
                or backup_identity is None
                or not stat.S_ISREG(final_target.st_mode)
                or not stat.S_ISREG(retained_old.st_mode)
                or final_target.st_nlink != 1
                or retained_old.st_nlink != 1
                or final_opened.st_nlink != 1
                or _snapshot_entry_identity(final_target)
                != temporary_identity
                or _snapshot_entry_identity(final_opened)
                != temporary_identity
                or _snapshot_entry_identity(retained_old)
                != backup_identity
                or _snapshot_entry_identity(os.fstat(target_fd))
                != backup_identity
            ):
                raise ImageRequestSnapshotError(
                    "snapshot publication final exchange identities changed"
                )

            # The exchange is now durable. Removing the retained old name is
            # hygiene only; cleanup failure must not report failure while the
            # committed new bytes remain canonical.
            committed = True
            exchange_pending = False
            exchange_resolved = True
            try:
                _snapshot_cleanup_public_name(
                    parent_fd=parent_fd,
                    name=temporary_name,
                    expected_identity=backup_identity,
                    cleanup_fd=cleanup_fd,
                    dispose=True,
                )
            except OSError:
                pass
            for descriptor in (parent_fd, cleanup_fd):
                try:
                    os.fsync(descriptor)
                except OSError:
                    pass
            return path

        if not _snapshot_cleanup_public_name(
            parent_fd=parent_fd,
            name=temporary_name,
            expected_identity=temporary_identity,
            cleanup_fd=cleanup_fd,
            dispose=True,
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication temporary changed before cleanup"
            )
        temporary_present = False
        final_target = _snapshot_named_stat(parent_fd, destination_name)
        final_opened = os.fstat(temporary_fd)
        if (
            final_target is None
            or not stat.S_ISREG(final_target.st_mode)
            or final_target.st_nlink != 1
            or final_opened.st_nlink != 1
            or _snapshot_entry_identity(final_target) != temporary_identity
            or _snapshot_entry_identity(final_opened) != temporary_identity
        ):
            raise ImageRequestSnapshotError(
                "snapshot publication final leaf is not private"
            )
        os.fsync(parent_fd)
        committed = True
        return path
    except BaseException as exc:
        if not committed and parent_fd >= 0 and cleanup_fd >= 0:
            destination_removed = not published
            if (
                target_fd >= 0
                and exchange_attempted
                and not exchange_pending
                and not exchange_resolved
                and temporary_identity is not None
                and backup_identity is not None
            ):
                try:
                    reconciled_target = _snapshot_named_stat(
                        parent_fd,
                        relative.parts[-1],
                    )
                    reconciled_temporary = _snapshot_named_stat(
                        parent_fd,
                        temporary_name,
                    )
                except OSError as reconciliation_exc:
                    temporary_present = False
                    rollback_failure = (
                        "atomic exchange state could not be reconciled "
                        f"({reconciliation_exc})"
                    )
                else:
                    if (
                        reconciled_target is not None
                        and reconciled_temporary is not None
                        and _snapshot_entry_identity(reconciled_target)
                        == temporary_identity
                        and _snapshot_entry_identity(reconciled_temporary)
                        == backup_identity
                    ):
                        published = True
                        exchange_pending = True
                        temporary_present = False
                        destination_removed = False
                    elif (
                        reconciled_target is not None
                        and reconciled_temporary is not None
                        and _snapshot_entry_identity(reconciled_target)
                        == backup_identity
                        and _snapshot_entry_identity(reconciled_temporary)
                        == temporary_identity
                    ):
                        published = False
                        exchange_resolved = True
                        temporary_present = True
                        destination_removed = True
                    else:
                        temporary_present = False
                        rollback_failure = (
                            "atomic exchange state could not be reconciled"
                        )
            if exchange_pending and temporary_identity is not None:
                try:
                    current_target = _snapshot_named_stat(
                        parent_fd,
                        relative.parts[-1],
                    )
                    current_old = _snapshot_named_stat(
                        parent_fd,
                        temporary_name,
                    )
                    if (
                        current_target is not None
                        and current_old is not None
                        and backup_identity is not None
                        and _snapshot_entry_identity(current_target)
                        == temporary_identity
                        and _snapshot_entry_identity(current_old)
                        == backup_identity
                    ):
                        rollback_exchange_error: BaseException | None = None
                        try:
                            atomic_exchange_names(
                                parent_fd,
                                relative.parts[-1],
                                parent_fd,
                                temporary_name,
                            )
                        except BaseException as exchange_exc:
                            rollback_exchange_error = exchange_exc
                        restored_target = _snapshot_named_stat(
                            parent_fd,
                            relative.parts[-1],
                        )
                        restored_temporary = _snapshot_named_stat(
                            parent_fd,
                            temporary_name,
                        )
                        if (
                            restored_target is not None
                            and restored_temporary is not None
                            and _snapshot_entry_identity(restored_target)
                            == backup_identity
                            and _snapshot_entry_identity(restored_temporary)
                            == temporary_identity
                        ):
                            published = False
                            exchange_pending = False
                            exchange_resolved = True
                            temporary_present = True
                            destination_removed = True
                        else:
                            detail = (
                                "previous snapshot could not be restored atomically"
                            )
                            if rollback_exchange_error is not None:
                                detail += f" ({rollback_exchange_error})"
                            rollback_failure = detail
                    else:
                        rollback_failure = (
                            "previous snapshot could not be restored atomically"
                        )
                except BaseException as rollback_exc:
                    # Namespace state is indeterminate. Do not unlink either
                    # name; preserve both candidates and make best-effort
                    # durability checks below.
                    temporary_present = False
                    detail = (
                        "rollback inspection or atomic exchange failed "
                        f"({rollback_exc})"
                    )
                    rollback_failure = (
                        f"{rollback_failure}; {detail}"
                        if rollback_failure
                        else detail
                    )
            elif published and temporary_identity is not None:
                try:
                    destination_removed = _snapshot_cleanup_public_name(
                        parent_fd=parent_fd,
                        name=relative.parts[-1],
                        expected_identity=temporary_identity,
                        cleanup_fd=cleanup_fd,
                        dispose=True,
                    )
                    if not destination_removed:
                        # A different leaf that raced into the canonical name
                        # is not owned by this invocation. Leave that winner
                        # exactly where it is; our publication link is gone.
                        racing_winner = _snapshot_named_stat(
                            parent_fd,
                            relative.parts[-1],
                        )
                        destination_removed = (
                            racing_winner is not None
                            and _snapshot_entry_identity(racing_winner)
                            != temporary_identity
                        )
                except BaseException as rollback_exc:
                    detail = (
                        "new-file rollback inspection failed "
                        f"({rollback_exc})"
                    )
                    rollback_failure = (
                        f"{rollback_failure}; {detail}"
                        if rollback_failure
                        else detail
                    )
            if published and not destination_removed and not rollback_failure:
                rollback_failure = (
                    "published snapshot could not be removed without clobbering"
                )
            if temporary_present and temporary_identity is not None:
                try:
                    if _snapshot_cleanup_public_name(
                        parent_fd=parent_fd,
                        name=temporary_name,
                        expected_identity=temporary_identity,
                        cleanup_fd=cleanup_fd,
                        dispose=True,
                    ):
                        temporary_present = False
                except BaseException as rollback_exc:
                    temporary_present = False
                    detail = (
                        "rollback temporary cleanup failed "
                        f"({rollback_exc})"
                    )
                    rollback_failure = (
                        f"{rollback_failure}; {detail}"
                        if rollback_failure
                        else detail
                    )
            rollback_fsync_errors: list[str] = []
            for label, descriptor in (
                ("parent", parent_fd),
                ("cleanup", cleanup_fd),
            ):
                try:
                    os.fsync(descriptor)
                except BaseException as rollback_exc:
                    rollback_fsync_errors.append(
                        f"{label}: {rollback_exc}"
                    )
            rollback_fsync_failure = "; ".join(rollback_fsync_errors)
        message = f"snapshot publication became unsafe: {exc}"
        if rollback_failure:
            message += f"; {rollback_failure}"
        if rollback_fsync_failure:
            message += (
                "; rollback durability could not be proved: "
                f"{rollback_fsync_failure}"
            )
        if not isinstance(exc, Exception) and not (
            rollback_failure or rollback_fsync_failure
        ):
            raise
        raise ImageRequestSnapshotError(message) from exc
    finally:
        if (
            temporary_present
            and temporary_identity is not None
            and parent_fd >= 0
            and cleanup_fd >= 0
        ):
            _snapshot_cleanup_public_name(
                parent_fd=parent_fd,
                name=temporary_name,
                expected_identity=temporary_identity,
                cleanup_fd=cleanup_fd,
                dispose=True,
            )
        if cleanup_fd >= 0:
            os.close(cleanup_fd)
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if target_fd >= 0:
            os.close(target_fd)
        for descriptor in reversed(opened_directories):
            os.close(descriptor)
        if root_fd >= 0:
            os.close(root_fd)


def write_request_snapshot_atomic(
    path: Path,
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path | None = None,
    expected_root_identity: PathIdentity | None = None,
) -> Path:
    """Durably replace a snapshot through its pinned run-root descriptor."""

    base, root_identity = _snapshot_root(
        run_dir or path.parent,
        expected_root_identity=expected_root_identity,
    )
    validate_request_snapshot(
        snapshot,
        run_dir=base,
        verify_references=True,
        expected_root_identity=root_identity,
    )
    serialized = (
        json.dumps(
            snapshot.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    return write_run_file_atomic_nofollow(
        path,
        serialized,
        run_dir=base,
        expected_root_identity=root_identity,
    )


def bind_request_snapshot_references(
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path,
    allow_existing_hash_changes: bool = False,
    expected_root_identity: PathIdentity | None = None,
) -> ImageRequestSnapshot:
    """Replace every deferred reference with a hash-bound reference.

    Review-time snapshots may defer assets that are generated earlier in the
    same run.  A provider-ready revision must instead bind the exact bytes now
    present on disk so later mutations invalidate that revision.
    """

    base, root_identity = _snapshot_root(
        run_dir,
        expected_root_identity=expected_root_identity,
    )
    validate_request_snapshot(
        snapshot,
        run_dir=base,
        verify_references=not allow_existing_hash_changes,
        expected_root_identity=root_identity,
    )
    bound_items: list[ImageRequestSnapshotItem] = []
    for item in snapshot.items:
        bound_references: list[ImageRequestReference] = []
        for reference in item.references:
            reference_path = _normalize_run_relative_path(
                base,
                reference.path,
                field="reference",
            )
            try:
                actual_sha256 = _snapshot_file_sha256(
                    base,
                    reference_path,
                    expected_root_identity=root_identity,
                )
            except (OSError, ValueError) as exc:
                raise ImageRequestSnapshotError(
                    f"reference does not exist for {item.item_id}: {reference.path}"
                ) from exc
            if (
                reference.sha256 is not None
                and reference.sha256 != actual_sha256
                and not allow_existing_hash_changes
            ):
                raise ImageRequestSnapshotError(
                    f"reference sha256 mismatch for {item.item_id}: {reference.path}"
                )
            bound_references.append(
                ImageRequestReference(
                    path=reference.path,
                    sha256=actual_sha256,
                    deferred=False,
                    producer_item_id=reference.producer_item_id,
                )
            )
        rebound_item = replace(item, references=tuple(bound_references), request_digest="")
        bound_items.append(
            replace(
                rebound_item,
                request_digest=sha256_canonical_json(_item_digest_payload(rebound_item)),
            )
        )
    rebound_snapshot = replace(
        snapshot,
        items=tuple(bound_items),
        request_revision="",
    )
    rebound_snapshot = replace(
        rebound_snapshot,
        request_revision=_expected_request_revision(rebound_snapshot),
    )
    validate_request_snapshot(
        rebound_snapshot,
        run_dir=base,
        verify_references=True,
        expected_root_identity=root_identity,
    )
    return rebound_snapshot


def load_request_snapshot(
    path: Path,
    *,
    run_dir: Path | None = None,
    verify_references: bool = True,
    expected_root_identity: tuple[int, int] | None = None,
) -> ImageRequestSnapshot:
    base = run_dir or path.parent
    lexical_base, root_identity = _snapshot_root(
        base,
        expected_root_identity=expected_root_identity,
    )
    try:
        lexical_path = Path(os.path.abspath(os.fspath(path)))
        try:
            relative = lexical_path.relative_to(lexical_base)
        except ValueError as exc:
            raise ImageRequestSnapshotError(
                "request snapshot path escapes its bound run root"
            ) from exc
        raw = read_regular_file_nofollow(
            lexical_base,
            relative,
            expected_root_identity=root_identity,
        )
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ImageRequestSnapshotError(f"could not load request snapshot: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ImageRequestSnapshotError("request snapshot root must be an object")
    snapshot = _snapshot_from_mapping(payload, run_dir=lexical_base)
    validate_request_snapshot(
        snapshot,
        run_dir=lexical_base,
        verify_references=verify_references,
        expected_root_identity=root_identity,
    )
    return snapshot


def validate_request_snapshot(
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path,
    verify_references: bool = True,
    expected_root_identity: tuple[int, int] | None = None,
) -> None:
    base, root_identity = _snapshot_root(
        run_dir,
        expected_root_identity=expected_root_identity,
    )
    if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise ImageRequestSnapshotError(
            f"unsupported snapshot schema_version: {snapshot.schema_version}"
        )
    if not snapshot.items:
        raise ImageRequestSnapshotError("snapshot must contain at least one item")
    if snapshot.source_artifact:
        normalized_source = _normalize_run_relative_path(
            base,
            snapshot.source_artifact,
            field="source_artifact",
        )
        if normalized_source != snapshot.source_artifact:
            raise ImageRequestSnapshotError("source_artifact is not normalized")
        _require_sha256(snapshot.source_artifact_sha256, field="source_artifact_sha256")
        if verify_references:
            try:
                source_sha256 = _snapshot_file_sha256(
                    base,
                    normalized_source,
                    expected_root_identity=root_identity,
                )
            except (OSError, ValueError) as exc:
                raise ImageRequestSnapshotError(
                    f"source_artifact does not exist: {normalized_source}"
                ) from exc
            if source_sha256 != snapshot.source_artifact_sha256:
                raise ImageRequestSnapshotError("source_artifact_sha256 mismatch")
    elif snapshot.source_artifact_sha256 is not None:
        raise ImageRequestSnapshotError("source_artifact_sha256 requires source_artifact")
    seen_ids: set[str] = set()
    producer_by_destination = {item.destination: item.item_id for item in snapshot.items}
    for item in snapshot.items:
        if item.item_id in seen_ids:
            raise ImageRequestSnapshotError(f"duplicate item id: {item.item_id}")
        seen_ids.add(item.item_id)
        if item.kind != snapshot.kind:
            raise ImageRequestSnapshotError(f"item kind mismatch for {item.item_id}")
        normalized_destination = _normalize_run_relative_path(
            base,
            item.destination,
            field="destination",
        )
        if normalized_destination != item.destination:
            raise ImageRequestSnapshotError(f"destination is not normalized for {item.item_id}")
        if sha256_text(item.prompt) != item.prompt_sha256:
            raise ImageRequestSnapshotError(f"prompt_sha256 mismatch for {item.item_id}")
        _require_sha256(item.source_digest, field=f"source_digest for {item.item_id}")
        if not item.prompt_policy_version:
            raise ImageRequestSnapshotError(
                f"prompt_policy_version is required for {item.item_id}"
            )
        if not item.compiler_version:
            raise ImageRequestSnapshotError(f"compiler_version is required for {item.item_id}")
        expected_request_digest = sha256_canonical_json(_item_digest_payload(item))
        if item.request_digest != expected_request_digest:
            raise ImageRequestSnapshotError(f"request_digest mismatch for {item.item_id}")
        for reference in item.references:
            normalized_reference = _normalize_run_relative_path(
                base,
                reference.path,
                field="reference",
            )
            if normalized_reference != reference.path:
                raise ImageRequestSnapshotError(
                    f"reference path is not normalized for {item.item_id}: {reference.path}"
                )
            if reference.deferred:
                if reference.sha256 is not None:
                    raise ImageRequestSnapshotError(
                        f"deferred reference must not freeze sha256 for {item.item_id}: {reference.path}"
                    )
                expected_producer = producer_by_destination.get(reference.path)
                external_producer = f"external:{reference.path}"
                if not reference.producer_item_id or reference.producer_item_id not in {
                    expected_producer,
                    external_producer,
                }:
                    raise ImageRequestSnapshotError(
                        f"deferred reference producer mismatch for {item.item_id}: {reference.path}"
                    )
            else:
                _require_sha256(
                    reference.sha256,
                    field=f"reference sha256 for {item.item_id}: {reference.path}",
                )
        if verify_references:
            current_reference_sha256s(
                base,
                item,
                allow_deferred=True,
                expected_root_identity=root_identity,
            )
    expected_revision = _expected_request_revision(snapshot)
    if snapshot.request_revision != expected_revision:
        raise ImageRequestSnapshotError("request_revision mismatch")


def current_reference_sha256s(
    run_dir: Path,
    item: ImageRequestSnapshotItem,
    *,
    allow_deferred: bool = False,
    expected_root_identity: tuple[int, int] | None = None,
) -> tuple[str | None, ...]:
    """Hash current reference bytes in provider attachment order.

    With ``allow_deferred=True``, an unresolved producer reference is returned
    as ``None``.  A send path should use the default and therefore fail until
    every producer dependency exists.
    """

    base, root_identity = _snapshot_root(
        run_dir,
        expected_root_identity=expected_root_identity,
    )
    hashes: list[str | None] = []
    for reference in item.references:
        reference_path = _normalize_run_relative_path(
            base,
            reference.path,
            field="reference",
        )
        try:
            actual_sha256 = _snapshot_file_sha256(
                base,
                reference_path,
                expected_root_identity=root_identity,
            )
        except (FileNotFoundError, OSError, ValueError):
            if reference.deferred and allow_deferred:
                hashes.append(None)
                continue
            raise ImageRequestSnapshotError(
                f"reference does not exist for {item.item_id}: {reference.path}"
            )
        if reference.sha256 is not None and reference.sha256 != actual_sha256:
            raise ImageRequestSnapshotError(
                f"reference sha256 mismatch for {item.item_id}: {reference.path}"
            )
        hashes.append(actual_sha256)
    return tuple(hashes)


def match_output_provenance(
    run_dir: Path,
    snapshot: ImageRequestSnapshot,
    item: ImageRequestSnapshotItem,
    provenance: Mapping[str, Any],
) -> OutputProvenanceMatch:
    """Return whether an existing output is reusable under strict provenance."""

    base = run_dir.resolve()
    reasons: list[str] = []
    try:
        canonical_item = snapshot.item(item.item_id)
    except KeyError:
        canonical_item = item
        reasons.append("item_not_in_snapshot")
    else:
        if canonical_item.request_digest != item.request_digest:
            reasons.append("item_request_digest_mismatch")

    record = _flatten_provenance(provenance)
    _compare_text(record, ("status",), None, reasons, status=True)
    if str(_first_value(record, "source") or "").strip() != "app_server":
        reasons.append("source_mismatch")
    if str(_first_value(record, "provenance_policy", "provenancePolicy", "policy") or "").strip() != "request_bound_v2":
        reasons.append("provenance_policy_mismatch")
    authoritative = _first_value(
        record,
        "authoritative",
        "provenance_authoritative",
        "provenanceAuthoritative",
    )
    if authoritative is not True:
        reasons.append("provenance_not_authoritative")
    for field, keys in (
        ("generation_job_id", ("generation_job_id", "generationJobId")),
        ("turn_id", ("turn_id", "turnId")),
        (
            "image_generation_item_id",
            ("image_generation_item_id", "imageGenerationItemId"),
        ),
        ("saved_path", ("saved_path", "savedPath")),
    ):
        if not _first_nonempty_text(*(_first_value(record, key) for key in keys)):
            reasons.append(f"{field}_missing")

    image_item_count = _first_value(
        record,
        "image_generation_item_count",
        "imageGenerationItemCount",
    )
    try:
        count = int(image_item_count)
    except (TypeError, ValueError):
        count = -1
    if count != 1:
        reasons.append("image_generation_item_count_mismatch")

    expected_fields = (
        ("request_revision", snapshot.request_revision, ("request_revision", "requestRevision")),
        ("request_digest", item.request_digest, ("request_digest", "requestDigest")),
        ("item_id", item.item_id, ("item_id", "itemId")),
        ("kind", item.kind, ("kind",)),
        ("prompt_sha256", item.prompt_sha256, ("prompt_sha256", "promptSha256")),
        (
            "compiler_version",
            item.compiler_version,
            ("compiler_version", "compilerVersion"),
        ),
        ("source_digest", item.source_digest, ("source_digest", "sourceDigest")),
    )
    for field, expected, keys in expected_fields:
        actual = _first_nonempty_text(*(_first_value(record, key) for key in keys))
        if actual != expected:
            reasons.append(f"{field}_mismatch")

    destination_value = _first_nonempty_text(
        _first_value(record, "destination"),
        _first_value(record, "output"),
    )
    try:
        normalized_destination = _normalize_record_destination(base, destination_value)
    except ImageRequestSnapshotError:
        reasons.append("destination_invalid")
    else:
        if normalized_destination != item.destination:
            reasons.append("destination_mismatch")

    try:
        current_reference_hashes = current_reference_sha256s(base, item)
    except ImageRequestSnapshotError:
        current_reference_hashes = ()
        reasons.append("current_reference_hashes_invalid")
    recorded_reference_hashes = _first_value(
        record,
        "reference_sha256s",
        "referenceSha256s",
    )
    if not isinstance(recorded_reference_hashes, (list, tuple)):
        recorded_reference_hashes = []
    if tuple(str(value) for value in recorded_reference_hashes) != tuple(current_reference_hashes):
        reasons.append("reference_sha256s_mismatch")

    output_path = base / item.destination
    recorded_output_sha256 = _first_nonempty_text(
        _first_value(record, "output_sha256"),
        _first_value(record, "outputSha256"),
    )
    if not output_path.is_file():
        reasons.append("output_missing")
    else:
        if recorded_output_sha256 != sha256_file(output_path):
            reasons.append("output_sha256_mismatch")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return OutputProvenanceMatch(matches=not unique_reasons, reasons=unique_reasons)


def _snapshot_from_mapping(
    payload: Mapping[str, Any],
    *,
    run_dir: Path,
) -> ImageRequestSnapshot:
    schema_version = _required_mapping_text(payload, "schema_version", field="schema_version")
    request_revision = _required_mapping_text(payload, "request_revision", field="request_revision")
    kind = _required_mapping_text(payload, "kind", field="kind")
    created_at = _required_mapping_text(payload, "created_at", field="created_at")
    source_artifact = _optional_mapping_text(payload, "source_artifact")
    source_artifact_sha256 = _optional_mapping_text(payload, "source_artifact_sha256")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ImageRequestSnapshotError("snapshot items must be a list")
    items: list[ImageRequestSnapshotItem] = []
    seen_ids: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise ImageRequestSnapshotError("snapshot items must be objects")
        item = _snapshot_item_from_mapping(raw_item, run_dir=run_dir)
        if item.item_id in seen_ids:
            raise ImageRequestSnapshotError(f"duplicate item id: {item.item_id}")
        seen_ids.add(item.item_id)
        items.append(item)
    if source_artifact_sha256 is not None:
        _require_sha256(source_artifact_sha256, field="source_artifact_sha256")
    return ImageRequestSnapshot(
        schema_version=schema_version,
        request_revision=request_revision,
        kind=kind,
        created_at=created_at,
        source_artifact=source_artifact,
        source_artifact_sha256=source_artifact_sha256,
        items=tuple(items),
    )


def _snapshot_item_from_mapping(
    payload: Mapping[str, Any],
    *,
    run_dir: Path,
) -> ImageRequestSnapshotItem:
    item_id = _required_mapping_text(payload, "item_id", field="item_id")
    kind = _required_mapping_text(payload, "kind", field="kind")
    destination_raw = _required_mapping_text(payload, "destination", field="destination")
    destination = _normalize_run_relative_path(run_dir, destination_raw, field="destination")
    prompt = _required_mapping_text(payload, "prompt", field="prompt")
    prompt_sha256 = _required_mapping_text(payload, "prompt_sha256", field="prompt_sha256")
    if sha256_text(prompt) != prompt_sha256:
        raise ImageRequestSnapshotError(f"prompt_sha256 mismatch for {item_id}")
    prompt_policy_version = _required_mapping_text(
        payload,
        "prompt_policy_version",
        field="prompt_policy_version",
    )
    compiler_version = _required_mapping_text(
        payload,
        "compiler_version",
        field="compiler_version",
    )
    source_digest = _required_mapping_text(payload, "source_digest", field="source_digest")
    request_digest = _required_mapping_text(payload, "request_digest", field="request_digest")
    raw_references = payload.get("references")
    if not isinstance(raw_references, list):
        raise ImageRequestSnapshotError(f"references must be a list for {item_id}")
    references: list[ImageRequestReference] = []
    for raw_reference in raw_references:
        if not isinstance(raw_reference, Mapping):
            raise ImageRequestSnapshotError(f"references must be objects for {item_id}")
        reference_path = _normalize_run_relative_path(
            run_dir,
            _required_mapping_text(raw_reference, "path", field="reference path"),
            field="reference",
        )
        reference_sha256 = _optional_mapping_text(raw_reference, "sha256")
        deferred_raw = raw_reference.get("deferred", False)
        if not isinstance(deferred_raw, bool):
            raise ImageRequestSnapshotError(
                f"reference deferred must be boolean for {item_id}: {reference_path}"
            )
        references.append(
            ImageRequestReference(
                path=reference_path,
                sha256=reference_sha256,
                deferred=deferred_raw,
                producer_item_id=_optional_mapping_text(raw_reference, "producer_item_id"),
            )
        )
    item = ImageRequestSnapshotItem(
        item_id=item_id,
        kind=kind,
        destination=destination,
        prompt=prompt,
        prompt_sha256=prompt_sha256,
        prompt_policy_version=prompt_policy_version,
        compiler_version=compiler_version,
        source_digest=source_digest,
        references=tuple(references),
        request_digest=request_digest,
    )
    expected_request_digest = sha256_canonical_json(_item_digest_payload(item))
    if request_digest != expected_request_digest:
        raise ImageRequestSnapshotError(f"request_digest mismatch for {item_id}")
    return item


def _item_digest_payload(item: ImageRequestSnapshotItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "kind": item.kind,
        "destination": item.destination,
        "prompt": item.prompt,
        "prompt_sha256": item.prompt_sha256,
        "prompt_policy_version": item.prompt_policy_version,
        "compiler_version": item.compiler_version,
        "source_digest": item.source_digest,
        "references": [reference.to_dict() for reference in item.references],
    }


def _snapshot_revision_payload(snapshot: ImageRequestSnapshot) -> dict[str, Any]:
    return {
        "schema_version": snapshot.schema_version,
        "kind": snapshot.kind,
        "source_artifact": snapshot.source_artifact,
        "source_artifact_sha256": snapshot.source_artifact_sha256,
        "items": [item.to_dict() for item in snapshot.items],
    }


def _expected_request_revision(snapshot: ImageRequestSnapshot) -> str:
    return sha256_canonical_json(_snapshot_revision_payload(snapshot))


def _normalize_run_relative_path(run_dir: Path, raw: Any, *, field: str) -> str:
    value = _required_text(raw, field=field)
    candidate = Path(value)
    if candidate.is_absolute():
        raise ImageRequestSnapshotError(f"{field} must be run-relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ImageRequestSnapshotError(f"{field} escapes run directory: {value}")
    normalized = candidate.as_posix()
    if normalized in {"", "."}:
        raise ImageRequestSnapshotError(f"{field} must identify a file")
    return normalized


def _normalize_record_destination(run_dir: Path, raw: str) -> str:
    value = _required_text(raw, field="destination")
    candidate = Path(value)
    base = run_dir.resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError as exc:
        raise ImageRequestSnapshotError(f"destination escapes run directory: {value}") from exc


def _required_text(value: Any, *, field: str) -> str:
    if not isinstance(value, (str, Path)):
        raise ImageRequestSnapshotError(f"{field} is required")
    text = str(value).strip()
    if not text:
        raise ImageRequestSnapshotError(f"{field} is required")
    return text


def _required_mapping_text(
    payload: Mapping[str, Any],
    *keys: str,
    field: str,
) -> str:
    value = _first_value(payload, *keys)
    return _required_text(value, field=field)


def _optional_mapping_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    value = _first_value(payload, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _first_nonempty_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, (str, Path)) and str(value).strip():
            return str(value).strip()
    return ""


def _require_sha256(value: str | None, *, field: str) -> None:
    if value is None or len(value) != _SHA256_LENGTH:
        raise ImageRequestSnapshotError(f"{field} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ImageRequestSnapshotError(f"{field} must be a SHA-256 hex digest") from exc


def _flatten_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    nested = provenance.get("provenance")
    record = dict(nested) if isinstance(nested, Mapping) else {}
    record.update(provenance)
    return record


def _compare_text(
    record: Mapping[str, Any],
    keys: tuple[str, ...],
    expected: str | None,
    reasons: list[str],
    *,
    status: bool = False,
) -> None:
    actual = _first_nonempty_text(*(_first_value(record, key) for key in keys))
    if status:
        if actual.lower() not in _SUCCESS_STATUSES:
            reasons.append("status_mismatch")
    elif actual != expected:
        reasons.append(f"{keys[0]}_mismatch")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
