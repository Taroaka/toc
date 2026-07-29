#!/usr/bin/env python3
"""Prepare and optionally continue an existing frontend-created run from p500."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, load_structured_document, parse_state_file
from toc.p500_resume import (
    P500ResumeError,
    RESUME_INPUT_IDENTITY_SCHEMA_VERSION,
    _plan_token as _compute_resume_plan_token,
    apply_resume_plan,
    build_resume_plan,
    canonical_state_before_sha256,
    prepare_p500_resume,
    resolve_run_dir,
)
from toc.runtime_locks import FileLockUnavailable, sync_file_lock
from scripts.world_walk_source import (
    PathIdentity,
    copy_regular_file_atomic_nofollow,
    directory_identity_nofollow,
    directory_identity_relative_nofollow,
    read_regular_file_nofollow,
    sha256_regular_file_nofollow,
    unlink_regular_file_verified_nofollow,
    validate_world_walk_source_contract_path,
    validate_world_walk_source_path,
)


CREATE_INPUT_SCHEMA_VERSION = "toc.create_input.v1"
CREATE_INPUT_REL_PATH = Path("logs/orchestration/create_input.json")


def _load_frontend_runner() -> ModuleType:
    path = REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location("toc_immersive_frontend_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load frontend runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _topic_for_run(run_dir: Path, explicit_topic: str) -> str:
    state_topic = str(parse_state_file(run_dir / "state.txt").get("topic") or "").strip()
    topic = explicit_topic.strip() or state_topic
    if not topic:
        _text, manifest = load_structured_document(run_dir / "video_manifest.md")
        metadata = manifest.get("video_metadata")
        if isinstance(metadata, dict):
            topic = str(metadata.get("topic") or "").strip()
    if not topic:
        raise P500ResumeError("could not resolve the existing run topic")
    if explicit_topic.strip() and state_topic and explicit_topic.strip() != state_topic:
        raise P500ResumeError(
            f"--topic does not match the existing run: {explicit_topic.strip()} != {state_topic}"
        )
    return topic


def _resume_profile(
    frontend: ModuleType,
    *,
    run_dir: Path,
    topic: str,
    source: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _manifest_text, manifest = load_structured_document(run_dir / "video_manifest.md")
    if not manifest:
        raise P500ResumeError("video_manifest.md is not a structured document")
    metadata = manifest.get("video_metadata")
    target_seconds = (
        metadata.get("target_duration_seconds")
        if isinstance(metadata, dict)
        else None
    )
    try:
        target_duration_seconds = frontend.normalize_target_duration(target_seconds)
    except ValueError as exc:
        raise P500ResumeError(
            f"existing manifest has an invalid target duration: {target_seconds!r}"
        ) from exc

    profile = frontend._duration_aware_profile(
        frontend._story_profile(topic, source, variant_seed=run_dir.name),
        target_duration_seconds=target_duration_seconds,
    )
    _research_text, research = load_structured_document(run_dir / "research.md")
    if research:
        profile = frontend._profile_from_reviewed_research(profile, research)
    _story_text, story = load_structured_document(run_dir / "story.md")
    if story:
        profile = frontend._profile_from_reviewed_story(profile, story)
    return profile, manifest


def _resume_checkpoint_metadata(
    run_dir: Path,
) -> tuple[Path, dict[str, Any]] | None:
    state = parse_state_file(run_dir / "state.txt")
    checkpoint_rel = str(state.get("runtime.resume.p500.checkpoint") or "").strip()
    if not checkpoint_rel:
        return None
    checkpoint_path = Path(checkpoint_rel)
    if (
        checkpoint_path.is_absolute()
        or checkpoint_path.parts[:3] != ("logs", "resume", "p500")
        or len(checkpoint_path.parts) != 4
        or any(part in {"", ".", ".."} for part in checkpoint_path.parts)
    ):
        raise P500ResumeError(
            "p500 resume checkpoint must be logs/resume/p500/<checkpoint_id>"
        )
    checkpoint = run_dir / checkpoint_path
    try:
        run_identity = directory_identity_nofollow(run_dir)
        raw_metadata = read_regular_file_nofollow(
            run_dir,
            checkpoint_path / "checkpoint.json",
            expected_root_identity=run_identity,
        )
        payload = json.loads(raw_metadata.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise P500ResumeError(
            f"p500 resume checkpoint metadata is invalid: {checkpoint}"
        ) from exc
    if not isinstance(payload, dict):
        raise P500ResumeError(
            f"p500 resume checkpoint metadata is invalid: {checkpoint}"
        )
    try:
        metadata_run_dir = Path(str(payload["run_dir"]))
        metadata_checkpoint_dir = Path(str(payload["checkpoint_dir"]))
        metadata_checkpoint_id = str(payload["checkpoint_id"])
    except (KeyError, ValueError) as exc:
        raise P500ResumeError(
            f"p500 resume checkpoint identity is missing: {checkpoint}"
        ) from exc
    if (
        not metadata_run_dir.is_absolute()
        or not metadata_checkpoint_dir.is_absolute()
        or metadata_checkpoint_id != checkpoint.name
    ):
        raise P500ResumeError(
            f"p500 resume checkpoint identity does not match: {checkpoint}"
        )
    try:
        metadata_run_identity = directory_identity_nofollow(
            metadata_run_dir
        )
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            f"p500 resume checkpoint identity does not match: {checkpoint}"
        ) from exc
    if (
        metadata_run_identity != run_identity
        or metadata_checkpoint_dir
        != metadata_run_dir / checkpoint_path
    ):
        raise P500ResumeError(
            f"p500 resume checkpoint identity does not match: {checkpoint}"
        )
    if not isinstance(payload.get("downstream_fingerprints"), dict):
        raise P500ResumeError(
            f"p500 resume checkpoint fingerprints are missing: {checkpoint}"
        )
    mapping_fields = (
        "upstream_sha256",
        "state_fingerprint",
        "index_fingerprint",
        "optional_upstream_fingerprints",
    )
    if any(not isinstance(payload.get(field), dict) for field in mapping_fields):
        raise P500ResumeError(
            f"p500 resume checkpoint provenance is incomplete: {checkpoint}"
        )
    raw_downstream_files = payload.get("downstream_files")
    if (
        not isinstance(raw_downstream_files, list)
        or any(
            not isinstance(rel, str) or not rel
            for rel in raw_downstream_files
        )
        or len(set(raw_downstream_files)) != len(raw_downstream_files)
    ):
        raise P500ResumeError(
            f"p500 resume checkpoint provenance is incomplete: {checkpoint}"
        )
    expected_plan_token = str(payload.get("plan_token") or "")
    if re.fullmatch(r"[0-9a-f]{64}", expected_plan_token) is None:
        raise P500ResumeError(
            f"p500 resume checkpoint plan token is missing: {checkpoint}"
        )
    state_before_digest = payload.get("state_before_sha256")
    if state_before_digest is not None:
        if (
            not isinstance(state_before_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", state_before_digest) is None
        ):
            raise P500ResumeError(
                f"p500 resume checkpoint state_before digest is invalid: "
                f"{checkpoint}"
            )
        state_before = payload.get("state_before")
        try:
            actual_state_before_digest = canonical_state_before_sha256(
                state_before
            )
        except P500ResumeError as exc:
            raise P500ResumeError(
                f"p500 resume checkpoint state_before is invalid: "
                f"{checkpoint}"
            ) from exc
        if actual_state_before_digest != state_before_digest:
            raise P500ResumeError(
                f"p500 resume checkpoint state_before digest does not match: "
                f"{checkpoint}"
            )
    actual_plan_token = _compute_resume_plan_token(
        run_dir=metadata_run_dir,
        checkpoint_id=metadata_checkpoint_id,
        upstream_sha256=payload["upstream_sha256"],
        state_fingerprint=payload["state_fingerprint"],
        index_fingerprint=payload["index_fingerprint"],
        optional_upstream_fingerprints=payload[
            "optional_upstream_fingerprints"
        ],
        downstream_files=tuple(raw_downstream_files),
        downstream_fingerprints=payload["downstream_fingerprints"],
        resume_input_identity=payload.get("resume_input_identity"),
        state_before_sha256=state_before_digest,
    )
    if actual_plan_token != expected_plan_token:
        raise P500ResumeError(
            f"p500 resume checkpoint plan token does not match: {checkpoint}"
        )
    return checkpoint, payload


def _resume_checkpoint_dir(run_dir: Path) -> Path | None:
    metadata = _resume_checkpoint_metadata(run_dir)
    return metadata[0] if metadata is not None else None


def _checkpoint_state_before(run_dir: Path) -> dict[str, str]:
    metadata = _resume_checkpoint_metadata(run_dir)
    if metadata is None:
        return {}
    _checkpoint, payload = metadata
    if "state_before_sha256" not in payload:
        raise P500ResumeError(
            "p500 resume checkpoint predates authenticated state_before; "
            "mode reconstruction is blocked"
        )
    state_before = payload.get("state_before")
    if not isinstance(state_before, dict):
        raise P500ResumeError(
            "p500 resume checkpoint state_before is missing"
        )
    return dict(state_before)


def _resolve_resume_mode_contract(
    *,
    run_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_state = parse_state_file(run_dir / "state.txt")
    checkpoint_present = _resume_checkpoint_dir(run_dir) is not None
    checkpoint_state = _checkpoint_state_before(run_dir)
    contract_state = (
        checkpoint_state if checkpoint_present else current_state
    )
    if manifest is None:
        manifest_path = run_dir / "video_manifest.md"
        manifest = (
            load_structured_document(manifest_path)[1]
            if manifest_path.is_file()
            else {}
        )
    metadata = (
        manifest.get("video_metadata")
        if isinstance(manifest, dict)
        and isinstance(manifest.get("video_metadata"), dict)
        else {}
    )

    state_experience = str(
        contract_state.get("immersive.experience")
        or ""
    ).strip()
    manifest_experience = str(metadata.get("experience") or "").strip()
    if (
        state_experience
        and manifest_experience
        and state_experience != manifest_experience
    ):
        raise P500ResumeError(
            "p500 resume experience contract conflicts between state.txt and "
            f"video_manifest.md: {state_experience} != {manifest_experience}"
        )
    experience = manifest_experience or state_experience or "cinematic_story"

    state_source_run = str(
        contract_state.get("immersive.source_run")
        or ""
    ).strip()
    manifest_source_run = str(metadata.get("source_run") or "").strip()
    if (
        state_source_run
        and manifest_source_run
        and state_source_run != manifest_source_run
    ):
        raise P500ResumeError(
            "p500 resume source_run contract conflicts between state.txt and "
            f"video_manifest.md: {state_source_run} != {manifest_source_run}"
        )
    source_run = manifest_source_run or state_source_run
    if experience == "world_walk" and not source_run:
        raise P500ResumeError(
            "p500 resume world_walk contract requires video_metadata.source_run "
            "or immersive.source_run"
        )

    state_updates = {
        key: value
        for key, value in contract_state.items()
        if key.startswith("immersive.") and str(value).strip()
    }
    state_updates["immersive.experience"] = experience
    if source_run:
        state_updates["immersive.source_run"] = source_run
    create_mode = str(
        contract_state.get("runtime.create_mode")
        or ("world_walk" if experience == "world_walk" else "")
        or ""
    ).strip()
    if experience not in {"cinematic_story", "world_walk"}:
        raise P500ResumeError(
            f"unsupported p500 resume experience contract: {experience}"
        )
    if experience == "world_walk":
        if create_mode not in {"", "world_walk"}:
            raise P500ResumeError(
                "p500 resume create_mode conflicts with world_walk "
                f"experience: {create_mode}"
            )
        create_mode = "world_walk"
    elif create_mode not in {"", "normal", "scene_storyboard"}:
        raise P500ResumeError(
            "p500 resume create_mode is unsupported for cinematic_story: "
            f"{create_mode}"
        )
    if create_mode:
        state_updates["runtime.create_mode"] = create_mode

    return {
        "experience": experience,
        "source_run": source_run,
        "create_mode": create_mode,
        "state_updates": state_updates,
    }


def _read_canonical_create_input(run_dir: Path) -> dict[str, Any] | None:
    try:
        raw_payload = read_regular_file_nofollow(
            run_dir,
            CREATE_INPUT_REL_PATH,
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            "canonical create input path is missing or unsafe"
        ) from exc
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise P500ResumeError(
            "canonical create input is unreadable or invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise P500ResumeError("canonical create input must be a JSON object")
    return payload


def _resolve_exact_resume_source(
    *,
    run_dir: Path,
    topic: str,
    explicit_source: str,
    mode_contract: dict[str, Any],
) -> str:
    """Resolve only an exact persisted or explicitly supplied source."""

    payload = _read_canonical_create_input(run_dir)
    if payload is None:
        if not isinstance(explicit_source, str) or not explicit_source.strip():
            raise P500ResumeError(
                "legacy p500 resume requires an explicit nonempty --source "
                "containing the exact original source"
            )
        return explicit_source

    if payload.get("schema_version") != CREATE_INPUT_SCHEMA_VERSION:
        raise P500ResumeError(
            "canonical create input has an unsupported schema_version"
        )
    canonical_topic = payload.get("topic")
    if not isinstance(canonical_topic, str) or canonical_topic != topic:
        raise P500ResumeError(
            "canonical create input topic does not match the existing run"
        )
    source = payload.get("source")
    if not isinstance(source, str) or not source.strip():
        raise P500ResumeError(
            "canonical create input source must be a nonempty string"
        )
    source_sha256 = payload.get("source_sha256")
    if (
        not isinstance(source_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
        or hashlib.sha256(source.encode("utf-8")).hexdigest() != source_sha256
    ):
        raise P500ResumeError(
            "canonical create input source hash is missing or mismatched"
        )

    experience = payload.get("experience")
    expected_experience = str(
        mode_contract.get("experience") or ""
    ).strip()
    if (
        not isinstance(experience, str)
        or experience not in {"cinematic_story", "world_walk"}
        or experience != expected_experience
    ):
        raise P500ResumeError(
            "canonical create input experience does not match the existing run"
        )

    raw_source_run = payload.get("source_run")
    if raw_source_run is not None and (
        not isinstance(raw_source_run, str)
        or not raw_source_run.strip()
        or raw_source_run != raw_source_run.strip()
        or Path(raw_source_run).is_absolute()
        or ".." in Path(raw_source_run).parts
    ):
        raise P500ResumeError(
            "canonical create input source_run is invalid"
        )
    expected_source_run = str(
        mode_contract.get("source_run") or ""
    ).strip()
    canonical_source_run = raw_source_run or ""
    if canonical_source_run != expected_source_run:
        raise P500ResumeError(
            "canonical create input source_run does not match the existing run"
        )
    if experience == "world_walk" and not canonical_source_run:
        raise P500ResumeError(
            "canonical world_walk create input requires source_run"
        )
    if experience != "world_walk" and raw_source_run is not None:
        raise P500ResumeError(
            "canonical cinematic create input must not contain source_run"
        )

    target_duration = payload.get("target_duration_seconds")
    if (
        isinstance(target_duration, bool)
        or not isinstance(target_duration, int)
        or not 300 <= target_duration <= 1200
    ):
        raise P500ResumeError(
            "canonical create input target duration is invalid"
        )
    _manifest_text, manifest = load_structured_document(
        run_dir / "video_manifest.md"
    )
    metadata = (
        manifest.get("video_metadata")
        if isinstance(manifest, dict)
        and isinstance(manifest.get("video_metadata"), dict)
        else None
    )
    manifest_topic = (
        metadata.get("topic")
        if isinstance(metadata, dict)
        else None
    )
    if not isinstance(manifest_topic, str) or manifest_topic != topic:
        raise P500ResumeError(
            "canonical create input topic does not match video_manifest.md"
        )
    manifest_target = (
        metadata.get("target_duration_seconds")
        if isinstance(metadata, dict)
        else None
    )
    if (
        isinstance(manifest_target, bool)
        or not isinstance(manifest_target, int)
        or manifest_target != target_duration
    ):
        raise P500ResumeError(
            "canonical create input target duration does not match "
            "video_manifest.md"
        )
    state_target = str(
        parse_state_file(run_dir / "state.txt").get(
            "runtime.target_video_seconds"
        )
        or ""
    ).strip()
    if state_target:
        try:
            parsed_state_target = int(state_target)
        except ValueError as exc:
            raise P500ResumeError(
                "canonical create input target duration does not match state.txt"
            ) from exc
        if parsed_state_target != target_duration:
            raise P500ResumeError(
                "canonical create input target duration does not match state.txt"
            )

    if explicit_source.strip() and explicit_source != source:
        raise P500ResumeError(
            "explicit --source conflicts with canonical create input"
        )
    return source


def _resume_input_identity(
    *,
    topic: str,
    source: str,
) -> dict[str, str]:
    return {
        "schema_version": RESUME_INPUT_IDENTITY_SCHEMA_VERSION,
        "source_sha256": hashlib.sha256(
            source.encode("utf-8")
        ).hexdigest(),
        "topic_sha256": hashlib.sha256(
            topic.encode("utf-8")
        ).hexdigest(),
    }


def _world_walk_reference_paths(manifest: dict[str, Any]) -> list[str]:
    raw_references: list[Any] = []
    world_walk_contract = manifest.get("world_walk_contract")
    if isinstance(world_walk_contract, dict):
        raw_references.extend(world_walk_contract.get("source_references") or [])
    assets = manifest.get("assets")
    if isinstance(assets, dict):
        style_guide = assets.get("style_guide")
        if isinstance(style_guide, dict):
            raw_references.extend(style_guide.get("reference_images") or [])

    references: list[str] = []
    for raw in raw_references:
        rel = str(raw or "").strip().replace("\\", "/")
        if not rel or rel in references:
            continue
        path = Path(rel)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parts[:2] != ("assets", "source_references")
        ):
            raise P500ResumeError(
                f"unsafe world_walk source reference in manifest: {rel}"
            )
        references.append(path.as_posix())
    if not references:
        raise P500ResumeError(
            "p500 resume world_walk manifest has no local source_references"
        )
    return references


def _require_safe_path_components(
    *,
    root: Path,
    path: Path,
    label: str,
) -> None:
    if root.is_symlink():
        raise P500ResumeError(f"{label} is unsafe: symlink root {root}")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise P500ResumeError(f"{label} is unsafe: {path}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise P500ResumeError(f"{label} is unsafe: symlink {current}")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise P500ResumeError(f"{label} is unsafe: {path}") from exc


def _world_walk_reference_destination(run_dir: Path, rel: str) -> Path:
    destination = run_dir / rel
    _require_safe_path_components(
        root=run_dir,
        path=destination,
        label="world_walk reference destination",
    )
    return destination


def _verified_checkpoint_world_walk_references(
    *,
    run_dir: Path,
    references: list[str],
) -> dict[str, str]:
    metadata = _resume_checkpoint_metadata(run_dir)
    if metadata is None:
        return {}
    checkpoint, payload = metadata
    fingerprints = payload["downstream_fingerprints"]
    downstream_files = set(payload["downstream_files"])
    checkpoint_relative = checkpoint.relative_to(run_dir)
    try:
        run_identity = directory_identity_nofollow(run_dir)
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            f"world_walk checkpoint run directory is unsafe: {run_dir}"
        ) from exc
    try:
        directory_identity_relative_nofollow(
            run_dir,
            checkpoint_relative / "artifacts",
            expected_root_identity=run_identity,
        )
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            "world_walk checkpoint artifacts directory is unsafe: "
            f"{checkpoint / 'artifacts'}"
        ) from exc
    verified: dict[str, str] = {}
    for rel in references:
        fingerprint = fingerprints.get(rel)
        if fingerprint is None and rel not in downstream_files:
            continue
        if (
            rel not in downstream_files
            or not isinstance(fingerprint, dict)
            or fingerprint.get("exists") is not True
            or fingerprint.get("lexical_type") != "regular_file"
            or fingerprint.get("is_symlink") is not False
        ):
            raise P500ResumeError(
                f"checkpointed world_walk reference has no regular-file "
                f"fingerprint: {rel}"
            )
        expected_sha256 = str(fingerprint.get("bytes_sha256") or "")
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise P500ResumeError(
                f"checkpointed world_walk reference has no sha256: {rel}"
            )
        try:
            actual_sha256 = sha256_regular_file_nofollow(
                run_dir,
                checkpoint_relative / "artifacts" / rel,
                expected_root_identity=run_identity,
            )
        except (OSError, ValueError) as exc:
            raise P500ResumeError(
                "checkpointed world_walk reference is missing or unsafe: "
                f"{rel}"
            ) from exc
        if actual_sha256 != expected_sha256:
            raise P500ResumeError(
                f"checkpointed world_walk reference sha256 mismatch: {rel}"
            )
        verified[rel] = expected_sha256
    return verified


def _validated_world_walk_resume_source(
    *,
    mode_contract: dict[str, Any],
    references: list[str],
    verified_checkpoint_references: dict[str, str],
) -> tuple[Path, PathIdentity, dict[str, str]] | None:
    source_run = str(mode_contract.get("source_run") or "").strip()
    try:
        contracted_source, _relative = validate_world_walk_source_contract_path(
            REPO_ROOT,
            source_run,
            allow_missing=True,
        )
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            f"unsafe world_walk source_run contract: {exc}"
        ) from exc
    if contracted_source.exists():
        try:
            source_identity = directory_identity_nofollow(
                contracted_source
            )
            resolved_source, _relative = validate_world_walk_source_path(
                REPO_ROOT,
                contracted_source,
            )
            if (
                directory_identity_nofollow(resolved_source)
                != source_identity
            ):
                raise ValueError("source directory identity changed")
        except (OSError, ValueError) as exc:
            raise P500ResumeError(
                f"unsafe world_walk source_run contract: {exc}"
            ) from exc
        source_assets = resolved_source / "assets"
        selected_references = {
            (
                Path("assets")
                / "source_references"
                / path.relative_to(source_assets)
            ).as_posix()
            for path in sorted(
                path
                for path in source_assets.rglob("*")
                if path.is_file()
                and path.suffix.lower()
                in {".png", ".jpg", ".jpeg", ".webp"}
            )[:12]
        }
        fallback_hashes: dict[str, str] = {}
        for rel in references:
            if rel in verified_checkpoint_references:
                continue
            if rel not in selected_references:
                raise P500ResumeError(
                    "world_walk source run cannot materialize required "
                    f"reference: {rel}"
                )
            source_relative = (
                Path("assets")
                / Path(rel).relative_to(
                    Path("assets/source_references")
                )
            )
            try:
                fallback_hashes[rel] = (
                    sha256_regular_file_nofollow(
                        resolved_source,
                        source_relative,
                        expected_root_identity=source_identity,
                    )
                )
            except (OSError, ValueError) as exc:
                raise P500ResumeError(
                    "world_walk source reference is missing or unsafe: "
                    f"{rel}"
                ) from exc
        return resolved_source, source_identity, fallback_hashes
    if set(references).issubset(verified_checkpoint_references):
        return None
    raise P500ResumeError(
        "world_walk source run is missing and the verified checkpoint does "
        "not contain every required source reference"
    )


def _preflight_world_walk_reference_restore(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    mode_contract: dict[str, Any],
) -> tuple[
    list[str],
    dict[str, str],
    tuple[Path, PathIdentity, dict[str, str]] | None,
]:
    if mode_contract.get("experience") != "world_walk":
        return [], {}, None
    references = _world_walk_reference_paths(manifest)
    destinations = {
        rel: _world_walk_reference_destination(run_dir, rel)
        for rel in references
    }
    preexisting = [
        rel
        for rel, destination in destinations.items()
        if destination.is_symlink() or destination.exists()
    ]
    if preexisting:
        raise P500ResumeError(
            "world_walk reference destinations must be absent before restore: "
            + ", ".join(preexisting)
        )
    verified = _verified_checkpoint_world_walk_references(
        run_dir=run_dir,
        references=references,
    )
    source_bundle = _validated_world_walk_resume_source(
        mode_contract=mode_contract,
        references=references,
        verified_checkpoint_references=verified,
    )
    return references, verified, source_bundle


def _preflight_world_walk_before_reset(
    *,
    run_dir: Path,
    mode_contract: dict[str, Any],
) -> None:
    if mode_contract.get("experience") != "world_walk":
        return
    _text, manifest = load_structured_document(run_dir / "video_manifest.md")
    references = _world_walk_reference_paths(manifest)
    for rel in references:
        _world_walk_reference_destination(run_dir, rel)
    _validated_world_walk_resume_source(
        mode_contract=mode_contract,
        references=references,
        verified_checkpoint_references={},
    )


def _restore_world_walk_source_references(
    frontend: ModuleType,
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    mode_contract: dict[str, Any],
) -> list[str]:
    if mode_contract.get("experience") != "world_walk":
        return []

    references, verified_checkpoint_references, source_bundle = (
        _preflight_world_walk_reference_restore(
            run_dir=run_dir,
            manifest=manifest,
            mode_contract=mode_contract,
        )
    )
    try:
        destination_root_identity = directory_identity_nofollow(run_dir)
    except (OSError, ValueError) as exc:
        raise P500ResumeError(
            f"world_walk destination run is unsafe: {run_dir}"
        ) from exc
    created: list[tuple[str, str]] = []
    try:
        checkpoint = _resume_checkpoint_dir(run_dir)
        if checkpoint is not None and verified_checkpoint_references:
            checkpoint_relative = checkpoint.relative_to(run_dir)
            for rel, expected_sha256 in (
                verified_checkpoint_references.items()
            ):
                try:
                    actual_sha256 = copy_regular_file_atomic_nofollow(
                        source_root=run_dir,
                        source_relative=(
                            checkpoint_relative / "artifacts" / rel
                        ),
                        destination_root=run_dir,
                        destination_relative=rel,
                        expected_source_root_identity=(
                            destination_root_identity
                        ),
                        expected_destination_root_identity=(
                            destination_root_identity
                        ),
                        expected_sha256=expected_sha256,
                    )
                    created.append((rel, actual_sha256))
                except (OSError, ValueError) as exc:
                    raise P500ResumeError(
                        "could not restore checkpointed world_walk "
                        f"reference {rel}: {exc}"
                    ) from exc

        missing = [
            rel
            for rel in references
            if rel not in verified_checkpoint_references
        ]
        if missing:
            if source_bundle is None:
                raise P500ResumeError(
                    "verified checkpoint is incomplete and world_walk "
                    "source run is unavailable"
                )
            source_run, source_identity, fallback_hashes = source_bundle
            for rel in missing:
                source_relative = (
                    Path("assets")
                    / Path(rel).relative_to(
                        Path("assets/source_references")
                    )
                )
                try:
                    actual_sha256 = copy_regular_file_atomic_nofollow(
                        source_root=source_run,
                        source_relative=source_relative,
                        destination_root=run_dir,
                        destination_relative=rel,
                        expected_source_root_identity=source_identity,
                        expected_destination_root_identity=(
                            destination_root_identity
                        ),
                        expected_sha256=fallback_hashes[rel],
                    )
                    created.append((rel, actual_sha256))
                except (KeyError, OSError, ValueError) as exc:
                    raise P500ResumeError(
                        "could not restore world_walk source reference "
                        f"{rel}: {exc}"
                    ) from exc

        expected_reference_hashes = dict(
            verified_checkpoint_references
        )
        if source_bundle is not None:
            expected_reference_hashes.update(source_bundle[2])
        verification_failures: list[str] = []
        for rel in references:
            expected_sha256 = expected_reference_hashes.get(rel)
            if expected_sha256 is None:
                verification_failures.append(
                    f"{rel} (missing expected sha256)"
                )
                continue
            try:
                actual_sha256 = sha256_regular_file_nofollow(
                    run_dir,
                    rel,
                    expected_root_identity=destination_root_identity,
                )
            except (OSError, ValueError) as exc:
                verification_failures.append(f"{rel} ({exc})")
                continue
            if actual_sha256 != expected_sha256:
                verification_failures.append(
                    f"{rel} (sha256 mismatch)"
                )
        if verification_failures:
            raise P500ResumeError(
                "world_walk source reference final verification failed: "
                + ", ".join(verification_failures)
            )
    except Exception as exc:
        rollback_failures: list[str] = []
        for rel, expected_sha256 in reversed(created):
            try:
                removed = unlink_regular_file_verified_nofollow(
                    root=run_dir,
                    relative_path=rel,
                    expected_root_identity=destination_root_identity,
                    expected_sha256=expected_sha256,
                )
            except (OSError, ValueError):
                removed = False
            if not removed:
                rollback_failures.append(rel)
        if rollback_failures:
            raise P500ResumeError(
                f"{exc}; world_walk restore rollback could not safely "
                "remove: "
                + ", ".join(rollback_failures)
            ) from exc
        raise
    return references


def _resume_state_updates(
    *,
    run_dir: Path,
    topic: str,
    profile: dict[str, Any],
    stop_target: str,
    now: str,
    mode_contract: dict[str, Any] | None = None,
) -> dict[str, str]:
    resolved_mode = mode_contract or _resolve_resume_mode_contract(run_dir=run_dir)
    state_updates = _write_resume_orchestration(
        run_dir=run_dir,
        stop_target=stop_target,
        now=now,
    )
    state_updates.update(
        {
            "slot.p520.status": "done",
            "slot.p520.note": "asset inventory rematerialized from preserved p450 manifest",
            "slot.p530.status": "done",
            "slot.p530.note": "asset plan rematerialized; semantic review pending",
            "slot.p540.status": "pending",
            "slot.p540.note": "asset semantic review has not completed",
            "slot.p550.status": "pending",
            "slot.p550.note": "candidate requests exist but are not frozen",
            "slot.p560.status": "pending",
            "slot.p560.note": "asset generation has not completed",
            "slot.p570.status": "pending",
            "slot.p570.note": "asset continuity review has not completed",
            "slot.p620.status": "done",
            "slot.p620.note": "preserved production manifest rematerialized into candidate requests",
            "slot.p630.status": "pending",
            "slot.p630.note": "scene implementation hard review has not completed",
            "slot.p640.status": "pending",
            "slot.p640.note": "scene implementation judgment has not completed",
            "slot.p650.status": "pending",
            "slot.p650.note": "candidate requests materialized; waiting for semantic review and final freeze",
            "review.image_prompt.request_freeze.status": "draft",
            "review.image_prompt.request_freeze.request": "image_generation_requests.md",
            "review.image_prompt.request_freeze.snapshot": "image_generation_request_snapshot.json",
        }
    )
    if stop_target == "p680":
        state_updates.update(
            {
                "slot.p660.status": "pending",
                "slot.p660.note": "waiting for image-prompt semantic review and final request freeze",
                "slot.p670.status": "pending",
                "slot.p670.note": "waiting for scene image generation to finish",
                "slot.p680.status": "pending",
                "slot.p680.note": "frontend image review waits for every scene image",
            }
        )
    duration_plan = dict(profile["duration_plan"])
    state_updates.update(
        {
            "timestamp": now,
            "topic": topic,
            "status": "P650",
            "runtime.stage": "image_prompt_semantic_review_pending",
            "runtime.stage_target": "p600",
            "runtime.stop_slot": stop_target,
            "runtime.resume.p500.status": "materialized",
            "runtime.resume.p500.stop_target": stop_target,
            "runtime.target_video_seconds": str(duration_plan["target_seconds"]),
            "runtime.duration_gate.minimum_seconds": str(
                int(duration_plan["minimum_effective_seconds"])
            ),
            "runtime.duration_plan.minimum_scene_count": str(
                duration_plan["minimum_scene_count"]
            ),
            "runtime.duration_plan.minimum_narration_seconds": str(
                duration_plan["minimum_narration_seconds"]
            ),
            "runtime.scaffold.content_status": "authored",
            "runtime.review_policy": "frontend",
            "review.policy.story": "required",
            "review.policy.image": "required",
            "review.policy.narration": "optional",
            "gate.research_review": "required",
            "gate.story_review": "required",
            "gate.narration_review": "optional",
            "review.research.status": "approved",
            "review.story.status": "approved",
            "review.script.status": "approved",
            "stage.research.status": "reviewed",
            "stage.story.status": "reviewed",
            "stage.asset.status": "in_progress",
            "stage.scene_implementation.status": "in_progress",
            "review.image.status": "pending",
            "gate.image_review": "required",
        }
    )
    state_updates.update(resolved_mode["state_updates"])
    return state_updates


def _write_resume_orchestration(
    *,
    run_dir: Path,
    stop_target: str,
    now: str,
) -> dict[str, str]:
    orchestration_dir = run_dir / "logs" / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)
    progress_path = orchestration_dir / "l2_supervisor_progress.md"
    if not progress_path.exists():
        progress_path.write_text(
            "| timestamp | bucket | supervisor | event | stop_slot | result | note |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    progress_rows: list[str] = []
    state_updates: dict[str, str] = {}
    bucket_specs = (
        (
            "p500",
            ("p510", "p520", "p530", "p540", "p550", "p560", "p570"),
            (
                "asset_inventory.md",
                "asset_plan.md",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
            ),
            "pending",
            "p600",
        ),
        (
            "p600",
            (
                ("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680")
                if stop_target == "p680"
                else ("p610", "p620", "p630", "p640", "p650")
            ),
            ("image_generation_requests.md",),
            "pending",
            None,
        ),
    )
    for bucket, slots, artifacts, status, next_bucket in bucket_specs:
        result_rel = f"logs/orchestration/{bucket}.supervisor_result.json"
        progress_rows.extend(
            [
                f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | invoked | {stop_target} | - | p500 resume |",
                f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | returned | {stop_target} | {result_rel} | {status} |",
            ]
        )
        key = f"orchestration.{bucket}.supervisor"
        state_updates.update(
            {
                f"{key}.call_status": "returned",
                f"{key}.status": status,
                f"{key}.finished_at": now,
            }
        )
        result = {
            "bucket": bucket,
            "status": "pending",
            "stop_slot": stop_target,
            "completed_slots": (
                ["p520", "p530"]
                if bucket == "p500"
                else ["p620"]
            ),
            "required_artifacts": [
                {"path": path, "exists": (run_dir / path).is_file()}
                for path in artifacts
            ],
            "state_keys": {
                f"slot.{slots[-1]}.status": (
                    "pending"
                )
            },
            "review_outputs": [],
            "next_bucket": next_bucket,
        }
        (orchestration_dir / f"{bucket}.supervisor_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(progress_rows) + "\n")
    return state_updates


def materialize_from_p500(
    frontend: ModuleType,
    *,
    run_dir: Path,
    topic: str,
    source: str,
    stop_target: str,
) -> None:
    profile, manifest = _resume_profile(
        frontend,
        run_dir=run_dir,
        topic=topic,
        source=source,
    )
    mode_contract = _resolve_resume_mode_contract(
        run_dir=run_dir,
        manifest=manifest,
    )
    expected_source_references, _verified_references, _source_run = (
        _preflight_world_walk_reference_restore(
            run_dir=run_dir,
            manifest=manifest,
            mode_contract=mode_contract,
        )
    )
    for rel in (
        "assets/characters",
        "assets/objects",
        "assets/locations",
        "assets/scenes",
        "assets/audio",
        "logs/grounding",
    ):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)

    now = frontend._now_iso()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.stage": "p500_resume_materializing",
            "runtime.resume.p500.status": "materializing",
            "last_error": "",
        },
    )
    _archive_p400_review_evidence(run_dir)
    source_references = _restore_world_walk_source_references(
        frontend,
        run_dir=run_dir,
        manifest=manifest,
        mode_contract=mode_contract,
    )
    if source_references != expected_source_references:
        raise P500ResumeError(
            "p500 resume restored source references do not match the "
            "world_walk manifest contract"
        )
    asset_inventory, asset_plan = frontend._build_asset_artifacts_from_manifest(
        profile=profile,
        manifest=manifest,
    )
    if mode_contract.get("experience") == "world_walk":
        frontend._apply_world_walk_asset_generation_contract(
            asset_plan=asset_plan,
            source_references=source_references,
        )
    (run_dir / "asset_inventory.md").write_text(
        frontend._md_yaml("Asset Inventory", asset_inventory),
        encoding="utf-8",
    )
    (run_dir / "asset_plan.md").write_text(
        frontend._md_yaml("Asset Plan", asset_plan),
        encoding="utf-8",
    )
    frontend._prepare_authoring_grounding(run_dir)
    frontend._refresh_p400_review_artifacts(run_dir)
    frontend._require_fresh_p400_readiness(run_dir)
    frontend._write_asset_request_files(run_dir, asset_plan, profile)
    frontend._materialize_standard_request_files(run_dir)
    # Request projection persists compiled payloads into video_manifest.md.
    # Re-ground and re-freeze P400 against that final pre-provider revision.
    frontend._prepare_authoring_grounding(run_dir)
    frontend._refresh_p400_review_artifacts(run_dir)
    frontend._require_fresh_p400_readiness(run_dir)
    append_state_snapshot(
        run_dir / "state.txt",
        _resume_state_updates(
            run_dir=run_dir,
            topic=topic,
            profile=profile,
            stop_target=stop_target,
            now=now,
            mode_contract=mode_contract,
        ),
    )


def _archive_p400_review_evidence(run_dir: Path) -> Path:
    checkpoint = _resume_checkpoint_dir(run_dir)
    if checkpoint is None:
        raise P500ResumeError("p500 resume checkpoint is missing from state")

    root_files = {
        "visual_value_review.md",
        "scene_set_review.md",
        "scene_detail_review.md",
        "scene_intent_review.md",
        "cut_blueprint_review.md",
        "script_review.md",
        "production_readiness_review.md",
    }
    eval_stages = (
        "visual_value",
        "scene_set",
        "scene_detail",
        "cut_blueprint",
        "script",
        "production_readiness",
    )
    semantic_stages = ("scene_set", "scene_detail", "cut_blueprint")
    selected: list[str] = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if rel in root_files:
            selected.append(rel)
            continue
        if any(rel.startswith(f"logs/eval/{stage}/") for stage in eval_stages):
            selected.append(rel)
            continue
        if any(
            rel.startswith(f"logs/review/semantic/{stage}.")
            for stage in semantic_stages
        ):
            selected.append(rel)
            continue
        if rel.startswith(("logs/grounding/script.", "logs/grounding/manifest.")):
            selected.append(rel)

    evidence_root = checkpoint / "p400_evidence"
    for rel in sorted(set(selected)):
        source = run_dir / rel
        destination = evidence_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (checkpoint / "p400_evidence_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "toc.p500_resume.p400_evidence.v1",
                "files": sorted(set(selected)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence_root


def _prepare_stage_context(run_dir: Path, stage: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "prepare-stage-context.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            "immersive",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _prepare_resume_grounding(run_dir: Path) -> None:
    for stage in ("asset", "scene_implementation"):
        _prepare_stage_context(run_dir, stage)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "slot.p510.status": "done",
            "slot.p510.note": "asset grounding refreshed for p500 resume",
            "slot.p610.status": "done",
            "slot.p610.note": "scene implementation grounding refreshed for p500 resume",
        },
    )


def _mark_materialized_asset_requests(run_dir: Path) -> None:
    """Keep non-executed media pending while recording the p550 handoff."""

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "slot.p550.status": "done",
            "slot.p550.note": "asset requests rematerialized after semantic review; media generation not requested",
            "slot.p560.status": "pending",
            "slot.p560.note": "materialize-only mode did not generate reusable assets",
            "slot.p570.status": "pending",
            "slot.p570.note": "asset continuity review waits for reusable asset generation",
            "stage.asset.status": "in_progress",
        },
    )


def _finalize_resume_orchestration(
    *,
    run_dir: Path,
    stop_target: str,
) -> dict[str, str]:
    state = parse_state_file(run_dir / "state.txt")
    bucket_slots = {
        "p500": ("p510", "p520", "p530", "p540", "p550", "p560", "p570"),
        "p600": (
            ("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680")
            if stop_target == "p680"
            else ("p610", "p620", "p630", "p640", "p650")
        ),
    }
    orchestration_dir = run_dir / "logs" / "orchestration"
    for bucket, slots in bucket_slots.items():
        path = orchestration_dir / f"{bucket}.supervisor_result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise P500ResumeError(
                f"resume supervisor result is missing or invalid: {path}"
            ) from exc
        result["status"] = "done"
        result["completed_slots"] = [
            slot
            for slot in slots
            if state.get(f"slot.{slot}.status")
            in {"done", "skipped", "awaiting_approval"}
        ]
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    progress_path = orchestration_dir / "l2_supervisor_progress.md"
    with progress_path.open("a", encoding="utf-8") as handle:
        for bucket in ("p500", "p600"):
            handle.write(
                f"| {state.get('timestamp', '')} | {bucket} | "
                f"{bucket} P-Bucket Supervisor | completed | {stop_target} | "
                f"logs/orchestration/{bucket}.supervisor_result.json | validated p500 resume |\n"
            )
    return {
        "orchestration.p500.supervisor.status": "done",
        "orchestration.p600.supervisor.status": "done",
    }


def _continue_run(
    *,
    run_dir: Path,
    topic: str,
    source: str,
    stop_target: str,
    materialize_only: bool,
    skip_validation: bool,
) -> None:
    frontend = _load_frontend_runner()
    materialize_stop_target = (
        "p650" if materialize_only and stop_target == "p680" else stop_target
    )
    with frontend._run_materialization_lock(run_dir):
        materialize_from_p500(
            frontend,
            run_dir=run_dir,
            topic=topic,
            source=source,
            stop_target=materialize_stop_target,
        )
        _prepare_resume_grounding(run_dir)
        frontend._refresh_downstream_review_artifacts(run_dir)
        if materialize_only:
            asyncio.run(
                frontend.run_pre_media_semantic_pipeline(
                    run_dir,
                    image_prompt_provider_ready=False,
                )
            )
            _mark_materialized_asset_requests(run_dir)
        else:
            asyncio.run(frontend.generate_images(run_dir, stop_target))
            mode_contract = _resolve_resume_mode_contract(
                run_dir=run_dir,
            )
            if (
                stop_target == "p680"
                and mode_contract.get("create_mode")
                == "scene_storyboard"
            ):
                from server import image_gen_app

                image_gen_app._finalize_scene_storyboard_p680(
                    run_dir.name
                )
            if stop_target == "p650":
                from server import image_gen_app

                image_gen_app._mark_asset_generation_handoff(
                    run_dir,
                    asset_quality_passed=False,
                )
        frontend.write_run_index(run_dir)
        if not skip_validation:
            if materialize_only:
                from server import image_gen_app

                image_gen_app._validate_materialized_p650_run(
                    frontend._run_id_from_dir(run_dir)
                )
            else:
                frontend.validate(run_dir, stop_target)
        final_updates = (
            {}
            if materialize_only
            else _finalize_resume_orchestration(
                run_dir=run_dir,
                stop_target=stop_target,
            )
        )
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **final_updates,
                "runtime.resume.p500.status": (
                    "semantic_materialized" if materialize_only else "completed"
                ),
                "runtime.resume.p500.stop_target": stop_target,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely reset an existing frontend-created ToC run and resume it from p500."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--topic", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--checkpoint-id", default="")
    parser.add_argument(
        "--plan-token",
        default="",
        help="Exact plan_token returned by the inspected dry-run.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reset. Without this flag, print a dry-run plan only.",
    )
    parser.add_argument(
        "--continue-to",
        choices=["p650", "p680"],
        help="After reset, continue the same run through this stop target.",
    )
    parser.add_argument(
        "--materialize-only",
        action="store_true",
        help="Run semantic materialization but do not generate media.",
    )
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    if args.continue_to and not args.apply:
        parser.error("--continue-to requires --apply")
    if args.materialize_only and not args.continue_to:
        parser.error("--materialize-only requires --continue-to")
    if args.apply and (not args.checkpoint_id.strip() or not args.plan_token.strip()):
        parser.error(
            "--apply requires the --checkpoint-id and --plan-token returned by dry-run"
        )

    try:
        resolved = resolve_run_dir(REPO_ROOT, args.run_dir)
        checkpoint_id = args.checkpoint_id.strip() or None
        if not args.apply:
            topic = _topic_for_run(resolved, args.topic)
            mode_contract = _resolve_resume_mode_contract(run_dir=resolved)
            _preflight_world_walk_before_reset(
                run_dir=resolved,
                mode_contract=mode_contract,
            )
            source = _resolve_exact_resume_source(
                run_dir=resolved,
                topic=topic,
                explicit_source=args.source,
                mode_contract=mode_contract,
            )
            resume_input_identity = _resume_input_identity(
                topic=topic,
                source=source,
            )
            plan, _checkpoint = prepare_p500_resume(
                repo_root=REPO_ROOT,
                run_dir=resolved,
                apply=False,
                checkpoint_id=checkpoint_id,
                resume_input_identity=resume_input_identity,
            )
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return

        try:
            with sync_file_lock(
                resolved / ".locks" / "create_resume.lock",
                wait=False,
            ):
                topic = _topic_for_run(resolved, args.topic)
                mode_contract = _resolve_resume_mode_contract(
                    run_dir=resolved
                )
                _preflight_world_walk_before_reset(
                    run_dir=resolved,
                    mode_contract=mode_contract,
                )
                source = _resolve_exact_resume_source(
                    run_dir=resolved,
                    topic=topic,
                    explicit_source=args.source,
                    mode_contract=mode_contract,
                )
                resume_input_identity = _resume_input_identity(
                    topic=topic,
                    source=source,
                )
                plan = build_resume_plan(
                    repo_root=REPO_ROOT,
                    run_dir=resolved,
                    checkpoint_id=checkpoint_id,
                    resume_input_identity=resume_input_identity,
                )
                if args.plan_token.strip() != plan.plan_token:
                    raise P500ResumeError(
                        "dry-run plan token is stale; inspect a new dry-run before apply"
                    )
                checkpoint = apply_resume_plan(
                    plan,
                    lock_already_held=True,
                )
                if args.continue_to:
                    _continue_run(
                        run_dir=resolved,
                        topic=topic,
                        source=source,
                        stop_target=args.continue_to,
                        materialize_only=args.materialize_only,
                        skip_validation=args.skip_validation,
                    )
        except FileLockUnavailable as exc:
            raise P500ResumeError(
                f"another create/resume process owns this run: {resolved}"
            ) from exc
        print(f"Run dir: {resolved}")
        print(f"Checkpoint: {checkpoint}")
        print(f"Moved downstream files: {len(plan.downstream_files)}")
        print(f"Stop target: {args.continue_to or 'p500 prepared'}")
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or exc.stdout or exc).strip()
        parser.exit(1, f"p500 resume failed: {detail}\n")
    except (P500ResumeError, RuntimeError) as exc:
        parser.exit(1, f"p500 resume failed: {exc}\n")


if __name__ == "__main__":
    main()
