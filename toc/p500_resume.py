"""Safe pseudo-rollback helpers for resuming an existing ToC run at p500."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from contextvars import ContextVar
import fcntl
import fnmatch
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable

from toc.harness import (
    _order_keys,
    append_state_snapshot as _harness_append_state_snapshot,
    artifact_inventory,
    nested_state,
    new_job_id,
    now_iso,
    parse_state_file,
    pending_gates,
)
from toc.run_index import build_run_index_markdown, classify_run_file
from toc.runtime_locks import FileLockUnavailable, sync_file_lock
from toc.stage_evaluator import check_manifest_single
from scripts.world_walk_source import (
    read_regular_file_nofollow,
    write_regular_file_nofollow,
)


class P500ResumeError(RuntimeError):
    """Raised when an existing run cannot be safely prepared for p500."""


_ACTIVE_P500_RUN: ContextVar[
    tuple[str, tuple[int, int]] | None
] = ContextVar("toc_p500_active_run", default=None)


PRESERVED_CANONICAL_FILES = (
    "research.md",
    "story.md",
    "visual_value.md",
    "script.md",
    "video_manifest.md",
    "state.txt",
    "p000_index.md",
)
OPTIONAL_PRESERVED_UPSTREAM_FILES = (
    "logs/orchestration/create_input.json",
)
RESUME_INPUT_IDENTITY_SCHEMA_VERSION = (
    "toc.p500_resume.input_identity.v1"
)

DOWNSTREAM_SLOTS = (
    "p510",
    "p520",
    "p530",
    "p540",
    "p550",
    "p560",
    "p570",
    "p610",
    "p620",
    "p630",
    "p640",
    "p650",
    "p660",
    "p670",
    "p680",
    "p710",
    "p720",
    "p730",
    "p740",
    "p750",
    "p810",
    "p820",
    "p830",
    "p840",
    "p850",
    "p860",
    "p910",
    "p920",
    "p930",
)

_PRESERVED_PREFIXES = (
    ".locks/",
    "logs/resume/",
)
_KNOWN_DOWNSTREAM_PREFIXES = (
    "assets/",
    "logs/app_server/",
    "logs/image_generation_jobs/",
    "logs/providers/",
    "logs/render/",
    "thumbnails/",
)
_KNOWN_DOWNSTREAM_FILES = {
    "final.mp4",
    "render.mp4",
    "output.mp4",
    "logs/image_generation_prompts.jsonl",
}
_EXTRA_DOWNSTREAM_ROOT_PATTERNS = (
    "asset_*.md",
    "asset_*.json",
    "image_*.md",
    "image_*.json",
    "video_*.md",
    "video_*.json",
    "video_*.txt",
    "narration_*.md",
    "narration_*.json",
    "generation_*.md",
    "generation_*.json",
    "render_*.md",
    "render_*.json",
    "final_*.md",
    "final_*.json",
)
_DOWNSTREAM_SEMANTIC_STAGES = (
    "asset_plan",
    "asset_output",
    "image_prompt",
    "scene_image",
    "narration",
    "video_motion",
    "video_clip",
    "render",
)
_DOWNSTREAM_STATE_PREFIXES = (
    "stage.asset.",
    "stage.scene_implementation.",
    "stage.narration.",
    "stage.video_generation.",
    "stage.render.",
    "stage.qa.",
    "review.asset",
    "review.image",
    "review.narration",
    "review.duration_fit",
    "review.video",
    "review.final",
    "review.frontend.",
    "review.semantic.scene_set",
    "review.semantic.scene_detail",
    "review.semantic.cut_blueprint",
    "review.semantic.asset_plan",
    "review.semantic.asset_output",
    "review.semantic.image_prompt",
    "review.semantic.scene_image",
    "review.semantic.narration",
    "review.semantic.video_motion",
    "review.semantic.video_clip",
    "review.semantic.render",
    "review.semantic.create_",
    "eval.asset",
    "eval.scene_set",
    "eval.scene_detail",
    "eval.cut_blueprint",
    "eval.image",
    "eval.manifest",
    "eval.scene_image",
    "eval.narration",
    "eval.video",
    "eval.render",
    "image_generation.",
    "video_generation.",
    "audio_generation.",
    "runtime.create_job.",
    "runtime.failure.",
    "runtime.app_server.",
    "runtime.app_server_skill.",
    "runtime.narration.",
    "runtime.video.",
    "runtime.render.",
)


@dataclass(frozen=True)
class ResumePlan:
    run_dir: str
    run_dir_identity: tuple[int, int]
    checkpoint_id: str
    checkpoint_dir: str
    preserved_files: tuple[str, ...]
    upstream_sha256: dict[str, str]
    state_fingerprint: dict[str, Any]
    state_before_sha256: str
    index_fingerprint: dict[str, Any]
    optional_upstream_fingerprints: dict[str, dict[str, Any]]
    resume_input_identity: dict[str, str]
    downstream_files: tuple[str, ...]
    downstream_fingerprints: dict[str, dict[str, Any]]
    p400_reason_keys: tuple[str, ...]
    plan_token: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_open_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not directory:
        raise P500ResumeError(
            "p500 resume requires no-follow directory descriptor support"
        )
    return (
        os.O_RDONLY
        | nofollow
        | directory
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_real_directory(
    path: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> int:
    try:
        lexical = path.lstat()
    except OSError as exc:
        raise P500ResumeError(f"run directory is unavailable: {path}") from exc
    if stat.S_ISLNK(lexical.st_mode) or not stat.S_ISDIR(lexical.st_mode):
        raise P500ResumeError(f"run directory must be a real directory: {path}")
    descriptor = -1
    try:
        descriptor = os.open(path, _directory_open_flags())
        opened = os.fstat(descriptor)
        opened_identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or opened_identity != (lexical.st_dev, lexical.st_ino)
            or (
                expected_identity is not None
                and opened_identity != expected_identity
            )
        ):
            raise P500ResumeError(
                f"run directory identity changed: {path}"
            )
        return descriptor
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _verify_real_directory_identity(
    path: Path,
    expected_identity: tuple[int, int],
) -> None:
    descriptor = _open_real_directory(
        path,
        expected_identity=expected_identity,
    )
    os.close(descriptor)


def _safe_relative_parts(value: str | Path, *, label: str) -> tuple[str, ...]:
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(
            part in {"", ".", ".."} or "/" in part
            for part in relative.parts
        )
    ):
        raise P500ResumeError(f"unsafe {label} path: {value}")
    return relative.parts


def _open_relative_directory(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    create: bool,
    label: str,
) -> int:
    current = os.dup(root_descriptor)
    try:
        for part in parts:
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
                    os.mkdir(part, 0o700, dir_fd=current)
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
    except Exception as exc:
        os.close(current)
        if isinstance(exc, P500ResumeError):
            raise
        joined = "/".join(parts) or "."
        raise P500ResumeError(
            f"unsafe {label} directory identity changed: {joined}"
        ) from exc


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        raise P500ResumeError("p500 resume directory descriptor is not a directory")
    return opened.st_dev, opened.st_ino


def _verify_relative_directory_identity(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    expected_identity: tuple[int, int],
    label: str,
) -> None:
    verification = _open_relative_directory(
        root_descriptor,
        parts,
        create=False,
        label=label,
    )
    try:
        if _descriptor_identity(verification) != expected_identity:
            raise P500ResumeError(
                f"unsafe {label} directory identity changed: "
                f"{'/'.join(parts) or '.'}"
            )
    finally:
        os.close(verification)


def _regular_file_fingerprint_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[dict[str, Any], os.stat_result]:
    try:
        lexical = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise P500ResumeError(f"{label} disappeared or became unsafe") from exc
    if not stat.S_ISREG(lexical.st_mode):
        raise P500ResumeError(f"{label} must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(lexical):
            raise P500ResumeError(f"{label} identity changed while opening")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if _stat_identity(os.fstat(descriptor)) != _stat_identity(opened):
            raise P500ResumeError(f"{label} changed while hashing")
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _stat_identity(current) != _stat_identity(opened):
            raise P500ResumeError(f"{label} identity changed after hashing")
        return (
            {
                "exists": True,
                "lexical_type": "regular_file",
                "is_symlink": False,
                "bytes_sha256": digest.hexdigest(),
            },
            opened,
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _entry_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _require_missing_entry(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
) -> None:
    try:
        os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    raise P500ResumeError(f"{label} already exists")


def _rename_regular_file_at(
    *,
    source_parent_descriptor: int,
    source_name: str,
    destination_parent_descriptor: int,
    destination_name: str,
) -> None:
    """Rename one verified leaf using only pinned parent descriptors."""

    os.rename(
        source_name,
        destination_name,
        src_dir_fd=source_parent_descriptor,
        dst_dir_fd=destination_parent_descriptor,
    )


def _restore_renamed_file_between_open_parents(
    *,
    source_parent_descriptor: int,
    source_name: str,
    destination_parent_descriptor: int,
    destination_name: str,
    expected_entry_identity: tuple[int, int, int],
) -> None:
    _require_missing_entry(
        source_parent_descriptor,
        source_name,
        label=f"rollback destination {source_name}",
    )
    destination = os.stat(
        destination_name,
        dir_fd=destination_parent_descriptor,
        follow_symlinks=False,
    )
    if _entry_identity(destination) != expected_entry_identity:
        raise P500ResumeError(
            f"rollback source identity changed: {destination_name}"
        )
    _rename_regular_file_at(
        source_parent_descriptor=destination_parent_descriptor,
        source_name=destination_name,
        destination_parent_descriptor=source_parent_descriptor,
        destination_name=source_name,
    )
    restored = os.stat(
        source_name,
        dir_fd=source_parent_descriptor,
        follow_symlinks=False,
    )
    if _entry_identity(restored) != expected_entry_identity:
        raise P500ResumeError(
            f"rollback destination identity changed: {source_name}"
        )


def _move_planned_downstream_file(
    *,
    run_descriptor: int,
    artifacts_descriptor: int,
    rel: str,
    expected_fingerprint: dict[str, Any],
) -> None:
    parts = _safe_relative_parts(rel, label="downstream artifact")
    source_parent = _open_relative_directory(
        run_descriptor,
        parts[:-1],
        create=False,
        label="downstream source",
    )
    destination_parent = _open_relative_directory(
        artifacts_descriptor,
        parts[:-1],
        create=True,
        label="checkpoint destination",
    )
    renamed = False
    source_entry_identity: tuple[int, int, int] | None = None
    try:
        source_parent_identity = _descriptor_identity(source_parent)
        destination_parent_identity = _descriptor_identity(destination_parent)
        actual_fingerprint, source_stat = _regular_file_fingerprint_at(
            source_parent,
            parts[-1],
            label=f"planned downstream artifact {rel}",
        )
        if actual_fingerprint != expected_fingerprint:
            raise P500ResumeError(
                "downstream artifact bytes or lexical type changed before "
                f"checkpoint move: {rel}"
            )
        source_entry_identity = _entry_identity(source_stat)
        _require_missing_entry(
            destination_parent,
            parts[-1],
            label=f"checkpoint destination {rel}",
        )
        _rename_regular_file_at(
            source_parent_descriptor=source_parent,
            source_name=parts[-1],
            destination_parent_descriptor=destination_parent,
            destination_name=parts[-1],
        )
        renamed = True
        destination_stat = os.stat(
            parts[-1],
            dir_fd=destination_parent,
            follow_symlinks=False,
        )
        if _entry_identity(destination_stat) != source_entry_identity:
            raise P500ResumeError(
                f"checkpoint destination identity changed after move: {rel}"
            )
        _verify_relative_directory_identity(
            run_descriptor,
            parts[:-1],
            expected_identity=source_parent_identity,
            label="downstream source",
        )
        _verify_relative_directory_identity(
            artifacts_descriptor,
            parts[:-1],
            expected_identity=destination_parent_identity,
            label="checkpoint destination",
        )
    except Exception as exc:
        if renamed and source_entry_identity is not None:
            try:
                _restore_renamed_file_between_open_parents(
                    source_parent_descriptor=source_parent,
                    source_name=parts[-1],
                    destination_parent_descriptor=destination_parent,
                    destination_name=parts[-1],
                    expected_entry_identity=source_entry_identity,
                )
            except Exception as rollback_exc:
                raise P500ResumeError(
                    "unsafe downstream move could not be rolled back for "
                    f"{rel}: {rollback_exc}"
                ) from exc
        raise
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _restore_one_moved_file(
    *,
    run_descriptor: int,
    artifacts_descriptor: int,
    rel: str,
    expected_fingerprint: dict[str, Any],
) -> None:
    parts = _safe_relative_parts(rel, label="rollback artifact")
    source_parent = _open_relative_directory(
        artifacts_descriptor,
        parts[:-1],
        create=False,
        label="checkpoint rollback source",
    )
    destination_parent = _open_relative_directory(
        run_descriptor,
        parts[:-1],
        create=True,
        label="downstream rollback destination",
    )
    renamed = False
    source_entry_identity: tuple[int, int, int] | None = None
    try:
        source_parent_identity = _descriptor_identity(source_parent)
        destination_parent_identity = _descriptor_identity(destination_parent)
        actual_fingerprint, source_stat = _regular_file_fingerprint_at(
            source_parent,
            parts[-1],
            label=f"checkpoint rollback artifact {rel}",
        )
        if actual_fingerprint != expected_fingerprint:
            raise P500ResumeError(
                f"checkpoint rollback artifact changed: {rel}"
            )
        source_entry_identity = _entry_identity(source_stat)
        _require_missing_entry(
            destination_parent,
            parts[-1],
            label=f"rollback destination {rel}",
        )
        _rename_regular_file_at(
            source_parent_descriptor=source_parent,
            source_name=parts[-1],
            destination_parent_descriptor=destination_parent,
            destination_name=parts[-1],
        )
        renamed = True
        destination_stat = os.stat(
            parts[-1],
            dir_fd=destination_parent,
            follow_symlinks=False,
        )
        if _entry_identity(destination_stat) != source_entry_identity:
            raise P500ResumeError(
                f"rollback destination identity changed after move: {rel}"
            )
        _verify_relative_directory_identity(
            artifacts_descriptor,
            parts[:-1],
            expected_identity=source_parent_identity,
            label="checkpoint rollback source",
        )
        _verify_relative_directory_identity(
            run_descriptor,
            parts[:-1],
            expected_identity=destination_parent_identity,
            label="downstream rollback destination",
        )
    except Exception as exc:
        if renamed and source_entry_identity is not None:
            try:
                _restore_renamed_file_between_open_parents(
                    source_parent_descriptor=source_parent,
                    source_name=parts[-1],
                    destination_parent_descriptor=destination_parent,
                    destination_name=parts[-1],
                    expected_entry_identity=source_entry_identity,
                )
            except Exception as rollback_exc:
                raise P500ResumeError(
                    "unsafe checkpoint rollback could not preserve "
                    f"{rel}: {rollback_exc}"
                ) from exc
        raise
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def _remove_tree_at(parent_descriptor: int, name: str) -> None:
    entry = os.stat(
        name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if not stat.S_ISDIR(entry.st_mode):
        os.unlink(name, dir_fd=parent_descriptor)
        return
    child = os.open(
        name,
        _directory_open_flags(),
        dir_fd=parent_descriptor,
    )
    try:
        for child_name in os.listdir(child):
            _remove_tree_at(child, child_name)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent_descriptor)


def _write_regular_file_at(
    parent_descriptor: int,
    name: str,
    data: bytes,
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(
        name,
        flags,
        0o600,
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise P500ResumeError(
                f"checkpoint metadata is not a private regular file: {name}"
            )
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("checkpoint metadata write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _entry_identity(current) != _entry_identity(opened):
            raise P500ResumeError(
                f"checkpoint metadata identity changed after write: {name}"
            )
    finally:
        os.close(descriptor)


def _descriptor_root_path(descriptor: int) -> Path:
    for root in (Path("/dev/fd"), Path("/proc/self/fd")):
        candidate = root / str(descriptor)
        if candidate.exists():
            return candidate
    raise P500ResumeError(
        "platform cannot address the pinned p500 run directory descriptor"
    )


def _parse_state_text(text: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if (
            not line
            or line == "---"
            or line.startswith("#")
            or "=" not in line
        ):
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            merged[key] = value.strip().replace("\n", " ")
    return merged


def _read_bound_run_bytes(
    run_dir: Path,
    relative_path: str | Path,
    *,
    identity: tuple[int, int],
    missing_ok: bool = False,
) -> bytes:
    try:
        return read_regular_file_nofollow(
            run_dir,
            relative_path,
            expected_root_identity=identity,
        )
    except FileNotFoundError:
        if missing_ok:
            return b""
        raise


def _parse_bound_state(
    run_dir: Path,
    *,
    identity: tuple[int, int],
) -> dict[str, str]:
    return _parse_state_text(
        _read_bound_run_bytes(
            run_dir,
            "state.txt",
            identity=identity,
            missing_ok=True,
        ).decode("utf-8")
    )


def _write_bound_run_bytes(
    run_dir: Path,
    relative_path: str | Path,
    data: bytes,
    *,
    identity: tuple[int, int],
) -> None:
    write_regular_file_nofollow(
        destination_root=run_dir,
        destination_relative=relative_path,
        data=data,
        expected_destination_root_identity=identity,
    )


def append_state_snapshot(
    state_path: Path,
    updates: dict[str, str],
) -> dict[str, str]:
    """Append state without ever writing through a replaced run pathname."""

    active = _ACTIVE_P500_RUN.get()
    lexical_run = os.path.abspath(os.fspath(state_path.parent))
    if active is None or active[0] != lexical_run:
        return _harness_append_state_snapshot(state_path, updates)
    if state_path.name != "state.txt":
        raise P500ResumeError(
            f"p500 state snapshot must target state.txt: {state_path}"
        )

    run_dir = Path(lexical_run)
    identity = active[1]
    current_bytes = _read_bound_run_bytes(
        run_dir,
        "state.txt",
        identity=identity,
        missing_ok=True,
    )
    try:
        current_text = current_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P500ResumeError("state.txt is not valid UTF-8") from exc
    merged = _parse_state_text(current_text)
    if "job_id" not in merged or not merged["job_id"].strip():
        merged["job_id"] = new_job_id()
    if "status" not in merged or not merged["status"].strip():
        merged["status"] = "INIT"
    merged.setdefault(
        "artifact.run_index",
        os.fspath(run_dir / "p000_index.md"),
    )
    merged.update(
        {
            key: value.replace("\n", " ").strip()
            for key, value in updates.items()
        }
    )
    merged["timestamp"] = now_iso()
    block = (
        "\n".join(
            f"{key}={merged[key]}" for key in _order_keys(merged)
        )
        + "\n---\n"
    )
    _write_bound_run_bytes(
        run_dir,
        "state.txt",
        current_bytes + block.encode("utf-8"),
        identity=identity,
    )

    _verify_real_directory_identity(run_dir, identity)
    index_text = build_run_index_markdown(run_dir, state=merged)
    _write_bound_run_bytes(
        run_dir,
        "p000_index.md",
        index_text.encode("utf-8"),
        identity=identity,
    )
    payload: dict[str, Any] = {
        "generated_at": now_iso(),
        "run_dir": os.fspath(run_dir),
        "state_file": os.fspath(run_dir / "state.txt"),
        "state_flat": merged,
        "state": nested_state(merged),
        "artifacts": artifact_inventory(run_dir, merged),
        "pending_gates": pending_gates(merged),
    }
    eval_bytes = _read_bound_run_bytes(
        run_dir,
        "eval_report.json",
        identity=identity,
        missing_ok=True,
    )
    if eval_bytes:
        try:
            payload["eval_report"] = json.loads(
                eval_bytes.decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload["eval_report"] = {
                "error": "Failed to parse eval_report.json"
            }
    _write_bound_run_bytes(
        run_dir,
        "run_status.json",
        (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        identity=identity,
    )
    return merged


def _lexical_path_fingerprint(path: Path) -> dict[str, Any]:
    """Fingerprint a path without following a final-component symlink."""

    try:
        lexical_stat = path.lstat()
    except FileNotFoundError:
        return {
            "exists": False,
            "lexical_type": "missing",
            "is_symlink": False,
            "bytes_sha256": None,
        }

    mode = lexical_stat.st_mode
    if stat.S_ISLNK(mode):
        try:
            target_bytes = os.fsencode(os.readlink(path))
            final_stat = path.lstat()
        except FileNotFoundError as exc:
            raise P500ResumeError(
                f"resume plan path changed while fingerprinting: {path}"
            ) from exc
        if _stat_identity(final_stat) != _stat_identity(lexical_stat):
            raise P500ResumeError(
                f"resume plan path changed while fingerprinting: {path}"
            )
        return {
            "exists": True,
            "lexical_type": "symlink",
            "is_symlink": True,
            "bytes_sha256": hashlib.sha256(target_bytes).hexdigest(),
        }

    if stat.S_ISREG(mode):
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise P500ResumeError(
                f"resume plan path changed while fingerprinting: {path}"
            ) from exc
        try:
            opened_stat = os.fstat(descriptor)
            if _stat_identity(opened_stat) != _stat_identity(lexical_stat):
                raise P500ResumeError(
                    f"resume plan path changed while fingerprinting: {path}"
                )
            digest = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            final_stat = os.fstat(descriptor)
            if _stat_identity(final_stat) != _stat_identity(opened_stat):
                raise P500ResumeError(
                    f"resume plan path changed while fingerprinting: {path}"
                )
        finally:
            os.close(descriptor)
        return {
            "exists": True,
            "lexical_type": "regular_file",
            "is_symlink": False,
            "bytes_sha256": digest.hexdigest(),
        }

    if stat.S_ISDIR(mode):
        lexical_type = "directory"
    elif stat.S_ISFIFO(mode):
        lexical_type = "fifo"
    elif stat.S_ISSOCK(mode):
        lexical_type = "socket"
    elif stat.S_ISCHR(mode):
        lexical_type = "character_device"
    elif stat.S_ISBLK(mode):
        lexical_type = "block_device"
    else:
        lexical_type = "other"
    return {
        "exists": True,
        "lexical_type": lexical_type,
        "is_symlink": False,
        "bytes_sha256": None,
    }


def _slot_number(slot: str) -> int:
    match = re.fullmatch(r"p(\d{3})", slot)
    return int(match.group(1)) if match else -1


def resolve_run_dir(repo_root: Path, raw_run_dir: str | Path) -> Path:
    output_path = repo_root / "output"
    if output_path.is_symlink():
        raise P500ResumeError(f"output directory must not be a symlink: {output_path}")
    output_root = output_path.resolve()
    candidate = Path(raw_run_dir)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if candidate.is_symlink():
        raise P500ResumeError(f"run directory must not be a symlink: {candidate}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(output_root)
    except ValueError as exc:
        raise P500ResumeError(f"run directory must be under {output_root}: {resolved}") from exc
    if resolved == output_root:
        raise P500ResumeError("output/ itself is not a run directory")
    if resolved.parent != output_root:
        raise P500ResumeError(
            f"run directory must be a direct child of {output_root}: {resolved}"
        )
    if not resolved.is_dir():
        raise P500ResumeError(f"run directory does not exist: {resolved}")
    return resolved


def _validate_upstream(run_dir: Path) -> None:
    missing: list[str] = []
    unsafe: list[str] = []
    for rel in PRESERVED_CANONICAL_FILES:
        path = run_dir / rel
        if not path.is_file():
            missing.append(rel)
        elif path.is_symlink():
            unsafe.append(rel)
    if missing:
        raise P500ResumeError(
            "p500 resume requires the materialized p400 run artifacts: "
            + ", ".join(missing)
        )
    if unsafe:
        raise P500ResumeError(
            "canonical run artifacts must not be symlinks: " + ", ".join(unsafe)
        )
    unsafe_optional: list[str] = []
    for rel in OPTIONAL_PRESERVED_UPSTREAM_FILES:
        path = run_dir / rel
        if path.is_symlink() or (path.exists() and not path.is_file()):
            unsafe_optional.append(rel)
    if unsafe_optional:
        raise P500ResumeError(
            "optional canonical run artifacts must be regular files and not "
            "symlinks: "
            + ", ".join(unsafe_optional)
        )


def _p400_readiness(run_dir: Path) -> tuple[str, tuple[str, ...]]:
    result, updates = check_manifest_single(
        run_dir,
        "standard",
        "immersive",
        # A Codex fix may intentionally make the old p400 review digest stale.
        # The continuation path rematerializes those reviews and runs the full
        # gate before any p500 request/provider work.
        require_review_artifacts=False,
    )
    status = str(updates.get("eval.p400_readiness.status") or "")
    reason_keys = tuple(
        value
        for value in str(updates.get("eval.p400_readiness.reason_keys") or "").split(",")
        if value
    )
    if status != "approved":
        failed = [
            str(check.get("id") or "")
            for check in result.get("checks", [])
            if isinstance(check, dict) and check.get("passed") is False
        ]
        reasons = reason_keys or tuple(value for value in failed if value.startswith("p400."))
        raise P500ResumeError(
            "fresh p400 readiness is not approved"
            + (f": {', '.join(reasons)}" if reasons else "")
        )
    return status, reason_keys


def _is_downstream_semantic_log(rel: str) -> bool:
    if not rel.startswith("logs/review/semantic/"):
        return False
    name = Path(rel).name
    return any(name.startswith(f"{stage}.") for stage in _DOWNSTREAM_SEMANTIC_STAGES)


def _is_extra_downstream_root_file(rel: str) -> bool:
    if "/" in rel or rel == "video_manifest.md":
        return False
    return any(fnmatch.fnmatch(rel, pattern) for pattern in _EXTRA_DOWNSTREAM_ROOT_PATTERNS)


def _is_downstream_file(run_dir: Path, rel: str) -> bool:
    if rel in PRESERVED_CANONICAL_FILES or rel in OPTIONAL_PRESERVED_UPSTREAM_FILES:
        return False
    if rel == ".toc_frontend_create.lock" or rel.startswith(_PRESERVED_PREFIXES):
        return False
    if rel in _KNOWN_DOWNSTREAM_FILES or rel.startswith(_KNOWN_DOWNSTREAM_PREFIXES):
        return True
    if _is_downstream_semantic_log(rel) or _is_extra_downstream_root_file(rel):
        return True
    entry = classify_run_file(rel, run_dir=run_dir)
    slot_number = _slot_number(entry.slot)
    return 500 <= slot_number < 950


def _iter_downstream_files(run_dir: Path) -> Iterable[str]:
    for path in run_dir.rglob("*"):
        if path.is_symlink():
            raise P500ResumeError(f"run artifacts must not be symlinks: {path.relative_to(run_dir)}")
        if not path.is_file() and not path.is_symlink():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if _is_downstream_file(run_dir, rel):
            yield rel


def _checkpoint_id(value: str | None) -> str:
    checkpoint = value or datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S%f%z"
    )
    if (
        checkpoint in {".", ".."}
        or checkpoint.startswith(".")
        or re.fullmatch(r"[A-Za-z0-9_+.-]+", checkpoint) is None
    ):
        raise P500ResumeError(
            "checkpoint id may contain only letters, numbers, _, +, ., and -"
        )
    return checkpoint


def _validate_no_active_bulk_jobs(run_dir: Path) -> None:
    job_dir = run_dir / "logs" / "image_generation_jobs"
    if not job_dir.exists():
        return
    if job_dir.is_symlink():
        raise P500ResumeError(f"bulk job directory must not be a symlink: {job_dir}")
    active: list[str] = []
    invalid: list[str] = []
    for path in sorted(job_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid.append(path.name)
            continue
        if not isinstance(payload, dict):
            invalid.append(path.name)
            continue
        if str(payload.get("status") or "").strip().lower() in {"queued", "running"}:
            active.append(str(payload.get("jobId") or path.stem))
    if invalid:
        raise P500ResumeError(
            "cannot prove bulk image jobs are inactive; invalid job records: "
            + ", ".join(invalid)
        )
    if active:
        raise P500ResumeError(
            "bulk image generation is still queued/running for this run: "
            + ", ".join(active)
        )


def _normalize_resume_input_identity(
    identity: dict[str, str] | None,
) -> dict[str, str]:
    if identity is None:
        return {}
    if not isinstance(identity, dict):
        raise P500ResumeError("resume input identity must be an object")
    if not identity:
        return {}
    expected_keys = {
        "schema_version",
        "topic_sha256",
        "source_sha256",
    }
    if set(identity) != expected_keys:
        raise P500ResumeError(
            "resume input identity has an invalid field contract"
        )
    if (
        identity.get("schema_version")
        != RESUME_INPUT_IDENTITY_SCHEMA_VERSION
    ):
        raise P500ResumeError(
            "resume input identity has an unsupported schema_version"
        )
    for field in ("topic_sha256", "source_sha256"):
        value = identity.get(field)
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[0-9a-f]{64}", value) is None
        ):
            raise P500ResumeError(
                f"resume input identity {field} is malformed"
            )
    return {
        "schema_version": RESUME_INPUT_IDENTITY_SCHEMA_VERSION,
        "source_sha256": identity["source_sha256"],
        "topic_sha256": identity["topic_sha256"],
    }


def canonical_state_before_sha256(state: dict[str, str]) -> str:
    """Hash the exact parsed-state mapping stored in checkpoint metadata."""

    if not isinstance(state, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in state.items()
    ):
        raise P500ResumeError(
            "checkpoint state_before must map strings to strings"
        )
    canonical_bytes = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def _plan_token(
    *,
    run_dir: Path,
    run_dir_identity: tuple[int, int] | list[int] | None = None,
    checkpoint_id: str,
    upstream_sha256: dict[str, str],
    state_fingerprint: dict[str, Any],
    index_fingerprint: dict[str, Any],
    optional_upstream_fingerprints: dict[str, dict[str, Any]],
    downstream_files: tuple[str, ...],
    downstream_fingerprints: dict[str, dict[str, Any]],
    resume_input_identity: dict[str, str] | None = None,
    state_before_sha256: str | None = None,
) -> str:
    normalized_run_identity: tuple[int, int] | None = None
    if run_dir_identity is not None:
        if (
            not isinstance(run_dir_identity, (tuple, list))
            or len(run_dir_identity) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in run_dir_identity
            )
        ):
            raise P500ResumeError("run directory identity is malformed")
        normalized_run_identity = (
            int(run_dir_identity[0]),
            int(run_dir_identity[1]),
        )
    include_input_identity = resume_input_identity is not None
    normalized_input_identity = _normalize_resume_input_identity(
        resume_input_identity
    )
    if (
        state_before_sha256 is not None
        and re.fullmatch(r"[0-9a-f]{64}", state_before_sha256) is None
    ):
        raise P500ResumeError("state_before_sha256 is malformed")
    payload = {
        "run_dir": str(run_dir),
        "checkpoint_id": checkpoint_id,
        "upstream_sha256": upstream_sha256,
        "state_fingerprint": state_fingerprint,
        "index_fingerprint": index_fingerprint,
        "optional_upstream_fingerprints": optional_upstream_fingerprints,
        "downstream_files": downstream_files,
        "downstream_fingerprints": downstream_fingerprints,
    }
    if normalized_run_identity is not None:
        payload["run_dir_identity"] = normalized_run_identity
    if include_input_identity:
        payload["resume_input_identity"] = normalized_input_identity
    if state_before_sha256 is not None:
        payload["state_before_sha256"] = state_before_sha256
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_resume_plan(
    *,
    repo_root: Path,
    run_dir: str | Path,
    checkpoint_id: str | None = None,
    resume_input_identity: dict[str, str] | None = None,
) -> ResumePlan:
    normalized_input_identity = _normalize_resume_input_identity(
        resume_input_identity
    )
    resolved = resolve_run_dir(repo_root, run_dir)
    root_descriptor = _open_real_directory(resolved)
    try:
        opened_root = os.fstat(root_descriptor)
        run_dir_identity = (opened_root.st_dev, opened_root.st_ino)
    finally:
        os.close(root_descriptor)
    _validate_upstream(resolved)
    _validate_no_active_bulk_jobs(resolved)
    _status, reason_keys = _p400_readiness(resolved)
    checkpoint = _checkpoint_id(checkpoint_id)
    upstream_sha256 = {
        rel: _sha256(resolved / rel)
        for rel in PRESERVED_CANONICAL_FILES
        if rel not in {"state.txt", "p000_index.md"}
    }
    state_before = parse_state_file(resolved / "state.txt")
    state_before_sha256 = canonical_state_before_sha256(state_before)
    downstream = tuple(sorted(set(_iter_downstream_files(resolved))))
    state_fingerprint = _lexical_path_fingerprint(resolved / "state.txt")
    index_fingerprint = _lexical_path_fingerprint(resolved / "p000_index.md")
    optional_upstream_fingerprints = {
        rel: _lexical_path_fingerprint(resolved / rel)
        for rel in OPTIONAL_PRESERVED_UPSTREAM_FILES
    }
    downstream_fingerprints = {
        rel: _lexical_path_fingerprint(resolved / rel)
        for rel in downstream
    }
    checkpoint_root = resolved / "logs" / "resume" / "p500"
    checkpoint_dir = checkpoint_root / checkpoint
    try:
        checkpoint_dir.resolve().relative_to(resolved)
    except ValueError as exc:
        raise P500ResumeError(
            f"checkpoint path escapes the run directory: {checkpoint_dir}"
        ) from exc
    plan = ResumePlan(
        run_dir=str(resolved),
        run_dir_identity=run_dir_identity,
        checkpoint_id=checkpoint,
        checkpoint_dir=str(checkpoint_dir),
        preserved_files=PRESERVED_CANONICAL_FILES,
        upstream_sha256=upstream_sha256,
        state_fingerprint=state_fingerprint,
        state_before_sha256=state_before_sha256,
        index_fingerprint=index_fingerprint,
        optional_upstream_fingerprints=optional_upstream_fingerprints,
        resume_input_identity=normalized_input_identity,
        downstream_files=downstream,
        downstream_fingerprints=downstream_fingerprints,
        p400_reason_keys=reason_keys,
        plan_token=_plan_token(
            run_dir=resolved,
            run_dir_identity=run_dir_identity,
            checkpoint_id=checkpoint,
            upstream_sha256=upstream_sha256,
            state_fingerprint=state_fingerprint,
            state_before_sha256=state_before_sha256,
            index_fingerprint=index_fingerprint,
            optional_upstream_fingerprints=optional_upstream_fingerprints,
            downstream_files=downstream,
            downstream_fingerprints=downstream_fingerprints,
            resume_input_identity=normalized_input_identity,
        ),
    )
    _verify_real_directory_identity(resolved, run_dir_identity)
    return plan


def _state_key_is_downstream(key: str) -> bool:
    slot_match = re.match(r"^(?:slot|orchestration)\.p(\d{3})\.", key)
    if slot_match and int(slot_match.group(1)) >= 500:
        return True
    return key.startswith(_DOWNSTREAM_STATE_PREFIXES)


def _neutral_state_value(key: str) -> str:
    if key.endswith(".status"):
        if key.startswith(("image_generation.", "video_generation.", "audio_generation.")):
            return "not_started"
        return "pending"
    if key.endswith(".current_round"):
        return "0"
    if key.endswith(".attempt") or key.endswith(".error_count"):
        return "0"
    return ""


def _state_updates_for_reset(
    *,
    run_dir: Path,
    plan: ResumePlan,
    state: dict[str, str],
) -> dict[str, str]:
    moved = set(plan.downstream_files)
    updates = {
        key: _neutral_state_value(key)
        for key in state
        if _state_key_is_downstream(key)
    }
    for key, value in state.items():
        if not key.startswith("artifact.") or not value:
            continue
        artifact_path = Path(value)
        try:
            rel = (
                artifact_path.resolve().relative_to(run_dir).as_posix()
                if artifact_path.is_absolute()
                else artifact_path.as_posix()
            )
        except ValueError:
            continue
        if rel in moved:
            updates[key] = ""
    for slot in DOWNSTREAM_SLOTS:
        updates[f"slot.{slot}.status"] = "pending"
        updates[f"slot.{slot}.note"] = "invalidated for p500 resume"
    updates.update(
        {
            "status": "P500",
            "runtime.stage": "p500_resume_prepared",
            "runtime.stage_target": "p500",
            "runtime.resume.p500.status": "prepared",
            "runtime.resume.p500.checkpoint": str(
                Path(plan.checkpoint_dir).relative_to(run_dir)
            ),
            "runtime.resume.p500.upstream_digest": hashlib.sha256(
                json.dumps(
                    plan.upstream_sha256,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "review.image_prompt.request_freeze.status": "pending",
            "review.image.status": "pending",
            "stage.asset.status": "pending",
            "stage.scene_implementation.status": "pending",
            "image_generation.status": "not_started",
            "video_generation.status": "not_started",
            "last_error": "",
        }
    )
    return updates


def _restore_moved_files(
    *,
    run_descriptor: int,
    artifacts_descriptor: int,
    plan: ResumePlan,
    moved: list[str],
) -> tuple[str, ...]:
    errors: list[str] = []
    for rel in reversed(moved):
        try:
            _restore_one_moved_file(
                run_descriptor=run_descriptor,
                artifacts_descriptor=artifacts_descriptor,
                rel=rel,
                expected_fingerprint=plan.downstream_fingerprints[rel],
            )
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    return tuple(errors)


def _apply_resume_plan_locked(
    plan: ResumePlan,
    *,
    run_descriptor: int,
) -> Path:
    run_dir = Path(plan.run_dir)
    checkpoint_dir = Path(plan.checkpoint_dir)
    expected_checkpoint_dir = (
        run_dir / "logs" / "resume" / "p500" / plan.checkpoint_id
    )
    if os.path.normpath(checkpoint_dir) != os.path.normpath(
        expected_checkpoint_dir
    ):
        raise P500ResumeError(
            "checkpoint path does not match the inspected resume plan"
        )

    moved: list[str] = []
    state_committed = False
    p500_parent_descriptor = -1
    checkpoint_descriptor = -1
    artifacts_descriptor = -1
    checkpoint_created = False
    try:
        if _descriptor_identity(run_descriptor) != plan.run_dir_identity:
            raise P500ResumeError(
                f"run directory identity changed: {run_dir}"
            )
        _verify_real_directory_identity(run_dir, plan.run_dir_identity)
        current = build_resume_plan(
            repo_root=run_dir.parents[1],
            run_dir=run_dir,
            checkpoint_id=plan.checkpoint_id,
            resume_input_identity=plan.resume_input_identity,
        )
        if current.run_dir_identity != plan.run_dir_identity:
            raise P500ResumeError(
                f"run directory identity changed: {run_dir}"
            )
        if current.upstream_sha256 != plan.upstream_sha256:
            raise P500ResumeError(
                "upstream artifacts changed after the resume plan was built; run dry-run again"
            )
        if current.state_fingerprint != plan.state_fingerprint:
            raise P500ResumeError(
                "state.txt changed after the resume plan was built; run dry-run again"
            )
        if current.state_before_sha256 != plan.state_before_sha256:
            raise P500ResumeError(
                "parsed state changed after the resume plan was built; "
                "run dry-run again"
            )
        if current.index_fingerprint != plan.index_fingerprint:
            raise P500ResumeError(
                "p000_index.md changed after the resume plan was built; "
                "run dry-run again"
            )
        if (
            current.optional_upstream_fingerprints
            != plan.optional_upstream_fingerprints
        ):
            raise P500ResumeError(
                "create_input.json changed after the resume plan was built; "
                "run dry-run again"
            )
        if current.resume_input_identity != plan.resume_input_identity:
            raise P500ResumeError(
                "resume input identity changed after the resume plan was "
                "built; run dry-run again"
            )
        if current.downstream_files != plan.downstream_files:
            raise P500ResumeError(
                "downstream artifacts changed after the resume plan was built; run dry-run again"
            )
        if current.downstream_fingerprints != plan.downstream_fingerprints:
            raise P500ResumeError(
                "downstream artifact bytes or lexical type changed after the "
                "resume plan was built; run dry-run again"
            )
        if current.plan_token != plan.plan_token:
            raise P500ResumeError(
                "resume plan token changed after the resume plan was built; "
                "run dry-run again"
            )

        _verify_real_directory_identity(run_dir, plan.run_dir_identity)
        p500_parent_descriptor = _open_relative_directory(
            run_descriptor,
            ("logs", "resume", "p500"),
            create=True,
            label="checkpoint parent",
        )
        try:
            os.mkdir(
                plan.checkpoint_id,
                0o700,
                dir_fd=p500_parent_descriptor,
            )
        except FileExistsError as exc:
            raise P500ResumeError(
                f"checkpoint already exists: {checkpoint_dir}"
            ) from exc
        checkpoint_created = True
        checkpoint_descriptor = _open_relative_directory(
            p500_parent_descriptor,
            (plan.checkpoint_id,),
            create=False,
            label="checkpoint",
        )
        os.mkdir("artifacts", 0o700, dir_fd=checkpoint_descriptor)
        artifacts_descriptor = _open_relative_directory(
            checkpoint_descriptor,
            ("artifacts",),
            create=False,
            label="checkpoint artifacts",
        )
        for rel in plan.downstream_files:
            _move_planned_downstream_file(
                run_descriptor=run_descriptor,
                artifacts_descriptor=artifacts_descriptor,
                rel=rel,
                expected_fingerprint=plan.downstream_fingerprints[rel],
            )
            moved.append(rel)
            _verify_real_directory_identity(run_dir, plan.run_dir_identity)

        state = _parse_bound_state(
            run_dir,
            identity=plan.run_dir_identity,
        )
        if canonical_state_before_sha256(state) != plan.state_before_sha256:
            raise P500ResumeError(
                "state_before changed before checkpoint metadata was written; "
                "run dry-run again"
            )
        metadata = {
            **plan.to_dict(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "moved_file_count": len(moved),
            "state_before": state,
        }
        _write_regular_file_at(
            checkpoint_descriptor,
            "checkpoint.json",
            (
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
        )
        try:
            append_state_snapshot(
                run_dir / "state.txt",
                _state_updates_for_reset(run_dir=run_dir, plan=plan, state=state),
            )
            state_committed = True
        except Exception:
            committed_state = _parse_bound_state(
                run_dir,
                identity=plan.run_dir_identity,
            )
            state_committed = (
                committed_state.get("runtime.resume.p500.checkpoint")
                == str(checkpoint_dir.relative_to(run_dir))
                and committed_state.get("runtime.resume.p500.status") == "prepared"
            )
            raise
        _verify_real_directory_identity(run_dir, plan.run_dir_identity)
    except Exception as exc:
        if not state_committed:
            rollback_errors: tuple[str, ...] = ()
            if artifacts_descriptor >= 0:
                rollback_errors = _restore_moved_files(
                    run_descriptor=run_descriptor,
                    artifacts_descriptor=artifacts_descriptor,
                    plan=plan,
                    moved=moved,
                )
            if not rollback_errors and checkpoint_created:
                if artifacts_descriptor >= 0:
                    os.close(artifacts_descriptor)
                    artifacts_descriptor = -1
                if checkpoint_descriptor >= 0:
                    os.close(checkpoint_descriptor)
                    checkpoint_descriptor = -1
                try:
                    _remove_tree_at(
                        p500_parent_descriptor,
                        plan.checkpoint_id,
                    )
                    checkpoint_created = False
                except Exception as cleanup_exc:
                    rollback_errors = (
                        f"checkpoint cleanup: {cleanup_exc}",
                    )
            if rollback_errors:
                raise P500ResumeError(
                    "p500 rollback could not safely restore the inspected "
                    "run; checkpoint preserved: "
                    + "; ".join(rollback_errors)
                ) from exc
        raise
    finally:
        if artifacts_descriptor >= 0:
            os.close(artifacts_descriptor)
        if checkpoint_descriptor >= 0:
            os.close(checkpoint_descriptor)
        if p500_parent_descriptor >= 0:
            os.close(p500_parent_descriptor)
    return expected_checkpoint_dir


def apply_resume_plan(
    plan: ResumePlan,
    *,
    lock_already_held: bool = False,
    run_descriptor: int | None = None,
    run_directory_lock_already_held: bool = False,
) -> Path:
    run_dir = Path(plan.run_dir)
    if not lock_already_held:
        pinned_descriptor = _open_real_directory(
            run_dir,
            expected_identity=plan.run_dir_identity,
        )
        try:
            with sync_file_lock(
                run_dir / ".locks" / "create_resume.lock",
                wait=False,
                run_root_descriptor=pinned_descriptor,
                expected_run_root_identity=plan.run_dir_identity,
            ):
                return apply_resume_plan(
                    plan,
                    lock_already_held=True,
                    run_descriptor=pinned_descriptor,
                    run_directory_lock_already_held=False,
                )
        except FileLockUnavailable as exc:
            raise P500ResumeError(
                "another create/resume process owns this run"
            ) from exc
        finally:
            os.close(pinned_descriptor)

    owns_run_descriptor = run_descriptor is None
    if run_descriptor is None:
        run_descriptor = _open_real_directory(
            run_dir,
            expected_identity=plan.run_dir_identity,
        )
    elif _descriptor_identity(run_descriptor) != plan.run_dir_identity:
        raise P500ResumeError(
            f"run directory identity changed: {run_dir}"
        )
    root_lock_acquired = False
    active_token = None
    try:
        if not run_directory_lock_already_held:
            try:
                fcntl.flock(
                    run_descriptor,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                root_lock_acquired = True
            except BlockingIOError as exc:
                raise P500ResumeError(
                    f"frontend create is active for this run: {run_dir}"
                ) from exc
        _verify_real_directory_identity(run_dir, plan.run_dir_identity)
        active_token = _ACTIVE_P500_RUN.set(
            (
                os.path.abspath(os.fspath(run_dir)),
                plan.run_dir_identity,
            )
        )
        return _apply_resume_plan_locked(
            plan,
            run_descriptor=run_descriptor,
        )
    finally:
        if active_token is not None:
            _ACTIVE_P500_RUN.reset(active_token)
        if root_lock_acquired:
            fcntl.flock(run_descriptor, fcntl.LOCK_UN)
        if owns_run_descriptor:
            os.close(run_descriptor)


def prepare_p500_resume(
    *,
    repo_root: Path,
    run_dir: str | Path,
    apply: bool,
    checkpoint_id: str | None = None,
    resume_input_identity: dict[str, str] | None = None,
) -> tuple[ResumePlan, Path | None]:
    plan = build_resume_plan(
        repo_root=repo_root,
        run_dir=run_dir,
        checkpoint_id=checkpoint_id,
        resume_input_identity=resume_input_identity,
    )
    checkpoint = apply_resume_plan(plan) if apply else None
    return plan, checkpoint
