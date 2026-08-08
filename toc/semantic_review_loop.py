from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from scripts.world_walk_source import read_regular_file_nofollow
from toc.harness import now_iso
from toc.review_projection import (
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    ReviewProjectionError,
    review_source_fingerprint_bytes,
)
from toc.semantic_review import (
    safe_semantic_write_text,
    semantic_review_input_digest,
    semantic_review_relpaths,
    semantic_review_scope_binding_sha256,
)


DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS = 2
DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS = 1800
DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS = 1800
DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY = 6
DEFAULT_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS = 3
DEFAULT_SEMANTIC_REPAIR_SNAPSHOT_ATTEMPTS = 3
SEMANTIC_REPAIR_COMMIT_SCHEMA = "semantic_repair_commit_v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


SEMANTIC_REVIEW_PRODUCER_TARGETS: dict[str, dict[str, object]] = {
    "research": {
        "slot": "p130",
        "owner": "research foundation producer",
        "artifacts": ["research.md"],
        "focus": "internal story baseline, chronological event coherence, characters, conflicts, and story-stage sufficiency",
    },
    "story": {
        "slot": "p230",
        "owner": "story foundation producer",
        "artifacts": ["story.md"],
        "focus": "research-baseline preservation, timeline, character continuity, conflict progression, and event-to-scene allocation",
    },
    "scene_set": {
        "slot": "p410",
        "owner": "scene design producer",
        "artifacts": ["story.md", "script.md", "video_manifest.md"],
        "focus": "scene purpose, causal order, scene time-of-day and location continuity, and story meaning",
    },
    "scene_detail": {
        "slot": "p410",
        "owner": "scene detail producer",
        "artifacts": ["script.md", "video_manifest.md"],
        "focus": "scene detail, time-of-day lighting, visual beats, character state, and handoff meaning",
    },
    "cut_blueprint": {
        "slot": "p420",
        "owner": "cut blueprint producer",
        "artifacts": ["script.md", "video_manifest.md"],
        "focus": "cut function, scene time-of-day lighting, must-show contract, reveal order, and downstream handoff",
    },
    "asset_plan": {
        "slot": "p540",
        "owner": "asset planning producer",
        "artifacts": ["asset_inventory.md", "video_manifest.md"],
        "focus": "character/object/location coverage, asset category, story purpose, and prompt contract",
    },
    "image_prompt": {
        "slot": "p640",
        "owner": "image prompt producer",
        "artifacts": ["video_manifest.md"],
        "focus": "cut-local include / omit / add / replace decisions, reference choice, historical time, scene time of day, location/object/character correctness, temporal polarity, and first-frame meaning",
    },
    "narration": {
        "slot": "p720",
        "owner": "narration producer",
        "artifacts": ["video_manifest.md", "narration_text_review.md", "assets/audio/**"],
        "focus": "narration role, non-redundant emotional meaning, TTS text, timing, and continuity",
    },
    "video_motion": {
        "slot": "p820",
        "owner": "video motion producer",
        "artifacts": ["video_manifest.md"],
        "focus": "motion prompt, first-frame contract, subject/environment movement, and end state",
    },
}


def semantic_review_max_attempts() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REVIEW_MAX_ATTEMPTS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS


def semantic_repair_timeout_seconds() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REPAIR_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS


def semantic_review_timeout_seconds() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REVIEW_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS


def scene_detail_review_concurrency() -> int:
    raw = os.environ.get("TOC_SCENE_DETAIL_REVIEW_CONCURRENCY", "").strip()
    if not raw:
        return DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY


def scene_detail_transport_retry_attempts() -> int:
    raw = os.environ.get("TOC_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS", "").strip()
    if not raw:
        return DEFAULT_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SCENE_DETAIL_TRANSPORT_RETRY_ATTEMPTS


def semantic_repair_relpaths(stage: str, round_number: int) -> dict[str, Path]:
    base = Path("logs/review/semantic")
    return {
        "prompt": base / f"{stage}.repair_round_{round_number:02d}.prompt.md",
        "report": base / f"{stage}.repair_round_{round_number:02d}.producer_report.md",
        "commit": base / f"{stage}.repair_round_{round_number:02d}.commit.json",
    }


def _semantic_review_failed_selectors(review_report: str) -> set[str]:
    selectors: set[str] = set()
    in_failed_list = False
    for raw in review_report.splitlines():
        stripped = raw.strip()
        if stripped.startswith("failed_selectors:") or stripped.startswith("blocked_entries:"):
            inline = stripped.split(":", 1)[1].strip()
            for value in _semantic_review_selector_values(inline):
                _add_semantic_review_selector_aliases(selectors, value)
            in_failed_list = inline in {"", "[]", "[ ]"}
            continue
        if in_failed_list and stripped and not stripped.startswith("-"):
            in_failed_list = False
        if in_failed_list and stripped.startswith("-"):
            value = _semantic_review_selector_scalar(stripped[1:])
            if value:
                _add_semantic_review_selector_aliases(selectors, value)
    return selectors


