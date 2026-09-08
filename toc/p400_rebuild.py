"""Checkpointed p400 scene-authoring rebuilds.

This module deliberately does not extend :mod:`toc.p500_resume`.  A p500
resume preserves the p400 script and manifest, while this transaction creates
new p400 bytes first and only then invalidates the old downstream generation.
The public API is callback-friendly so the frontend authoring compiler can
provide candidate bytes without coupling this migration layer to provider
calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Iterable, Mapping, Sequence

from toc.harness import extract_yaml_block, now_iso, safe_load_yaml
from toc.p500_resume import (
    _ACTIVE_P500_RUN,
    _iter_downstream_files,
    _validate_no_active_bulk_jobs,
    append_state_snapshot,
    resolve_run_dir,
)
from toc.run_root_binding import bind_run_root
from toc.scene_acceptance_contract import (
    CRITERION_REGISTRY_VERSION,
    criterion_registry_digest,
    criterion_registry_payload,
    digest_contract,
    digest_scene_draft,
    domain_separated_digest,
    validate_scene_draft,
    validate_scene_set_authoring_contract,
    validate_scene_set_preflight,
)
from toc.state_store import read_current_state
from toc.runtime_locks import FileLockUnavailable, sync_file_lock
from scripts.world_walk_source import (
    PathIdentity,
    copy_regular_file_atomic_nofollow,
    directory_identity_nofollow,
    ensure_directory_relative_nofollow,
    open_directory_nofollow,
    read_regular_file_nofollow,
    sha256_regular_file_nofollow,
    unlink_regular_file_verified_nofollow,
    write_regular_file_nofollow,
)


SCHEMA_VERSION = "p400_rebuild_plan_v1"
REUSE_POLICY = "no_p500_plus_reuse_v1"
BULK_JOB_PRECONDITION = "no_queued_or_running_jobs"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]*$")
_JOURNAL_PHASE_INDEX = {
    "planned": 0,
    "checkpointing": 1,
    "checkpointed": 2,
    "published": 3,
    "state_invalidated": 4,
    "completed": 5,
    "rolled_back": 6,
}

PRESERVED_SOURCE_PATHS: tuple[str, ...] = (
    "research.md",
    "story.md",
    "visual_value.md",
)

# These are p400/derived paths.  A missing entry is represented in the plan,
# so a candidate may create it without allowing an unplanned overwrite.
P400_REPLACED_PATHS: tuple[str, ...] = (
    "script.md",
    "video_manifest.md",
    "p000_index.md",
    "run_status.json",
)

INVALIDATED_STATE_PREFIXES: tuple[str, ...] = (
    "runtime.resume.p500.",
    "slot.p5",
    "slot.p6",
    "slot.p7",
    "slot.p8",
    "slot.p9",
    "artifact.",
    "orchestration.p5",
    "orchestration.p6",
    "orchestration.p7",
    "orchestration.p8",
    "orchestration.p9",
)

REQUIRED_CANDIDATE_PATHS: tuple[str, ...] = (
    "script.md",
    "video_manifest.md",
    "logs/authoring/scene_acceptance/contract.json",
    "logs/authoring/scene_acceptance/preflight.json",
    "logs/authoring/scene_acceptance/criterion_registry.json",
)

_RESERVED_CANDIDATE_PATHS = {
    "state.txt",
    "p000_index.md",
    "run_status.json",
}

_ALLOWED_CANDIDATE_EXACT = {
    *REQUIRED_CANDIDATE_PATHS,
    "logs/authoring/scene_acceptance/source_ledger.json",
}
_ALLOWED_CANDIDATE_PATTERNS = (
    re.compile(r"^logs/authoring/scene_acceptance/scenes/[A-Za-z0-9_.+\-]+\.json$"),
    re.compile(
        r"^logs/authoring/staging/[A-Za-z0-9][A-Za-z0-9_.+\-]*/"
        r"(?:contract|preflight|criterion_registry|source_ledger)\.json$"
    ),
    re.compile(
        r"^logs/authoring/staging/[A-Za-z0-9][A-Za-z0-9_.+\-]*/"
        r"scene_drafts/[A-Za-z0-9_.+\-]+\.json$"
    ),
)


class P400RebuildError(RuntimeError):
    """Raised when a p400 rebuild cannot be safely prepared or committed."""


@dataclass(frozen=True)
class P400RebuildContext:
    """Read-only input supplied to a candidate builder."""

    run_dir: Path
    generation_id: str
    source_bytes: Mapping[str, bytes]
    source_sha256: Mapping[str, str]
    state_before: Mapping[str, str]
    previous_artifacts: Mapping[str, bytes]


@dataclass(frozen=True)
class CandidateBundle:
    """Candidate p400 artifacts produced by the scene authoring compiler."""

    artifacts: Mapping[str, bytes | str]
    preflight_status: str = "passed"
    implementation_revision: str | None = None


@dataclass(frozen=True)
class P400RebuildPlan:
    """Immutable prepare result.  ``plan_token`` covers every field."""

    schema_version: str
    run_dir: str
    run_id: str
    run_root_device: int
    run_root_inode: int
    checkpoint_id: str
    checkpoint_dir: str
    generation_id: str
    staging_dir: str
    state_before_sha256: str
    state_file_sha256: str
    source_digest: str
    preserved_sources: tuple[dict[str, Any], ...]
    replaced_artifacts: tuple[dict[str, Any], ...]
    invalidated_downstream: tuple[dict[str, Any], ...]
    reuse_policy: str
    invalidated_state_prefixes: tuple[str, ...]
    bulk_job_precondition: str
    candidate: dict[str, str]
    candidate_artifacts: tuple[dict[str, Any], ...]
    candidate_sha256: str
    implementation_revision: str
    plan_token: str

    @property
    def run_dir_identity(self) -> PathIdentity:
        return self.run_root_device, self.run_root_inode

    @property
    def candidate_digest(self) -> str:
        return self.candidate_sha256

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_dir": self.run_dir,
            "checkpoint_dir": self.checkpoint_dir,
            "staging_dir": self.staging_dir,
            "run_binding": {
                "run_id": self.run_id,
                "run_root_device": self.run_root_device,
                "run_root_inode": self.run_root_inode,
            },
            "checkpoint_id": self.checkpoint_id,
            "generation_id": self.generation_id,
            "state_before_sha256": self.state_before_sha256,
            "state_file_sha256": self.state_file_sha256,
            "preserved_sources": list(self.preserved_sources),
            "replaced_artifacts": list(self.replaced_artifacts),
            "invalidated_downstream": list(self.invalidated_downstream),
            "reuse_policy": self.reuse_policy,
            "invalidated_state_prefixes": list(self.invalidated_state_prefixes),
            "bulk_job_precondition": self.bulk_job_precondition,
            "candidate": dict(self.candidate),
            "candidate_artifacts": list(self.candidate_artifacts),
            "candidate_sha256": self.candidate_sha256,
            "implementation_revision": self.implementation_revision,
            "source_digest": self.source_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload.update(
            {
                "run_dir": self.run_dir,
                "checkpoint_dir": self.checkpoint_dir,
                "staging_dir": self.staging_dir,
                "plan_token": self.plan_token,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "P400RebuildPlan":
        if not isinstance(payload, Mapping):
            raise P400RebuildError("p400 rebuild plan must be an object")
        binding = payload.get("run_binding")
        if not isinstance(binding, Mapping):
            raise P400RebuildError("p400 rebuild plan has no run_binding")
        try:
            plan = cls(
                schema_version=str(payload["schema_version"]),
                run_dir=str(payload["run_dir"]),
                run_id=str(binding["run_id"]),
                run_root_device=int(binding["run_root_device"]),
                run_root_inode=int(binding["run_root_inode"]),
                checkpoint_id=str(payload["checkpoint_id"]),
                checkpoint_dir=str(payload["checkpoint_dir"]),
                generation_id=str(payload["generation_id"]),
                staging_dir=str(payload["staging_dir"]),
                state_before_sha256=str(payload["state_before_sha256"]),
                state_file_sha256=str(payload["state_file_sha256"]),
                source_digest=str(payload["source_digest"]),
                preserved_sources=tuple(payload["preserved_sources"]),
                replaced_artifacts=tuple(payload["replaced_artifacts"]),
                invalidated_downstream=tuple(payload["invalidated_downstream"]),
                reuse_policy=str(payload["reuse_policy"]),
                invalidated_state_prefixes=tuple(payload["invalidated_state_prefixes"]),
                bulk_job_precondition=str(payload["bulk_job_precondition"]),
                candidate=dict(payload["candidate"]),
                candidate_artifacts=tuple(payload["candidate_artifacts"]),
                candidate_sha256=str(payload["candidate_sha256"]),
                implementation_revision=str(payload["implementation_revision"]),
                plan_token=str(payload["plan_token"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise P400RebuildError("malformed p400 rebuild plan") from exc
        _validate_plan_shape(plan)
        return plan


CandidateBuilder = Callable[[P400RebuildContext], CandidateBundle | Mapping[str, bytes | str]]
BulkJobPrecondition = Callable[[Path], Any]
PublishHook = Callable[[str, int], Any]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_bytes(data: bytes, *, domain: str = "toc.p400_rebuild.bytes.v1") -> str:
    return "sha256:" + hashlib.sha256(
        domain.encode("ascii") + b"\0" + data
    ).hexdigest()


def _raw_sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _domain_digest(value: Any, domain: str = "toc.p400_rebuild.plan.v1") -> str:
    return "sha256:" + hashlib.sha256(
        domain.encode("ascii") + b"\0" + _canonical_bytes(value)
    ).hexdigest()


def _require_id(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise P400RebuildError(f"unsafe {label}: {value!r}")
    return value


def _safe_relative(value: str | Path, *, label: str = "artifact") -> str:
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} or "/" in part for part in path.parts)
    ):
        raise P400RebuildError(f"unsafe {label} path: {value}")
    return path.as_posix()


def _ensure_sha(value: str, *, label: str) -> str:
    if _DIGEST_RE.fullmatch(value) is None:
        raise P400RebuildError(f"malformed {label} digest")
    return value


def _module_revision() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    trusted_paths = (
        Path(__file__).resolve(),
        repo_root / "toc" / "scene_acceptance_contract.py",
        repo_root / "scripts" / "toc-immersive-frontend-run.py",
    )
    try:
        records = [
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": _raw_sha256(path.read_bytes()),
            }
            for path in trusted_paths
        ]
    except (OSError, ValueError) as exc:
        raise P400RebuildError("cannot fingerprint p400 rebuild implementation") from exc
    return _domain_digest(records, "toc.p400_rebuild.implementation.v1")


def _resolve(repo_root: Path, run_dir: str | Path) -> Path:
    try:
        return resolve_run_dir(repo_root, run_dir)
    except Exception as exc:
        raise P400RebuildError(str(exc)) from exc


def _identity(root: Path) -> PathIdentity:
    try:
        return directory_identity_nofollow(root)
    except Exception as exc:
        raise P400RebuildError(f"unsafe run directory: {root}") from exc


def _fingerprint(root: Path, relative: str, *, identity: PathIdentity) -> dict[str, Any]:
    rel = _safe_relative(relative)
    path = root / rel
    try:
        lexical = path.lstat()
    except FileNotFoundError:
        return {
            "path": rel,
            "exists": False,
            "lexical_type": "missing",
            "sha256": None,
        }
    if stat.S_ISLNK(lexical.st_mode):
        raise P400RebuildError(f"run artifact must not be a symlink: {rel}")
    if not stat.S_ISREG(lexical.st_mode):
        raise P400RebuildError(f"run artifact must be a regular file: {rel}")
    try:
        digest = sha256_regular_file_nofollow(
            root,
            rel,
            expected_root_identity=identity,
        )
    except Exception as exc:
        raise P400RebuildError(f"could not fingerprint {rel}") from exc
    return {
        "path": rel,
        "exists": True,
        "lexical_type": "regular_file",
        "sha256": "sha256:" + digest,
    }


def _read(root: Path, relative: str, *, identity: PathIdentity) -> bytes:
    try:
        return read_regular_file_nofollow(
            root,
            relative,
            expected_root_identity=identity,
        )
    except Exception as exc:
        raise P400RebuildError(f"could not read run artifact: {relative}") from exc


def _fingerprints_match(
    root: Path,
    expected: Iterable[Mapping[str, Any]],
    *,
    identity: PathIdentity,
    label: str,
) -> None:
    failures: list[str] = []
    for record in expected:
        rel = _safe_relative(str(record.get("path") or ""), label=label)
        actual = _fingerprint(root, rel, identity=identity)
        expected_exists = bool(record.get("exists"))
        expected_digest = record.get("sha256")
        if actual.get("exists") != expected_exists or (
            expected_exists and actual.get("sha256") != expected_digest
        ):
            failures.append(rel)
    if failures:
        raise P400RebuildError(
            f"{label} changed after prepare: " + ", ".join(failures)
        )


def _source_digest(records: Sequence[Mapping[str, Any]]) -> str:
    return _domain_digest(
        [(record["path"], record["sha256"]) for record in records],
        "toc.p400_rebuild.source.v1",
    )


def _candidate_digest(records: Sequence[Mapping[str, Any]]) -> str:
    return _domain_digest(
        [(record["path"], record["sha256"]) for record in records],
        "toc.p400_rebuild.candidate.v1",
    )


def _default_bulk_job_precondition(run_dir: Path) -> None:
    try:
        _validate_no_active_bulk_jobs(run_dir)
    except Exception as exc:
        raise P400RebuildError(str(exc)) from exc


def _call_bulk_precondition(
    hook: BulkJobPrecondition | None,
    run_dir: Path,
) -> None:
    callback = hook or _default_bulk_job_precondition
    try:
        result = callback(run_dir)
    except P400RebuildError:
        raise
    except Exception as exc:
        raise P400RebuildError("bulk job precondition failed") from exc
    if result is False:
        raise P400RebuildError("bulk job precondition failed")


def _candidate_path_allowed(relative: str) -> bool:
    return relative in _ALLOWED_CANDIDATE_EXACT or any(
        pattern.fullmatch(relative) for pattern in _ALLOWED_CANDIDATE_PATTERNS
    )


def _parse_candidate_document(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P400RebuildError(f"candidate {label} is not UTF-8") from exc
    try:
        yaml_text = extract_yaml_block(text)
    except ValueError:
        yaml_text = text
    parsed = safe_load_yaml(yaml_text)
    if not parsed:
        raise P400RebuildError(f"candidate {label} has no structured document")
    return parsed


def _candidate_json(data: bytes, *, label: str) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise P400RebuildError(
                    f"candidate {label} has duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P400RebuildError(f"candidate {label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise P400RebuildError(f"candidate {label} must be a JSON object")
    return value


def _validate_candidate_semantics(
    artifacts: Mapping[str, bytes],
    *,
    context: P400RebuildContext,
) -> None:
    script = _parse_candidate_document(artifacts["script.md"], label="script.md")
    manifest = _parse_candidate_document(
        artifacts["video_manifest.md"], label="video_manifest.md"
    )
    contract = _candidate_json(
        artifacts["logs/authoring/scene_acceptance/contract.json"],
        label="contract.json",
    )
    preflight = _candidate_json(
        artifacts["logs/authoring/scene_acceptance/preflight.json"],
        label="preflight.json",
    )
    registry = _candidate_json(
        artifacts["logs/authoring/scene_acceptance/criterion_registry.json"],
        label="criterion_registry.json",
    )
    script_contract = script.get("scene_set_authoring_contract")
    if not isinstance(script_contract, Mapping) or dict(script_contract) != contract:
        raise P400RebuildError("candidate contract.json disagrees with script.md")
    script_preflight = script.get("authoring_preflight")
    if not isinstance(script_preflight, Mapping) or dict(script_preflight) != preflight:
        raise P400RebuildError("candidate preflight.json disagrees with script.md")
    if contract.get("generation_id") != context.generation_id:
        raise P400RebuildError("candidate generation_id disagrees with rebuild plan")
    if contract.get("contract_digest") != digest_contract(contract):
        raise P400RebuildError("candidate contract digest is stale")
    if registry != {
        "schema_version": CRITERION_REGISTRY_VERSION,
        "criterion_registry_sha256": criterion_registry_digest(),
        "criteria": criterion_registry_payload(),
    }:
        raise P400RebuildError("candidate criterion registry is stale or malformed")

    source_artifacts: dict[str, bytes] = {}
    bindings = contract.get("source_bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        raise P400RebuildError("candidate source bindings are missing")
    for binding_name, raw_binding in bindings.items():
        if not isinstance(raw_binding, Mapping):
            raise P400RebuildError(f"candidate source binding is malformed: {binding_name}")
        relative = _safe_relative(
            str(raw_binding.get("path") or ""), label="source binding"
        )
        if relative in context.source_bytes:
            data = context.source_bytes[relative]
        elif relative in artifacts:
            data = artifacts[relative]
        else:
            raise P400RebuildError(
                f"candidate source binding is not preserved or staged: {relative}"
            )
        if _raw_sha256(data) != str(raw_binding.get("sha256") or ""):
            raise P400RebuildError(
                f"candidate source binding digest is stale: {binding_name}"
            )
        source_artifacts[str(binding_name)] = data

    validation = validate_scene_set_authoring_contract(
        contract,
        source_artifacts=source_artifacts,
    )
    if not validation.valid:
        raise P400RebuildError(
            "candidate scene acceptance contract is invalid: "
            + ", ".join(validation.reason_keys)
        )
    raw_scenes = script.get("scenes")
    if not isinstance(raw_scenes, list):
        raw_scenes = (
            script.get("script", {}).get("scenes")
            if isinstance(script.get("script"), Mapping)
            else None
        )
    if not isinstance(raw_scenes, list):
        raise P400RebuildError("candidate script scene list is missing")
    drafts: list[dict[str, Any]] = []
    for scene in raw_scenes:
        if not isinstance(scene, Mapping) or not isinstance(
            scene.get("scene_acceptance_draft"), Mapping
        ):
            raise P400RebuildError("candidate scene acceptance draft set is incomplete")
        draft = dict(scene["scene_acceptance_draft"])
        draft_validation = validate_scene_draft(draft, contract)
        if not draft_validation.valid:
            raise P400RebuildError(
                "candidate scene acceptance draft is invalid: "
                + ", ".join(draft_validation.reason_keys)
            )
        drafts.append(draft)
    set_validation = validate_scene_set_preflight(
        contract,
        drafts,
        source_artifacts=source_artifacts,
    )
    if not set_validation.valid:
        raise P400RebuildError(
            "candidate scene acceptance preflight is invalid: "
            + ", ".join(set_validation.reason_keys)
        )
    expected_preflight_digest = str(
        set_validation.metadata.get("preflight_digest") or ""
    )
    expected_draft_digests = [digest_scene_draft(draft) for draft in drafts]
    if (
        preflight.get("status") != "passed"
        or preflight.get("generation_id") != contract.get("generation_id")
        or preflight.get("contract_digest") != contract.get("contract_digest")
        or preflight.get("criterion_registry_digest") != criterion_registry_digest()
        or preflight.get("preflight_digest") != expected_preflight_digest
        or preflight.get("scene_draft_digests") != expected_draft_digests
        or preflight.get("source_digest")
        != domain_separated_digest(
            "toc.scene_acceptance.sources.v1",
            contract.get("source_bindings") or {},
        )
    ):
        raise P400RebuildError("candidate preflight bindings are stale")
    projection = manifest.get("scene_acceptance_contract")
    if not isinstance(projection, Mapping):
        raise P400RebuildError("candidate manifest acceptance projection is missing")
    if (
        projection.get("canonical_script_path") != "script.md"
        or projection.get("generation_id") != contract.get("generation_id")
        or projection.get("contract_digest") != contract.get("contract_digest")
        or projection.get("criterion_registry_sha256")
        != criterion_registry_digest()
        or projection.get("preflight_status") != "passed"
        or projection.get("preflight_digest") != expected_preflight_digest
        or projection.get("scene_slice_digests")
        != {
            str(draft.get("scene_id")): draft.get("scene_slice_digest")
            for draft in drafts
        }
    ):
        raise P400RebuildError("candidate manifest acceptance projection is stale")


def _normalize_candidate(
    value: CandidateBundle | Mapping[str, bytes | str],
    *,
    context: P400RebuildContext,
) -> CandidateBundle:
    if isinstance(value, CandidateBundle):
        bundle = value
    elif isinstance(value, Mapping):
        bundle = CandidateBundle(artifacts=value)
    else:
        raise P400RebuildError("candidate builder must return an artifact mapping")
    artifacts: dict[str, bytes] = {}
    for raw_path, raw_data in bundle.artifacts.items():
        rel = _safe_relative(str(raw_path), label="candidate")
        if rel in _RESERVED_CANDIDATE_PATHS or rel.startswith(".locks/"):
            raise P400RebuildError(f"candidate cannot publish reserved path: {rel}")
        if rel.startswith("logs/resume/") or rel.startswith("logs/authoring/staging/"):
            if not _candidate_path_allowed(rel):
                raise P400RebuildError(f"candidate cannot publish internal path: {rel}")
        if not _candidate_path_allowed(rel):
            raise P400RebuildError(f"candidate path is not a p400 artifact: {rel}")
        parts = Path(rel).parts
        if (
            len(parts) >= 4
            and parts[:3] == ("logs", "authoring", "staging")
            and parts[3] != context.generation_id
        ):
            raise P400RebuildError(
                f"candidate staging path uses another generation: {rel}"
            )
        if isinstance(raw_data, str):
            data = raw_data.encode("utf-8")
        elif isinstance(raw_data, bytes):
            data = raw_data
        else:
            raise P400RebuildError(f"candidate bytes are not bytes: {rel}")
        artifacts[rel] = data
    missing = sorted(set(REQUIRED_CANDIDATE_PATHS) - set(artifacts))
    if missing:
        raise P400RebuildError(
            "candidate is missing required artifacts: " + ", ".join(missing)
        )
    _validate_candidate_semantics(artifacts, context=context)
    revision = _module_revision()
    if (
        bundle.implementation_revision is not None
        and bundle.implementation_revision != revision
    ):
        raise P400RebuildError(
            "caller-declared implementation revision does not match running code"
        )
    return CandidateBundle(
        artifacts=artifacts,
        preflight_status="passed",
        implementation_revision=revision,
    )


def _invoke_builder(
    builder: CandidateBuilder,
    context: P400RebuildContext,
) -> CandidateBundle | Mapping[str, bytes | str]:
    # The documented signature is one context argument.  A small compatibility
    # allowance for keyword-only ``context`` helps callers using dataclasses or
    # dependency-injection wrappers without adding provider calls here.
    try:
        return builder(context)
    except TypeError as first_error:
        try:
            signature = inspect.signature(builder)
        except (TypeError, ValueError):
            raise P400RebuildError("candidate builder invocation failed") from first_error
        if len(signature.parameters) != 1:
            raise P400RebuildError("candidate builder must accept one context argument") from first_error
        try:
            return builder(context=context)  # type: ignore[call-arg]
        except Exception as exc:
            raise P400RebuildError("candidate builder invocation failed") from exc
    except Exception as exc:
        raise P400RebuildError("candidate builder invocation failed") from exc


def _validate_plan_shape(plan: P400RebuildPlan) -> None:
    if plan.schema_version != SCHEMA_VERSION:
        raise P400RebuildError("unsupported p400 rebuild plan schema")
    _require_id(plan.checkpoint_id, label="checkpoint id")
    _require_id(plan.generation_id, label="generation id")
    if (
        isinstance(plan.run_root_device, bool)
        or isinstance(plan.run_root_inode, bool)
        or not isinstance(plan.run_root_device, int)
        or not isinstance(plan.run_root_inode, int)
        or plan.run_root_device < 0
        or plan.run_root_inode < 0
    ):
        raise P400RebuildError("run directory identity is malformed")
    run_path = Path(plan.run_dir)
    if not run_path.is_absolute() or plan.run_id != run_path.name:
        raise P400RebuildError("run binding path is malformed")
    expected_checkpoint = run_path / "logs" / "resume" / "p400" / plan.checkpoint_id
    expected_staging = run_path / "logs" / "authoring" / "staging" / plan.generation_id
    if os.path.normpath(os.path.abspath(plan.checkpoint_dir)) != os.path.normpath(
        os.path.abspath(os.fspath(expected_checkpoint))
    ) or os.path.normpath(os.path.abspath(plan.staging_dir)) != os.path.normpath(
        os.path.abspath(os.fspath(expected_staging))
    ):
        raise P400RebuildError("p400 checkpoint/staging path is not run-bound")
    if plan.reuse_policy != REUSE_POLICY:
        raise P400RebuildError("unsupported p400 reuse policy")
    for label, value in (
        ("state_before_sha256", plan.state_before_sha256),
        ("state_file_sha256", plan.state_file_sha256),
        ("source_digest", plan.source_digest),
        ("candidate_sha256", plan.candidate_sha256),
        ("implementation_revision", plan.implementation_revision),
        ("plan_token", plan.plan_token),
    ):
        _ensure_sha(value, label=label)
    if not isinstance(plan.candidate, dict):
        raise P400RebuildError("candidate digest map is malformed")
    required_candidate_digest_keys = {
        "contract_sha256",
        "script_sha256",
        "video_manifest_sha256",
        "preflight_sha256",
        "registry_sha256",
        "contract_semantic_sha256",
        "preflight_semantic_sha256",
        "source_semantic_sha256",
        "registry_semantic_sha256",
    }
    for key, digest in plan.candidate.items():
        if not isinstance(key, str) or not key.endswith("_sha256"):
            raise P400RebuildError(f"malformed candidate digest key: {key!r}")
        _ensure_sha(digest, label=f"candidate {key}")
    if not required_candidate_digest_keys.issubset(plan.candidate):
        raise P400RebuildError("candidate digest map is incomplete")
    seen_candidate_paths: set[str] = set()
    for record in plan.candidate_artifacts:
        if not isinstance(record, Mapping):
            raise P400RebuildError("candidate artifact record is malformed")
        relative = _safe_relative(str(record.get("path") or ""), label="candidate")
        if not _candidate_path_allowed(relative):
            raise P400RebuildError(
                f"candidate artifact is not allowlisted: {relative}"
            )
        parts = Path(relative).parts
        if (
            len(parts) >= 4
            and parts[:3] == ("logs", "authoring", "staging")
            and parts[3] != plan.generation_id
        ):
            raise P400RebuildError(
                f"candidate artifact generation mismatch: {relative}"
            )
        if relative in seen_candidate_paths:
            raise P400RebuildError(f"duplicate candidate artifact: {relative}")
        seen_candidate_paths.add(relative)
        if not record.get("exists") or record.get("lexical_type") != "regular_file":
            raise P400RebuildError(f"candidate artifact is not a regular file: {relative}")
        _ensure_sha(str(record.get("sha256") or ""), label=f"candidate {relative}")
    if not set(REQUIRED_CANDIDATE_PATHS).issubset(seen_candidate_paths):
        raise P400RebuildError("candidate artifact records are incomplete")
    replace_paths: set[str] = set()
    invalidate_paths: set[str] = set()
    for label, records in (
        ("replace", plan.replaced_artifacts),
        ("invalidate", plan.invalidated_downstream),
    ):
        for record in records:
            if not isinstance(record, Mapping):
                raise P400RebuildError(f"{label} artifact record is malformed")
            relative = _safe_relative(str(record.get("path") or ""), label=label)
            if relative in replace_paths and label == "replace":
                raise P400RebuildError(f"duplicate replace artifact: {relative}")
            if label == "replace":
                replace_paths.add(relative)
            else:
                if relative in replace_paths:
                    raise P400RebuildError(
                        f"artifact is both replaced and invalidated: {relative}"
                    )
                if relative in invalidate_paths:
                    raise P400RebuildError(f"duplicate invalidated artifact: {relative}")
                invalidate_paths.add(relative)
            exists = bool(record.get("exists"))
            if exists:
                if record.get("lexical_type") != "regular_file":
                    raise P400RebuildError(f"{label} artifact is not a regular file: {relative}")
                _ensure_sha(str(record.get("sha256") or ""), label=f"{label} {relative}")
            elif record.get("sha256") is not None:
                raise P400RebuildError(f"missing {label} artifact has a digest: {relative}")


def _plan_token(payload: Mapping[str, Any]) -> str:
    return _domain_digest(payload, "toc.p400_rebuild.plan_token.v1")


def _make_plan(
    *,
    run_dir: Path,
    identity: PathIdentity,
    checkpoint_id: str,
    generation_id: str,
    state_before_sha256: str,
    state_file_sha256: str,
    source_digest: str,
    preserved_sources: Sequence[Mapping[str, Any]],
    replaced_artifacts: Sequence[Mapping[str, Any]],
    invalidated_downstream: Sequence[Mapping[str, Any]],
    candidate_artifacts: Sequence[Mapping[str, Any]],
    candidate_semantic_bindings: Mapping[str, str],
    implementation_revision: str,
) -> P400RebuildPlan:
    candidate_records = tuple(dict(record) for record in candidate_artifacts)
    candidate_sha256 = _candidate_digest(candidate_records)
    candidate_map = {
        "contract_sha256": next(
            record["sha256"]
            for record in candidate_records
            if record["path"] == "logs/authoring/scene_acceptance/contract.json"
        ),
        "script_sha256": next(
            record["sha256"] for record in candidate_records if record["path"] == "script.md"
        ),
        "video_manifest_sha256": next(
            record["sha256"]
            for record in candidate_records
            if record["path"] == "video_manifest.md"
        ),
        "preflight_sha256": next(
            record["sha256"]
            for record in candidate_records
            if record["path"] == "logs/authoring/scene_acceptance/preflight.json"
        ),
        "registry_sha256": next(
            record["sha256"]
            for record in candidate_records
            if record["path"] == "logs/authoring/scene_acceptance/criterion_registry.json"
        ),
        **dict(candidate_semantic_bindings),
    }
    # Keep the complete list as a separate field while the design's compact
    # candidate map retains the five named digests used by integration code.
    checkpoint_dir = run_dir / "logs" / "resume" / "p400" / checkpoint_id
    staging_dir = run_dir / "logs" / "authoring" / "staging" / generation_id
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_dir": str(run_dir),
        "checkpoint_dir": str(checkpoint_dir),
        "staging_dir": str(staging_dir),
        "run_binding": {
            "run_id": run_dir.name,
            "run_root_device": identity[0],
            "run_root_inode": identity[1],
        },
        "checkpoint_id": checkpoint_id,
        "generation_id": generation_id,
        "state_before_sha256": state_before_sha256,
        "state_file_sha256": state_file_sha256,
        "preserved_sources": list(preserved_sources),
        "replaced_artifacts": list(replaced_artifacts),
        "invalidated_downstream": list(invalidated_downstream),
        "reuse_policy": REUSE_POLICY,
        "invalidated_state_prefixes": list(INVALIDATED_STATE_PREFIXES),
        "bulk_job_precondition": BULK_JOB_PRECONDITION,
        "candidate": candidate_map,
        "candidate_artifacts": list(candidate_records),
        "candidate_sha256": candidate_sha256,
        "implementation_revision": implementation_revision,
        "source_digest": source_digest,
    }
    plan_token = _plan_token(payload)
    plan = P400RebuildPlan(
        schema_version=SCHEMA_VERSION,
        run_dir=str(run_dir),
        run_id=run_dir.name,
        run_root_device=identity[0],
        run_root_inode=identity[1],
        checkpoint_id=checkpoint_id,
        checkpoint_dir=str(checkpoint_dir),
        generation_id=generation_id,
        staging_dir=str(staging_dir),
        state_before_sha256=state_before_sha256,
        state_file_sha256=state_file_sha256,
        source_digest=source_digest,
        preserved_sources=tuple(dict(record) for record in preserved_sources),
        replaced_artifacts=tuple(dict(record) for record in replaced_artifacts),
        invalidated_downstream=tuple(dict(record) for record in invalidated_downstream),
        reuse_policy=REUSE_POLICY,
        invalidated_state_prefixes=INVALIDATED_STATE_PREFIXES,
        bulk_job_precondition=BULK_JOB_PRECONDITION,
        candidate=candidate_map,
        candidate_artifacts=candidate_records,
        candidate_sha256=candidate_sha256,
        implementation_revision=implementation_revision,
        plan_token=plan_token,
    )
    _validate_plan_shape(plan)
    return plan


def _write_bytes(root: Path, relative: str, data: bytes, *, identity: PathIdentity, exclusive: bool = False) -> None:
    try:
        write_regular_file_nofollow(
            destination_root=root,
            destination_relative=relative,
            data=data,
            expected_destination_root_identity=identity,
            exclusive=exclusive,
        )
    except Exception as exc:
        raise P400RebuildError(f"could not write {relative}") from exc


def _read_json(root: Path, relative: str, *, identity: PathIdentity) -> dict[str, Any]:
    try:
        data = _read(root, relative, identity=identity)
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P400RebuildError(f"invalid JSON artifact: {relative}") from exc
    if not isinstance(value, dict):
        raise P400RebuildError(f"JSON artifact must be an object: {relative}")
    return value


def _journal_payload(plan: P400RebuildPlan, phase: str, **extra: Any) -> dict[str, Any]:
    if phase not in _JOURNAL_PHASE_INDEX:
        raise P400RebuildError(f"unsupported p400 journal phase: {phase}")
    return {
        "schema_version": "p400_rebuild_journal_v1",
        "run_id": plan.run_id,
        "generation_id": plan.generation_id,
        "checkpoint_id": plan.checkpoint_id,
        "plan_token": plan.plan_token,
        "phase": phase,
        "phase_index": _JOURNAL_PHASE_INDEX[phase],
        "updated_at": now_iso(),
        **extra,
    }


def _write_journal(root: Path, relative: str, payload: Mapping[str, Any], *, identity: PathIdentity) -> None:
    _write_bytes(
        root,
        relative,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        identity=identity,
    )


def _plan_state_updates(
    plan: P400RebuildPlan,
    *,
    status: str,
    state: Mapping[str, str] | None = None,
) -> dict[str, str]:
    updates: dict[str, str] = {
        "status": "P400" if status == "completed" else "P400_REBUILD",
        "runtime.stage": "p400_rebuild",
        "runtime.stage_target": "p400",
        "runtime.resume.p400.status": status,
        "runtime.resume.p400.checkpoint": f"logs/resume/p400/{plan.checkpoint_id}",
        "runtime.resume.p400.generation_id": plan.generation_id,
        "runtime.resume.p400.plan_token": plan.plan_token,
        "runtime.resume.p500.status": "invalidated",
        "runtime.resume.p500.checkpoint": "",
        "runtime.resume.p500.stop_target": "",
        "authoring.scene_set.preflight.status": (
            "passed" if status == "completed" else status
        ),
        "authoring.scene_set.generation_id": plan.generation_id,
        "authoring.scene_set.contract.status": (
            "validated" if status == "completed" else status
        ),
        "authoring.scene_set.contract.digest": plan.candidate.get(
            "contract_semantic_sha256", ""
        ),
        "authoring.scene_set.preflight.digest": plan.candidate.get(
            "preflight_semantic_sha256", ""
        ),
        "authoring.scene_set.preflight.source_digest": plan.candidate.get(
            "source_semantic_sha256", ""
        ),
        "authoring.scene_set.preflight.criterion_registry_digest": plan.candidate.get(
            "registry_semantic_sha256", ""
        ),
        "image_generation.status": "not_started",
        "video_generation.status": "not_started",
        "last_error": "" if status == "completed" else f"p400 rebuild {status}",
    }
    for slot_number in range(410, 950, 10):
        updates[f"slot.p{slot_number}.status"] = "pending"
        updates[f"slot.p{slot_number}.note"] = "invalidated for p400 rebuild"
    if state is not None:
        for key in state:
            slot_match = re.match(r"^slot\.p(\d{3})\.", key)
            invalidate = any(key.startswith(prefix) for prefix in INVALIDATED_STATE_PREFIXES)
            if slot_match and int(slot_match.group(1)) >= 410:
                invalidate = True
            if not invalidate:
                continue
            if key.startswith("artifact."):
                updates[key] = ""
            elif key.startswith("slot.") and key.endswith(".status"):
                updates[key] = "pending"
            elif key.endswith(".status"):
                updates[key] = "invalidated"
            elif key.endswith(".current_round") or key.endswith(".attempt") or key.endswith(".error_count"):
                updates[key] = "0"
            else:
                updates[key] = ""
    if status == "rollback":
        updates["authoring.scene_set.contract.status"] = "invalidated"
        updates["authoring.scene_set.preflight.status"] = "invalidated"
    return updates


def _append_state(root: Path, identity: PathIdentity, updates: Mapping[str, str]) -> None:
    descriptor = open_directory_nofollow(root, expected_identity=identity)
    token = _ACTIVE_P500_RUN.set(
        (os.path.abspath(os.fspath(root)), identity, descriptor)
    )
    try:
        append_state_snapshot(root / "state.txt", dict(updates))
    except Exception as exc:
        raise P400RebuildError("could not append p400 rebuild state") from exc
    finally:
        _ACTIVE_P500_RUN.reset(token)
        os.close(descriptor)


def _read_state(root: Path, identity: PathIdentity) -> dict[str, str]:
    descriptor = open_directory_nofollow(root, expected_identity=identity)
    try:
        with bind_run_root(
            root,
            expected_identity=identity,
            descriptor=descriptor,
        ):
            return dict(read_current_state(root / "state.txt").state)
    finally:
        os.close(descriptor)


def prepare_p400_rebuild(
    *,
    repo_root: Path,
    run_dir: str | Path,
    candidate_builder: CandidateBuilder,
    checkpoint_id: str | None = None,
    generation_id: str | None = None,
    bulk_job_precondition: BulkJobPrecondition | None = None,
) -> P400RebuildPlan:
    """Build and stage a p400 candidate without changing canonical artifacts."""

    resolved = _resolve(repo_root, run_dir)
    identity = _identity(resolved)
    checkpoint = _require_id(
        checkpoint_id or datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z"),
        label="checkpoint id",
    )
    generation = _require_id(
        generation_id or f"p400-{datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%f%z')}",
        label="generation id",
    )
    _call_bulk_precondition(bulk_job_precondition, resolved)
    source_bytes = {
        relative: _read(resolved, relative, identity=identity)
        for relative in PRESERVED_SOURCE_PATHS
    }
    source_records = tuple(
        {
            "path": relative,
            "exists": True,
            "lexical_type": "regular_file",
            "sha256": _raw_sha256(source_bytes[relative]),
        }
        for relative in PRESERVED_SOURCE_PATHS
    )
    state_record = _fingerprint(resolved, "state.txt", identity=identity)
    if not state_record["exists"]:
        raise P400RebuildError("state.txt is required for p400 rebuild")
    state_before = _read_state(resolved, identity)
    previous: dict[str, bytes] = {}
    for relative in ("script.md", "video_manifest.md"):
        record = _fingerprint(resolved, relative, identity=identity)
        if record["exists"]:
            previous[relative] = _read(resolved, relative, identity=identity)
    context = P400RebuildContext(
        run_dir=resolved,
        generation_id=generation,
        source_bytes=source_bytes,
        source_sha256={record["path"]: record["sha256"] for record in source_records},
        state_before=dict(state_before),
        previous_artifacts=previous,
    )
    bundle = _normalize_candidate(
        _invoke_builder(candidate_builder, context),
        context=context,
    )
    candidate_paths = tuple(sorted(bundle.artifacts))
    # Inventory is intentionally captured before staging so p500+ selectors,
    # requests and media cannot silently survive this v1 migration.
    try:
        downstream_paths = tuple(sorted(set(_iter_downstream_files(resolved))))
    except Exception as exc:
        raise P400RebuildError(str(exc)) from exc
    replaced_paths = tuple(
        sorted(set(P400_REPLACED_PATHS).union(candidate_paths))
    )
    replaced_set = set(replaced_paths)
    invalidated_paths = tuple(
        relative
        for relative in downstream_paths
        if relative not in replaced_set
    )
    replaced_records = tuple(
        _fingerprint(resolved, relative, identity=identity)
        for relative in replaced_paths
    )
    invalidated_records = tuple(
        _fingerprint(resolved, relative, identity=identity)
        for relative in invalidated_paths
    )
    source_digest = _source_digest(source_records)
    candidate_records = tuple(
        {
            "path": relative,
            "exists": True,
            "lexical_type": "regular_file",
            "sha256": _raw_sha256(bundle.artifacts[relative]),
        }
        for relative in candidate_paths
    )
    plan = _make_plan(
        run_dir=resolved,
        identity=identity,
        checkpoint_id=checkpoint,
        generation_id=generation,
        state_before_sha256=_domain_digest(state_before, "toc.p400_rebuild.state.v1"),
        state_file_sha256=str(state_record["sha256"]),
        source_digest=source_digest,
        preserved_sources=source_records,
        replaced_artifacts=replaced_records,
        invalidated_downstream=invalidated_records,
        candidate_artifacts=candidate_records,
        candidate_semantic_bindings={
            "contract_semantic_sha256": str(
                _candidate_json(
                    bundle.artifacts[
                        "logs/authoring/scene_acceptance/contract.json"
                    ],
                    label="contract.json",
                ).get("contract_digest")
                or ""
            ),
            "preflight_semantic_sha256": str(
                _candidate_json(
                    bundle.artifacts[
                        "logs/authoring/scene_acceptance/preflight.json"
                    ],
                    label="preflight.json",
                ).get("preflight_digest")
                or ""
            ),
            "source_semantic_sha256": str(
                _candidate_json(
                    bundle.artifacts[
                        "logs/authoring/scene_acceptance/preflight.json"
                    ],
                    label="preflight.json",
                ).get("source_digest")
                or ""
            ),
            "registry_semantic_sha256": str(
                _candidate_json(
                    bundle.artifacts[
                        "logs/authoring/scene_acceptance/preflight.json"
                    ],
                    label="preflight.json",
                ).get("criterion_registry_digest")
                or ""
            ),
        },
        implementation_revision=str(bundle.implementation_revision),
    )
    staging = resolved / "logs" / "authoring" / "staging" / generation
    if staging.exists() or staging.is_symlink():
        raise P400RebuildError(f"staging generation already exists: {staging}")
    try:
        ensure_directory_relative_nofollow(
            resolved,
            staging.relative_to(resolved),
            expected_root_identity=identity,
        )
        staging_identity = _identity(staging)
        for relative in candidate_paths:
            _write_bytes(
                staging,
                relative,
                bundle.artifacts[relative],
                identity=staging_identity,
                exclusive=True,
            )
        _write_journal(
            staging,
            "publish.journal.json",
            _journal_payload(plan, "planned"),
            identity=staging_identity,
        )
        _write_bytes(
            staging,
            "plan.json",
            (json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            identity=staging_identity,
            exclusive=True,
        )
    except Exception:
        # Staging is isolated from active artifacts.  Leave it for diagnosis;
        # no canonical path was touched and apply cannot consume an incomplete
        # plan because plan.json is written last.
        raise
    _identity(resolved)
    return plan


def _verify_candidate_staging(plan: P400RebuildPlan) -> dict[str, bytes]:
    staging = Path(plan.staging_dir)
    if not staging.is_dir() or staging.is_symlink():
        raise P400RebuildError("prepared p400 staging directory is unavailable")
    staging_identity = _identity(staging)
    artifacts: dict[str, bytes] = {}
    expected_records = {str(record["path"]): record for record in plan.candidate_artifacts}
    for relative, record in expected_records.items():
        actual = _fingerprint(staging, relative, identity=staging_identity)
        if not actual["exists"] or actual["sha256"] != record["sha256"]:
            raise P400RebuildError(f"candidate bytes changed after prepare: {relative}")
        artifacts[relative] = _read(staging, relative, identity=staging_identity)
    return artifacts


def _verify_active_candidate(plan: P400RebuildPlan, *, identity: PathIdentity) -> None:
    run_dir = Path(plan.run_dir)
    for record in plan.candidate_artifacts:
        relative = str(record["path"])
        actual = _fingerprint(run_dir, relative, identity=identity)
        if not actual.get("exists") or actual.get("sha256") != record.get("sha256"):
            raise P400RebuildError(
                f"active candidate is missing or changed: {relative}"
            )


def _read_active_candidate(
    plan: P400RebuildPlan,
    *,
    identity: PathIdentity,
) -> dict[str, bytes]:
    _verify_active_candidate(plan, identity=identity)
    return {
        str(record["path"]): _read(
            Path(plan.run_dir),
            str(record["path"]),
            identity=identity,
        )
        for record in plan.candidate_artifacts
    }


def _candidate_context_for_plan(
    plan: P400RebuildPlan,
    *,
    identity: PathIdentity,
    state: Mapping[str, str],
) -> P400RebuildContext:
    run_dir = Path(plan.run_dir)
    source_bytes = {
        str(record["path"]): _read(
            run_dir,
            str(record["path"]),
            identity=identity,
        )
        for record in plan.preserved_sources
        if record.get("exists")
    }
    return P400RebuildContext(
        run_dir=run_dir,
        generation_id=plan.generation_id,
        source_bytes=source_bytes,
        source_sha256={
            str(record["path"]): str(record.get("sha256") or "")
            for record in plan.preserved_sources
        },
        state_before=dict(state),
        previous_artifacts={},
    )


def _verify_post_invalidation_state(
    plan: P400RebuildPlan,
    *,
    identity: PathIdentity,
) -> None:
    _verify_active_candidate(plan, identity=identity)
    candidate_paths = {str(record["path"]) for record in plan.candidate_artifacts}
    for record in (*plan.replaced_artifacts, *plan.invalidated_downstream):
        relative = str(record["path"])
        if relative in candidate_paths or not record.get("exists"):
            continue
        if _fingerprint(Path(plan.run_dir), relative, identity=identity).get("exists"):
            raise P400RebuildError(
                f"invalidated artifact is still active: {relative}"
            )


def _validate_checkpoint_journal(
    plan: P400RebuildPlan,
    journal: Mapping[str, Any],
) -> str:
    if plan.plan_token != _plan_current_token(plan):
        raise P400RebuildError("checkpoint p400 plan token is invalid")
    expected = {
        "schema_version": "p400_rebuild_journal_v1",
        "run_id": plan.run_id,
        "generation_id": plan.generation_id,
        "checkpoint_id": plan.checkpoint_id,
        "plan_token": plan.plan_token,
    }
    if any(journal.get(key) != value for key, value in expected.items()):
        raise P400RebuildError("checkpoint journal binding is invalid")
    phase = str(journal.get("phase") or "")
    if (
        phase not in _JOURNAL_PHASE_INDEX
        or journal.get("phase_index") != _JOURNAL_PHASE_INDEX[phase]
    ):
        raise P400RebuildError("checkpoint journal phase is invalid")
    return phase


def _copy_to_checkpoint(
    run_dir: Path,
    checkpoint: Path,
    record: Mapping[str, Any],
    *,
    run_identity: PathIdentity,
    checkpoint_identity: PathIdentity,
) -> None:
    if not record.get("exists"):
        return
    relative = _safe_relative(str(record["path"]))
    digest = str(record["sha256"])
    if not _DIGEST_RE.fullmatch(digest):
        raise P400RebuildError(f"malformed checkpoint source digest: {relative}")
    try:
        copy_regular_file_atomic_nofollow(
            source_root=run_dir,
            source_relative=relative,
            destination_root=checkpoint,
            destination_relative=f"artifacts/{relative}",
            expected_source_root_identity=run_identity,
            expected_destination_root_identity=checkpoint_identity,
            expected_sha256=digest.removeprefix("sha256:"),
        )
    except Exception as exc:
        raise P400RebuildError(f"could not checkpoint {relative}") from exc


def _checkpoint_metadata(plan: P400RebuildPlan, *, phase: str) -> dict[str, Any]:
    return {
        **plan.to_dict(),
        "phase": phase,
        "created_at": now_iso(),
        "state_before": {},
    }


def _write_checkpoint_metadata(
    checkpoint: Path,
    plan: P400RebuildPlan,
    phase: str,
    *,
    checkpoint_identity: PathIdentity,
    state_before: Mapping[str, str] | None = None,
) -> None:
    payload = _checkpoint_metadata(plan, phase=phase)
    if state_before is not None:
        payload["state_before"] = dict(state_before)
    _write_bytes(
        checkpoint,
        "checkpoint.json",
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        identity=checkpoint_identity,
    )


def _restore_record(
    run_dir: Path,
    checkpoint: Path,
    record: Mapping[str, Any],
    *,
    run_identity: PathIdentity,
    checkpoint_identity: PathIdentity,
    allowed_current_sha256: set[str] | None = None,
) -> None:
    relative = _safe_relative(str(record["path"]))
    if record.get("exists"):
        current = _fingerprint(run_dir, relative, identity=run_identity)
        allowed = {str(record["sha256"])}
        if allowed_current_sha256:
            allowed.update(allowed_current_sha256)
        if (
            current.get("exists")
            and "*" not in allowed
            and current.get("sha256") not in allowed
        ):
            raise P400RebuildError(f"rollback active artifact changed: {relative}")
        checkpoint_relative = f"artifacts/{relative}"
        data = _read(checkpoint, checkpoint_relative, identity=checkpoint_identity)
        if _raw_sha256(data) != record.get("sha256"):
            raise P400RebuildError(f"checkpoint bytes changed: {relative}")
        _write_bytes(run_dir, relative, data, identity=run_identity)
        return
    current = _fingerprint(run_dir, relative, identity=run_identity)
    if not current["exists"]:
        return
    # A path absent before prepare may only be removed when it still contains
    # the exact candidate bytes we published.
    raise P400RebuildError(f"rollback found an unexpected active artifact: {relative}")


def _remove_if_candidate(
    run_dir: Path,
    relative: str,
    candidate_digest: str,
    *,
    identity: PathIdentity,
) -> None:
    current = _fingerprint(run_dir, relative, identity=identity)
    if not current["exists"]:
        return
    if current["sha256"] != candidate_digest:
        raise P400RebuildError(f"rollback active artifact changed: {relative}")
    try:
        if not unlink_regular_file_verified_nofollow(
            root=run_dir,
            relative_path=relative,
            expected_root_identity=identity,
            expected_sha256=candidate_digest.removeprefix("sha256:"),
        ):
            raise P400RebuildError(f"could not remove candidate artifact: {relative}")
    except P400RebuildError:
        raise
    except Exception as exc:
        raise P400RebuildError(f"could not remove candidate artifact: {relative}") from exc


def _rollback_locked(
    plan: P400RebuildPlan,
    *,
    run_identity: PathIdentity,
    checkpoint_identity: PathIdentity,
    checkpoint: Path,
) -> None:
    # Restore all paths that had bytes before prepare.  Candidate paths that
    # were absent are removed only after exact-byte verification.
    candidate_by_path = {
        str(record["path"]): str(record["sha256"])
        for record in plan.candidate_artifacts
    }
    for record in reversed(plan.replaced_artifacts):
        relative = str(record["path"])
        if record.get("exists"):
            _restore_record(
                Path(plan.run_dir),
                checkpoint,
                record,
                run_identity=run_identity,
                checkpoint_identity=checkpoint_identity,
                allowed_current_sha256=(
                    {candidate_by_path[relative]}
                    if relative in candidate_by_path
                    else {"*"}
                    if relative in {"p000_index.md", "run_status.json"}
                    else None
                ),
            )
        elif relative in candidate_by_path:
            _remove_if_candidate(
                Path(plan.run_dir),
                relative,
                candidate_by_path[relative],
                identity=run_identity,
            )
    for record in plan.invalidated_downstream:
        if record.get("exists"):
            _restore_record(
                Path(plan.run_dir),
                checkpoint,
                record,
                run_identity=run_identity,
                checkpoint_identity=checkpoint_identity,
                allowed_current_sha256=None,
            )
    run_root = Path(plan.run_dir)
    current_state = _read_state(run_root, run_identity)
    _append_state(
        run_root,
        run_identity,
        _plan_state_updates(plan, status="rollback", state=current_state),
    )
    _write_journal(
        checkpoint,
        "publish.journal.json",
        _journal_payload(plan, "rolled_back"),
        identity=checkpoint_identity,
    )


@contextmanager
def _run_transaction_lock(run_dir: Path, identity: PathIdentity):
    pinned = open_directory_nofollow(run_dir, expected_identity=identity)
    root_locked = False
    try:
        try:
            with sync_file_lock(
                run_dir / ".locks" / "create_resume.lock",
                wait=False,
                run_root_descriptor=pinned,
                expected_run_root_identity=identity,
            ):
                try:
                    fcntl.flock(pinned, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    root_locked = True
                except BlockingIOError as exc:
                    raise P400RebuildError("frontend create/resume is active for this run") from exc
                yield pinned
                if root_locked:
                    fcntl.flock(pinned, fcntl.LOCK_UN)
                    root_locked = False
        except FileLockUnavailable as exc:
            raise P400RebuildError("another create/resume process owns this run") from exc
    finally:
        if root_locked:
            fcntl.flock(pinned, fcntl.LOCK_UN)
        os.close(pinned)


def _plan_current_token(plan: P400RebuildPlan) -> str:
    payload = plan._payload()
    return _plan_token(payload)


def apply_p400_rebuild(
    plan: P400RebuildPlan,
    *,
    plan_token: str,
    bulk_job_precondition: BulkJobPrecondition | None = None,
    publish_hook: PublishHook | None = None,
) -> Path:
    """Publish prepare-time bytes under lock; never invoke the builder."""

    if not isinstance(plan, P400RebuildPlan):
        raise P400RebuildError("apply requires a P400RebuildPlan")
    _validate_plan_shape(plan)
    if plan_token != plan.plan_token or plan_token != _plan_current_token(plan):
        raise P400RebuildError("p400 rebuild plan token is stale or invalid")
    if plan.implementation_revision != _module_revision():
        raise P400RebuildError("p400 rebuild implementation changed after prepare")
    run_dir = Path(plan.run_dir)
    identity = _identity(run_dir)
    if identity != plan.run_dir_identity:
        raise P400RebuildError("run directory identity changed")
    checkpoint = Path(plan.checkpoint_dir)
    staging = Path(plan.staging_dir)
    if checkpoint.exists() or checkpoint.is_symlink():
        raise P400RebuildError("p400 rebuild checkpoint is already consumed")
    if not staging.is_dir() or staging.is_symlink():
        raise P400RebuildError("p400 rebuild staging is unavailable")
    with _run_transaction_lock(run_dir, identity):
        if checkpoint.exists() or checkpoint.is_symlink():
            raise P400RebuildError("p400 rebuild checkpoint is already consumed")
        try:
            _call_bulk_precondition(bulk_job_precondition, run_dir)
            if _identity(run_dir) != identity:
                raise P400RebuildError("run directory identity changed under lock")
            _fingerprints_match(
                run_dir,
                plan.preserved_sources,
                identity=identity,
                label="preserved source",
            )
            state = _read_state(run_dir, identity)
            if _domain_digest(state, "toc.p400_rebuild.state.v1") != plan.state_before_sha256:
                raise P400RebuildError("state mapping changed after prepare")
            if _fingerprint(run_dir, "state.txt", identity=identity)["sha256"] != plan.state_file_sha256:
                raise P400RebuildError("state.txt bytes changed after prepare")
            _fingerprints_match(
                run_dir,
                plan.replaced_artifacts,
                identity=identity,
                label="replace target",
            )
            _fingerprints_match(
                run_dir,
                plan.invalidated_downstream,
                identity=identity,
                label="invalidated artifact",
            )
            candidate = _verify_candidate_staging(plan)
            _validate_candidate_semantics(
                candidate,
                context=_candidate_context_for_plan(
                    plan,
                    identity=identity,
                    state=state,
                ),
            )
            ensure_directory_relative_nofollow(
                run_dir,
                checkpoint.relative_to(run_dir),
                expected_root_identity=identity,
            )
            checkpoint_identity = _identity(checkpoint)
            ensure_directory_relative_nofollow(
                checkpoint,
                "artifacts",
                expected_root_identity=checkpoint_identity,
            )
            checkpoint_identity = _identity(checkpoint)
            _write_checkpoint_metadata(
                checkpoint,
                plan,
                "checkpointing",
                checkpoint_identity=checkpoint_identity,
                state_before=state,
            )
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "checkpointing"),
                identity=checkpoint_identity,
            )
            for record in (*plan.replaced_artifacts, *plan.invalidated_downstream):
                _copy_to_checkpoint(
                    run_dir,
                    checkpoint,
                    record,
                    run_identity=identity,
                    checkpoint_identity=checkpoint_identity,
                )
            _write_checkpoint_metadata(
                checkpoint,
                plan,
                "checkpointed",
                checkpoint_identity=checkpoint_identity,
                state_before=state,
            )
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "checkpointed"),
                identity=checkpoint_identity,
            )
            published: list[str] = []
            for index, relative in enumerate(sorted(candidate)):
                _write_bytes(run_dir, relative, candidate[relative], identity=identity)
                published.append(relative)
                if publish_hook is not None:
                    try:
                        publish_hook(relative, index)
                    except Exception as exc:
                        raise P400RebuildError("p400 candidate publish hook failed") from exc
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "published", published=published),
                identity=checkpoint_identity,
            )
            candidate_paths = set(candidate)
            for record in plan.replaced_artifacts:
                relative = str(record["path"])
                if relative in candidate_paths or not record.get("exists"):
                    continue
                if not unlink_regular_file_verified_nofollow(
                    root=run_dir,
                    relative_path=relative,
                    expected_root_identity=identity,
                    expected_sha256=str(record["sha256"]).removeprefix("sha256:"),
                ):
                    raise P400RebuildError(f"could not remove stale p400 artifact: {relative}")
            for record in plan.invalidated_downstream:
                if not record.get("exists"):
                    continue
                relative = str(record["path"])
                if not unlink_regular_file_verified_nofollow(
                    root=run_dir,
                    relative_path=relative,
                    expected_root_identity=identity,
                    expected_sha256=str(record["sha256"]).removeprefix("sha256:"),
                ):
                    raise P400RebuildError(f"could not invalidate downstream artifact: {relative}")
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "state_invalidated"),
                identity=checkpoint_identity,
            )
            _verify_post_invalidation_state(plan, identity=identity)
            _append_state(
                run_dir,
                identity,
                _plan_state_updates(plan, status="completed", state=state),
            )
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "completed"),
                identity=checkpoint_identity,
            )
            _write_checkpoint_metadata(
                checkpoint,
                plan,
                "completed",
                checkpoint_identity=checkpoint_identity,
                state_before=state,
            )
            return checkpoint
        except Exception as exc:
            if checkpoint.is_dir() and not checkpoint.is_symlink():
                try:
                    checkpoint_identity = _identity(checkpoint)
                    journal = _read_json(
                        checkpoint,
                        "publish.journal.json",
                        identity=checkpoint_identity,
                    )
                    phase = str(journal.get("phase") or "")
                    if phase == "checkpointing":
                        _write_journal(
                            checkpoint,
                            "publish.journal.json",
                            _journal_payload(plan, "rolled_back"),
                            identity=checkpoint_identity,
                        )
                    elif phase not in {"rolled_back", "completed"}:
                        _rollback_locked(
                            plan,
                            run_identity=identity,
                            checkpoint_identity=checkpoint_identity,
                            checkpoint=checkpoint,
                        )
                except Exception as rollback_error:
                    raise P400RebuildError(
                        f"p400 rebuild failed and rollback failed: {rollback_error}"
                    ) from exc
            if isinstance(exc, P400RebuildError):
                raise
            raise P400RebuildError("p400 rebuild failed") from exc


def _load_checkpoint_plan(checkpoint: Path) -> tuple[P400RebuildPlan, dict[str, Any]]:
    identity = _identity(checkpoint)
    metadata = _read_json(checkpoint, "checkpoint.json", identity=identity)
    plan = P400RebuildPlan.from_dict(metadata)
    if Path(plan.checkpoint_dir).resolve() != checkpoint.resolve():
        raise P400RebuildError("checkpoint plan path mismatch")
    if plan.plan_token != _plan_current_token(plan):
        raise P400RebuildError("checkpoint p400 plan token is invalid")
    return plan, metadata


def recover_p400_rebuild(
    run_dir: str | Path,
    checkpoint_id: str,
    *,
    action: str = "rollback",
    bulk_job_precondition: BulkJobPrecondition | None = None,
) -> Path:
    """Complete or rollback a checkpoint journal after a process crash."""

    if action not in {"rollback", "complete"}:
        raise P400RebuildError("recovery action must be rollback or complete")
    root = Path(run_dir)
    identity = _identity(root)
    _require_id(checkpoint_id, label="checkpoint id")
    checkpoint = root / "logs" / "resume" / "p400" / checkpoint_id
    if not checkpoint.is_dir() or checkpoint.is_symlink():
        raise P400RebuildError("p400 rebuild checkpoint is unavailable")
    with _run_transaction_lock(root, identity):
        _call_bulk_precondition(bulk_job_precondition, root)
        plan, metadata = _load_checkpoint_plan(checkpoint)
        if (
            _identity(root) != plan.run_dir_identity
            or Path(plan.run_dir).resolve() != root.resolve()
            or plan.run_id != root.name
            or plan.checkpoint_id != checkpoint_id
        ):
            raise P400RebuildError("run directory identity changed")
        checkpoint_identity = _identity(checkpoint)
        journal = _read_json(checkpoint, "publish.journal.json", identity=checkpoint_identity)
        phase = _validate_checkpoint_journal(plan, journal)
        if action == "complete" and plan.implementation_revision != _module_revision():
            raise P400RebuildError(
                "p400 rebuild implementation changed before recovery completion"
            )
        if phase == "completed":
            if action == "rollback":
                raise P400RebuildError("completed p400 rebuild is single-use")
            active_candidate = _read_active_candidate(plan, identity=identity)
            _validate_candidate_semantics(
                active_candidate,
                context=_candidate_context_for_plan(
                    plan,
                    identity=identity,
                    state=_read_state(root, identity),
                ),
            )
            _verify_post_invalidation_state(plan, identity=identity)
            return checkpoint
        if phase == "rolled_back":
            if action == "complete":
                raise P400RebuildError("rolled-back p400 rebuild cannot be completed")
            return checkpoint
        if phase == "checkpointing":
            if action == "complete":
                raise P400RebuildError(
                    "incomplete p400 checkpoint must be rolled back"
                )
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "rolled_back"),
                identity=checkpoint_identity,
            )
            return checkpoint
        if action == "rollback":
            _rollback_locked(
                plan,
                run_identity=identity,
                checkpoint_identity=checkpoint_identity,
                checkpoint=checkpoint,
            )
            return checkpoint
        if phase not in {"checkpointed", "published", "state_invalidated"}:
            raise P400RebuildError(f"cannot complete journal in phase: {phase}")
        if phase == "checkpointed":
            candidate = _verify_candidate_staging(plan)
            _validate_candidate_semantics(
                candidate,
                context=_candidate_context_for_plan(
                    plan,
                    identity=identity,
                    state=_read_state(root, identity),
                ),
            )
            for relative in sorted(candidate):
                _write_bytes(root, relative, candidate[relative], identity=identity)
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "published"),
                identity=checkpoint_identity,
            )
            _verify_active_candidate(plan, identity=identity)
        elif phase in {"published", "state_invalidated"}:
            active_candidate = _read_active_candidate(plan, identity=identity)
            _validate_candidate_semantics(
                active_candidate,
                context=_candidate_context_for_plan(
                    plan,
                    identity=identity,
                    state=_read_state(root, identity),
                ),
            )
        if phase in {"checkpointed", "published"}:
            for record in plan.replaced_artifacts:
                relative = str(record["path"])
                if relative in {str(item["path"]) for item in plan.candidate_artifacts} or not record.get("exists"):
                    continue
                unlink_regular_file_verified_nofollow(
                    root=root,
                    relative_path=relative,
                    expected_root_identity=identity,
                    expected_sha256=str(record["sha256"]).removeprefix("sha256:"),
                )
            for record in plan.invalidated_downstream:
                if record.get("exists"):
                    unlink_regular_file_verified_nofollow(
                        root=root,
                        relative_path=str(record["path"]),
                        expected_root_identity=identity,
                        expected_sha256=str(record["sha256"]).removeprefix("sha256:"),
                    )
            _write_journal(
                checkpoint,
                "publish.journal.json",
                _journal_payload(plan, "state_invalidated"),
                identity=checkpoint_identity,
            )
        _verify_post_invalidation_state(plan, identity=identity)
        current_state = _read_state(root, identity)
        _append_state(
            root,
            identity,
            _plan_state_updates(plan, status="completed", state=current_state),
        )
        _write_journal(
            checkpoint,
            "publish.journal.json",
            _journal_payload(plan, "completed"),
            identity=checkpoint_identity,
        )
        _write_checkpoint_metadata(
            checkpoint,
            plan,
            "completed",
            checkpoint_identity=checkpoint_identity,
        )
        return checkpoint


def load_p400_rebuild_plan(run_dir: str | Path, generation_id: str) -> P400RebuildPlan:
    """Load a prepare-time plan from staging for a CLI apply."""

    root = Path(run_dir)
    identity = _identity(root)
    _require_id(generation_id, label="generation id")
    staging = root / "logs" / "authoring" / "staging" / generation_id
    if not staging.is_dir() or staging.is_symlink():
        raise P400RebuildError("p400 staging generation is unavailable")
    staging_identity = _identity(staging)
    plan = P400RebuildPlan.from_dict(_read_json(staging, "plan.json", identity=staging_identity))
    if (
        Path(plan.run_dir).resolve() != root.resolve()
        or plan.run_dir_identity != identity
        or plan.generation_id != generation_id
    ):
        raise P400RebuildError("staged p400 plan run binding mismatch")
    if _plan_current_token(plan) != plan.plan_token:
        raise P400RebuildError("staged p400 plan token is invalid")
    return plan


# Explicit aliases make the transaction vocabulary discoverable to callers
# that use ``build/apply`` naming, while keeping prepare's no-publish contract
# obvious in the primary API.
build_p400_rebuild_plan = prepare_p400_rebuild
apply_rebuild_plan = apply_p400_rebuild


__all__ = [
    "BULK_JOB_PRECONDITION",
    "CandidateBundle",
    "P400RebuildContext",
    "P400RebuildError",
    "P400RebuildPlan",
    "REQUIRED_CANDIDATE_PATHS",
    "apply_p400_rebuild",
    "apply_rebuild_plan",
    "build_p400_rebuild_plan",
    "load_p400_rebuild_plan",
    "prepare_p400_rebuild",
    "recover_p400_rebuild",
]
