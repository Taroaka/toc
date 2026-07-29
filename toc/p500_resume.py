"""Safe pseudo-rollback helpers for resuming an existing ToC run at p500."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path
from typing import Any, Iterable

from toc.harness import append_state_snapshot, parse_state_file
from toc.run_index import classify_run_file
from toc.runtime_locks import FileLockUnavailable, sync_file_lock
from toc.stage_evaluator import check_manifest_single


class P500ResumeError(RuntimeError):
    """Raised when an existing run cannot be safely prepared for p500."""


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
    return ResumePlan(
        run_dir=str(resolved),
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


def _restore_moved_files(run_dir: Path, quarantine_root: Path, moved: list[str]) -> None:
    for rel in reversed(moved):
        quarantined = quarantine_root / rel
        original = run_dir / rel
        if not quarantined.exists():
            continue
        original.parent.mkdir(parents=True, exist_ok=True)
        quarantined.replace(original)


def _apply_resume_plan_locked(plan: ResumePlan) -> Path:
    run_dir = Path(plan.run_dir)
    checkpoint_dir = Path(plan.checkpoint_dir)
    quarantine_root = checkpoint_dir / "artifacts"
    if checkpoint_dir.exists():
        raise P500ResumeError(f"checkpoint already exists: {checkpoint_dir}")
    if (run_dir / ".toc_frontend_create.lock").exists():
        raise P500ResumeError(f"frontend create is active for this run: {run_dir}")

    moved: list[str] = []
    state_committed = False
    try:
        current = build_resume_plan(
            repo_root=run_dir.parents[1],
            run_dir=run_dir,
            checkpoint_id=plan.checkpoint_id,
            resume_input_identity=plan.resume_input_identity,
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

        checkpoint_dir.mkdir(parents=True, exist_ok=False)
        for rel in plan.downstream_files:
            source = run_dir / rel
            if not source.exists():
                raise P500ResumeError(f"planned downstream artifact disappeared: {rel}")
            destination = quarantine_root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            moved.append(rel)

        state = parse_state_file(run_dir / "state.txt")
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
        (checkpoint_dir / "checkpoint.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            append_state_snapshot(
                run_dir / "state.txt",
                _state_updates_for_reset(run_dir=run_dir, plan=plan, state=state),
            )
            state_committed = True
        except Exception:
            committed_state = parse_state_file(run_dir / "state.txt")
            state_committed = (
                committed_state.get("runtime.resume.p500.checkpoint")
                == str(checkpoint_dir.relative_to(run_dir))
                and committed_state.get("runtime.resume.p500.status") == "prepared"
            )
            raise
    except Exception:
        if not state_committed:
            _restore_moved_files(run_dir, quarantine_root, moved)
            if checkpoint_dir.exists():
                shutil.rmtree(checkpoint_dir)
        raise
    return checkpoint_dir


def apply_resume_plan(
    plan: ResumePlan,
    *,
    lock_already_held: bool = False,
) -> Path:
    run_dir = Path(plan.run_dir)
    if lock_already_held:
        return _apply_resume_plan_locked(plan)
    try:
        with sync_file_lock(
            run_dir / ".locks" / "create_resume.lock",
            wait=False,
        ):
            return _apply_resume_plan_locked(plan)
    except FileLockUnavailable as exc:
        raise P500ResumeError(
            f"another create/resume process owns this run: {run_dir}"
        ) from exc


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