def _semantic_review_selector_values(raw: str) -> list[str]:
    value = raw.strip()
    if not value or value in {"[]", "[ ]"}:
        return []
    if value.startswith("[") and value.endswith("]"):
        return [
            cleaned
            for item in value[1:-1].split(",")
            if (cleaned := _semantic_review_selector_scalar(item))
        ]
    cleaned = _semantic_review_selector_scalar(value)
    return [cleaned] if cleaned else []


def _semantic_review_selector_scalar(raw: str) -> str:
    value = raw.strip().strip(",").strip().strip("`\"'")
    return "" if value in {"...", "[]"} else value


def _add_semantic_review_selector_aliases(selectors: set[str], value: str) -> None:
    selectors.add(value)
    if value.startswith("scene:"):
        selectors.add("scene" + value.split(":", 1)[1])
    elif value.startswith("scene") and value[5:].isdigit():
        selectors.add("scene:" + value[5:])


def _semantic_collection_excerpt(collection_text: str, review_report: str, *, max_chars: int = 14000) -> str:
    failed_selectors = _semantic_review_failed_selectors(review_report)
    if not failed_selectors:
        return collection_text[:max_chars]

    selected_sections: list[str] = []
    chunks = collection_text.split("\n## ")
    preamble = chunks[0].strip()
    for chunk in chunks[1:]:
        heading = chunk.splitlines()[0].strip().strip("`")
        if heading in failed_selectors:
            selected_sections.append("## " + chunk.strip())

    if not selected_sections:
        return collection_text[:max_chars]

    excerpt = "\n\n".join(section[:5000] for section in selected_sections)
    if preamble:
        excerpt = preamble + "\n\n" + excerpt
    return excerpt[:max_chars]


def semantic_loop_state_updates(
    stage: str,
    *,
    status: str,
    attempt: int,
    max_attempts: int,
    error_count: int | None = None,
) -> dict[str, str]:
    updates = {
        f"review.semantic.{stage}.loop.status": status,
        f"review.semantic.{stage}.loop.attempt": str(attempt),
        f"review.semantic.{stage}.loop.max_attempts": str(max_attempts),
        f"review.semantic.{stage}.loop.updated_at": now_iso(),
    }
    if error_count is not None:
        updates[f"review.semantic.{stage}.loop.error_count"] = str(error_count)
    return updates


def semantic_repair_state_updates(
    stage: str,
    *,
    status: str,
    round_number: int,
    max_attempts: int,
    error_count: int | None = None,
) -> dict[str, str]:
    relpaths = semantic_repair_relpaths(stage, round_number)
    updates = {
        f"review.semantic.{stage}.repair.status": status,
        f"review.semantic.{stage}.repair.round": str(round_number),
        f"review.semantic.{stage}.repair.max_attempts": str(max_attempts),
        f"review.semantic.{stage}.repair.prompt": relpaths["prompt"].as_posix(),
        f"review.semantic.{stage}.repair.report": relpaths["report"].as_posix(),
        f"review.semantic.{stage}.repair.commit": relpaths["commit"].as_posix(),
        f"review.semantic.{stage}.repair.updated_at": now_iso(),
    }
    if error_count is not None:
        updates[f"review.semantic.{stage}.repair.error_count"] = str(error_count)
    return updates


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _semantic_report_input_digests(report_text: str) -> list[str]:
    values: list[str] = []
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if line.startswith("-"):
            line = line[1:].strip()
        key, separator, raw_value = line.partition(":")
        if separator and key.strip() == "semantic_review_input_digest":
            values.append(raw_value.strip().strip("`"))
    return values


