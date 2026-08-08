"""Request-bound projection for localized semantic partial-media failures."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from toc.image_request_snapshot import (
    ImageRequestSnapshotError,
    _snapshot_from_mapping,
    validate_request_snapshot,
)
from toc.run_root_binding import (
    current_run_root_binding,
    read_run_file_bytes,
    run_file_entry_exists,
)
from toc.semantic_review import (
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    parse_judgment_report_status,
    safe_semantic_write_text,
    semantic_report_required_field_issues,
    semantic_review_input_digest,
    semantic_review_relpaths,
    semantic_review_scope_binding_sha256,
)
from toc.review_projection import (
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    ReviewProjectionError,
    review_source_fingerprint_bytes,
)


PARTIAL_MEDIA_SEMANTIC_STAGES = (
    "scene_detail",
    "cut_blueprint",
    "image_prompt",
)
PARTIAL_MEDIA_PROJECTION_SCHEMA = "toc.partial_media_projection.v1"
PARTIAL_MEDIA_RECEIPT_SCHEMA = "toc.partial_media_generation_receipt.v2"
PARTIAL_MEDIA_PROJECTION_RELPATH = Path(
    "logs/review/semantic/partial_media_projection.json"
)
PARTIAL_MEDIA_RECEIPT_RELPATH = Path(
    "logs/review/semantic/partial_media_generation_receipt.json"
)

_SCENE_CUT_RE = re.compile(
    r"scene[_:]?(\d+)[_-]?cut[_:]?0*(\d+)",
    re.IGNORECASE,
)
_SCENE_RE = re.compile(
    r"scene[_:]?(\d+)",
    re.IGNORECASE,
)


class PartialMediaProjectionError(ValueError):
    """Raised when a localized failure cannot be proven fail-closed."""

    def __init__(self, issues: Iterable[str]):
        self.issues = tuple(dict.fromkeys(str(issue) for issue in issues))
        super().__init__("; ".join(self.issues))


def normalize_scene_cut_token(value: Any) -> str:
    raw = str(value or "").strip().strip("`\"'")
    match = _SCENE_CUT_RE.fullmatch(raw)
    if not match:
        return raw
    return f"scene{int(match.group(1))}_cut{int(match.group(2))}"


def normalize_stage_selector(value: Any, *, stage: str) -> str | None:
    """Return the canonical selector key allowed by one semantic stage."""

    raw = str(value or "").strip().strip("`\"'")
    if stage == "cut_blueprint" and raw.lower().startswith("cut:"):
        raw = raw[4:]
    cut_match = _SCENE_CUT_RE.fullmatch(raw)
    if cut_match:
        return (
            f"scene{int(cut_match.group(1))}_cut"
            f"{int(cut_match.group(2))}"
        )
    scene_match = _SCENE_RE.fullmatch(raw)
    if scene_match and stage in {"scene_detail", "image_prompt"}:
        return f"scene:{int(scene_match.group(1))}"
    return None


def _is_canonical_scope_selector(value: Any, *, stage: str) -> bool:
    raw = str(value or "").strip()
    if stage == "scene_detail":
        return re.fullmatch(r"scene:(?:0|[1-9]\d*)", raw) is not None
    if stage == "cut_blueprint":
        return (
            re.fullmatch(
                r"cut:scene(?:0|[1-9]\d*)_cut\d{2,}",
                raw,
            )
            is not None
        )
    if stage == "image_prompt":
        return (
            re.fullmatch(
                r"scene(?:0|[1-9]\d*)(?:_cut\d{2,})?",
                raw,
            )
            is not None
        )
    return False


def _is_allowed_failed_selector(value: Any, *, stage: str) -> bool:
    raw = str(value or "").strip().strip("`\"'")
    if stage == "scene_detail":
        return _SCENE_RE.fullmatch(raw) is not None
    if stage == "cut_blueprint":
        if raw.lower().startswith("cut:"):
            raw = raw[4:]
        return _SCENE_CUT_RE.fullmatch(raw) is not None
    if stage == "image_prompt":
        return (
            _SCENE_CUT_RE.fullmatch(raw) is not None
            or _SCENE_RE.fullmatch(raw) is not None
        )
    return False


def scene_numbers_from_selectors(selectors: Iterable[Any]) -> set[str]:
    scene_numbers: set[str] = set()
    for selector in selectors:
        value = str(selector or "").strip().strip("`\"'")
        cut_match = _SCENE_CUT_RE.fullmatch(value)
        scene_match = _SCENE_RE.fullmatch(value)
        if cut_match:
            scene_numbers.add(str(int(cut_match.group(1))))
        elif scene_match:
            scene_numbers.add(str(int(scene_match.group(1))))
    return scene_numbers


def _item_value(item: Any, *names: str) -> str:
    for name in names:
        if isinstance(item, dict):
            value = item.get(name)
        else:
            value = getattr(item, name, None)
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def image_item_id(item: Any) -> str:
    return _item_value(item, "item_id", "id", "selector")


def image_item_destination(item: Any) -> str:
    return _item_value(item, "destination", "output")


def _image_item_selector_aliases(item: Any) -> set[str]:
    item_id = image_item_id(item)
    destination = image_item_destination(item)
    aliases: set[str] = set()
    for value in (item_id, Path(destination).stem if destination else ""):
        if value:
            aliases.add(value)
            aliases.add(normalize_scene_cut_token(value))
    return {alias for alias in aliases if alias}


def _item_matches_scene_number(item: Any, scene_number: str) -> bool:
    scene_token = f"scene{int(scene_number)}"
    item_id = image_item_id(item).lower()
    output = image_item_destination(item).lower()
    return (
        item_id == scene_token
        or item_id.startswith(f"{scene_token}_")
        or item_id.startswith(f"{scene_token}cut")
        or f"/{scene_token}_" in output
        or f"/{scene_token}cut" in output
    )


def selector_image_item_ids(
    items: Sequence[Any],
    selector: Any,
    *,
    stage: str | None = None,
) -> set[str]:
    """Map one report selector to current request items without widening cuts."""

    raw_selector = str(selector or "").strip().strip("`\"'")
    if stage is not None:
        normalized_selector = normalize_stage_selector(
            raw_selector,
            stage=stage,
        )
        if normalized_selector is None:
            return set()
    else:
        normalized_selector = normalize_scene_cut_token(raw_selector)
    exact_matches = {
        image_item_id(item)
        for item in items
        if normalized_selector in _image_item_selector_aliases(item)
    }
    if exact_matches:
        return {item_id for item_id in exact_matches if item_id}

    if stage not in {None, "scene_detail", "image_prompt"}:
        return set()
    scene_numbers = (
        {normalized_selector.split(":", 1)[1]}
        if normalized_selector.startswith("scene:")
        else scene_numbers_from_selectors((selector,))
    )
    return {
        image_item_id(item)
        for item in items
        if image_item_id(item)
        and any(
            _item_matches_scene_number(item, scene_number)
            for scene_number in scene_numbers
        )
    }


def localize_semantic_failure_selectors(
    *,
    stage: str,
    items: Sequence[Any],
    failed_selectors: Sequence[Any],
    blocked_entries: Sequence[Any],
    scope_entry_ids: Sequence[Any] = (),
    transport_scene_numbers: Iterable[Any] = (),
    require_surviving_item: bool = True,
) -> tuple[set[str], tuple[str, ...]]:
    """Return exact blocked ids only when every failure is fully accounted."""

    if stage not in PARTIAL_MEDIA_SEMANTIC_STAGES:
        return set(), (
            f"{stage} is not eligible for localized partial media",
        )

    normalized_failed = [
        str(value).strip()
        for value in failed_selectors
        if str(value).strip()
    ]
    normalized_blocked = [
        str(value).strip()
        for value in blocked_entries
        if str(value).strip()
    ]
    issues: list[str] = []
    if not normalized_failed:
        issues.append("current failed report has no failed_selectors")
    if not normalized_blocked:
        issues.append("current failed report has no blocked_entries")
    failed_keys = [
        normalize_stage_selector(value, stage=stage)
        for value in normalized_failed
    ]
    blocked_keys = [
        normalize_stage_selector(value, stage=stage)
        for value in normalized_blocked
    ]
    if (
        len(set(normalized_failed)) != len(normalized_failed)
        or len(set(failed_keys)) != len(failed_keys)
    ):
        issues.append("current failed report has duplicate failed_selectors")
    if (
        len(set(normalized_blocked)) != len(normalized_blocked)
        or len(set(blocked_keys)) != len(blocked_keys)
    ):
        issues.append("current failed report has duplicate blocked_entries")

    item_ids = [image_item_id(item) for item in items if image_item_id(item)]
    if not item_ids:
        issues.append("scene request snapshot has no image items")
    if len(set(item_ids)) != len(item_ids):
        issues.append("scene request snapshot has duplicate image item ids")

    def map_selectors(
        selectors: Sequence[str],
        *,
        field: str,
    ) -> set[str]:
        mapped_ids: set[str] = set()
        unmapped: list[str] = []
        for selector in selectors:
            matched = selector_image_item_ids(
                items,
                selector,
                stage=stage,
            )
            if not matched:
                unmapped.append(selector)
            mapped_ids.update(matched)
        if unmapped:
            issues.append(
                f"{field} are not localized to current scene image request "
                "items: "
                + ", ".join(dict.fromkeys(unmapped))
            )
        return mapped_ids

    failed_item_ids = map_selectors(
        normalized_failed,
        field="failed_selectors",
    )
    blocked_item_ids = map_selectors(
        normalized_blocked,
        field="blocked_entries",
    )
    if failed_item_ids != blocked_item_ids:
        issues.append(
            "failed_selectors and blocked_entries do not account for the "
            "same current image items"
        )

    normalized_scope_entries = [
        str(value).strip()
        for value in scope_entry_ids
        if str(value).strip()
    ]
    if normalized_scope_entries:
        normalized_scope_keys = {
            key
            for value in normalized_scope_entries
            if (
                key := normalize_stage_selector(
                    value,
                    stage=stage,
                )
            )
        }
        invalid_scope_entries = [
            value
            for value in normalized_scope_entries
            if not _is_canonical_scope_selector(value, stage=stage)
        ]
        if invalid_scope_entries:
            issues.append(
                "semantic scope contains non-canonical stage selectors: "
                + ", ".join(invalid_scope_entries)
            )
        normalized_scope_key_values = [
            normalize_stage_selector(value, stage=stage)
            for value in normalized_scope_entries
        ]
        if (
            len(set(normalized_scope_entries))
            != len(normalized_scope_entries)
            or len(set(normalized_scope_key_values))
            != len(normalized_scope_key_values)
        ):
            issues.append(
                "semantic scope contains duplicate canonical selectors"
            )
        out_of_scope_failed = [
            selector
            for selector in normalized_failed
            if (
                not _is_allowed_failed_selector(
                    selector,
                    stage=stage,
                )
                or normalize_stage_selector(selector, stage=stage)
                not in normalized_scope_keys
            )
        ]
        if out_of_scope_failed:
            issues.append(
                "failed_selectors are not canonical members of the current "
                "semantic scope: "
                + ", ".join(out_of_scope_failed)
            )
        scope_item_ids = map_selectors(
            normalized_scope_entries,
            field="scope entry_ids",
        )
        if not failed_item_ids.issubset(scope_item_ids):
            issues.append(
                "failed selectors resolve outside the current semantic review "
                "scope"
            )

    normalized_transport_scenes = {
        str(int(str(value).strip()))
        for value in transport_scene_numbers
        if str(value).strip().isdigit()
    }
    if normalized_transport_scenes:
        reported_scene_numbers = scene_numbers_from_selectors(
            [*normalized_failed, *normalized_blocked]
        )
        unreported_transport_scenes = sorted(
            normalized_transport_scenes - reported_scene_numbers,
            key=int,
        )
        if unreported_transport_scenes:
            issues.append(
                "transport-failed scenes are absent from the current failed "
                "report: "
                + ", ".join(
                    f"scene:{scene_number}"
                    for scene_number in unreported_transport_scenes
                )
            )
        transport_item_ids = {
            image_item_id(item)
            for item in items
            if image_item_id(item)
            and any(
                _item_matches_scene_number(item, scene_number)
                for scene_number in normalized_transport_scenes
            )
        }
        if not transport_item_ids:
            issues.append(
                "transport-failed scenes are not localized to current scene "
                "image request items"
            )
        if not transport_item_ids.issubset(blocked_item_ids):
            issues.append(
                "transport-failed scene image items are not fully covered by "
                "blocked_entries"
            )

    if not blocked_item_ids:
        issues.append(
            "failed report localized to zero scene image request items"
        )
    if require_surviving_item and set(item_ids) == blocked_item_ids:
        issues.append(
            "localized partial media requires at least one surviving scene "
            "image request item"
        )
    return blocked_item_ids, tuple(dict.fromkeys(issues))


def _report_list_values(text: str, key: str) -> list[str]:
    values: list[str] = []
    collecting = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(f"{key}:") or stripped.startswith(
            f"- {key}:"
        ):
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                body = inline[1:-1].strip()
                return [
                    value
                    for item in body.split(",")
                    if (
                        value := item.strip().strip("`\"'")
                    )
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


def _normalized_run_relpath(raw_path: Any) -> str:
    value = str(raw_path or "").strip()
    relative = Path(value)
    if (
        not value
        or "\\" in value
        or relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PartialMediaProjectionError(
            (f"partial-media artifact path is unsafe: {value or '(missing)'}",)
        )
    return value


def _read_run_relative_bytes(run_dir: Path, raw_path: Any) -> bytes:
    """Read one regular run-local file through no-follow directory FDs."""

    value = _normalized_run_relpath(raw_path)
    if current_run_root_binding() is not None:
        try:
            return read_run_file_bytes(run_dir, Path(value))
        except (OSError, ValueError) as exc:
            raise PartialMediaProjectionError(
                (
                    "partial-media artifact must be a readable regular "
                    f"non-symlink file: {value}",
                )
            ) from exc
    parts = Path(value).parts
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        current_fd = os.open(
            run_dir.resolve(strict=True),
            directory_flags,
        )
    except OSError as exc:
        raise PartialMediaProjectionError(
            ("partial-media run directory is unreadable",)
        ) from exc
    opened_fds = [current_fd]
    file_fd: int | None = None
    try:
        for component in parts[:-1]:
            current_fd = os.open(
                component,
                directory_flags,
                dir_fd=current_fd,
            )
            opened_fds.append(current_fd)
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            file_flags |= os.O_NONBLOCK
        file_fd = os.open(
            parts[-1],
            file_flags,
            dir_fd=current_fd,
        )
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(file_fd, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise PartialMediaProjectionError(
            (
                "partial-media artifact must be a readable regular "
                f"non-symlink file: {value}",
            )
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for opened_fd in reversed(opened_fds):
            os.close(opened_fd)


def read_run_relative_regular_file_bytes(
    run_dir: Path,
    raw_path: Any,
) -> bytes:
    """Read a regular run-local file without following any symlink component."""

    return _read_run_relative_bytes(run_dir, raw_path)


def run_relative_entry_exists_no_follow(
    run_dir: Path,
    raw_path: Any,
) -> bool:
    """Return whether an exact run-local directory entry exists, without following links."""

    value = _normalized_run_relpath(raw_path)
    if current_run_root_binding() is not None:
        try:
            return run_file_entry_exists(run_dir, Path(value))
        except (OSError, ValueError) as exc:
            raise PartialMediaProjectionError(
                (
                    "partial-media destination ancestry must contain only "
                    f"readable non-symlink directories: {value}",
                )
            ) from exc
    parts = Path(value).parts
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        current_fd = os.open(
            run_dir.resolve(strict=True),
            directory_flags,
        )
    except OSError as exc:
        raise PartialMediaProjectionError(
            ("partial-media run directory is unreadable",)
        ) from exc
    opened_fds = [current_fd]
    try:
        for component in parts[:-1]:
            try:
                current_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=current_fd,
                )
            except FileNotFoundError:
                # A missing ancestor proves that the exact destination entry
                # does not exist yet.  This is the normal pre-generation
                # state; only an existing but unsafe ancestor must fail closed.
                return False
            opened_fds.append(current_fd)
        try:
            os.stat(
                parts[-1],
                dir_fd=current_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return False
        return True
    except OSError as exc:
        raise PartialMediaProjectionError(
            (
                "partial-media destination ancestry must contain only "
                f"readable non-symlink directories: {value}",
            )
        ) from exc
    finally:
        for opened_fd in reversed(opened_fds):
            os.close(opened_fd)


def _semantic_bundle(
    run_dir: Path,
    stage: str,
) -> tuple[dict[str, bytes], dict[str, Any], str]:
    """Capture every canonical and shard artifact exactly once."""

    paths = semantic_review_relpaths(stage)
    canonical_scope_path = paths["scope"].as_posix()
    pending = {
        path.as_posix()
        for path in paths.values()
    }
    scope_paths = {canonical_scope_path}
    captured: dict[str, bytes] = {}
    parsed_scopes: dict[str, dict[str, Any]] = {}
    while pending:
        relpath = sorted(pending)[0]
        pending.remove(relpath)
        if relpath in captured:
            continue
        artifact_bytes = _read_run_relative_bytes(run_dir, relpath)
        captured[relpath] = artifact_bytes
        if relpath not in scope_paths:
            continue
        try:
            raw_scope = json.loads(artifact_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PartialMediaProjectionError(
                (f"{stage} semantic scope is unreadable: {exc}",)
            ) from exc
        if not isinstance(raw_scope, dict):
            raise PartialMediaProjectionError(
                (f"{stage} semantic scope must be an object",)
            )
        parsed_scopes[relpath] = raw_scope
        raw_sources = raw_scope.get("source_artifacts")
        if isinstance(raw_sources, list):
            pending.update(
                str(value).strip()
                for value in raw_sources
                if str(value).strip()
            )
        artifact_map = raw_scope.get("artifacts")
        if isinstance(artifact_map, dict):
            pending.update(
                str(value).strip()
                for value in artifact_map.values()
                if str(value).strip()
            )
        raw_shards = raw_scope.get("shards")
        if isinstance(raw_shards, list):
            for shard in raw_shards:
                shard_artifacts = (
                    shard.get("artifacts")
                    if isinstance(shard, dict)
                    and isinstance(shard.get("artifacts"), dict)
                    else {}
                )
                shard_paths = {
                    str(value).strip()
                    for value in shard_artifacts.values()
                    if str(value).strip()
                }
                pending.update(shard_paths)
                shard_scope_path = str(
                    shard_artifacts.get("scope") or ""
                ).strip()
                if shard_scope_path:
                    scope_paths.add(shard_scope_path)

    scope = parsed_scopes.get(canonical_scope_path)
    if scope is None:
        raise PartialMediaProjectionError(
            (f"{stage} canonical semantic scope was not captured",)
        )
    try:
        report_text = captured[
            paths["report"].as_posix()
        ].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PartialMediaProjectionError(
            (f"{stage} semantic report is not UTF-8",)
        ) from exc
    return captured, scope, report_text


def _report_scalar_values(text: str, key: str) -> list[str]:
    pattern = re.compile(
        rf"^-?\s*{re.escape(key)}\s*:\s*(.*?)\s*$"
    )
    return [
        match.group(1).strip().strip("`").strip()
        for raw in text.splitlines()
        if (match := pattern.match(raw.strip()))
    ]


def _captured_scope_report_issues(
    *,
    stage: str,
    scope: Mapping[str, Any],
    report_text: str,
    captured: Mapping[str, bytes],
    scope_relpath: str,
    report_relpath: str,
    require_failed: bool,
) -> list[str]:
    """Validate one scope/report view using only its captured byte map."""

    issues: list[str] = []
    if str(scope.get("stage") or "").strip() != stage:
        issues.append(
            f"{scope_relpath}: semantic scope stage must be {stage}"
        )
    entry_ids = scope.get("entry_ids")
    if (
        not isinstance(entry_ids, list)
        or not entry_ids
        or any(
            not isinstance(entry_id, str) or not entry_id.strip()
            for entry_id in entry_ids
        )
        or len(set(entry_ids)) != len(entry_ids)
    ):
        issues.append(
            f"{scope_relpath}: semantic scope has invalid entry_ids"
        )
        entry_ids = []
    if scope.get("entry_count") != len(entry_ids):
        issues.append(
            f"{scope_relpath}: entry_count does not match entry_ids"
        )
    if (
        scope.get("semantic_review_input_schema")
        != SEMANTIC_REVIEW_INPUT_SCHEMA
    ):
        issues.append(
            f"{scope_relpath}: unsupported semantic review input schema"
        )

    artifacts = scope.get("artifacts")
    if not isinstance(artifacts, dict):
        issues.append(
            f"{scope_relpath}: semantic scope is missing artifacts"
        )
        artifacts = {}
    for key in ("collection", "scope", "prompt", "report"):
        value = str(artifacts.get(key) or "").strip()
        if not value or value not in captured:
            issues.append(
                f"{scope_relpath}: artifacts.{key} is not captured"
            )
    if str(artifacts.get("scope") or "") != scope_relpath:
        issues.append(
            f"{scope_relpath}: artifacts.scope does not match checked scope"
        )
    if str(artifacts.get("report") or "") != report_relpath:
        issues.append(
            f"{scope_relpath}: artifacts.report does not match checked report"
        )

    source_artifacts = scope.get("source_artifacts")
    if not isinstance(source_artifacts, list):
        issues.append(
            f"{scope_relpath}: semantic scope is missing source_artifacts"
        )
        source_artifacts = []
    normalized_sources = [
        str(value).strip()
        for value in source_artifacts
        if isinstance(value, str) and str(value).strip()
    ]
    if (
        len(normalized_sources) != len(source_artifacts)
        or len(set(normalized_sources)) != len(normalized_sources)
    ):
        issues.append(
            f"{scope_relpath}: source_artifacts are invalid or duplicated"
        )

    raw_records = scope.get("source_artifact_digests")
    records: list[dict[str, str]] = []
    if not isinstance(raw_records, list):
        issues.append(
            f"{scope_relpath}: source_artifact_digests must be an array"
        )
        raw_records = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            issues.append(
                f"{scope_relpath}: source digest record {index} is invalid"
            )
            continue
        source_path = str(raw_record.get("path") or "").strip()
        expected_sha256 = str(
            raw_record.get("sha256") or ""
        ).strip()
        policy = raw_record.get(
            REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD
        )
        source_bytes = captured.get(source_path)
        if source_bytes is None:
            issues.append(
                f"{scope_relpath}: source is not captured: {source_path}"
            )
            actual_sha256 = ""
        elif policy is None:
            actual_sha256 = hashlib.sha256(source_bytes).hexdigest()
        else:
            try:
                fingerprint = review_source_fingerprint_bytes(
                    source_bytes,
                    artifact_relpath=source_path,
                    review_kind="semantic",
                    stage=stage,
                )
            except ReviewProjectionError as exc:
                issues.append(
                    f"{scope_relpath}: source projection is invalid: "
                    f"{source_path}: {exc}"
                )
                actual_sha256 = ""
            else:
                if str(policy) != fingerprint.policy:
                    issues.append(
                        f"{scope_relpath}: source fingerprint policy "
                        f"mismatch: {source_path}"
                    )
                actual_sha256 = fingerprint.sha256
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            issues.append(
                f"{scope_relpath}: source SHA-256 is invalid: {source_path}"
            )
        elif expected_sha256 != actual_sha256:
            issues.append(
                f"{scope_relpath}: source SHA-256 mismatch: {source_path}"
            )
        record = {
            "path": source_path,
            "sha256": expected_sha256,
        }
        if policy is not None:
            record[REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD] = str(
                policy
            )
        records.append(record)
    if [record["path"] for record in records] != normalized_sources:
        issues.append(
            f"{scope_relpath}: source digest paths do not exactly match "
            "source_artifacts"
        )

    collection_relpath = str(
        artifacts.get("collection") or ""
    ).strip()
    prompt_relpath = str(artifacts.get("prompt") or "").strip()
    for key, relpath in (
        ("collection", collection_relpath),
        ("prompt", prompt_relpath),
    ):
        expected = str(scope.get(f"{key}_sha256") or "").strip()
        content = captured.get(relpath)
        actual = (
            hashlib.sha256(content).hexdigest()
            if content is not None
            else ""
        )
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            issues.append(
                f"{scope_relpath}: {key}_sha256 is invalid"
            )
        elif expected != actual:
            issues.append(
                f"{scope_relpath}: {key} SHA-256 mismatch"
            )

    stored_binding = str(
        scope.get("scope_binding_sha256") or ""
    ).strip()
    if stored_binding != semantic_review_scope_binding_sha256(scope):
        issues.append(
            f"{scope_relpath}: scope binding SHA-256 mismatch"
        )
    request_revision = scope.get("request_revision")
    if request_revision is not None and (
        not isinstance(request_revision, str)
        or not request_revision.strip()
    ):
        issues.append(
            f"{scope_relpath}: request_revision must be non-empty"
        )
        request_revision = None
    stored_digest = str(
        scope.get("semantic_review_input_digest") or ""
    ).strip()
    expected_digest = semantic_review_input_digest(
        stage=stage,
        entry_ids=entry_ids,
        collection_sha256=str(
            scope.get("collection_sha256") or ""
        ),
        prompt_sha256=str(scope.get("prompt_sha256") or ""),
        source_artifact_digests=records,
        request_revision=(
            request_revision
            if isinstance(request_revision, str)
            else None
        ),
        scope_binding_sha256=stored_binding,
    )
    if stored_digest != expected_digest:
        issues.append(
            f"{scope_relpath}: semantic input digest mismatch"
        )

    issues.extend(
        f"{report_relpath}: {issue}"
        for issue in semantic_report_required_field_issues(
            report_text,
            require_digest=True,
        )
    )
    report_digests = _report_scalar_values(
        report_text,
        "semantic_review_input_digest",
    )
    if report_digests != [stored_digest]:
        issues.append(
            f"{report_relpath}: report semantic input digest mismatch"
        )
    status = parse_judgment_report_status(report_text)
    if require_failed:
        if status != "failed":
            issues.append(
                f"{report_relpath}: semantic status must be failed"
            )
    elif status not in {"passed", "failed"}:
        issues.append(
            f"{report_relpath}: semantic status must be terminal"
        )
    reviewed_entries = _report_list_values(
        report_text,
        "reviewed_entries",
    )
    if reviewed_entries != entry_ids:
        issues.append(
            f"{report_relpath}: reviewed_entries coverage mismatch"
        )
    blocked_entries = _report_list_values(
        report_text,
        "blocked_entries",
    )
    failed_selectors = _report_list_values(
        report_text,
        "failed_selectors",
    )
    if status == "passed" and (
        blocked_entries or failed_selectors
    ):
        issues.append(
            f"{report_relpath}: passed review contains failures"
        )
    if "`...`" in report_text or "- `...`" in report_text:
        issues.append(
            f"{report_relpath}: report contains template placeholders"
        )
    return issues


def _captured_shard_issues(
    *,
    stage: str,
    canonical_scope: Mapping[str, Any],
    captured: Mapping[str, bytes],
) -> list[str]:
    shards = canonical_scope.get("shards")
    review_scope = str(
        canonical_scope.get("review_scope") or "all_entries"
    ).strip()
    if shards is None:
        return (
            ["per_scene_shards scope requires non-empty shards"]
            if review_scope == "per_scene_shards"
            else []
        )
    if not isinstance(shards, list):
        return ["semantic review shards must be an array"]
    if review_scope == "per_scene_shards" and not shards:
        return ["per_scene_shards scope requires non-empty shards"]

    issues: list[str] = []
    canonical_entry_ids = [
        str(value).strip()
        for value in canonical_scope.get("entry_ids", [])
    ]
    canonical_paths = semantic_review_relpaths(stage)
    canonical_scope_rel = canonical_paths["scope"].as_posix()
    canonical_report_rel = canonical_paths["report"].as_posix()
    seen_shard_ids: set[str] = set()
    seen_artifact_paths: set[str] = set()
    assigned_entry_ids: list[str] = []
    aggregate_blocked_entries: list[str] = []
    aggregate_reason_keys: list[str] = []

    def extend_unique(target: list[str], values: Iterable[str]) -> None:
        for value in values:
            if value and value not in target:
                target.append(value)

    for index, shard in enumerate(shards, start=1):
        if not isinstance(shard, dict):
            issues.append(
                f"semantic review shard {index} must be an object"
            )
            continue
        shard_id = str(shard.get("shard_id") or "").strip()
        scene_id = str(shard.get("scene_id") or "").strip()
        raw_entry_ids = shard.get("entry_ids")
        entry_ids = (
            [str(value).strip() for value in raw_entry_ids]
            if isinstance(raw_entry_ids, list)
            else []
        )
        if not shard_id or shard_id in seen_shard_ids:
            issues.append(
                f"semantic review shard {index} has invalid shard_id"
            )
        seen_shard_ids.add(shard_id)
        if not scene_id:
            issues.append(
                f"semantic review shard {index} has no scene_id"
            )
        if (
            not entry_ids
            or any(not value for value in entry_ids)
            or len(set(entry_ids)) != len(entry_ids)
            or shard.get("entry_count") != len(entry_ids)
        ):
            issues.append(
                f"semantic review shard {index} has invalid entry coverage"
            )
        assigned_entry_ids.extend(entry_ids)
        artifacts = shard.get("artifacts")
        if not isinstance(artifacts, dict):
            issues.append(
                f"semantic review shard {index} is missing artifacts"
            )
            continue
        for key in ("collection", "scope", "prompt", "report"):
            relpath = str(artifacts.get(key) or "").strip()
            if (
                not relpath
                or relpath in seen_artifact_paths
                or relpath in {canonical_scope_rel, canonical_report_rel}
            ):
                issues.append(
                    f"semantic review shard {index} has invalid {key} path"
                )
            seen_artifact_paths.add(relpath)
        scope_relpath = str(artifacts.get("scope") or "").strip()
        report_relpath = str(artifacts.get("report") or "").strip()
        try:
            shard_scope = json.loads(
                captured[scope_relpath].decode("utf-8")
            )
            shard_report = captured[report_relpath].decode("utf-8")
        except (
            KeyError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            issues.append(
                f"semantic review shard {index} is unreadable: {exc}"
            )
            continue
        if not isinstance(shard_scope, dict):
            issues.append(
                f"semantic review shard {index} scope is not an object"
            )
            continue
        expected_links = {
            "shard_id": shard_id,
            "scene_id": scene_id,
            "entry_ids": entry_ids,
            "canonical_scope": canonical_scope_rel,
            "canonical_report": canonical_report_rel,
            "artifacts": artifacts,
        }
        for key, expected in expected_links.items():
            if shard_scope.get(key) != expected:
                issues.append(
                    f"semantic review shard {index} {key} mismatch"
                )
        issues.extend(
            _captured_scope_report_issues(
                stage=stage,
                scope=shard_scope,
                report_text=shard_report,
                captured=captured,
                scope_relpath=scope_relpath,
                report_relpath=report_relpath,
                require_failed=False,
            )
        )
        shard_status = parse_judgment_report_status(shard_report)
        if shard_status == "failed":
            shard_failed = _report_list_values(
                shard_report,
                "failed_selectors",
            )
            shard_blocked = _report_list_values(
                shard_report,
                "blocked_entries",
            )
            shard_reasons = _report_list_values(
                shard_report,
                "reason_keys",
            )
            if stage == "image_prompt":
                extend_unique(aggregate_blocked_entries, entry_ids)
                extend_unique(
                    aggregate_reason_keys,
                    shard_reasons or ["image_prompt_shard_failed"],
                )
            else:
                extend_unique(
                    aggregate_blocked_entries,
                    [*shard_failed, *shard_blocked] or entry_ids,
                )
                extend_unique(
                    aggregate_reason_keys,
                    shard_reasons
                    or ["scene_detail_shard_report_inconsistent"],
                )
    if review_scope == "per_scene_shards":
        expected_coverage = {
            "status": "valid",
            "expected_entry_count": len(canonical_entry_ids),
            "assigned_entry_count": len(assigned_entry_ids),
            "expected_entry_ids": canonical_entry_ids,
            "assigned_entry_ids": assigned_entry_ids,
            "missing_entry_ids": [],
            "duplicate_entry_ids": [],
        }
        if (
            assigned_entry_ids != canonical_entry_ids
            or canonical_scope.get("coverage") != expected_coverage
        ):
            issues.append(
                "per_scene_shards coverage does not exactly match canonical "
                "entry_ids"
            )
    canonical_report_relpath = semantic_review_relpaths(stage)[
        "report"
    ].as_posix()
    try:
        canonical_report = captured[
            canonical_report_relpath
        ].decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        issues.append(
            f"canonical shard aggregate report is unreadable: {exc}"
        )
    else:
        canonical_blocked = _report_list_values(
            canonical_report,
            "blocked_entries",
        )
        canonical_failed = _report_list_values(
            canonical_report,
            "failed_selectors",
        )
        canonical_reasons = _report_list_values(
            canonical_report,
            "reason_keys",
        )
        if canonical_blocked != aggregate_blocked_entries:
            issues.append(
                "canonical blocked_entries do not exactly match shard "
                "aggregate"
            )
        if canonical_failed != aggregate_blocked_entries:
            issues.append(
                "canonical failed_selectors do not exactly match shard "
                "aggregate"
            )
        if canonical_reasons != sorted(set(aggregate_reason_keys)):
            issues.append(
                "canonical reason_keys do not exactly match shard aggregate"
            )
    return issues


def _request_snapshot_bundle(
    run_dir: Path,
) -> tuple[dict[str, str], bytes]:
    snapshot_relpath = "image_generation_request_snapshot.json"
    snapshot_bytes = _read_run_relative_bytes(
        run_dir,
        snapshot_relpath,
    )
    try:
        payload = json.loads(snapshot_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PartialMediaProjectionError(
            (f"scene request snapshot is unreadable: {exc}",)
        ) from exc
    if not isinstance(payload, dict):
        raise PartialMediaProjectionError(
            ("scene request snapshot root must be an object",)
        )
    fingerprints = {
        snapshot_relpath: hashlib.sha256(snapshot_bytes).hexdigest()
    }
    source_artifact = payload.get("source_artifact")
    if source_artifact:
        source_bytes = _read_run_relative_bytes(
            run_dir,
            source_artifact,
        )
        fingerprints[str(source_artifact)] = hashlib.sha256(
            source_bytes
        ).hexdigest()
    raw_items = payload.get("items")
    if isinstance(raw_items, list):
        for item in raw_items:
            references = (
                item.get("references")
                if isinstance(item, dict)
                and isinstance(item.get("references"), list)
                else []
            )
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                reference_path = reference.get("path")
                if not reference_path:
                    continue
                if reference.get("deferred") is True:
                    fingerprints[
                        f"deferred:{reference_path}"
                    ] = str(reference.get("producer_item_id") or "")
                    continue
                reference_bytes = _read_run_relative_bytes(
                    run_dir,
                    reference_path,
                )
                fingerprints[str(reference_path)] = hashlib.sha256(
                    reference_bytes
                ).hexdigest()
    return fingerprints, snapshot_bytes


def _stable_scene_request_snapshot(
    run_dir: Path,
) -> tuple[Any, str]:
    before_fingerprints, before_bytes = _request_snapshot_bundle(
        run_dir
    )
    try:
        payload = json.loads(before_bytes.decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ImageRequestSnapshotError(
                "request snapshot root must be an object"
            )
        validation_root = Path(
            os.path.abspath(os.fspath(run_dir))
        )
        snapshot = _snapshot_from_mapping(
            payload,
            run_dir=validation_root,
        )
        validate_request_snapshot(
            snapshot,
            run_dir=validation_root,
            verify_references=False,
        )
        if snapshot.source_artifact and (
            before_fingerprints.get(snapshot.source_artifact)
            != snapshot.source_artifact_sha256
        ):
            raise ImageRequestSnapshotError(
                "source_artifact_sha256 mismatch"
            )
        for item in snapshot.items:
            for reference in item.references:
                if reference.deferred:
                    continue
                if (
                    before_fingerprints.get(reference.path)
                    != reference.sha256
                ):
                    raise ImageRequestSnapshotError(
                        "reference sha256 mismatch for "
                        f"{item.item_id}: {reference.path}"
                    )
    except (
        ImageRequestSnapshotError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise PartialMediaProjectionError(
            (
                "localized partial media requires a current immutable scene "
                f"request snapshot: {exc}",
            )
        ) from exc
    after_fingerprints, after_bytes = _request_snapshot_bundle(run_dir)
    if before_fingerprints != after_fingerprints:
        raise PartialMediaProjectionError(
            (
                "scene request snapshot or its bound inputs changed while "
                "deriving partial media",
            )
        )
    return snapshot, hashlib.sha256(after_bytes).hexdigest()


def _stable_failed_semantic_bundle(
    run_dir: Path,
    stage: str,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    """Validate one immutable semantic failure from one no-follow capture."""

    captured, scope, report_text = _semantic_bundle(run_dir, stage)
    paths = semantic_review_relpaths(stage)
    issues = _captured_scope_report_issues(
        stage=stage,
        scope=scope,
        report_text=report_text,
        captured=captured,
        scope_relpath=paths["scope"].as_posix(),
        report_relpath=paths["report"].as_posix(),
        require_failed=True,
    )
    issues.extend(
        _captured_shard_issues(
            stage=stage,
            canonical_scope=scope,
            captured=captured,
        )
    )
    if issues:
        raise PartialMediaProjectionError(issues)
    fingerprints = {
        relpath: hashlib.sha256(content).hexdigest()
        for relpath, content in captured.items()
    }
    return scope, report_text, fingerprints


def _content_digest(
    payload: Mapping[str, Any],
    *,
    digest_field: str,
) -> str:
    normalized = {
        key: value
        for key, value in payload.items()
        if key != digest_field
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def derive_partial_media_projection(
    run_dir: Path,
    *,
    stages: Sequence[str],
    transport_scene_numbers_by_stage: Mapping[
        str,
        Iterable[Any],
    ] | None = None,
) -> dict[str, Any]:
    """Derive one immutable request/report-bound partial-media projection."""

    normalized_stages = [
        str(stage).strip()
        for stage in stages
        if str(stage).strip()
    ]
    if (
        not normalized_stages
        or len(set(normalized_stages)) != len(normalized_stages)
        or any(
            stage not in PARTIAL_MEDIA_SEMANTIC_STAGES
            for stage in normalized_stages
        )
    ):
        raise PartialMediaProjectionError(
            ("partial-media stages are missing, duplicated, or ineligible",)
        )
    normalized_stages = sorted(normalized_stages)

    snapshot, snapshot_sha256 = _stable_scene_request_snapshot(run_dir)
    if snapshot.kind != "scene":
        raise PartialMediaProjectionError(
            ("localized partial media request snapshot kind must be scene",)
        )

    stage_records: list[dict[str, Any]] = []
    blocked_by_item: dict[str, list[str]] = {}
    reasons_by_item: dict[str, list[str]] = {}
    issues: list[str] = []
    for stage in normalized_stages:
        try:
            scope, report_text, fingerprints = (
                _stable_failed_semantic_bundle(run_dir, stage)
            )
        except PartialMediaProjectionError as exc:
            issues.extend(exc.issues)
            continue
        scope_entry_ids = (
            scope.get("entry_ids")
            if isinstance(scope.get("entry_ids"), list)
            else []
        )
        failed_selectors = _report_list_values(
            report_text,
            "failed_selectors",
        )
        blocked_entries = _report_list_values(
            report_text,
            "blocked_entries",
        )
        reason_keys = _report_list_values(report_text, "reason_keys")
        blocked_ids, localization_issues = (
            localize_semantic_failure_selectors(
                stage=stage,
                items=list(snapshot.items),
                failed_selectors=failed_selectors,
                blocked_entries=blocked_entries,
                scope_entry_ids=scope_entry_ids,
                transport_scene_numbers=(
                    (transport_scene_numbers_by_stage or {}).get(stage, ())
                ),
            )
        )
        issues.extend(
            f"{stage}: {issue}"
            for issue in localization_issues
        )
        if localization_issues:
            continue
        input_digest = str(
            scope.get("semantic_review_input_digest") or ""
        ).strip()
        if not input_digest.startswith("sha256:"):
            issues.append(
                f"{stage}: semantic_review_input_digest is missing"
            )
            continue
        if stage == "image_prompt" and str(
            scope.get("request_revision") or ""
        ).strip() != snapshot.request_revision:
            issues.append(
                "image_prompt semantic failure is not bound to the current "
                "request revision"
            )
            continue

        selector_mapping = {
            selector: sorted(
                selector_image_item_ids(
                    list(snapshot.items),
                    selector,
                    stage=stage,
                )
            )
            for selector in dict.fromkeys(
                [*failed_selectors, *blocked_entries]
            )
        }
        stage_record = {
            "stage": stage,
            "semantic_review_input_digest": input_digest,
            "scope_sha256": fingerprints[
                semantic_review_relpaths(stage)["scope"].as_posix()
            ],
            "report_sha256": fingerprints[
                semantic_review_relpaths(stage)["report"].as_posix()
            ],
            "scope_entry_ids": [
                str(value)
                for value in scope_entry_ids
            ],
            "failed_selectors": failed_selectors,
            "blocked_entries": blocked_entries,
            "reason_keys": reason_keys,
            "selector_to_image_item_ids": selector_mapping,
            "blocked_image_item_ids": sorted(blocked_ids),
        }
        stage_records.append(stage_record)
        for item_id in blocked_ids:
            blocked_by_item.setdefault(item_id, []).append(stage)
            reasons_by_item.setdefault(item_id, []).extend(reason_keys)
    if issues:
        raise PartialMediaProjectionError(issues)
    if len(stage_records) != len(normalized_stages):
        raise PartialMediaProjectionError(
            ("not every localized semantic stage produced a projection",)
        )

    snapshot_item_by_id = {
        item.item_id: item
        for item in snapshot.items
    }
    blocked_item_ids = set(blocked_by_item)
    surviving_item_ids = set(snapshot_item_by_id) - blocked_item_ids
    if not blocked_item_ids:
        raise PartialMediaProjectionError(
            ("partial-media projection blocks zero request items",)
        )
    if not surviving_item_ids:
        raise PartialMediaProjectionError(
            (
                "localized partial media requires at least one surviving "
                "scene image request item",
            )
        )

    synthetic_candidates: dict[str, dict[str, Any]] = {}
    for item_id in sorted(blocked_item_ids):
        blocking_stages = sorted(set(blocked_by_item[item_id]))
        reason_keys = sorted(
            {
                reason
                for reason in reasons_by_item.get(item_id, [])
                if reason
            }
        )
        reason_suffix = (
            f" ({', '.join(reason_keys)})"
            if reason_keys
            else ""
        )
        synthetic_candidates[item_id] = {
            "index": 1,
            "status": "failed",
            "path": None,
            "error": (
                "semantic review failed in "
                + ", ".join(blocking_stages)
                + "; image generation skipped for this item"
                + reason_suffix
            ),
            "blocking_stages": blocking_stages,
        }

    projection: dict[str, Any] = {
        "schema_version": PARTIAL_MEDIA_PROJECTION_SCHEMA,
        "request_revision": snapshot.request_revision,
        "request_snapshot_sha256": snapshot_sha256,
        "request_item_ids": sorted(snapshot_item_by_id),
        "request_destinations": {
            item_id: snapshot_item_by_id[item_id].destination
            for item_id in sorted(snapshot_item_by_id)
        },
        "stages": stage_records,
        "blocked_image_item_ids": sorted(blocked_item_ids),
        "blocked_destinations": sorted(
            snapshot_item_by_id[item_id].destination
            for item_id in blocked_item_ids
        ),
        "surviving_image_item_ids": sorted(surviving_item_ids),
        "synthetic_candidates": synthetic_candidates,
    }
    projection["projection_sha256"] = _content_digest(
        projection,
        digest_field="projection_sha256",
    )
    return projection


def write_partial_media_projection(
    run_dir: Path,
    projection: Mapping[str, Any],
) -> Path:
    path = run_dir / PARTIAL_MEDIA_PROJECTION_RELPATH
    return safe_semantic_write_text(
        run_dir,
        path,
        json.dumps(
            dict(projection),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def load_partial_media_projection(run_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            _read_run_relative_bytes(
                run_dir,
                PARTIAL_MEDIA_PROJECTION_RELPATH.as_posix(),
            ).decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        PartialMediaProjectionError,
    ) as exc:
        raise PartialMediaProjectionError(
            (f"partial-media projection is unreadable: {exc}",)
        ) from exc
    if not isinstance(payload, dict):
        raise PartialMediaProjectionError(
            ("partial-media projection root must be an object",)
        )
    if payload.get("schema_version") != PARTIAL_MEDIA_PROJECTION_SCHEMA:
        raise PartialMediaProjectionError(
            ("partial-media projection schema is unsupported",)
        )
    if payload.get("projection_sha256") != _content_digest(
        payload,
        digest_field="projection_sha256",
    ):
        raise PartialMediaProjectionError(
            ("partial-media projection digest does not match its contents",)
        )
    return payload


def write_partial_media_generation_receipt(
    run_dir: Path,
    *,
    projection: Mapping[str, Any],
    provider_submitted_item_ids: Sequence[str],
    reused_item_ids: Sequence[str],
    generated_item_ids: Sequence[str],
    satisfied_item_ids: Sequence[str],
) -> dict[str, Any]:
    """Write receipt truth sets; generated includes reused surviving files."""

    blocked_item_ids = list(projection.get("blocked_image_item_ids") or [])
    synthetic_candidates = projection.get("synthetic_candidates")
    receipt: dict[str, Any] = {
        "schema_version": PARTIAL_MEDIA_RECEIPT_SCHEMA,
        "request_revision": projection.get("request_revision"),
        "projection_sha256": projection.get("projection_sha256"),
        "provider_submitted_item_ids": list(provider_submitted_item_ids),
        "provider_call_count": len(provider_submitted_item_ids),
        "reused_item_ids": list(reused_item_ids),
        "generated_item_ids": list(generated_item_ids),
        "satisfied_item_ids": list(satisfied_item_ids),
        "skipped_item_ids": blocked_item_ids,
        "synthetic_candidates": synthetic_candidates,
    }
    receipt["receipt_sha256"] = _content_digest(
        receipt,
        digest_field="receipt_sha256",
    )
    safe_semantic_write_text(
        run_dir,
        run_dir / PARTIAL_MEDIA_RECEIPT_RELPATH,
        json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return receipt


def load_partial_media_generation_receipt(
    run_dir: Path,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            _read_run_relative_bytes(
                run_dir,
                PARTIAL_MEDIA_RECEIPT_RELPATH.as_posix(),
            ).decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        PartialMediaProjectionError,
    ) as exc:
        raise PartialMediaProjectionError(
            (f"partial-media generation receipt is unreadable: {exc}",)
        ) from exc
    if not isinstance(payload, dict):
        raise PartialMediaProjectionError(
            ("partial-media generation receipt root must be an object",)
        )
    if payload.get("schema_version") != PARTIAL_MEDIA_RECEIPT_SCHEMA:
        raise PartialMediaProjectionError(
            ("partial-media generation receipt schema is unsupported",)
        )
    expected_digest = _content_digest(
        payload,
        digest_field="receipt_sha256",
    )
    if payload.get("receipt_sha256") != expected_digest:
        raise PartialMediaProjectionError(
            ("partial-media generation receipt digest is invalid",)
        )
    return payload
