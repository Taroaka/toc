"""Typed, deterministic contracts for image-generation request snapshots.

The Markdown request files are review projections.  This module provides the
versioned JSON contract that runtime code can freeze, validate, and bind to
request-bound output provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


SNAPSHOT_SCHEMA_VERSION = "toc.image_generation_request_snapshot.v1"
DEFAULT_SNAPSHOT_FILENAME = "image_generation_request_snapshot.json"
_SHA256_LENGTH = 64
_SUCCESS_STATUSES = {"completed", "success", "succeeded"}


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
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def materialize_request_snapshot(
    run_dir: Path,
    *,
    kind: str,
    items: Iterable[Mapping[str, Any]],
    compiler_version: str | None = None,
    source_artifact: str | None = None,
    created_at: str | None = None,
    defer_missing_references: bool = False,
) -> ImageRequestSnapshot:
    """Freeze normalized generic request dictionaries into a v1 snapshot.

    Existing reference files are content-hashed immediately.  A missing
    reference is allowed only when another item in the same snapshot produces
    that exact destination; such a reference is marked deferred and must be
    resolved before provider submission.
    """

    base = run_dir.resolve()
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
                    resolved_reference = base / reference_path
                    if not resolved_reference.is_file():
                        raise ImageRequestSnapshotError(
                            f"self-reference does not exist for {item_id}: {reference_path}"
                        )
                    actual_sha256 = sha256_file(resolved_reference)
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
            resolved_reference = base / reference_path
            if resolved_reference.is_file():
                actual_sha256 = sha256_file(resolved_reference)
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
        resolved_source = base / source_path
        if not resolved_source.is_file():
            raise ImageRequestSnapshotError(f"source_artifact does not exist: {source_path}")
        source_sha256 = sha256_file(resolved_source)

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


def write_request_snapshot_atomic(
    path: Path,
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path | None = None,
) -> Path:
    """Durably replace a snapshot without exposing a partially written file."""

    base = (run_dir or path.parent).resolve()
    validate_request_snapshot(snapshot, run_dir=base, verify_references=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        snapshot.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path


def bind_request_snapshot_references(
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path,
    allow_existing_hash_changes: bool = False,
) -> ImageRequestSnapshot:
    """Replace every deferred reference with a hash-bound reference.

    Review-time snapshots may defer assets that are generated earlier in the
    same run.  A provider-ready revision must instead bind the exact bytes now
    present on disk so later mutations invalidate that revision.
    """

    base = run_dir.resolve()
    validate_request_snapshot(
        snapshot,
        run_dir=base,
        verify_references=not allow_existing_hash_changes,
    )
    bound_items: list[ImageRequestSnapshotItem] = []
    for item in snapshot.items:
        bound_references: list[ImageRequestReference] = []
        for reference in item.references:
            reference_path = base / _normalize_run_relative_path(
                base,
                reference.path,
                field="reference",
            )
            if not reference_path.is_file():
                raise ImageRequestSnapshotError(
                    f"reference does not exist for {item.item_id}: {reference.path}"
                )
            actual_sha256 = sha256_file(reference_path)
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
    validate_request_snapshot(rebound_snapshot, run_dir=base, verify_references=True)
    return rebound_snapshot


def load_request_snapshot(
    path: Path,
    *,
    run_dir: Path | None = None,
    verify_references: bool = True,
) -> ImageRequestSnapshot:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImageRequestSnapshotError(f"could not load request snapshot: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ImageRequestSnapshotError("request snapshot root must be an object")
    snapshot = _snapshot_from_mapping(payload, run_dir=(run_dir or path.parent).resolve())
    validate_request_snapshot(
        snapshot,
        run_dir=(run_dir or path.parent).resolve(),
        verify_references=verify_references,
    )
    return snapshot


def validate_request_snapshot(
    snapshot: ImageRequestSnapshot,
    *,
    run_dir: Path,
    verify_references: bool = True,
) -> None:
    base = run_dir.resolve()
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
        source_path = base / normalized_source
        if not source_path.is_file():
            raise ImageRequestSnapshotError(f"source_artifact does not exist: {normalized_source}")
        if verify_references and sha256_file(source_path) != snapshot.source_artifact_sha256:
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
            current_reference_sha256s(base, item, allow_deferred=True)
    expected_revision = _expected_request_revision(snapshot)
    if snapshot.request_revision != expected_revision:
        raise ImageRequestSnapshotError("request_revision mismatch")


def current_reference_sha256s(
    run_dir: Path,
    item: ImageRequestSnapshotItem,
    *,
    allow_deferred: bool = False,
) -> tuple[str | None, ...]:
    """Hash current reference bytes in provider attachment order.

    With ``allow_deferred=True``, an unresolved producer reference is returned
    as ``None``.  A send path should use the default and therefore fail until
    every producer dependency exists.
    """

    base = run_dir.resolve()
    hashes: list[str | None] = []
    for reference in item.references:
        reference_path = base / _normalize_run_relative_path(
            base,
            reference.path,
            field="reference",
        )
        if not reference_path.is_file():
            if reference.deferred and allow_deferred:
                hashes.append(None)
                continue
            raise ImageRequestSnapshotError(
                f"reference does not exist for {item.item_id}: {reference.path}"
            )
        actual_sha256 = sha256_file(reference_path)
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
    base = run_dir.resolve()
    resolved = (base / candidate).resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ImageRequestSnapshotError(f"{field} escapes run directory: {value}") from exc
    normalized = relative.as_posix()
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
