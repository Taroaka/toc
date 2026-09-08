#!/usr/bin/env python3
"""
Scaffold a run folder for the immersive (cinematic) workflow (/toc-immersive-ride).

This script is intentionally a helper:
- It creates output/<topic>_<timestamp>/ with standard files and folders
- It writes a draft video_manifest.md based on an experience-specific template in workflow/
- It does NOT call external generation APIs
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator, NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import (
    StageGroundingError,
    build_stage_grounding_audit,
    build_stage_grounding_readset,
    canonical_stage_name,
    grounding_audit_relpath,
    grounding_readset_relpath,
    grounding_report_relpath,
    load_grounding_contract,
    resolve_stage_grounding,
)
from toc.harness import new_job_id, sync_run_status
from toc.run_root_binding import bind_run_root
from toc.state_store import append_state_delta, read_current_state
from scripts.world_walk_source import (
    PathIdentity,
    directory_identity_nofollow,
    ensure_directory_relative_nofollow,
    open_directory_nofollow,
    read_regular_file_nofollow,
    sha256_regular_file_nofollow,
    validate_world_walk_source_path,
)

EXPERIENCE_TEMPLATES: dict[str, Path] = {
    "cinematic_story": Path("workflow/immersive-ride-video-manifest-template.md"),
    "cloud_island_walk": Path("workflow/immersive-cloud-island-walk-video-manifest-template.md"),
    "world_walk": Path("workflow/immersive-world-walk-video-manifest-template.md"),
    # legacy alias (kept for backward compatibility; canonicalized to cinematic_story)
    "ride_action_boat": Path("workflow/immersive-ride-video-manifest-template.md"),
}
SCENE_CONTE_TEMPLATE = Path("workflow/scene-conte-template.md")
VISUAL_VALUE_TEMPLATE = Path("workflow/visual-value-template.yaml")
BIG_STAGE_HANDOFF_SLOTS: dict[str, str] = {
    "p100": "p130",
    "p200": "p230",
    "p300": "p330",
    "p400": "p450",
    "p500": "p570",
    "p600": "p680",
    "p700": "p750",
    "p800": "p850",
    "p900": "p930",
}

STAGE_TARGETS: dict[str, str] = {
    "100": "p130",
    "p100": "p130",
    "research": "p130",
    "200": "p230",
    "p200": "p230",
    "story": "p230",
    "300": "p330",
    "p300": "p330",
    "visual": "p330",
    "visual_value": "p330",
    "400": "p450",
    "p400": "p450",
    "450": "p450",
    "p450": "p450",
    "script": "p450",
    "500": "p570",
    "p500": "p570",
    "asset": "p570",
    "600": "p680",
    "p600": "p680",
    "image": "p680",
    "image_generation": "p680",
    "scene_implementation": "p680",
    "700": "p750",
    "p700": "p750",
    "narration": "p750",
    "800": "p850",
    "p800": "p850",
    "video_generation": "p850",
}
for _big_stage, _handoff_slot in BIG_STAGE_HANDOFF_SLOTS.items():
    STAGE_TARGETS.setdefault(_big_stage, _handoff_slot)
    STAGE_TARGETS.setdefault(_big_stage.removeprefix("p"), _handoff_slot)
for _slot_number in range(110, 931, 10):
    STAGE_TARGETS.setdefault(str(_slot_number), f"p{_slot_number}")
    STAGE_TARGETS.setdefault(f"p{_slot_number}", f"p{_slot_number}")
STAGE_TARGETS.setdefault("435", "p435")
STAGE_TARGETS.setdefault("p435", "p435")

SCAFFOLD_AUTHORING_UPDATES: dict[str, dict[str, str]] = {
    "research": {
        "stage.research.status": "pending",
        "artifact.research.status": "scaffold",
        "slot.p120.status": "pending",
        "slot.p120.note": "scaffold placeholder; author research.md before marking done",
    },
    "story": {
        "stage.story.status": "pending",
        "artifact.story.status": "scaffold",
        "slot.p220.status": "pending",
        "slot.p220.note": "scaffold placeholder; author story.md before marking done",
    },
    "visual_value": {
        "stage.visual_value.status": "pending",
        "artifact.visual_value.status": "scaffold",
        "slot.p310.status": "pending",
        "slot.p310.note": "scaffold template; replace placeholders before marking done",
    },
    "script": {
        "stage.script.status": "pending",
        "artifact.script.status": "scaffold",
        "slot.p410.status": "pending",
        "slot.p410.note": "scene set authoring is pending",
        "slot.p420.status": "pending",
        "slot.p420.note": "cut blueprint authoring is pending",
        "slot.p435.status": "pending",
        "slot.p435.note": "production readiness checks are pending",
        "slot.p450.status": "pending",
        "slot.p450.note": "skeleton manifest handoff remains pending before p500",
    },
    "narration": {
        "stage.narration.status": "pending",
        "runtime.scaffold.narration_status": "pending",
        "runtime.scaffold.audio_status": "pending",
        "slot.p710.status": "pending",
        "slot.p710.note": "scaffold grounding only; author narration runtime handoff before marking done",
        "slot.p730.status": "pending",
        "slot.p730.note": "scaffold audio directory only; generate narration audio before marking done",
    },
    "asset": {
        "stage.asset.status": "pending",
        "artifact.asset_inventory.status": "scaffold",
        "artifact.asset_plan.status": "scaffold",
        "slot.p510.status": "pending",
        "slot.p510.note": "scaffold grounding only; resolve asset stage context before marking done",
        "slot.p520.status": "pending",
        "slot.p520.note": "scaffold placeholder; inventory reusable characters, objects, locations, setpieces, and stills before asset planning",
        "slot.p530.status": "pending",
        "slot.p530.note": "scaffold placeholder; author asset_plan.md before marking done",
        "slot.p550.status": "pending",
        "slot.p550.note": "scaffold placeholder; materialize asset requests before generation",
        "slot.p560.status": "pending",
        "slot.p560.note": "scaffold only; reusable asset generation has not run",
    },
    "scene_implementation": {
        "stage.scene_implementation.status": "pending",
        "slot.p620.status": "pending",
        "slot.p620.note": "skeleton manifest only; production cut prompts are not authored",
    },
    "video_generation": {
        "stage.video_generation.status": "pending",
        "slot.p830.status": "pending",
        "slot.p830.note": "scaffold placeholder; video generation requests are not frozen",
        "slot.p840.status": "pending",
        "slot.p840.note": "scaffold only; video generation has not run",
    },
    "qa": {
        "stage.qa.status": "pending",
        "slot.p910.status": "pending",
        "slot.p910.note": "scaffold placeholder; render inputs are not frozen",
        "slot.p920.status": "pending",
        "slot.p920.note": "scaffold only; final render has not run",
    },
}

SOURCE_RECEIPT_SCHEMA_VERSION = "toc.world_walk_source_receipt.v1"
SOURCE_RECEIPT_REL_PATH = Path(
    "logs/provenance/world_walk_source_receipt.json"
)
_SOURCE_RECEIPT_BEGIN = "  # toc-source-receipt: begin"
_SOURCE_RECEIPT_END = "  # toc-source-receipt: end"


class PinnedRunRoot(NamedTuple):
    path: Path
    lexical: str
    identity: PathIdentity
    descriptor: int


class WorldWalkSource(NamedTuple):
    path: Path
    relative: Path
    identity: PathIdentity


_ACTIVE_RUN_ROOT: ContextVar[PinnedRunRoot | None] = ContextVar(
    "toc_immersive_ride_active_run_root",
    default=None,
)
_ACTIVE_SOURCE: ContextVar[WorldWalkSource | None] = ContextVar(
    "toc_immersive_ride_active_world_walk_source",
    default=None,
)


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _safe_relative_parts(relative: str | Path) -> tuple[str, ...]:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} or "/" in part for part in path.parts)
    ):
        raise ValueError(f"unsafe run-relative path: {path}")
    return path.parts


def _ensure_absolute_directory_nofollow(path: Path) -> PathIdentity:
    absolute = _lexical_absolute(path)
    if not absolute.is_absolute():
        raise ValueError(f"directory must be absolute: {path}")
    descriptor = os.open(absolute.anchor, _directory_open_flags())
    try:
        for part in absolute.parts[1:]:
            try:
                child = os.open(
                    part,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(
                    part,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise ValueError(
                    f"directory path contains an unsafe component: {absolute}"
                ) from exc
            os.close(descriptor)
            descriptor = child
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValueError(f"directory must be a real directory: {absolute}")
        return opened.st_dev, opened.st_ino
    finally:
        os.close(descriptor)


def _validated_run_directory(
    *,
    raw_base: str,
    raw_run_dir: str | None,
    topic_slug: str,
    timestamp: str,
) -> tuple[Path, PathIdentity]:
    requested_base = _lexical_absolute(Path(raw_base))
    base = _lexical_absolute(Path(raw_base).resolve(strict=False))
    base_identity = _ensure_absolute_directory_nofollow(base)
    if raw_run_dir is None:
        candidate = base / f"{topic_slug}_{timestamp}"
    else:
        raw_path = Path(raw_run_dir)
        if ".." in raw_path.parts:
            raise ValueError("--run-dir must not contain traversal components")
        requested_candidate = _lexical_absolute(raw_path)
        try:
            relative = requested_candidate.relative_to(requested_base)
        except ValueError as exc:
            try:
                relative = requested_candidate.relative_to(base)
            except ValueError:
                raise ValueError(
                    "--run-dir must be confined under --base "
                    f"({requested_base})"
                ) from exc
        candidate = base / relative
    candidate = _lexical_absolute(candidate)
    relative = candidate.relative_to(base)
    if not relative.parts:
        raise ValueError("--run-dir must be a child of --base")
    identity = ensure_directory_relative_nofollow(
        base,
        relative,
        expected_root_identity=base_identity,
    )
    return candidate, identity


def _pin_run_root(
    run_dir: Path,
    *,
    expected_identity: PathIdentity | None = None,
) -> PinnedRunRoot:
    lexical_path = _lexical_absolute(run_dir)
    descriptor = open_directory_nofollow(
        lexical_path,
        expected_identity=expected_identity,
    )
    opened = os.fstat(descriptor)
    return PinnedRunRoot(
        path=lexical_path,
        lexical=os.fspath(lexical_path),
        identity=(opened.st_dev, opened.st_ino),
        descriptor=descriptor,
    )


def _verify_run_root(root: PinnedRunRoot) -> None:
    descriptor = open_directory_nofollow(
        root.path,
        expected_identity=root.identity,
    )
    os.close(descriptor)


@contextmanager
def _using_run_root(
    run_dir: Path,
    *,
    expected_identity: PathIdentity | None = None,
) -> Iterator[PinnedRunRoot]:
    lexical = os.fspath(_lexical_absolute(run_dir))
    active = _ACTIVE_RUN_ROOT.get()
    if active is not None:
        if active.lexical != lexical:
            raise ValueError(
                "cannot operate on a second run root while another root is pinned"
            )
        _verify_run_root(active)
        yield active
        _verify_run_root(active)
        return
    root = _pin_run_root(run_dir, expected_identity=expected_identity)
    token = _ACTIVE_RUN_ROOT.set(root)
    try:
        yield root
        _verify_run_root(root)
    finally:
        _ACTIVE_RUN_ROOT.reset(token)
        os.close(root.descriptor)


def _active_root_for_path(path: Path) -> tuple[PinnedRunRoot, Path]:
    active = _ACTIVE_RUN_ROOT.get()
    if active is None:
        raise ValueError("run root is not pinned")
    absolute = _lexical_absolute(path)
    try:
        relative = absolute.relative_to(active.path)
    except ValueError as exc:
        raise ValueError(f"artifact path escapes the pinned run root: {path}") from exc
    _safe_relative_parts(relative)
    return active, relative


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
            except OSError as exc:
                raise ValueError(
                    f"run path contains a symlink or non-directory: {part}"
                ) from exc
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _open_current_parent_verified(
    root: PinnedRunRoot,
    parent_parts: tuple[str, ...],
    *,
    expected_parent_identity: PathIdentity,
) -> int:
    current_root = open_directory_nofollow(
        root.path,
        expected_identity=root.identity,
    )
    parent: int | None = None
    try:
        parent = _open_parent_directory(
            current_root,
            parent_parts,
            create=False,
        )
        opened = os.fstat(parent)
        if (opened.st_dev, opened.st_ino) != expected_parent_identity:
            raise ValueError("run artifact parent identity changed")
        result = parent
        parent = None
        return result
    finally:
        if parent is not None:
            os.close(parent)
        os.close(current_root)


def _secure_stat(
    run_dir: Path,
    relative: str | Path,
) -> os.stat_result | None:
    parts = _safe_relative_parts(relative)
    with _using_run_root(run_dir) as root:
        current_root = open_directory_nofollow(
            root.path,
            expected_identity=root.identity,
        )
        parent: int | None = None
        try:
            try:
                parent = _open_parent_directory(
                    current_root,
                    parts[:-1],
                    create=False,
                )
                result = os.stat(
                    parts[-1],
                    dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return None
            if stat.S_ISLNK(result.st_mode):
                raise ValueError(
                    f"run artifact must not be a symlink: {Path(relative)}"
                )
            return result
        finally:
            if parent is not None:
                os.close(parent)
            os.close(current_root)


def _secure_exists(run_dir: Path, relative: str | Path) -> bool:
    return _secure_stat(run_dir, relative) is not None


def _secure_is_regular(run_dir: Path, relative: str | Path) -> bool:
    value = _secure_stat(run_dir, relative)
    return bool(value and stat.S_ISREG(value.st_mode))


def _secure_read_bytes(
    run_dir: Path,
    relative: str | Path,
    *,
    missing_ok: bool = False,
) -> bytes:
    with _using_run_root(run_dir) as root:
        try:
            return read_regular_file_nofollow(
                root.path,
                relative,
                expected_root_identity=root.identity,
            )
        except FileNotFoundError:
            if missing_ok:
                return b""
            raise


def _secure_read_text(
    run_dir: Path,
    relative: str | Path,
    *,
    missing_ok: bool = False,
) -> str:
    return _secure_read_bytes(
        run_dir,
        relative,
        missing_ok=missing_ok,
    ).decode("utf-8")


def _secure_write_bytes(
    run_dir: Path,
    relative: str | Path,
    data: bytes,
    *,
    overwrite: bool,
) -> bool:
    parts = _safe_relative_parts(relative)
    with _using_run_root(run_dir) as root:
        current_root = open_directory_nofollow(
            root.path,
            expected_identity=root.identity,
        )
        parent: int | None = None
        temporary_name: str | None = None
        temporary: int | None = None
        verification_parent: int | None = None
        verification_file: int | None = None
        try:
            parent = _open_parent_directory(
                current_root,
                parts[:-1],
                create=True,
            )
            parent_value = os.fstat(parent)
            parent_identity = (
                parent_value.st_dev,
                parent_value.st_ino,
            )
            initial: os.stat_result | None
            try:
                initial = os.stat(
                    parts[-1],
                    dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                initial = None
            if initial is not None:
                if not stat.S_ISREG(initial.st_mode):
                    raise ValueError(
                        f"run artifact must be a regular file: {Path(relative)}"
                    )
                if not overwrite:
                    return False

            temporary_name = (
                f".{parts[-1]}.toc-tmp-{os.getpid()}-{secrets.token_hex(8)}"
            )
            temporary = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent,
            )
            remaining = memoryview(data)
            while remaining:
                written = os.write(temporary, remaining)
                if written <= 0:
                    raise OSError("run artifact write made no progress")
                remaining = remaining[written:]
            os.fsync(temporary)
            opened_temporary = os.fstat(temporary)
            if not stat.S_ISREG(opened_temporary.st_mode):
                raise ValueError("temporary run artifact is not a regular file")

            current_temporary = os.stat(
                temporary_name,
                dir_fd=parent,
                follow_symlinks=False,
            )
            if (
                current_temporary.st_dev,
                current_temporary.st_ino,
                stat.S_IFMT(current_temporary.st_mode),
            ) != (
                opened_temporary.st_dev,
                opened_temporary.st_ino,
                stat.S_IFMT(opened_temporary.st_mode),
            ):
                raise ValueError(
                    "temporary run artifact identity changed"
                )
            verification_parent = _open_current_parent_verified(
                root,
                parts[:-1],
                expected_parent_identity=parent_identity,
            )
            try:
                current = os.stat(
                    parts[-1],
                    dir_fd=verification_parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                current = None
            if initial is None:
                if current is not None:
                    raise ValueError(
                        f"run artifact appeared during write: {Path(relative)}"
                    )
            elif (
                current is None
                or (current.st_dev, current.st_ino, stat.S_IFMT(current.st_mode))
                != (
                    initial.st_dev,
                    initial.st_ino,
                    stat.S_IFMT(initial.st_mode),
                )
            ):
                raise ValueError(
                    f"run artifact identity changed during write: {Path(relative)}"
                )

            os.replace(
                temporary_name,
                parts[-1],
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
            temporary_name = None
            os.fsync(parent)
            os.close(verification_parent)
            verification_parent = None
            verification_parent = _open_current_parent_verified(
                root,
                parts[:-1],
                expected_parent_identity=parent_identity,
            )
            verification_file = os.open(
                parts[-1],
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=verification_parent,
            )
            final_value = os.fstat(verification_file)
            if (
                not stat.S_ISREG(final_value.st_mode)
                or (final_value.st_dev, final_value.st_ino)
                != (
                    opened_temporary.st_dev,
                    opened_temporary.st_ino,
                )
            ):
                raise ValueError(
                    "written run artifact identity mismatch: "
                    f"{Path(relative)}"
                )
            digest = hashlib.sha256()
            while True:
                chunk = os.read(verification_file, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            if digest.digest() != hashlib.sha256(data).digest():
                raise ValueError(
                    f"written run artifact digest mismatch: {Path(relative)}"
                )
        finally:
            if verification_file is not None:
                os.close(verification_file)
            if verification_parent is not None:
                os.close(verification_parent)
            if temporary is not None:
                os.close(temporary)
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent)
                except FileNotFoundError:
                    pass
            if parent is not None:
                os.close(parent)
            os.close(current_root)
        _verify_run_root(root)
        return True


def _secure_write_text(
    run_dir: Path,
    relative: str | Path,
    text: str,
    *,
    overwrite: bool,
) -> bool:
    return _secure_write_bytes(
        run_dir,
        relative,
        text.encode("utf-8"),
        overwrite=overwrite,
    )


def _secure_ensure_directory(run_dir: Path, relative: str | Path) -> None:
    _safe_relative_parts(relative)
    with _using_run_root(run_dir) as root:
        ensure_directory_relative_nofollow(
            root.path,
            relative,
            expected_root_identity=root.identity,
        )


def _scan_directory_descriptor(
    descriptor: int,
    *,
    prefix: Path,
) -> tuple[str, ...]:
    paths: list[str] = []
    for name in sorted(os.listdir(descriptor)):
        value = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        relative = prefix / name
        if stat.S_ISLNK(value.st_mode):
            raise ValueError(f"run tree contains a symlink: {relative}")
        if stat.S_ISDIR(value.st_mode):
            child = os.open(name, _directory_open_flags(), dir_fd=descriptor)
            try:
                paths.append(relative.as_posix() + "/")
                paths.extend(
                    _scan_directory_descriptor(child, prefix=relative)
                )
            finally:
                os.close(child)
        elif stat.S_ISREG(value.st_mode):
            paths.append(relative.as_posix())
        else:
            raise ValueError(
                f"run tree contains a special file: {relative}"
            )
    return tuple(paths)


def _assert_safe_run_tree(run_dir: Path) -> tuple[str, ...]:
    with _using_run_root(run_dir) as root:
        descriptor = open_directory_nofollow(
            root.path,
            expected_identity=root.identity,
        )
        try:
            return _scan_directory_descriptor(descriptor, prefix=Path())
        finally:
            os.close(descriptor)


def _preflight_remove_path(
    root_descriptor: int,
    relative: str | Path,
) -> None:
    parts = _safe_relative_parts(relative)
    try:
        parent = _open_parent_directory(
            root_descriptor,
            parts[:-1],
            create=False,
        )
    except FileNotFoundError:
        return
    try:
        try:
            value = os.stat(
                parts[-1],
                dir_fd=parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        if stat.S_ISLNK(value.st_mode):
            raise ValueError(f"refusing to delete symlink: {Path(relative)}")
        if stat.S_ISREG(value.st_mode):
            return
        if not stat.S_ISDIR(value.st_mode):
            raise ValueError(
                f"refusing to delete special file: {Path(relative)}"
            )
        child = os.open(parts[-1], _directory_open_flags(), dir_fd=parent)
        try:
            _scan_directory_descriptor(child, prefix=Path(relative))
        finally:
            os.close(child)
    finally:
        os.close(parent)


def _remove_entry_at(parent: int, name: str, *, relative: Path) -> None:
    value = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if stat.S_ISLNK(value.st_mode):
        raise ValueError(f"refusing to delete symlink: {relative}")
    if stat.S_ISREG(value.st_mode):
        os.unlink(name, dir_fd=parent)
        return
    if not stat.S_ISDIR(value.st_mode):
        raise ValueError(f"refusing to delete special file: {relative}")
    child = os.open(name, _directory_open_flags(), dir_fd=parent)
    try:
        for child_name in sorted(os.listdir(child)):
            _remove_entry_at(
                child,
                child_name,
                relative=relative / child_name,
            )
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent)


def _secure_remove_path(run_dir: Path, relative: str | Path) -> bool:
    parts = _safe_relative_parts(relative)
    with _using_run_root(run_dir) as root:
        current_root = open_directory_nofollow(
            root.path,
            expected_identity=root.identity,
        )
        parent: int | None = None
        try:
            try:
                parent = _open_parent_directory(
                    current_root,
                    parts[:-1],
                    create=False,
                )
                os.stat(
                    parts[-1],
                    dir_fd=parent,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return False
            _verify_run_root(root)
            _remove_entry_at(
                parent,
                parts[-1],
                relative=Path(relative),
            )
            os.fsync(parent)
        finally:
            if parent is not None:
                os.close(parent)
            os.close(current_root)
        _verify_run_root(root)
        return True


def _parse_state(run_dir: Path) -> dict[str, str]:
    with _using_run_root(run_dir) as root:
        with bind_run_root(
            run_dir,
            expected_identity=root.identity,
            descriptor=root.descriptor,
        ):
            return dict(read_current_state(run_dir / "state.txt").state)


def _artifact_absolute(run_dir: Path, relative: str | Path) -> str:
    return os.fspath(_lexical_absolute(run_dir / Path(relative)))


def _artifact_inventory_safe(
    run_dir: Path,
    state: dict[str, str],
) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    root = _lexical_absolute(run_dir)
    for key, raw_value in state.items():
        if not key.startswith("artifact."):
            continue
        name = key.removeprefix("artifact.")
        value = str(raw_value)
        candidate = Path(value)
        candidate = (
            _lexical_absolute(candidate)
            if candidate.is_absolute()
            else _lexical_absolute(root / candidate)
        )
        try:
            relative = candidate.relative_to(root)
            exists = _secure_exists(run_dir, relative)
        except (OSError, ValueError):
            exists = False
        inventory[name] = {"path": os.fspath(candidate), "exists": exists}
    inventory.setdefault(
        "run_index",
        {
            "path": _artifact_absolute(run_dir, "p000_index.md"),
            "exists": _secure_exists(run_dir, "p000_index.md"),
            "derived": True,
        },
    )
    return inventory


def _sync_run_status_safe(
    run_dir: Path,
    state: dict[str, str],
) -> None:
    sync_run_status(run_dir, state)


def normalize_timestamp(value: str) -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"\d{8}_\d{4}", candidate):
        raise argparse.ArgumentTypeError(
            "timestamp must use the exact YYYYMMDD_HHMM format"
        )
    try:
        dt.datetime.strptime(candidate, "%Y%m%d_%H%M")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "timestamp must be a valid YYYYMMDD_HHMM value"
        ) from exc
    return candidate


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def _source_asset_relpaths(source: WorldWalkSource) -> tuple[Path, ...]:
    descriptor = open_directory_nofollow(
        source.path,
        expected_identity=source.identity,
    )
    assets: int | None = None
    try:
        try:
            assets = os.open(
                "assets",
                _directory_open_flags(),
                dir_fd=descriptor,
            )
        except OSError as exc:
            raise ValueError(
                "world-walk source assets/ must be a real directory"
            ) from exc
        files: list[Path] = []

        def visit(current: int, prefix: Path) -> None:
            for name in sorted(os.listdir(current)):
                value = os.stat(
                    name,
                    dir_fd=current,
                    follow_symlinks=False,
                )
                relative = prefix / name
                if stat.S_ISLNK(value.st_mode):
                    raise ValueError(
                        f"world-walk source contains a symlink: {relative}"
                    )
                if stat.S_ISDIR(value.st_mode):
                    child = os.open(
                        name,
                        _directory_open_flags(),
                        dir_fd=current,
                    )
                    try:
                        visit(child, relative)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(value.st_mode):
                    files.append(relative)
                else:
                    raise ValueError(
                        "world-walk source contains a special file: "
                        f"{relative}"
                    )

        visit(assets, Path("assets"))
        return tuple(files)
    finally:
        if assets is not None:
            os.close(assets)
        os.close(descriptor)


def build_world_walk_source_receipt(
    source: WorldWalkSource,
) -> dict[str, Any]:
    if directory_identity_nofollow(source.path) != source.identity:
        raise ValueError("world-walk source root identity changed")
    story_sha256 = sha256_regular_file_nofollow(
        source.path,
        "story.md",
        expected_root_identity=source.identity,
    )
    first_inventory = _source_asset_relpaths(source)
    references = [
        {
            "path": relative.as_posix(),
            "sha256": sha256_regular_file_nofollow(
                source.path,
                relative,
                expected_root_identity=source.identity,
            ),
        }
        for relative in first_inventory
    ]
    if _source_asset_relpaths(source) != first_inventory:
        raise ValueError(
            "world-walk source reference inventory changed while hashing"
        )
    reference_payload = json.dumps(
        references,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    references_sha256 = hashlib.sha256(reference_payload).hexdigest()
    if directory_identity_nofollow(source.path) != source.identity:
        raise ValueError("world-walk source root identity changed")
    root_identity = f"{source.identity[0]}:{source.identity[1]}"
    binding = {
        "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
        "source_run": source.relative.as_posix(),
        "root_identity": root_identity,
        "story_sha256": story_sha256,
        "references_sha256": references_sha256,
    }
    bundle_sha256 = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        **binding,
        "bundle_sha256": bundle_sha256,
        "references": references,
    }


def _source_receipt_state(receipt: dict[str, Any]) -> dict[str, str]:
    return {
        "immersive.source_receipt.schema_version": str(
            receipt["schema_version"]
        ),
        "immersive.source_receipt.root_identity": str(
            receipt["root_identity"]
        ),
        "immersive.source_receipt.story_sha256": str(
            receipt["story_sha256"]
        ),
        "immersive.source_receipt.references_sha256": str(
            receipt["references_sha256"]
        ),
        "immersive.source_receipt.bundle_sha256": str(
            receipt["bundle_sha256"]
        ),
        "immersive.source_receipt.artifact": (
            SOURCE_RECEIPT_REL_PATH.as_posix()
        ),
    }


def _bind_source_receipt_to_manifest(
    manifest: str,
    receipt: dict[str, Any],
) -> str:
    block = "\n".join(
        (
            _SOURCE_RECEIPT_BEGIN,
            "  source_receipt:",
            f'    schema_version: "{receipt["schema_version"]}"',
            f'    root_identity: "{receipt["root_identity"]}"',
            f'    story_sha256: "{receipt["story_sha256"]}"',
            (
                '    references_sha256: '
                f'"{receipt["references_sha256"]}"'
            ),
            f'    bundle_sha256: "{receipt["bundle_sha256"]}"',
            _SOURCE_RECEIPT_END,
        )
    )
    marker_pattern = re.compile(
        rf"(?ms)^{re.escape(_SOURCE_RECEIPT_BEGIN)}\n.*?"
        rf"^{re.escape(_SOURCE_RECEIPT_END)}\n?"
    )
    if bool(_SOURCE_RECEIPT_BEGIN in manifest) != bool(
        _SOURCE_RECEIPT_END in manifest
    ):
        raise ValueError("video manifest has a malformed source receipt block")
    stripped = marker_pattern.sub("", manifest)
    source_assets = re.search(
        r'(?m)^\s{2}source_assets:\s*.*$',
        stripped,
    )
    if source_assets is None:
        raise ValueError(
            "world-walk video manifest is missing video_metadata.source_assets"
        )
    insertion = source_assets.end()
    return stripped[:insertion] + "\n" + block + stripped[insertion:]


def _persist_world_walk_source_receipt(
    run_dir: Path,
    source: WorldWalkSource,
    *,
    bind_manifest: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    receipt = build_world_walk_source_receipt(source)
    _secure_write_text(
        run_dir,
        SOURCE_RECEIPT_REL_PATH,
        json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        overwrite=True,
    )
    if bind_manifest and _secure_is_regular(run_dir, "video_manifest.md"):
        manifest = _secure_read_text(run_dir, "video_manifest.md")
        bound = _bind_source_receipt_to_manifest(manifest, receipt)
        if bound != manifest:
            _secure_write_text(
                run_dir,
                "video_manifest.md",
                bound,
                overwrite=True,
            )
    return receipt, _source_receipt_state(receipt)


def _refresh_active_source_receipt(
    run_dir: Path,
    *,
    bind_manifest: bool = True,
) -> dict[str, str]:
    source = _ACTIVE_SOURCE.get()
    if source is None:
        return {}
    _receipt, state = _persist_world_walk_source_receipt(
        run_dir,
        source,
        bind_manifest=bind_manifest,
    )
    return state


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    run_dir = state_path.parent
    with _using_run_root(run_dir) as root:
        try:
            relative = _lexical_absolute(state_path).relative_to(
                _lexical_absolute(run_dir)
            )
        except ValueError as exc:
            raise ValueError("state path escapes run root") from exc
        if relative != Path("state.txt"):
            raise ValueError("state append must target state.txt")
        timestamp = now_iso()
        with bind_run_root(
            run_dir,
            expected_identity=root.identity,
            descriptor=root.descriptor,
        ):
            replay = append_state_delta(
                state_path,
                kv,
                event_type="state.immersive_ride.updated",
                occurred_at=timestamp,
                committed_at=timestamp,
                defaults={
                    "job_id": new_job_id(),
                    "status": "INIT",
                    "artifact.run_index": _artifact_absolute(
                        run_dir, "p000_index.md"
                    ),
                },
            )
        merged = dict(replay.state)
        _sync_run_status_safe(run_dir, merged)


def write_text(path: Path, content: str, force: bool) -> bool:
    root, relative = _active_root_for_path(path)
    return _secure_write_text(
        root.path,
        relative,
        content,
        overwrite=force,
    )


def maybe_run_stage_grounding(run_dir: Path, stage: str, *, flow: str, fatal: bool = True) -> None:
    attempts = 2
    contract = load_grounding_contract()
    canonical_stage = canonical_stage_name(stage, contract)
    last_report: dict[str, Any] | None = None
    try:
        with _using_run_root(run_dir):
            for _ in range(attempts):
                _assert_safe_run_tree(run_dir)
                report = resolve_stage_grounding(
                    stage=canonical_stage,
                    run_dir=run_dir,
                    flow=flow,
                )
                _assert_safe_run_tree(run_dir)
                readset = build_stage_grounding_readset(
                    report,
                    stage=canonical_stage,
                )
                audit = build_stage_grounding_audit(
                    run_dir=run_dir,
                    stage=canonical_stage,
                    report=report,
                    readset=readset,
                    contract=contract,
                )
                artifacts = (
                    (
                        grounding_report_relpath(canonical_stage),
                        report,
                    ),
                    (
                        grounding_readset_relpath(canonical_stage),
                        readset,
                    ),
                    (
                        grounding_audit_relpath(canonical_stage),
                        audit,
                    ),
                )
                for relative, payload in artifacts:
                    _secure_write_text(
                        run_dir,
                        relative,
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n",
                        overwrite=True,
                    )
                append_state_block(
                    run_dir / "state.txt",
                    {
                        (
                            f"stage.{canonical_stage}.grounding.status"
                        ): str(report["status"]),
                        (
                            f"stage.{canonical_stage}.grounding.report"
                        ): grounding_report_relpath(
                            canonical_stage
                        ).as_posix(),
                        (
                            f"stage.{canonical_stage}.readset.report"
                        ): grounding_readset_relpath(
                            canonical_stage
                        ).as_posix(),
                        (
                            f"stage.{canonical_stage}.audit.status"
                        ): str(audit["status"]),
                        (
                            f"stage.{canonical_stage}.audit.report"
                        ): grounding_audit_relpath(
                            canonical_stage
                        ).as_posix(),
                    },
                )
                last_report = report
                if (
                    report["status"] == "ready"
                    and audit["status"] == "passed"
                ):
                    return
            assert last_report is not None
            append_state_block(
                run_dir / "state.txt",
                {
                    f"stage.{canonical_stage}.status": "failed",
                    "last_error": (
                        "grounding_failed:"
                        f"{canonical_stage}:{last_report['status']}"
                    ),
                },
            )
            raise StageGroundingError(
                stage=canonical_stage,
                status=str(last_report["status"]),
                run_dir=run_dir,
                report=last_report,
            )
    except StageGroundingError:
        if fatal:
            raise


def require_fresh_p400_readiness(run_dir: Path) -> None:
    """Validate the current p400 manifest's structural execution contract.

    The name is kept for callers from older runs.  Readiness is now based on
    the deterministic manifest evaluator only; no reviewer report or approval
    state is consulted.
    """
    _refresh_active_source_receipt(run_dir)
    _assert_safe_run_tree(run_dir)
    # Keep the evaluator lazy so early authoring scaffolds do not load the
    # optional downstream evaluator package.
    from toc.stage_evaluator import check_manifest_single

    stage_result, updates = check_manifest_single(run_dir, "standard", "immersive")
    _assert_safe_run_tree(run_dir)
    if updates:
        append_state_block(run_dir / "state.txt", updates)
    failures = [
        str(check.get("id") or "structural_check")
        for check in (stage_result.get("checks", []) if isinstance(stage_result, dict) else [])
        if isinstance(check, dict) and check.get("passed") is False
    ]
    if failures:
        raise SystemExit(
            "p400 structural validation failed: " + ", ".join(failures)
        )


def ensure_skeleton_manifest(manifest_text: str) -> str:
    if "manifest_phase:" in manifest_text:
        return re.sub(r"(?m)^(\s*manifest_phase:\s*).*$", r"\1skeleton", manifest_text, count=1)
    return manifest_text.replace("```yaml\n", "```yaml\nmanifest_phase: skeleton\n", 1)


def ensure_skeleton_manifest_file(manifest_path: Path) -> None:
    run_dir = manifest_path.parent
    with _using_run_root(run_dir):
        if not _secure_exists(run_dir, manifest_path.name):
            return
        text = _secure_read_text(run_dir, manifest_path.name)
        updated = ensure_skeleton_manifest(text)
        if updated != text:
            _secure_write_text(
                run_dir,
                manifest_path.name,
                updated,
                overwrite=True,
            )


def ensure_production_manifest_file(manifest_path: Path) -> None:
    run_dir = manifest_path.parent
    with _using_run_root(run_dir):
        if not _secure_exists(run_dir, manifest_path.name):
            return
        text = _secure_read_text(run_dir, manifest_path.name)
        if "manifest_phase:" in text:
            updated = re.sub(
                r"(?m)^(\s*manifest_phase:\s*).*$",
                r"\1production",
                text,
                count=1,
            )
        else:
            updated = text.replace(
                "```yaml\n",
                "```yaml\nmanifest_phase: production\n",
                1,
            )
        if updated != text:
            _secure_write_text(
                run_dir,
                manifest_path.name,
                updated,
                overwrite=True,
            )


def normalize_stage_target(value: str) -> str:
    key = value.strip().lower().removeprefix("--stage=").replace("-", "_")
    if key not in STAGE_TARGETS:
        allowed = ", ".join(sorted(STAGE_TARGETS))
        raise argparse.ArgumentTypeError(f"unknown stage target: {value!r}; expected one of {allowed}")
    return STAGE_TARGETS[key]


def slot_number(slot: str) -> int:
    return int(slot.removeprefix("p"))


def slot_bucket(slot: str) -> str:
    number = slot_number(slot)
    return f"p{number // 100}00"


def target_reaches(stop_slot: str, slot: str) -> bool:
    return slot_number(stop_slot) >= slot_number(slot)


def previous_stop_slot(state: dict[str, str]) -> str | None:
    raw = str(state.get("runtime.stop_slot") or "").strip().lower()
    return raw if re.fullmatch(r"p\d{3}", raw) else None


def is_genuine_rewind(state: dict[str, str], stop_slot: str) -> bool:
    previous = previous_stop_slot(state)
    return previous is not None and slot_number(stop_slot) < slot_number(previous)


def finish_scaffold(
    state_path: Path,
    topic: str,
    run_dir: Path,
    stop_slot: str,
    updates: dict[str, str] | None = None,
    *,
    legacy_done: bool = False,
) -> None:
    if legacy_done:
        payload = {
            "timestamp": now_iso(),
            "topic": topic,
            "status": "DONE",
            "runtime.stage": "immersive_ride_scaffolded",
        }
    else:
        stage_target = slot_bucket(stop_slot)
        payload = {
            "timestamp": now_iso(),
            "topic": topic,
            "status": stage_target.upper(),
            "runtime.stage": f"immersive_ride_scaffolded_{stop_slot}",
            "runtime.stage_target": stage_target,
            "runtime.stop_slot": stop_slot,
        }
    if updates:
        payload.update(updates)
    payload.update(_refresh_active_source_receipt(run_dir))
    append_state_block(state_path, payload)
    print(f"Run dir: {_lexical_absolute(run_dir)}")


def scaffold_authoring_updates(*stage_names: str) -> dict[str, str]:
    updates = {
        "runtime.scaffold.status": "draft",
        "runtime.scaffold.content_status": "placeholder",
    }
    for stage_name in stage_names:
        updates.update(SCAFFOLD_AUTHORING_UPDATES[stage_name])
    return updates


def reset_p400_handoff(
    run_dir: Path,
    *,
    experience: str,
    source_run: Path | None,
) -> dict[str, str]:
    """Reset p400 authoring handoff state after a rewind or source change.

    Historical review files are intentionally left untouched.  A new run
    continues from the current authored inputs and deterministic contracts;
    no replacement prompt/report or synthetic approval evidence is created.
    """
    updates = {
        **scaffold_authoring_updates("script"),
        "immersive.experience": experience,
        "immersive.source_run": source_run.as_posix() if source_run is not None else "",
        "artifact.video_manifest": _artifact_absolute(
            run_dir,
            "video_manifest.md",
        ),
        **_refresh_active_source_receipt(run_dir),
    }
    return updates


def _main_impl() -> None:
    parser = argparse.ArgumentParser(description="Scaffold an immersive run folder.")
    parser.add_argument("--topic", required=True, help="Video topic (used for folder name).")
    parser.add_argument(
        "--timestamp",
        type=normalize_timestamp,
        default=None,
        help="Timestamp (YYYYMMDD_HHMM).",
    )
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument(
        "--source-run",
        default=None,
        help="Existing ToC run directory to reference. Required for --experience world_walk.",
    )
    parser.add_argument(
        "--stage",
        type=normalize_stage_target,
        default=None,
        help="Stop target. Coarse p100/100-style targets stop at that stage's authoring handoff slot; fine slots stop exactly.",
    )
    parser.add_argument(
        "--experience",
        choices=sorted(EXPERIENCE_TEMPLATES.keys()),
        default="cloud_island_walk",
        help="Experience template to scaffold (default: cloud_island_walk).",
    )
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "seedance", "veo"],
        default="kling-omni",
        help='Video generation tool in manifest ("kling", "kling-omni", or "seedance"). "veo" is mapped to Kling for safety.',
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    # Legacy compatibility flags are accepted but ignored.  The production
    # pipeline no longer selects a reviewer policy or creates synthetic review
    # evidence for either mode.
    parser.add_argument("--review-policy", choices=["strict", "drafts"], default=None, help=argparse.SUPPRESS)
    parser.add_argument("--story-review", choices=["required", "optional"], default=None, help=argparse.SUPPRESS)
    parser.add_argument("--image-review", choices=["required", "optional"], default=None, help=argparse.SUPPRESS)
    parser.add_argument("--narration-review", choices=["required", "optional"], default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    stop_slot = args.stage or "p570"
    legacy_default = args.stage is None

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()

    experience = str(args.experience)
    if experience == "ride_action_boat":
        print("[warn] --experience ride_action_boat is deprecated; using cinematic_story.")
        experience = "cinematic_story"
    if experience == "world_walk" and args.stage is None:
        # The world-walk template is an authored source-reference skeleton.
        # Stop at the script/manifest handoff until its p400 design is approved.
        stop_slot = "p450"
    source_run_path: Path | None = (
        Path(args.source_run) if args.source_run else None
    )
    source_context: WorldWalkSource | None = None
    if experience == "world_walk":
        if source_run_path is None:
            parser.error("--source-run is required when --experience world_walk")
        try:
            resolved_source_run, source_run_relative = validate_world_walk_source_path(
                REPO_ROOT,
                source_run_path,
            )
            source_identity = directory_identity_nofollow(
                resolved_source_run
            )
            if (
                directory_identity_nofollow(resolved_source_run)
                != source_identity
            ):
                raise ValueError("world-walk source root identity changed")
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        source_run_path = Path(source_run_relative)
        source_context = WorldWalkSource(
            path=resolved_source_run,
            relative=source_run_path,
            identity=source_identity,
        )

    try:
        run_dir, run_dir_identity = _validated_run_directory(
            raw_base=str(args.base),
            raw_run_dir=args.run_dir,
            topic_slug=topic_slug,
            timestamp=ts,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    active_root = _pin_run_root(
        run_dir,
        expected_identity=run_dir_identity,
    )
    if _ACTIVE_RUN_ROOT.get() is not None:
        os.close(active_root.descriptor)
        raise RuntimeError("immersive runner root is already active")
    _ACTIVE_RUN_ROOT.set(active_root)
    if source_context is not None:
        _ACTIVE_SOURCE.set(source_context)
    _assert_safe_run_tree(run_dir)
    # assets
    for relative_directory in (
        Path("assets/characters"),
        Path("assets/objects"),
        Path("assets/styles"),
        Path("assets/scenes"),
        Path("assets/audio"),
        Path("logs"),
        Path("logs/grounding"),
    ):
        _secure_ensure_directory(run_dir, relative_directory)

    state_path = run_dir / "state.txt"
    state_preexisting = _secure_exists(run_dir, "state.txt")
    prior_state = _parse_state(run_dir) if state_preexisting else {}
    source_receipt_state = _refresh_active_source_receipt(
        run_dir,
        bind_manifest=False,
    )
    prior_source_changed = bool(
        state_preexisting
        and source_context is not None
        and (
            prior_state.get(
                "immersive.source_receipt.root_identity",
                "",
            )
            != source_receipt_state.get(
                "immersive.source_receipt.root_identity",
                "",
            )
            or prior_state.get(
                "immersive.source_receipt.bundle_sha256",
                "",
            )
            != source_receipt_state.get(
                "immersive.source_receipt.bundle_sha256",
                "",
            )
        )
    )
    genuine_rewind = state_preexisting and is_genuine_rewind(prior_state, stop_slot)
    preserve_existing_authoring_grounding = (
        state_preexisting
        and not args.force
        and not genuine_rewind
        and not prior_source_changed
    )
    if not state_preexisting:
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "immersive_ride_scaffold",
                "immersive.experience": str(experience),
                **({"immersive.source_run": str(source_run_path)} if source_run_path is not None else {}),
                **source_receipt_state,
            },
        )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", force=args.force)
    if not preserve_existing_authoring_grounding:
        maybe_run_stage_grounding(run_dir, "research", flow="immersive")
    if not target_reaches(stop_slot, "p210"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research"),
                "artifact.research": _artifact_absolute(
                    run_dir,
                    "research.md",
                ),
            },
        )
        return

    write_text(run_dir / "story.md", "# 物語（story）\n\nTODO\n", force=args.force)
    if not preserve_existing_authoring_grounding:
        maybe_run_stage_grounding(run_dir, "story", flow="immersive")
    if not target_reaches(stop_slot, "p310"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story"),
                "artifact.research": _artifact_absolute(
                    run_dir,
                    "research.md",
                ),
                "artifact.story": _artifact_absolute(run_dir, "story.md"),
            },
        )
        return

    if VISUAL_VALUE_TEMPLATE.exists():
        visual_value = (
            VISUAL_VALUE_TEMPLATE.read_text(encoding="utf-8")
            .replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "visual_value.md", visual_value, force=args.force)
    else:
        write_text(run_dir / "visual_value.md", "# 視覚化価値パート（visual value）\n\nTODO\n", force=args.force)
    if not preserve_existing_authoring_grounding:
        maybe_run_stage_grounding(run_dir, "visual_value", flow="immersive")
    if not target_reaches(stop_slot, "p410"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value"),
                "artifact.research": _artifact_absolute(
                    run_dir,
                    "research.md",
                ),
                "artifact.story": _artifact_absolute(run_dir, "story.md"),
                "artifact.visual_value": _artifact_absolute(
                    run_dir,
                    "visual_value.md",
                ),
            },
        )
        return

    write_text(run_dir / "script.md", "# 台本（没入型 / cinematic）\n\nTODO\n", force=args.force)
    if not preserve_existing_authoring_grounding:
        maybe_run_stage_grounding(run_dir, "script", flow="immersive")

    template_path = EXPERIENCE_TEMPLATES.get(str(experience))
    if template_path is None:
        raise SystemExit(f"Unknown --experience: {experience}")
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
            .replace("<source_run>", source_run_path.as_posix() if source_run_path is not None else "")
            .replace("<source_story>", (source_run_path / "story.md").as_posix() if source_run_path is not None else "")
            .replace("<source_assets>", (source_run_path / "assets").as_posix() if source_run_path is not None else "")
        )
        if args.video_tool == "kling":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "kling_3_0"', tmpl)
        elif args.video_tool == "seedance":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "seedance"', tmpl)
        elif args.video_tool in {"kling-omni", "veo"}:
            if args.video_tool == "veo":
                print('[warn] --video-tool veo is disabled for safety; using kling_3_0_omni instead.')
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
        write_text(run_dir / "video_manifest.md", ensure_skeleton_manifest(tmpl), force=args.force)
    else:
        write_text(run_dir / "video_manifest.md", "```yaml\nmanifest_phase: skeleton\nvideo_metadata:\n  topic: \"<topic>\"\nscenes: []\n```\n", force=args.force)
    manifest_path = run_dir / "video_manifest.md"
    if genuine_rewind and not target_reaches(stop_slot, "p510"):
        ensure_skeleton_manifest_file(manifest_path)
    elif target_reaches(stop_slot, "p510"):
        # P400 approvals bind video_manifest.md. Promote before refreshing the
        # final P400 snapshots and before running the readiness gate.
        ensure_production_manifest_file(manifest_path)
    source_receipt_state = _refresh_active_source_receipt(run_dir)

    requested_source_run = source_run_path.as_posix() if source_run_path is not None else ""
    source_context_changed = state_preexisting and (
        str(prior_state.get("immersive.experience") or "") != experience
        or str(prior_state.get("immersive.source_run") or "") != requested_source_run
        or prior_source_changed
    )
    p400_reset = bool(
        state_preexisting
        and (
            genuine_rewind
            or source_context_changed
            or prior_source_changed
        )
    )
    if p400_reset:
        append_state_block(
            state_path,
            reset_p400_handoff(
                run_dir,
                experience=experience,
                source_run=source_run_path,
            ),
        )

    if not target_reaches(stop_slot, "p450"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script"),
                "artifact.research": _artifact_absolute(
                    run_dir,
                    "research.md",
                ),
                "artifact.story": _artifact_absolute(run_dir, "story.md"),
                "artifact.visual_value": _artifact_absolute(
                    run_dir,
                    "visual_value.md",
                ),
                "artifact.script": _artifact_absolute(run_dir, "script.md"),
                "artifact.video_manifest": _artifact_absolute(
                    run_dir,
                    "video_manifest.md",
                ),
                "immersive.experience": str(experience),
                "immersive.source_run": (
                    source_run_path.as_posix()
                    if source_run_path is not None
                    else ""
                ),
            },
        )
        return

    if SCENE_CONTE_TEMPLATE.exists():
        tmpl = SCENE_CONTE_TEMPLATE.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
            .replace("<source_run>", source_run_path.as_posix() if source_run_path is not None else "")
            .replace("<source_story>", (source_run_path / "story.md").as_posix() if source_run_path is not None else "")
            .replace("<source_assets>", (source_run_path / "assets").as_posix() if source_run_path is not None else "")
        )
        write_text(run_dir / "scene_conte.md", tmpl, force=args.force)

    if not target_reaches(stop_slot, "p510"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script"),
                "immersive.experience": str(experience),
                "artifact.research": _artifact_absolute(
                    run_dir,
                    "research.md",
                ),
                "artifact.story": _artifact_absolute(run_dir, "story.md"),
                "artifact.visual_value": _artifact_absolute(
                    run_dir,
                    "visual_value.md",
                ),
                "artifact.script": _artifact_absolute(run_dir, "script.md"),
                "artifact.video_manifest": _artifact_absolute(
                    run_dir,
                    "video_manifest.md",
                ),
                "immersive.source_run": requested_source_run,
            },
        )
        return

    common_artifacts = {
        "immersive.experience": str(experience),
        "immersive.source_run": requested_source_run,
        "artifact.research": _artifact_absolute(run_dir, "research.md"),
        "artifact.story": _artifact_absolute(run_dir, "story.md"),
        "artifact.visual_value": _artifact_absolute(
            run_dir,
            "visual_value.md",
        ),
        "artifact.script": _artifact_absolute(run_dir, "script.md"),
        "artifact.video_manifest": _artifact_absolute(
            run_dir,
            "video_manifest.md",
        ),
        **source_receipt_state,
    }
    require_fresh_p400_readiness(run_dir)
    maybe_run_stage_grounding(run_dir, "asset", flow="immersive")
    write_text(run_dir / "asset_inventory.md", "# Asset Inventory\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_plan.md", "# Asset Plan\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_requests.md", "# Asset Generation Requests\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_manifest.md", "```yaml\nassets: []\n```\n", force=args.force)
    asset_artifacts = {
        "artifact.asset_inventory": _artifact_absolute(
            run_dir,
            "asset_inventory.md",
        ),
        "artifact.asset_plan": _artifact_absolute(
            run_dir,
            "asset_plan.md",
        ),
        "artifact.asset_generation_requests": _artifact_absolute(
            run_dir,
            "asset_generation_requests.md",
        ),
        "artifact.asset_generation_manifest": _artifact_absolute(
            run_dir,
            "asset_generation_manifest.md",
        ),
    }
    if not target_reaches(stop_slot, "p610"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "asset"),
                **common_artifacts,
                **asset_artifacts,
            },
            legacy_done=legacy_default,
        )
        return

    maybe_run_stage_grounding(run_dir, "scene_implementation", flow="immersive")
    write_text(run_dir / "image_generation_requests.md", "# Image Generation Requests\n\nTODO\n", force=args.force)
    scene_artifacts = {
        "artifact.image_generation_requests": _artifact_absolute(
            run_dir,
            "image_generation_requests.md",
        ),
    }
    if not target_reaches(stop_slot, "p710"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "asset", "scene_implementation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
            },
        )
        return

    maybe_run_stage_grounding(run_dir, "narration", flow="immersive")
    if not target_reaches(stop_slot, "p810"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
            },
        )
        return

    write_text(run_dir / "video_generation_requests.md", "# Video Generation Requests\n\nTODO\n", force=args.force)
    video_artifacts = {
        "artifact.video_generation_requests": _artifact_absolute(
            run_dir,
            "video_generation_requests.md",
        ),
    }
    if not target_reaches(stop_slot, "p910"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation", "video_generation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
                **video_artifacts,
            },
        )
        return

    write_text(run_dir / "run_report.md", "# Run Report\n\nTODO\n", force=args.force)
    write_text(run_dir / "eval_report.json", "{}\n", force=args.force)
    finish_scaffold(
        state_path,
        topic_raw,
        run_dir,
        stop_slot,
        {
            **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation", "video_generation", "qa"),
            **common_artifacts,
            **asset_artifacts,
            **scene_artifacts,
            **video_artifacts,
            "artifact.run_report": _artifact_absolute(
                run_dir,
                "run_report.md",
            ),
            "artifact.eval_report": _artifact_absolute(
                run_dir,
                "eval_report.json",
            ),
        },
    )


def main() -> None:
    previous_root = _ACTIVE_RUN_ROOT.get()
    previous_source = _ACTIVE_SOURCE.get()
    try:
        _main_impl()
    finally:
        current_source = _ACTIVE_SOURCE.get()
        if current_source is not previous_source:
            _ACTIVE_SOURCE.set(previous_source)
        current_root = _ACTIVE_RUN_ROOT.get()
        if current_root is not previous_root:
            _ACTIVE_RUN_ROOT.set(previous_root)
            if current_root is not None:
                os.close(current_root.descriptor)


if __name__ == "__main__":
    main()