def _semantic_review_snapshot_relationship_issues(
    *,
    stage: str,
    collection_bytes: bytes,
    prompt_bytes: bytes,
    scope_bytes: bytes,
    report_bytes: bytes,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    issues: list[str] = []
    try:
        raw_scope = json.loads(scope_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, (f"invalid semantic review scope JSON: {exc}",)
    if not isinstance(raw_scope, dict):
        return None, ("semantic review scope JSON must be an object",)
    scope: dict[str, Any] = raw_scope

    if str(scope.get("stage") or "").strip() != stage:
        issues.append("semantic review scope stage does not match repair stage")

    collection_sha256 = _sha256_bytes(collection_bytes)
    stored_collection_sha256 = scope.get("collection_sha256")
    if stored_collection_sha256 != collection_sha256:
        issues.append("semantic review collection SHA-256 does not match scope")

    entry_ids = scope.get("entry_ids")
    if not isinstance(entry_ids, list) or any(
        not isinstance(entry_id, str) or not entry_id.strip()
        for entry_id in entry_ids
    ):
        issues.append("semantic review scope entry_ids are invalid")
        normalized_entry_ids: list[str] = []
    else:
        normalized_entry_ids = [entry_id.strip() for entry_id in entry_ids]
        if len(set(normalized_entry_ids)) != len(normalized_entry_ids):
            issues.append("semantic review scope entry_ids are duplicated")

    source_artifact_digests = scope.get("source_artifact_digests")
    if not isinstance(source_artifact_digests, list) or any(
        not isinstance(record, dict)
        for record in source_artifact_digests
    ):
        issues.append("semantic review scope source_artifact_digests are invalid")
        normalized_source_digests: list[Mapping[str, str]] = []
    else:
        normalized_source_digests = source_artifact_digests
    source_artifacts = scope.get("source_artifacts")
    normalized_source_artifacts = (
        [item.strip() for item in source_artifacts]
        if isinstance(source_artifacts, list)
        and all(isinstance(item, str) and item.strip() for item in source_artifacts)
        else []
    )
    source_digest_paths = [
        str(record.get("path") or "").strip()
        for record in normalized_source_digests
    ]
    if (
        not normalized_source_artifacts
        or len(set(normalized_source_artifacts)) != len(normalized_source_artifacts)
        or source_digest_paths != normalized_source_artifacts
    ):
        issues.append(
            "semantic review source digest paths do not match source_artifacts"
        )

    expected_review_paths = semantic_review_relpaths(stage)
    scope_artifacts = scope.get("artifacts")
    if not isinstance(scope_artifacts, dict) or any(
        scope_artifacts.get(key) != expected_review_paths[key].as_posix()
        for key in ("collection", "scope", "prompt", "report")
    ):
        issues.append("semantic review scope artifacts do not match canonical paths")

    stored_prompt_sha256 = scope.get("prompt_sha256")
    if not isinstance(stored_prompt_sha256, str) or _SHA256_RE.fullmatch(
        stored_prompt_sha256
    ) is None:
        issues.append("semantic review prompt_sha256 is invalid")
        stored_prompt_sha256 = ""
    elif stored_prompt_sha256 != _sha256_bytes(prompt_bytes):
        issues.append("semantic review prompt SHA-256 does not match scope")

    stored_scope_binding_sha256 = scope.get("scope_binding_sha256")
    expected_scope_binding_sha256 = semantic_review_scope_binding_sha256(scope)
    if stored_scope_binding_sha256 != expected_scope_binding_sha256:
        issues.append("semantic review scope binding SHA-256 mismatch")

    stored_input_digest = scope.get("semantic_review_input_digest")
    if not isinstance(stored_input_digest, str) or _SHA256_DIGEST_RE.fullmatch(
        stored_input_digest
    ) is None:
        issues.append("semantic review input digest is invalid")
        stored_input_digest = ""

    request_revision = scope.get("request_revision")
    if request_revision is not None and (
        not isinstance(request_revision, str) or not request_revision.strip()
    ):
        issues.append("semantic review request revision is invalid")
        request_revision = None

    if (
        normalized_entry_ids
        and isinstance(stored_collection_sha256, str)
        and stored_prompt_sha256
        and normalized_source_digests
        and isinstance(stored_scope_binding_sha256, str)
    ):
        expected_input_digest = semantic_review_input_digest(
            stage=stage,
            entry_ids=normalized_entry_ids,
            collection_sha256=stored_collection_sha256,
            prompt_sha256=stored_prompt_sha256,
            source_artifact_digests=normalized_source_digests,
            request_revision=(
                request_revision.strip()
                if isinstance(request_revision, str)
                else None
            ),
            scope_binding_sha256=stored_scope_binding_sha256,
        )
        if stored_input_digest != expected_input_digest:
            issues.append(
                "semantic review input digest does not match canonical scope inputs"
            )

    report_text = report_bytes.decode("utf-8", errors="replace")
    report_input_digests = _semantic_report_input_digests(report_text)
    if len(report_input_digests) != 1:
        issues.append(
            "semantic review report must contain exactly one input digest"
        )
    elif report_input_digests[0] != stored_input_digest:
        issues.append("semantic review report input digest does not match scope")

    return scope, tuple(issues)


def _read_semantic_review_snapshot_once(
    run_dir: Path,
    stage: str,
    *,
    expected_root_identity: tuple[int, int] | None,
) -> tuple[dict[str, bytes], dict[str, Any] | None, tuple[str, ...]]:
    review_paths = semantic_review_relpaths(stage)
    artifacts: dict[str, bytes] = {}
    for key in ("collection", "prompt", "scope", "report"):
        artifacts[key] = read_regular_file_nofollow(
            run_dir,
            review_paths[key],
            expected_root_identity=expected_root_identity,
        )
    scope, issues = _semantic_review_snapshot_relationship_issues(
        stage=stage,
        collection_bytes=artifacts["collection"],
        prompt_bytes=artifacts["prompt"],
        scope_bytes=artifacts["scope"],
        report_bytes=artifacts["report"],
    )
    return artifacts, scope, issues


def _read_semantic_review_source_snapshot(
    run_dir: Path,
    stage: str,
    scope: Mapping[str, Any],
    *,
    expected_root_identity: tuple[int, int] | None,
) -> tuple[dict[str, bytes], tuple[str, ...]]:
    raw_records = scope.get("source_artifact_digests")
    if not isinstance(raw_records, list):
        return {}, ("semantic review source digest records are missing",)
    source_bytes: dict[str, bytes] = {}
    issues: list[str] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            issues.append("semantic review source digest record is invalid")
            continue
        raw_path = raw_record.get("path")
        raw_sha256 = raw_record.get("sha256")
        raw_policy = raw_record.get(REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD)
        if not isinstance(raw_path, str) or not raw_path.strip():
            issues.append("semantic review source digest path is invalid")
            continue
        if not isinstance(raw_sha256, str) or _SHA256_RE.fullmatch(raw_sha256) is None:
            issues.append(
                f"semantic review source digest SHA-256 is invalid: {raw_path}"
            )
            continue
        if raw_path in source_bytes:
            issues.append(f"semantic review source digest path is duplicated: {raw_path}")
            continue
        try:
            content = read_regular_file_nofollow(
                run_dir,
                Path(raw_path),
                expected_root_identity=expected_root_identity,
            )
            if raw_policy is None:
                current_sha256 = _sha256_bytes(content)
            else:
                fingerprint = review_source_fingerprint_bytes(
                    content,
                    artifact_relpath=raw_path,
                    review_kind="semantic",
                    stage=stage,
                )
                if raw_policy != fingerprint.policy:
                    issues.append(
                        f"semantic review source fingerprint policy mismatch: {raw_path}"
                    )
                current_sha256 = fingerprint.sha256
        except (FileNotFoundError, OSError, ValueError, ReviewProjectionError) as exc:
            issues.append(f"cannot read semantic review source {raw_path}: {exc}")
            continue
        source_bytes[raw_path] = content
        if current_sha256 != raw_sha256:
            issues.append(f"semantic review source SHA-256 mismatch: {raw_path}")
    return source_bytes, tuple(issues)


def _read_consistent_semantic_review_snapshot(
    run_dir: Path,
    stage: str,
    *,
    expected_root_identity: tuple[int, int] | None,
) -> dict[str, Any]:
    last_issues: tuple[str, ...] = ()
    for _attempt in range(DEFAULT_SEMANTIC_REPAIR_SNAPSHOT_ATTEMPTS):
        try:
            first_artifacts, first_scope, relationship_issues = (
                _read_semantic_review_snapshot_once(
                    run_dir,
                    stage,
                    expected_root_identity=expected_root_identity,
                )
            )
            first_source_bytes, first_source_issues = (
                _read_semantic_review_source_snapshot(
                    run_dir,
                    stage,
                    first_scope or {},
                    expected_root_identity=expected_root_identity,
                )
            )
            second_artifacts, second_scope, second_relationship_issues = (
                _read_semantic_review_snapshot_once(
                    run_dir,
                    stage,
                    expected_root_identity=expected_root_identity,
                )
            )
            second_source_bytes, second_source_issues = (
                _read_semantic_review_source_snapshot(
                    run_dir,
                    stage,
                    second_scope or {},
                    expected_root_identity=expected_root_identity,
                )
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            last_issues = (str(exc),)
            continue

        if first_artifacts != second_artifacts:
            last_issues = (
                "semantic review collection/scope/report changed while snapshot was read",
            )
            continue
        if relationship_issues or second_relationship_issues:
            last_issues = tuple(
                dict.fromkeys([*relationship_issues, *second_relationship_issues])
            )
            continue
        if first_source_bytes != second_source_bytes:
            last_issues = (
                "semantic review source artifacts changed while snapshot was read",
            )
            continue
        if first_source_issues or second_source_issues:
            last_issues = tuple(
                dict.fromkeys([*first_source_issues, *second_source_issues])
            )
            continue
        if first_scope is None or second_scope is None or first_scope != second_scope:
            last_issues = ("semantic review scope changed while snapshot was read",)
            continue

        source_artifact_digests = second_scope.get("source_artifact_digests")
        return {
            "collection_bytes": second_artifacts["collection"],
            "scope_bytes": second_artifacts["scope"],
            "report_bytes": second_artifacts["report"],
            "collection_sha256": _sha256_bytes(second_artifacts["collection"]),
            "review_prompt_sha256": _sha256_bytes(second_artifacts["prompt"]),
            "scope_sha256": _sha256_bytes(second_artifacts["scope"]),
            "report_sha256": _sha256_bytes(second_artifacts["report"]),
            "semantic_review_input_digest": second_scope[
                "semantic_review_input_digest"
            ],
            "source_artifact_digests": source_artifact_digests,
        }

    detail = "; ".join(last_issues) or "review inputs were unavailable"
    raise RuntimeError(
        f"could not capture a consistent semantic review snapshot for {stage}: {detail}"
    )


def _semantic_repair_commit_payload(
    *,
    stage: str,
    round_number: int,
    status: str,
    created_at: str,
    relpaths: Mapping[str, Path],
    review_snapshot: Mapping[str, Any] | None = None,
    prompt_bytes: bytes | None = None,
    report_bytes: bytes | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SEMANTIC_REPAIR_COMMIT_SCHEMA,
        "status": status,
        "stage": stage,
        "round_number": round_number,
        "created_at": created_at,
    }
    if status == "committed":
        if review_snapshot is None or prompt_bytes is None or report_bytes is None:
            raise ValueError("committed semantic repair payload requires exact bytes")
        payload["review_snapshot"] = {
            "semantic_review_input_digest": review_snapshot[
                "semantic_review_input_digest"
            ],
            "collection_sha256": review_snapshot["collection_sha256"],
            "review_prompt_sha256": review_snapshot[
                "review_prompt_sha256"
            ],
            "scope_sha256": review_snapshot["scope_sha256"],
            "report_sha256": review_snapshot["report_sha256"],
            "source_artifact_digests": review_snapshot[
                "source_artifact_digests"
            ],
        }
        payload["artifacts"] = {
            "prompt": {
                "path": relpaths["prompt"].as_posix(),
                "sha256": _sha256_bytes(prompt_bytes),
            },
            "report": {
                "path": relpaths["report"].as_posix(),
                "sha256": _sha256_bytes(report_bytes),
            },
        }
    return payload


def _commit_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ) + "\n"


def read_committed_semantic_repair_prompt(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    expected_root_identity: tuple[int, int] | None = None,
) -> str:
    """Return prompt text only when its full repair pair commit still validates."""

    relpaths = semantic_repair_relpaths(stage, round_number)
    try:
        commit_bytes = read_regular_file_nofollow(
            run_dir,
            relpaths["commit"],
            expected_root_identity=expected_root_identity,
        )
        raw_commit = json.loads(commit_bytes.decode("utf-8"))
        if not isinstance(raw_commit, dict):
            raise ValueError("commit manifest must be a JSON object")
        commit: dict[str, Any] = raw_commit
        if commit.get("schema_version") != SEMANTIC_REPAIR_COMMIT_SCHEMA:
            raise ValueError("commit manifest schema is invalid")
        if commit.get("status") != "committed":
            raise ValueError("commit manifest is not committed")
        if commit.get("stage") != stage or commit.get("round_number") != round_number:
            raise ValueError("commit manifest stage or round does not match")

        artifacts = commit.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("commit manifest artifacts are missing")
        artifact_bytes: dict[str, bytes] = {}
        for key in ("prompt", "report"):
            record = artifacts.get(key)
            if not isinstance(record, dict):
                raise ValueError(f"commit manifest {key} record is missing")
            if record.get("path") != relpaths[key].as_posix():
                raise ValueError(f"commit manifest {key} path does not match")
            stored_sha256 = record.get("sha256")
            if not isinstance(stored_sha256, str) or _SHA256_RE.fullmatch(
                stored_sha256
            ) is None:
                raise ValueError(f"commit manifest {key} SHA-256 is invalid")
            artifact_bytes[key] = read_regular_file_nofollow(
                run_dir,
                relpaths[key],
                expected_root_identity=expected_root_identity,
            )
            if _sha256_bytes(artifact_bytes[key]) != stored_sha256:
                raise ValueError(f"commit manifest {key} SHA-256 does not match")

        review_snapshot = commit.get("review_snapshot")
        if not isinstance(review_snapshot, dict):
            raise ValueError("commit manifest review snapshot is missing")
        current_snapshot = _read_consistent_semantic_review_snapshot(
            run_dir,
            stage,
            expected_root_identity=expected_root_identity,
        )
        for key in (
            "semantic_review_input_digest",
            "collection_sha256",
            "review_prompt_sha256",
            "scope_sha256",
            "report_sha256",
            "source_artifact_digests",
        ):
            if review_snapshot.get(key) != current_snapshot.get(key):
                raise ValueError(
                    f"commit manifest review snapshot {key} no longer matches"
                )

        if (
            read_regular_file_nofollow(
                run_dir,
                relpaths["commit"],
                expected_root_identity=expected_root_identity,
            )
            != commit_bytes
        ):
            raise ValueError("commit manifest changed while it was consumed")
        return artifact_bytes["prompt"].decode("utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            f"committed semantic repair pair is unavailable for {stage} round {round_number}: {exc}"
        ) from exc


def write_semantic_repair_prompt(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    max_attempts: int,
    errors: list[str] | tuple[str, ...],
    expected_root_identity: tuple[int, int] | None = None,
) -> dict[str, Path]:
    relpaths = semantic_repair_relpaths(stage, round_number)
    prompt_path = run_dir / relpaths["prompt"]
    report_path = run_dir / relpaths["report"]
    commit_path = run_dir / relpaths["commit"]
    review_paths = semantic_review_relpaths(stage)
    review_snapshot = _read_consistent_semantic_review_snapshot(
        run_dir,
        stage,
        expected_root_identity=expected_root_identity,
    )
    review_report = review_snapshot["report_bytes"].decode(
        "utf-8", errors="replace"
    )
    collection_text = review_snapshot["collection_bytes"].decode(
        "utf-8", errors="replace"
    )
    failed_selectors = sorted(_semantic_review_failed_selectors(review_report))
    failed_selector_text = "\n".join(f"- `{selector}`" for selector in failed_selectors) or "- `(not parsed; use failed report findings)`"
    collection_excerpt = _semantic_collection_excerpt(collection_text, review_report)
    target = SEMANTIC_REVIEW_PRODUCER_TARGETS.get(stage, {})
    owner = str(target.get("owner") or f"{stage} producer")
    slot = str(target.get("slot") or "")
    focus = str(target.get("focus") or "stage semantic contract")
    artifacts = [str(item) for item in target.get("artifacts", [])] if isinstance(target.get("artifacts"), list) else []
    error_text = "\n".join(f"- {error}" for error in errors) or "- semantic reviewer did not provide a specific error"
    source_digest_text = json.dumps(
        review_snapshot["source_artifact_digests"],
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    stage_specific_repair = ""
    if stage in {"research", "story"}:
        editable_artifact = "research.md" if stage == "research" else "story.md"
        locked_artifact = "" if stage == "research" else " `research.md` is approved upstream input and must not be edited during story repair."
        story_time_of_day_repair = "" if stage == "research" else """
- Restore every current-contract story scene `time_of_day` at its canonical `story.md` source as an open, non-empty string. Preserve authored causal transitions, and do not infer it from location or image-prompt prose.
- Keep the scene daypart separate from historical `story_metadata.time`: daypart controls sky, natural/artificial light, shadow, and color temperature, while historical time controls clothing, architecture, materials, tools, and technology.
- When a scene declares `location.mode: sequence`, restore one complete `location.segments[]` item for every ordered `location.sequence[]` item. Preserve exact location order and give each segment its own responsibility, primary subject, visible action, required evidence/roles, motion brief, and physical motion end state.
- Do not invent a transition, merge two locations into one scene-wide action, or remove an authored route merely to pass validation. Repair only the missing or contradictory route fields at the canonical `story.md` scene.
"""
        stage_specific_repair = f"""
## Foundation Repair Boundary

- Edit only `{editable_artifact}`.{locked_artifact}
- Repair internal story sufficiency and consistency only. Do not browse, fetch, or validate external URLs, editions, translations, rights, or factual fidelity.
- Preserve the requested target duration and keep research/story responsibilities separate from cut, image, audio, or video authoring.
- Preserve the existing Markdown fenced YAML structure. Quote any scalar containing `: ` so the YAML remains parseable.
- After editing, use `toc.harness.load_structured_document` on `{run_dir / editable_artifact}` and do not finish while it returns an empty mapping.
- Do not delegate this repair. You must make the targeted edit, validate the structured round trip, and write the producer repair report yourself.
{story_time_of_day_repair}
"""
    elif stage in {"scene_set", "scene_detail", "cut_blueprint"}:
        stage_specific_repair = """
## Scene Time-of-Day Repair Boundary

- Treat each scene-level `time_of_day` as the authored daypart and keep it an open, non-empty string for current-contract artifacts. Values such as 朝, 昼, 夕方, 夜, 夜明け前, and 真夜中 are valid; do not reduce the field to a fixed enum.
- Use the review entry's `time_of_day_contract_declared` and `time_of_day_status`: the contract is declared only by metadata marker `scene_time_of_day_contract: required_v1`. Repair missing/blank values only when declared, always repair invalid_type, and do not rewrite an undeclared legacy artifact solely to add this newer key.
- Keep historical `story_metadata.time` / `script_metadata.time` / `video_metadata.time` separate. A daypart repair controls sky brightness, natural and artificial light, shadows, and color temperature; it must not change historical clothing, architecture, materials, or technology.
- Preserve scene order and authored transitions. If adjacent scenes change daypart, make the transition causally legible; do not infer or overwrite `time_of_day` from a location description or prompt prose.
- Repair the earliest stage-owned scene projection, then keep the same value through downstream script/manifest projections. For a cut finding, fix the scene-level source and cut-local light plan rather than inventing a second historical-time field.
"""
    elif stage == "asset_plan":
        stage_specific_repair = """
## Asset Plan Repair Boundary

- Treat `video_manifest.md.assets` as the canonical editable asset bible. Repair character, object, location, style, output, reference, and prompt-source contracts there, and keep `asset_inventory.md` aligned with the repaired coverage.
- `asset_plan.md`, `asset_generation_manifest.md`, `asset_generation_requests.md`, and `asset_generation_request_snapshot.json` are compiler/materializer projections. Do not hand-edit `asset_generation_requests.md` or any of those derived files; the orchestrator will rebuild them from the canonical manifest after this repair.
- Preserve every current scene/cut dependency while changing only the failed asset ids. Do not delete an asset merely to remove a finding, and do not attach an unrelated reference to make coverage appear complete.
- Keep historical time and asset identity constraints at the canonical bible source. The orchestrator will compile the provider prompt, request digest, snapshot, and provenance contract from that source.
"""
    elif stage == "image_prompt":
        stage_specific_repair = """
## Image Prompt Repair Boundary

- Treat `video_manifest.md` `image_generation.first_frame_visual_plan` plus the cut-local character/object/location ids and references as the editable source of truth.
- For every failed selector, make an explicit `include / omit / add / replace` decision: include only drawable facts needed in this still, omit downstream motion/design metadata/unneeded references, add visible behavior or period detail required to make the source meaning imageable, and replace abstract or contradictory prose without changing the story event.
- Do not hand-edit `api_prompt_payload.prompt`, `image_generation_requests.md`, or `image_generation_request_snapshot.json`; they are compiler/materializer outputs. The orchestrator recompiles and re-freezes them after this repair.
- When a positive must-show/current-state instruction also appears in `not_yet_happened_in_still`, keep the positive source fact and remove or rewrite the invalid negative projection. Preserve genuine later-event and reveal constraints.
- Check `video_metadata.time`: when non-empty, the repaired plan and dependencies must allow the compiler to keep period-accurate clothing, architecture, everyday objects, materials, and technology in the provider prompt.
- Check `scene.time_of_day` separately from `video_metadata.time`. The required contract is declared only by `video_metadata.scene_time_of_day_contract: required_v1`; use `time_of_day_contract_declared` / `time_of_day_status` to repair current-contract missing, blank, or invalid values without forcing this newer key into an undeclared legacy artifact. When valid, preserve the authored daypart and repair sky brightness, natural-light direction and intensity, shadows, color temperature, and artificial lighting so they agree with it. Do not use a daypart repair to change the historical era.
- If a visibly required character, object, or location lacks an id/reference, repair the cut dependency and the matching `video_manifest.md.assets` bible entry rather than merely naming it in prose. Do not attach scene-wide assets that are not visible in this cut.
- Keep `scene_event` as the event canon. Do not change what happened in the story to make an image prompt pass.
- Align the API prompt with the cut's designed visual role: `scene_cut_coverage_plan.cut_assignments`, `scene_film_coverage_plan`, and `scene_shot_mix_plan` are the comparison targets.
- If the failure is film-role alignment, fix the visual implementation fields together so `shot_role`, `shot_scale`, location zone, visible subject, object detail, reaction behavior, and handoff path agree; the orchestrator will render the paired API prompt.
"""
    elif stage == "video_motion":
        stage_specific_repair = """
## Video Motion Repair Boundary

- Treat `video_manifest.md` `cut_contract.motion_contract`, `continuity_contract`, the approved first-frame boundary, and `video_input_contract.reference_roles` as the editable canonical sources.
- For every failed selector, make an explicit `include / omit / add / replace` decision for start state, one primary motion, camera, independent environment motion, visible emotional change, physical end state, continuity, constraints, and reference-role use.
- Do not hand-edit `api_prompt_payload.prompt`, `video_generation.motion_prompt`, or `video_generation_requests.md`; they are compiler/materializer outputs. The orchestrator will recompile, refresh the digest, rematerialize the request artifact, and run semantic review again.
- Repair every blocking `quality_issues[]` item at its canonical source. Do not delete diagnostics, copy compiler fallback prose into the contract, or hide unresolved alternatives.
- Make the primary action name one visible subject and one observable action. Make the end state say who or what stops where and in which physical state. Keep environment and emotion independent from the primary action.
- Compare failed selectors with neighboring cuts in the same scene. Replace exact or near-duplicate primary motions and end states with obligation-specific actions without crossing the assigned event beat, location, reveal, or first/last-frame boundary.
- Keep historical time and scene daypart stable. A motion repair must not introduce an unauthored time-lapse, lighting transition, costume change, architecture change, or technology mismatch.
- Keep `video_input_contract.reference_roles` aligned one-to-one with ordered references. Repair count, 1-based index, order, and semantic role at the contract; never put a file path or asset id into provider prose.
"""

    prompt = f"""# Semantic QA Producer Repair: {stage}

You are the original production-side agent for `{stage}` in this ToC run.

The contextless semantic review agent rejected the current artifact. Use the review findings as improvement instructions, repair the production artifacts, and leave the process in semantic-QA repair state.

This is a real semantic repair, not a bypass. Do not advance the process slot to the next stage. Do not edit `state.txt`, `run_status.json`, or `p000_index.md`; the orchestrator is the only writer for process state. Do not edit any `logs/review/semantic/*` files except the producer repair report named below. In particular, do not edit the semantic review report, collection, scope, or prompt to fake a pass; the orchestrator will rebuild the pack and call the semantic reviewer again from the production artifacts.

- Run directory: `{run_dir}`
- Current semantic stage: `{stage}`
- Process slot kept in semantic QA: `{slot or "(stage-owned slot)"}`
- Repair round: `{round_number}` of `{max_attempts - 1}`
- Producing owner: `{owner}`
- Repair focus: {focus}
- Primary editable artifacts: {", ".join(artifacts) if artifacts else "(stage-owned artifacts)"}
- Non-editable state/navigation artifacts: `state.txt`, `run_status.json`, `p000_index.md`
- Non-editable review artifacts: `logs/review/semantic/{stage}.collection.md`, `logs/review/semantic/{stage}.scope.json`, `logs/review/semantic/{stage}.prompt.md`, `logs/review/semantic/{stage}.report.md`
- Producer repair report to write: `{relpaths["report"].as_posix()}`

## Reviewer Findings / Gate Errors

{error_text}

## Target Failed Selectors

{failed_selector_text}

## Bound Semantic Review Snapshot

- semantic_review_input_digest: `{review_snapshot["semantic_review_input_digest"]}`
- collection_sha256: `{review_snapshot["collection_sha256"]}`
- review_prompt_sha256: `{review_snapshot["review_prompt_sha256"]}`
- scope_sha256: `{review_snapshot["scope_sha256"]}`
- report_sha256: `{review_snapshot["report_sha256"]}`
- source_artifact_digests:

```json
{source_digest_text}
```

This repair prompt is valid only for the exact review snapshot and source digests above. If any bound artifact has changed, stop and require the orchestrator to rebuild the repair prompt from a fresh semantic review.

## Failed Semantic Review Report

```text
{review_report[:16000]}
```

## Review Scope

- collection: `{review_paths["collection"].as_posix()}`
- scope: `{review_paths["scope"].as_posix()}`
- report: `{review_paths["report"].as_posix()}`

{stage_specific_repair}

## Collection Excerpt

```text
{collection_excerpt}
```

## Required Work

1. Treat every `blocked_entries`, `failed_selectors`, `findings`, and `reason_keys` item in the failed semantic report as a required fix.
2. Repair the production artifact(s) so the reviewed meaning is genuinely correct. If a previous repair only partially fixed the stage, focus on the remaining failed selectors rather than rewriting already-passed entries.
3. Preserve existing structure and paths unless a reviewer finding requires a targeted change.
4. If this stage owns generated media, update prompts/contracts and regenerate the affected media through the repository's canonical tooling when needed.
5. Before writing your report, inspect the edited production artifacts for the rejected meaning and remove contradictory language such as stale withheld/reveal/order/object continuity instructions.
6. Keep the stage visible as semantic-QA repair, not as approved or advanced.
7. Stay narrowly scoped: read only the listed run artifacts and the failed selectors unless a direct dependency is missing. Do not run repo-wide searches, do not print full artifact files to stdout, and do not run commands that can emit thousands of lines.
8. Do not edit passed selectors or unrelated scenes/cuts. For repeated generic wording, never use broad search-and-replace or a patch that can match the same phrase in multiple selectors. Anchor every edit to the failed selector id, scene id, cut id, asset id, or exact artifact section.
9. After editing, inspect the failed selectors and a small sample of neighboring passed selectors to ensure the repair did not move later-stage meaning into earlier scenes, change reveal order, or mutate unrelated semantic contracts.
10. Write `{relpaths["report"].as_posix()}` immediately after the targeted repair with:
   - `status: done`
   - changed artifacts
   - reviewer findings addressed
   - remaining risks, if any
   Do not include `state.txt`, `run_status.json`, `p000_index.md`, `logs/review/semantic/{stage}.collection.md`, `.scope.json`, `.prompt.md`, or `.report.md` as changed artifacts.

The next action after your repair will be a fresh contextless semantic review. Passing requires the reviewer report to say `status: passed`.
"""
    created_at = now_iso()
    prompt_text = prompt + "\n"
    report_text = (
        f"# Semantic Producer Repair Report: {stage}\n\n"
        f"status: pending\nround: {round_number}\ncreated_at: {created_at}\n\n"
    )
    preparing_commit = _semantic_repair_commit_payload(
        stage=stage,
        round_number=round_number,
        status="preparing",
        created_at=created_at,
        relpaths=relpaths,
    )
    safe_semantic_write_text(
        run_dir,
        commit_path,
        _commit_json(preparing_commit),
        expected_root_identity=expected_root_identity,
    )
    safe_semantic_write_text(
        run_dir,
        prompt_path,
        prompt_text,
        expected_root_identity=expected_root_identity,
    )
    safe_semantic_write_text(
        run_dir,
        report_path,
        report_text,
        expected_root_identity=expected_root_identity,
    )
    committed_payload = _semantic_repair_commit_payload(
        stage=stage,
        round_number=round_number,
        status="committed",
        created_at=created_at,
        relpaths=relpaths,
        review_snapshot=review_snapshot,
        prompt_bytes=prompt_text.encode("utf-8"),
        report_bytes=report_text.encode("utf-8"),
    )
    safe_semantic_write_text(
        run_dir,
        commit_path,
        _commit_json(committed_payload),
        expected_root_identity=expected_root_identity,
    )
    try:
        committed_prompt = read_committed_semantic_repair_prompt(
            run_dir,
            stage,
            round_number=round_number,
            expected_root_identity=expected_root_identity,
        )
    except RuntimeError:
        safe_semantic_write_text(
            run_dir,
            commit_path,
            _commit_json(preparing_commit),
            expected_root_identity=expected_root_identity,
        )
        raise
    if committed_prompt != prompt_text:
        safe_semantic_write_text(
            run_dir,
            commit_path,
            _commit_json(preparing_commit),
            expected_root_identity=expected_root_identity,
        )
        raise RuntimeError("committed semantic repair prompt bytes changed after write")
    return {"prompt": prompt_path, "report": report_path, "commit": commit_path}
