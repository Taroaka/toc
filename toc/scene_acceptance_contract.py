"""Canonical scene-set authoring contract and deterministic preflight.

This module deliberately uses plain dictionaries instead of Pydantic models.  The
story artifacts are Markdown/YAML documents which may contain extension fields,
legacy markers, and cross-field rules that are easier to express with a small
validator.  Provider-facing code can use the result objects here without having
to know about the implementation details of the validator.

The validator is intentionally conservative: IDs and ownership are exact
references, while prose cannot substitute for an explicit contract value.  A
generic sentence cannot satisfy a missing event/evidence/role reference.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


SCENE_ACCEPTANCE_CONTRACT_VERSION = "scene_set_authoring_contract_v1"
SCENE_DRAFT_VERSION = "scene_draft_v1"
CRITERION_REGISTRY_VERSION = "scene_acceptance_criteria_v1"

SCENE_ACCEPTANCE_MARKER = "required_v1"
LEGACY_STATUS = "legacy_not_applicable"
SUPPORTED_STATUS = "supported"
UNSUPPORTED_STATUS = "unsupported"
PARTIAL_STATUS = "partial"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_SCENE_ID_TYPES = (str, int)
_REVEAL_STATES = ("withheld", "revealed", "carried", "known")
_REVEAL_RANK = {state: rank for rank, state in enumerate(_REVEAL_STATES)}
_VISIBILITIES = ("visible", "audible", "offscreen_context")

CONTRACT_DIGEST_DOMAIN = "toc.scene_acceptance.contract.v1"
SCENE_SLICE_DIGEST_DOMAIN = "toc.scene_acceptance.scene_slice.v1"
SCENE_DRAFT_DIGEST_DOMAIN = "toc.scene_acceptance.scene_draft.v1"
PREFLIGHT_DIGEST_DOMAIN = "toc.scene_acceptance.preflight.v1"
REGISTRY_DIGEST_DOMAIN = "toc.scene_acceptance.registry.v1"


# Keep the old reason key as a stable compatibility value.  ``canonical_reason_key``
# is the namespaced value emitted by artifact writers.  The registry is the one
# source of truth for authoring projection and deterministic routing.
SCENE_ACCEPTANCE_CRITERIA: tuple[dict[str, Any], ...] = (
    {
        "criterion_id": "scene.canonical_event_ownership",
        "reason_key": "scene_event_canonical_event_missing",
        "canonical_reason_key": "scene_set.scene_event_canonical_event_missing",
        "owner": "deterministic",
        "required_inputs": ["canonical_event_ledger", "scene_event.event_sequence"],
        "authoring_instruction": "割り当てられた source event を同順の owned beat として出力する",
    },
    {
        "criterion_id": "scene.canonical_event_order",
        "reason_key": "scene_event_canonical_order_broken",
        "canonical_reason_key": "scene_set.scene_event_canonical_order_broken",
        "owner": "deterministic",
        "required_inputs": ["canonical_event_ledger", "ordered_scene_list"],
        "authoring_instruction": "canonical order を変更せずに scene の順序へ投影する",
    },
    {
        "criterion_id": "scene.reveal_monotonicity",
        "reason_key": "reveal_state_rollback",
        "canonical_reason_key": "scene_set.reveal_state_rollback",
        "owner": "deterministic",
        "required_inputs": ["reveal_ledger", "scene.reveal_state_before", "scene.reveal_state_after"],
        "authoring_instruction": "情報の開示状態を withheld から逆行させない",
    },
    {
        "criterion_id": "scene.role_visibility_closure",
        "reason_key": "role_coverage_missing",
        "canonical_reason_key": "scene_set.role_coverage_missing",
        "owner": "deterministic",
        "required_inputs": ["scene.required_beat_specs", "participants", "role_bindings"],
        "authoring_instruction": "required role と character を visible participant として閉じる",
    },
    {
        "criterion_id": "scene.handoff_chain",
        "reason_key": "handoff_state_mismatch",
        "canonical_reason_key": "scene_set.handoff_state_mismatch",
        "owner": "deterministic",
        "required_inputs": ["handoff_chain", "handoff_refs"],
        "authoring_instruction": "前 scene の出力と次 scene の入力を同じ anchor/state で参照する",
    },
    {
        "criterion_id": "scene.time_location_transition",
        "reason_key": "time_transition_cue_missing",
        "canonical_reason_key": "scene_set.time_transition_cue_missing",
        "owner": "deterministic",
        "required_inputs": ["time_location_transition", "transition_cues"],
        "authoring_instruction": "時刻または場所の断絶には具体的な transition cue を割り当てる",
    },
    {
        "criterion_id": "scene.source_grounding",
        "reason_key": "scene_event_missing_source_grounding",
        "canonical_reason_key": "scene_set.scene_event_missing_source_grounding",
        "owner": "deterministic",
        "required_inputs": ["source_refs", "evidence_catalog", "non_replaceable_elements"],
        "authoring_instruction": "generic prose ではなく source-specific evidence ID を出力する",
    },
    {
        "criterion_id": "scene.causal_proof_references",
        "reason_key": "causal_proof_weak",
        "canonical_reason_key": "scene_set.causal_proof_weak",
        "owner": "deterministic",
        "required_inputs": ["causal_proof_contract", "event_sequence"],
        "authoring_instruction": "cause/action/result/evidence を同じ beat の ID へ結合する",
    },
)

_CRITERION_BY_ID = {item["criterion_id"]: item for item in SCENE_ACCEPTANCE_CRITERIA}
_CRITERION_BY_REASON = {item["reason_key"]: item for item in SCENE_ACCEPTANCE_CRITERIA}
_CRITERION_BY_CANONICAL_REASON = {
    item["canonical_reason_key"]: item for item in SCENE_ACCEPTANCE_CRITERIA
}

# Legacy reports used unscoped reason keys.  New callers can resolve either
# ``(stage, old_key)`` or just ``old_key`` when the stage is unavailable.
LEGACY_REASON_KEY_ALIASES: dict[tuple[str, str], str] = {
    ("scene_set", item["reason_key"]): item["criterion_id"]
    for item in SCENE_ACCEPTANCE_CRITERIA
}


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic contract/preflight finding."""

    reason_key: str
    message: str
    path: str = ""
    criterion_id: str | None = None
    severity: str = "error"

    @property
    def canonical_reason_key(self) -> str:
        criterion = _CRITERION_BY_ID.get(self.criterion_id or "")
        if criterion:
            return str(criterion["canonical_reason_key"])
        criterion = _CRITERION_BY_REASON.get(self.reason_key)
        if criterion:
            return str(criterion["canonical_reason_key"])
        return f"scene_set.{self.reason_key}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_key": self.reason_key,
            "canonical_reason_key": self.canonical_reason_key,
            "message": self.message,
            "path": self.path,
            "criterion_id": self.criterion_id,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Result shared by contract, draft, and whole-set validation."""

    valid: bool
    issues: tuple[ValidationIssue, ...] = ()
    status: str = "passed"
    artifact: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.valid

    @property
    def reason_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(issue.reason_key for issue in self.issues))

    @property
    def canonical_reason_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(issue.canonical_reason_key for issue in self.issues))

    @property
    def blocking_reason_keys(self) -> tuple[str, ...]:
        return self.reason_keys

    @property
    def findings(self) -> tuple[dict[str, Any], ...]:
        """JSON-friendly finding projection used by report writers."""

        return tuple(issue.to_dict() for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self.issues

    def __bool__(self) -> bool:
        return self.valid

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "valid": self.valid,
            "passed": self.valid,
            "reason_keys": list(self.reason_keys),
            "canonical_reason_keys": list(self.canonical_reason_keys),
            "issues": [issue.to_dict() for issue in self.issues],
            "findings": [issue.to_dict() for issue in self.issues],
            "error_count": len(self.issues),
            "metadata": deepcopy(self.metadata),
        }


def _result(
    issues: Iterable[ValidationIssue],
    *,
    status: str | None = None,
    artifact: dict[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ValidationResult:
    collected = tuple(issues)
    return ValidationResult(
        valid=not collected,
        issues=collected,
        status=status or ("failed" if collected else "passed"),
        artifact=artifact,
        metadata=dict(metadata or {}),
    )


def _issue(
    reason_key: str,
    message: str,
    path: str = "",
    *,
    criterion_id: str | None = None,
    severity: str = "error",
) -> ValidationIssue:
    if criterion_id is None:
        criterion_id = str((_CRITERION_BY_REASON.get(reason_key) or {}).get("criterion_id") or "") or None
    return ValidationIssue(reason_key, message, path, criterion_id, severity)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value using the repository digest rules."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def domain_separated_digest(domain: str, value: Any) -> str:
    """Return a domain-separated SHA-256 digest in the canonical ``sha256:`` form."""

    if not isinstance(domain, str) or not domain:
        raise ValueError("digest domain must be a non-empty string")
    payload = domain.encode("utf-8") + b"\0" + canonical_json_bytes(value)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _without_derived_contract_fields(contract: Mapping[str, Any]) -> dict[str, Any]:
    derived = {
        "authoring_preflight",
        "publish_metadata",
        "preflight",
        "preflight_digest",
        "preflight_status",
        # This value is computed from the contract and is therefore not part of
        # its own digest.  Accepting it here also makes digesting a published
        # artifact idempotent.
        "contract_digest",
    }
    return {key: deepcopy(value) for key, value in contract.items() if key not in derived}


def digest_contract(contract: Mapping[str, Any]) -> str:
    resolved = _resolve_contract_mapping(contract)
    return domain_separated_digest(CONTRACT_DIGEST_DOMAIN, _without_derived_contract_fields(resolved))


def build_scene_slice(contract: Mapping[str, Any], scene_id: str | int) -> dict[str, Any]:
    """Return the frozen, minimal contract view supplied to one scene author."""

    scene = _find_scene(contract, scene_id)
    if scene is None:
        raise KeyError(f"unknown scene_id: {scene_id}")
    scene_id_value = scene.get("scene_id")
    event_ids = set(_as_list(scene.get("owned_event_ids")))
    event_map = {
        str(item.get("event_id")): deepcopy(item)
        for item in _as_list(contract.get("canonical_events"))
        if isinstance(item, Mapping) and str(item.get("event_id")) in event_ids
    }
    evidence_ids: set[str] = set()
    for beat in _as_list(scene.get("required_beat_specs")):
        if isinstance(beat, Mapping):
            evidence_ids.update(str(value) for value in _as_list(beat.get("required_evidence_ids")))
    evidence = {
        str(item.get("evidence_id")): deepcopy(item)
        for item in _as_list(contract.get("evidence_catalog"))
        if isinstance(item, Mapping) and str(item.get("evidence_id")) in evidence_ids
    }
    return {
        "schema_version": "scene_contract_slice_v1",
        "contract_digest": digest_contract(contract),
        "scene_id": scene_id_value,
        "scene": deepcopy(scene),
        "canonical_events": list(event_map.values()),
        "evidence_catalog": list(evidence.values()),
        "handoff_chain": deepcopy(contract.get("handoff_chain") or []),
        "transition_cues": deepcopy(contract.get("transition_cues") or []),
        "reveal_ledger": deepcopy(contract.get("reveal_ledger") or []),
        "criterion_registry_version": contract.get("criterion_registry_version"),
        "criterion_registry_sha256": contract.get("criterion_registry_sha256"),
    }


def digest_scene_slice(contract: Mapping[str, Any], scene_id: str | int) -> str:
    return domain_separated_digest(SCENE_SLICE_DIGEST_DOMAIN, build_scene_slice(contract, scene_id))


def digest_scene_draft(draft: Mapping[str, Any]) -> str:
    return domain_separated_digest(SCENE_DRAFT_DIGEST_DOMAIN, draft)


def digest_preflight(payload: Mapping[str, Any]) -> str:
    return domain_separated_digest(PREFLIGHT_DIGEST_DOMAIN, payload)


def criterion_registry_payload() -> list[dict[str, Any]]:
    return deepcopy(list(SCENE_ACCEPTANCE_CRITERIA))


def criterion_registry_digest() -> str:
    return domain_separated_digest(REGISTRY_DIGEST_DOMAIN, criterion_registry_payload())


def resolve_criterion(reason_key: str, *, stage: str | None = None) -> dict[str, Any] | None:
    if stage:
        criterion_id = LEGACY_REASON_KEY_ALIASES.get((stage, reason_key))
        if criterion_id:
            return deepcopy(_CRITERION_BY_ID[criterion_id])
    criterion = _CRITERION_BY_ID.get(reason_key)
    if criterion is None:
        criterion = _CRITERION_BY_REASON.get(reason_key)
    if criterion is None:
        criterion = _CRITERION_BY_CANONICAL_REASON.get(reason_key)
    return deepcopy(criterion) if criterion else None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _is_scene_id(value: Any) -> bool:
    return isinstance(value, _SCENE_ID_TYPES) and not isinstance(value, bool) and bool(str(value).strip())


def _scene_key(value: Any) -> str:
    return str(value)


def _find_scene(contract: Mapping[str, Any], scene_id: str | int) -> Mapping[str, Any] | None:
    target = _scene_key(scene_id)
    for scene in _as_list(contract.get("scenes")):
        if isinstance(scene, Mapping) and _scene_key(scene.get("scene_id")) == target:
            return scene
    return None


def _scene_maps(contract: Mapping[str, Any]) -> tuple[dict[str, Mapping[str, Any]], dict[str, int]]:
    scenes: dict[str, Mapping[str, Any]] = {}
    positions: dict[str, int] = {}
    for index, scene in enumerate(_as_list(contract.get("scenes"))):
        if isinstance(scene, Mapping) and _is_scene_id(scene.get("scene_id")):
            scenes[_scene_key(scene["scene_id"])] = scene
            positions[_scene_key(scene["scene_id"])] = index
    return scenes, positions


def _map_by_id(items: Any, key: str) -> tuple[dict[str, Mapping[str, Any]], list[ValidationIssue]]:
    result: dict[str, Mapping[str, Any]] = {}
    issues: list[ValidationIssue] = []
    for index, item in enumerate(_as_list(items)):
        path = f"[{index}]"
        if not isinstance(item, Mapping):
            issues.append(_issue("output_contract_invalid", "entry must be an object", path))
            continue
        value = item.get(key)
        if not _is_id(value):
            issues.append(_issue("id_invalid", f"{key} must be a stable identifier", f"{path}.{key}"))
            continue
        if value in result:
            issues.append(_issue("duplicate_id", f"duplicate {key}: {value}", f"{path}.{key}"))
        else:
            result[value] = item
    return result, issues


def _validate_sha(value: Any, path: str, issues: list[ValidationIssue], reason: str = "digest_invalid") -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        issues.append(_issue(reason, "digest must match sha256:<64 lowercase hex>", path))


def _validate_id_list(
    values: Any,
    known: set[str],
    path: str,
    issues: list[ValidationIssue],
    *,
    unknown_reason: str = "reference_unknown",
) -> list[str]:
    result: list[str] = []
    if not isinstance(values, (list, tuple)):
        issues.append(_issue("output_contract_invalid", "reference list must be a list", path))
        return result
    for index, value in enumerate(values):
        if not _is_id(value):
            issues.append(_issue("id_invalid", "reference must be a stable identifier", f"{path}[{index}]"))
            continue
        if value not in known:
            issues.append(_issue(unknown_reason, f"unknown reference: {value}", f"{path}[{index}]"))
        result.append(value)
    return result


def _json_pointer_get(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise KeyError(pointer)
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = current[token]
        elif isinstance(current, list):
            current = current[int(token)]
        else:
            raise KeyError(pointer)
    return current


def _resolve_contract_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Resolve a contract embedded in a script/document root.

    New script artifacts carry the marker in ``script_metadata`` and the
    machine-readable contract in ``scene_set_authoring_contract``.  Direct
    contract callers pass the contract itself.  Keeping this resolution here
    means all public helpers use the same canonical bytes.
    """

    if value.get("schema_version") == SCENE_ACCEPTANCE_CONTRACT_VERSION:
        return value
    for key in ("scene_set_authoring_contract", "authoring_contract"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            return nested
    metadata = value.get("script_metadata")
    if isinstance(metadata, Mapping):
        nested = metadata.get("scene_set_authoring_contract")
        if isinstance(nested, Mapping):
            return nested
    return value


def _validate_source_refs(
    contract: Mapping[str, Any],
    issues: list[ValidationIssue],
    source_artifacts: Mapping[str, Any] | None = None,
) -> dict[str, Mapping[str, Any]]:
    raw_bindings = contract.get("source_bindings")
    bindings = raw_bindings if isinstance(raw_bindings, Mapping) else {}
    if not bindings:
        issues.append(
            _issue(
                "source_ref_missing",
                "source_bindings must contain at least one artifact",
                "source_bindings",
            )
        )
    for binding_name, raw_binding in bindings.items():
        binding_path = f"source_bindings.{binding_name}"
        if not _is_id(binding_name) or not isinstance(raw_binding, Mapping):
            issues.append(
                _issue(
                    "source_ref_invalid",
                    "source binding must be an ID-keyed object",
                    binding_path,
                )
            )
            continue
        artifact_path = raw_binding.get("path")
        if (
            not isinstance(artifact_path, str)
            or not artifact_path.strip()
            or artifact_path.startswith("/")
            or ".." in artifact_path.split("/")
        ):
            issues.append(
                _issue(
                    "source_ref_invalid",
                    "source binding path must be a safe relative path",
                    f"{binding_path}.path",
                )
            )
        _validate_sha(
            raw_binding.get("sha256"),
            f"{binding_path}.sha256",
            issues,
            "source_digest_invalid",
        )
    source_refs, source_issues = _map_by_id(contract.get("source_refs"), "source_ref_id")
    issues.extend(source_issues)
    for source_id, source_ref in source_refs.items():
        path = f"source_refs.{source_id}"
        artifact = source_ref.get("artifact")
        if not isinstance(artifact, str) or not artifact.strip():
            issues.append(_issue("source_ref_invalid", "source artifact is required", f"{path}.artifact"))
            continue
        binding = bindings.get(artifact)
        if not isinstance(binding, Mapping):
            issues.append(
                _issue(
                    "source_ref_missing",
                    f"source artifact has no binding: {artifact}",
                    f"{path}.artifact",
                )
            )
            continue
        _validate_sha(source_ref.get("artifact_sha256"), f"{path}.artifact_sha256", issues, "source_digest_invalid")
        if source_ref.get("artifact_sha256") != binding.get("sha256"):
            issues.append(
                _issue(
                    "source_digest_mismatch",
                    f"source ref digest disagrees with binding: {artifact}",
                    f"{path}.artifact_sha256",
                )
            )
        pointer = source_ref.get("pointer")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            issues.append(_issue("source_pointer_invalid", "source pointer must be a JSON Pointer", f"{path}.pointer"))
        expected_id = source_ref.get("expected_id")
        if not _is_id(expected_id):
            issues.append(_issue("source_expected_id_missing", "source expected_id is required", f"{path}.expected_id"))
        if source_artifacts is None:
            continue
        if artifact not in source_artifacts:
            issues.append(
                _issue(
                    "source_ref_missing",
                    f"bound source artifact was not provided: {artifact}",
                    path,
                )
            )
            continue
        raw = source_artifacts[artifact]
        pointer_source = raw
        if isinstance(raw, bytes):
            actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            if pointer:
                try:
                    pointer_source = json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_strict_json_object,
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    issues.append(
                        _issue(
                            "source_pointer_invalid",
                            f"source artifact is not JSON: {artifact}",
                            f"{path}.pointer",
                        )
                    )
                    continue
        else:
            actual_digest = "sha256:" + hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
        if actual_digest != source_ref.get("artifact_sha256"):
            issues.append(_issue("source_digest_mismatch", f"source artifact digest mismatch for {artifact}", path))
        try:
            selected = _json_pointer_get(pointer_source, pointer or "")
        except (KeyError, IndexError, TypeError, ValueError):
            issues.append(_issue("source_pointer_missing", f"source pointer not found: {pointer}", f"{path}.pointer"))
            continue
        if isinstance(selected, Mapping):
            selected_id = selected.get("id") or selected.get("event_id") or selected.get("beat_id") or selected.get("source_id")
            if selected_id != expected_id:
                issues.append(_issue("source_expected_id_mismatch", f"expected {expected_id}, got {selected_id}", path))
        elif selected != expected_id:
            issues.append(_issue("source_expected_id_mismatch", f"expected {expected_id}, got {selected}", path))
    return source_refs


def _validate_contract_marker(value: Mapping[str, Any]) -> tuple[str | None, list[ValidationIssue]]:
    """Return marker mode and marker-level issues.

    The marker can be present under ``script_metadata`` (the canonical location),
    at the top level (useful for a contract artifact), or as a mapping carrying a
    ``schema_version``.  A missing marker is a legacy artifact, not an error.
    """

    metadata = value.get("script_metadata") if isinstance(value.get("script_metadata"), Mapping) else value
    marker = metadata.get("scene_acceptance_contract") if isinstance(metadata, Mapping) else None
    if marker is None:
        marker = value.get("scene_acceptance_marker")
    if marker is None:
        return None, []
    if isinstance(marker, Mapping):
        marker = marker.get("schema_version") or marker.get("version")
    if marker == SCENE_ACCEPTANCE_MARKER or marker == SCENE_ACCEPTANCE_CONTRACT_VERSION:
        return SCENE_ACCEPTANCE_MARKER, []
    return str(marker), [
        _issue(
            "unsupported_scene_acceptance_contract_version",
            f"unsupported scene acceptance marker: {marker}",
            "script_metadata.scene_acceptance_contract",
        )
    ]


def _validate_contract_marker_and_version(contract: Mapping[str, Any], issues: list[ValidationIssue]) -> str:
    marker, marker_issues = _validate_contract_marker(contract)
    issues.extend(marker_issues)
    schema = contract.get("schema_version")
    if marker is None and schema is None:
        return LEGACY_STATUS
    if schema != SCENE_ACCEPTANCE_CONTRACT_VERSION:
        if schema is None and marker == SCENE_ACCEPTANCE_MARKER:
            issues.append(
                _issue(
                    "partial_scene_acceptance_contract",
                    "required_v1 marker is present but the contract schema is missing",
                    "schema_version",
                )
            )
        elif schema is not None:
            issues.append(
                _issue(
                    "unsupported_scene_acceptance_contract_version",
                    f"unsupported schema version: {schema}",
                    "schema_version",
                )
            )
        return PARTIAL_STATUS if schema is None else UNSUPPORTED_STATUS
    # A marker is required for a new script artifact, but a direct contract
    # validation call may intentionally omit it.  This keeps the contract helper
    # useful to compilers while the script-level gate remains strict.
    return SUPPORTED_STATUS


def validate_scene_set_authoring_contract(
    contract: Mapping[str, Any],
    *,
    source_artifacts: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Validate the whole-set authoring contract and all exact references."""

    if not isinstance(contract, Mapping):
        return _result([_issue("output_contract_invalid", "contract must be an object")], status="failed")
    resolved_contract = _resolve_contract_mapping(contract)
    if resolved_contract is not contract:
        # Preserve the script-level marker while validating the embedded
        # contract.  Do not mutate the caller's dictionary.
        resolved_copy = deepcopy(dict(resolved_contract))
        root_metadata = contract.get("script_metadata")
        root_marker = root_metadata.get("scene_acceptance_contract") if isinstance(root_metadata, Mapping) else contract.get("scene_acceptance_marker")
        if root_marker is not None and "script_metadata" not in resolved_copy:
            resolved_copy["script_metadata"] = {"scene_acceptance_contract": root_marker}
        contract = resolved_copy
    issues: list[ValidationIssue] = []
    status = _validate_contract_marker_and_version(contract, issues)
    if status == LEGACY_STATUS:
        return _result(issues, status=LEGACY_STATUS, metadata={"marker": None})
    if issues and status in (PARTIAL_STATUS, UNSUPPORTED_STATUS):
        return _result(issues, status=status, metadata={"marker": contract.get("scene_acceptance_marker")})

    if not _is_id(contract.get("generation_id")):
        issues.append(_issue("generation_id_missing", "generation_id is required", "generation_id"))
    if contract.get("criterion_registry_version") != CRITERION_REGISTRY_VERSION:
        issues.append(_issue("criterion_registry_version_mismatch", "criterion registry version mismatch", "criterion_registry_version"))
    _validate_sha(contract.get("criterion_registry_sha256"), "criterion_registry_sha256", issues, "criterion_registry_digest_invalid")
    if contract.get("criterion_registry_sha256") != criterion_registry_digest():
        issues.append(_issue("criterion_registry_digest_mismatch", "criterion registry digest mismatch", "criterion_registry_sha256"))

    scenes, scene_positions = _scene_maps(contract)
    scene_items = _as_list(contract.get("scenes"))
    if not scene_items:
        issues.append(_issue("scene_set_empty", "at least one scene is required", "scenes"))
    for index, scene in enumerate(scene_items):
        if not isinstance(scene, Mapping):
            issues.append(_issue("output_contract_invalid", "scene must be an object", f"scenes[{index}]"))
        elif not _is_scene_id(scene.get("scene_id")):
            issues.append(_issue("scene_id_invalid", "scene_id is required", f"scenes[{index}].scene_id"))
    if len(scenes) != len([scene for scene in scene_items if isinstance(scene, Mapping)]):
        issues.append(_issue("duplicate_scene_id", "scene_id values must be unique", "scenes"))

    source_refs = _validate_source_refs(contract, issues, source_artifacts)
    source_ids = set(source_refs)

    canonical_events, event_issues = _map_by_id(contract.get("canonical_events"), "event_id")
    issues.extend(event_issues)
    event_ids = set(canonical_events)
    event_orders: dict[int, str] = {}
    for event_id, event in canonical_events.items():
        path = f"canonical_events.{event_id}"
        order = event.get("canonical_order_index")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            issues.append(_issue("canonical_order_invalid", "canonical_order_index must be a positive integer", f"{path}.canonical_order_index"))
        elif order in event_orders:
            issues.append(_issue("scene_event_canonical_order_broken", "canonical order index is duplicated", f"{path}.canonical_order_index"))
        else:
            event_orders[order] = event_id
        owner = _scene_key(event.get("owner_scene_id"))
        if owner not in scenes:
            issues.append(_issue("scene_event_owner_unknown", f"unknown owner scene: {owner}", f"{path}.owner_scene_id"))
        _validate_id_list(event.get("required_beat_ids"), set(_all_beat_ids(contract)), f"{path}.required_beat_ids", issues, unknown_reason="beat_unknown")
        _validate_id_list(event.get("source_ref_ids"), source_ids, f"{path}.source_ref_ids", issues, unknown_reason="source_ref_missing")

    evidence, evidence_issues = _map_by_id(contract.get("evidence_catalog"), "evidence_id")
    issues.extend(evidence_issues)
    evidence_ids = set(evidence)
    for evidence_id, item in evidence.items():
        path = f"evidence_catalog.{evidence_id}"
        if _scene_key(item.get("owner_scene_id")) not in scenes:
            issues.append(_issue("evidence_owner_unknown", "evidence owner scene is unknown", f"{path}.owner_scene_id"))
        _validate_id_list(item.get("source_ref_ids"), source_ids, f"{path}.source_ref_ids", issues, unknown_reason="source_ref_missing")
        if not isinstance(item.get("visible_form"), str) or not item.get("visible_form", "").strip():
            issues.append(_issue("evidence_visible_form_missing", "visual evidence must have a visible_form", f"{path}.visible_form"))

    reveals, reveal_issues = _map_by_id(contract.get("reveal_ledger"), "information_id")
    issues.extend(reveal_issues)
    reveal_ids = set(reveals)
    reveal_transitions: dict[str, Mapping[str, Any]] = {}
    for info_id, item in reveals.items():
        path = f"reveal_ledger.{info_id}"
        initial = item.get("initial_state")
        allowed = _as_list(item.get("allowed_states"))
        if initial not in _REVEAL_STATES or initial not in allowed:
            issues.append(_issue("reveal_state_invalid", "initial state must be an allowed reveal state", f"{path}.initial_state"))
        for state in allowed:
            if state not in _REVEAL_STATES:
                issues.append(_issue("reveal_state_invalid", f"unsupported reveal state: {state}", f"{path}.allowed_states"))
        for transition_index, transition in enumerate(_as_list(item.get("transitions"))):
            tpath = f"{path}.transitions[{transition_index}]"
            if not isinstance(transition, Mapping):
                issues.append(_issue("output_contract_invalid", "reveal transition must be an object", tpath))
                continue
            transition_id = transition.get("reveal_transition_id")
            if not _is_id(transition_id):
                issues.append(_issue("id_invalid", "reveal_transition_id is required", f"{tpath}.reveal_transition_id"))
                continue
            if transition_id in reveal_transitions:
                issues.append(_issue("duplicate_id", f"duplicate reveal transition: {transition_id}", f"{tpath}.reveal_transition_id"))
            reveal_transitions[transition_id] = transition
            from_state, to_state = transition.get("from_state"), transition.get("to_state")
            if from_state not in allowed or to_state not in allowed:
                issues.append(_issue("reveal_state_invalid", "transition states must be allowed", tpath))
            elif _REVEAL_RANK[to_state] < _REVEAL_RANK[from_state]:
                issues.append(_issue("reveal_state_rollback", "reveal transition moves state backwards", tpath))
            owner = _scene_key(transition.get("owner_scene_id"))
            if owner not in scenes:
                issues.append(_issue("reveal_transition_owner_unknown", "reveal transition owner scene is unknown", f"{tpath}.owner_scene_id"))
            else:
                beat_ids = set(_all_beat_ids_for_scene(scenes[owner]))
                if transition.get("owner_beat_id") not in beat_ids:
                    issues.append(_issue("beat_unknown", "reveal transition owner beat is unknown", f"{tpath}.owner_beat_id"))
            _validate_id_list(transition.get("evidence_ids"), evidence_ids, f"{tpath}.evidence_ids", issues, unknown_reason="evidence_unknown")

    handoffs, handoff_issues = _map_by_id(contract.get("handoff_chain"), "anchor_id")
    issues.extend(handoff_issues)
    handoff_ids = set(handoffs)
    for anchor_id, handoff in handoffs.items():
        path = f"handoff_chain.{anchor_id}"
        producer = _scene_key(handoff.get("owner_scene_id"))
        consumer = _scene_key(handoff.get("consumer_scene_id"))
        if producer not in scenes or consumer not in scenes:
            issues.append(_issue("handoff_anchor_unknown", "handoff producer/consumer scene is unknown", path))
        elif scene_positions.get(consumer, -1) != scene_positions.get(producer, -1) + 1:
            issues.append(_issue("handoff_route_order_mismatch", "handoff consumer must be the adjacent next scene", path))
        _validate_id_list(handoff.get("evidence_ids"), evidence_ids, f"{path}.evidence_ids", issues, unknown_reason="evidence_unknown")
        for key in ("state_id", "producer_beat_id", "consumer_beat_id"):
            if not _is_id(handoff.get(key)):
                issues.append(_issue("handoff_reference_invalid", f"{key} is required", f"{path}.{key}"))
        if producer in scenes:
            producer_beats = set(_all_beat_ids_for_scene(scenes[producer]))
            if handoff.get("producer_beat_id") not in producer_beats:
                issues.append(
                    _issue(
                        "handoff_reference_invalid",
                        "producer_beat_id is not owned by producer scene",
                        f"{path}.producer_beat_id",
                    )
                )
            producer_causal = scenes[producer].get("causal_proof_contract")
            producer_state = (
                producer_causal.get("result_state_id")
                if isinstance(producer_causal, Mapping)
                else None
            )
            if handoff.get("state_id") != producer_state:
                issues.append(
                    _issue(
                        "handoff_state_mismatch",
                        "handoff state must equal producer causal result state",
                        f"{path}.state_id",
                    )
                )
        if consumer in scenes:
            consumer_beats = set(_all_beat_ids_for_scene(scenes[consumer]))
            if handoff.get("consumer_beat_id") not in consumer_beats:
                issues.append(
                    _issue(
                        "handoff_reference_invalid",
                        "consumer_beat_id is not owned by consumer scene",
                        f"{path}.consumer_beat_id",
                    )
                )

    cues, cue_issues = _map_by_id(contract.get("transition_cues"), "transition_cue_id")
    issues.extend(cue_issues)
    cue_ids = set(cues)
    for cue_id, cue in cues.items():
        path = f"transition_cues.{cue_id}"
        owner = _scene_key(cue.get("owner_scene_id"))
        if owner not in scenes:
            issues.append(_issue("transition_cue_owner_unknown", "transition cue owner scene is unknown", f"{path}.owner_scene_id"))
        elif cue.get("owner_beat_id") not in set(_all_beat_ids_for_scene(scenes[owner])):
            issues.append(_issue("beat_unknown", "transition cue owner beat is unknown", f"{path}.owner_beat_id"))
        _validate_id_list(cue.get("evidence_ids"), evidence_ids, f"{path}.evidence_ids", issues, unknown_reason="evidence_unknown")
        for key in ("from_time_of_day", "to_time_of_day"):
            if not isinstance(cue.get(key), str) or not cue.get(key, "").strip():
                issues.append(_issue("transition_cue_invalid", f"{key} is required", f"{path}.{key}"))

    # Validate scene-local cross references after all catalog IDs are known.
    scene_owned_event_ids: dict[str, list[str]] = {}
    scene_beats: dict[str, dict[str, Mapping[str, Any]]] = {}
    for scene_key, scene in scenes.items():
        path = f"scenes.{scene_key}"
        owned = _validate_id_list(scene.get("owned_event_ids"), event_ids, f"{path}.owned_event_ids", issues, unknown_reason="scene_event_canonical_event_missing")
        scene_owned_event_ids[scene_key] = owned
        if len(owned) != len(set(owned)):
            issues.append(_issue("scene_event_canonical_event_duplicate", "scene owned event is duplicated", f"{path}.owned_event_ids"))
        beat_map, beat_issues = _map_by_id(scene.get("required_beat_specs"), "beat_id")
        issues.extend(beat_issues)
        scene_beats[scene_key] = beat_map
        scene_beat_ids = set(beat_map)
        for beat_id, beat in beat_map.items():
            bpath = f"{path}.required_beat_specs.{beat_id}"
            source_events = _validate_id_list(beat.get("source_event_ids"), event_ids, f"{bpath}.source_event_ids", issues, unknown_reason="scene_event_canonical_event_missing")
            if any(event_id not in owned for event_id in source_events):
                issues.append(_issue("scene_event_owner_mismatch", "beat references an event not owned by this scene", bpath))
            _validate_id_list(beat.get("required_role_ids"), None if False else set(_role_ids(scene)), f"{bpath}.required_role_ids", issues, unknown_reason="role_unknown")
            _validate_id_list(beat.get("required_character_ids"), _character_ids(scene), f"{bpath}.required_character_ids", issues, unknown_reason="character_unknown")
            _validate_id_list(beat.get("required_evidence_ids"), evidence_ids, f"{bpath}.required_evidence_ids", issues, unknown_reason="scene_event_missing_source_grounding")
            _validate_id_list(beat.get("required_non_replaceable_element_ids"), _element_ids(scene), f"{bpath}.required_non_replaceable_element_ids", issues, unknown_reason="scene_event_missing_non_replaceable_elements")
        # canonical event -> owned scene and exact beat projection
        for event_id in owned:
            event = canonical_events.get(event_id)
            if not event:
                continue
            if _scene_key(event.get("owner_scene_id")) != scene_key:
                issues.append(_issue("scene_event_owner_mismatch", f"event {event_id} owner_scene_id disagrees with scene ownership", path))
            required_beats = _as_list(event.get("required_beat_ids"))
            scene_beats_for_event = [beat_id for beat_id, beat in beat_map.items() if event_id in _as_list(beat.get("source_event_ids"))]
            if set(required_beats) != set(scene_beats_for_event):
                issues.append(_issue("scene_event_canonical_event_missing", f"event {event_id} beat coverage is incomplete", path))
        # role bindings are local to the scene and must close over required beats.
        role_bindings, role_binding_issues = _map_by_id(scene.get("role_bindings"), "role_id")
        issues.extend(role_binding_issues)
        for role_id, binding in role_bindings.items():
            character_ids = _as_list(binding.get("character_ids"))
            _validate_id_list(character_ids, _character_ids(scene), f"{path}.role_bindings.{role_id}.character_ids", issues, unknown_reason="character_unknown")
            if not character_ids:
                issues.append(_issue("role_binding_character_missing", f"role {role_id} has no character binding", f"{path}.role_bindings.{role_id}.character_ids"))
            _validate_id_list(binding.get("required_for_beat_ids"), scene_beat_ids, f"{path}.role_bindings.{role_id}.required_for_beat_ids", issues, unknown_reason="beat_unknown")
        declared_roles = set(role_bindings)
        for beat_id, beat in beat_map.items():
            for role_id in _as_list(beat.get("required_role_ids")):
                if role_id not in declared_roles:
                    issues.append(_issue("role_binding_missing", f"required role {role_id} has no binding", f"{path}.required_beat_specs.{beat_id}"))

        _validate_scene_reveal_contract(scene, scene_key, reveals, reveal_transitions, issues, scene_beat_ids)
        _validate_scene_handoff_contract(scene, scene_key, scenes, handoffs, handoff_ids, issues)
        _validate_scene_transition_contract(scene, scene_key, cues, cue_ids, scenes, scene_positions, issues)
        _validate_scene_source_and_causal_contract(scene, scene_key, source_ids, evidence_ids, issues, scene_beat_ids)

    # Event ownership is exactly once and follows canonical scene order.
    owner_count: dict[str, list[str]] = {event_id: [] for event_id in event_ids}
    for scene_key, event_list in scene_owned_event_ids.items():
        for event_id in event_list:
            owner_count.setdefault(event_id, []).append(scene_key)
    for event_id, owners in owner_count.items():
        event = canonical_events.get(event_id)
        expected = _scene_key(event.get("owner_scene_id")) if event else ""
        if not owners:
            issues.append(_issue("scene_event_canonical_event_missing", f"event {event_id} has no scene owner", "canonical_events"))
        elif len(owners) > 1:
            issues.append(_issue("scene_event_canonical_event_duplicate", f"event {event_id} has multiple scene owners", "scenes"))
        elif owners[0] != expected:
            issues.append(_issue("scene_event_owner_mismatch", f"event {event_id} owner mismatch", "canonical_events"))
    ordered_events = sorted(canonical_events.values(), key=lambda item: item.get("canonical_order_index", 0))
    ordered_scene_positions = [scene_positions.get(_scene_key(item.get("owner_scene_id")), -1) for item in ordered_events]
    if ordered_scene_positions != sorted(ordered_scene_positions):
        issues.append(_issue("scene_event_canonical_order_broken", "canonical event scene ownership violates order", "canonical_events"))

    # A scene's before-state must be the previous scene's after-state.  This is
    # the cross-scene check that catches the common "revealed, then withheld"
    # reveal rollback failure even when each individual scene is otherwise
    # shaped correctly.
    ordered_scenes = [scene for _, scene in sorted(scenes.items(), key=lambda item: scene_positions[item[0]])]
    previous_after: dict[str, Any] = {}
    for scene_index, scene in enumerate(ordered_scenes):
        scene_key = _scene_key(scene.get("scene_id"))
        before = scene.get("reveal_state_before") if isinstance(scene.get("reveal_state_before"), Mapping) else {}
        after = scene.get("reveal_state_after") if isinstance(scene.get("reveal_state_after"), Mapping) else {}
        for info_id, before_state in before.items():
            if info_id in previous_after and before_state != previous_after[info_id]:
                previous_state = previous_after[info_id]
                reason = "reveal_state_rollback" if (
                    before_state in _REVEAL_RANK and previous_state in _REVEAL_RANK
                    and _REVEAL_RANK[before_state] < _REVEAL_RANK[previous_state]
                ) else "reveal_state_transition_mismatch"
                issues.append(_issue(reason, f"scene {scene_key} starts {info_id} at {before_state}, previous scene ended at {previous_state}", f"scenes.{scene_key}.reveal_state_before.{info_id}"))
        previous_after.update(after)

    return _result(
        issues,
        status="failed" if issues else "validated",
        metadata={
            "schema_version": contract.get("schema_version"),
            "contract_digest": digest_contract(contract),
            "criterion_registry_version": contract.get("criterion_registry_version"),
            "criterion_registry_sha256": contract.get("criterion_registry_sha256"),
        },
    )


def _all_beat_ids(contract: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for scene in _as_list(contract.get("scenes")):
        if isinstance(scene, Mapping):
            result.extend(_all_beat_ids_for_scene(scene))
    return result


def _all_beat_ids_for_scene(scene: Mapping[str, Any]) -> list[str]:
    return [str(item.get("beat_id")) for item in _as_list(scene.get("required_beat_specs")) if isinstance(item, Mapping) and _is_id(item.get("beat_id"))]


def _role_ids(scene: Mapping[str, Any]) -> list[str]:
    return [str(item.get("role_id")) for item in _as_list(scene.get("role_bindings")) if isinstance(item, Mapping) and _is_id(item.get("role_id"))]


def _character_ids(scene: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in _as_list(scene.get("role_bindings")):
        if isinstance(item, Mapping):
            result.update(str(value) for value in _as_list(item.get("character_ids")) if _is_id(value))
    for beat in _as_list(scene.get("required_beat_specs")):
        if isinstance(beat, Mapping):
            result.update(str(value) for value in _as_list(beat.get("required_character_ids")) if _is_id(value))
    return result


def _element_ids(scene: Mapping[str, Any]) -> set[str]:
    return {
        str(item.get("element_id"))
        for item in _as_list(scene.get("non_replaceable_elements"))
        if isinstance(item, Mapping) and _is_id(item.get("element_id"))
    }


def _validate_scene_reveal_contract(
    scene: Mapping[str, Any],
    scene_key: str,
    reveals: Mapping[str, Mapping[str, Any]],
    transitions: Mapping[str, Mapping[str, Any]],
    issues: list[ValidationIssue],
    beat_ids: set[str],
) -> None:
    path = f"scenes.{scene_key}"
    before = scene.get("reveal_state_before")
    after = scene.get("reveal_state_after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        issues.append(_issue("reveal_state_missing", "scene must declare reveal_state_before and reveal_state_after", path))
        return
    info_ids = set(reveals)
    if set(before) != info_ids or set(after) != info_ids:
        issues.append(_issue("reveal_state_missing", "scene reveal state must cover every information_id", path))
    allowed_ids = _as_list(scene.get("allowed_reveal_transition_ids"))
    for transition_id in allowed_ids:
        if transition_id not in transitions:
            issues.append(_issue("reveal_transition_unknown", f"unknown reveal transition: {transition_id}", f"{path}.allowed_reveal_transition_ids"))
            continue
        transition = transitions[transition_id]
        if _scene_key(transition.get("owner_scene_id")) != scene_key:
            issues.append(_issue("reveal_transition_ownership_mismatch", f"transition {transition_id} belongs to another scene", path))
        if transition.get("owner_beat_id") not in beat_ids:
            issues.append(_issue("beat_unknown", "reveal transition beat is not owned by scene", path))
    transitions_by_info: dict[str, list[Mapping[str, Any]]] = {info_id: [] for info_id in reveals}
    for info_id, ledger in reveals.items():
        for transition in _as_list(ledger.get("transitions")):
            if isinstance(transition, Mapping) and _scene_key(transition.get("owner_scene_id")) == scene_key:
                transitions_by_info[info_id].append(transition)
    for info_id, ledger in reveals.items():
        before_state, after_state = before.get(info_id), after.get(info_id)
        if before_state not in _REVEAL_STATES or after_state not in _REVEAL_STATES:
            issues.append(_issue("reveal_state_invalid", f"invalid state for {info_id}", path))
            continue
        if _REVEAL_RANK[after_state] < _REVEAL_RANK[before_state]:
            issues.append(_issue("reveal_state_rollback", f"scene rolls back {info_id}", path))
        current = before_state
        for transition in sorted(transitions_by_info[info_id], key=lambda value: _REVEAL_RANK.get(value.get("to_state"), 99)):
            transition_id = transition.get("reveal_transition_id")
            if transition_id not in allowed_ids:
                issues.append(_issue("reveal_transition_ownership_mismatch", f"scene transition {transition_id} is not allowed by scene", path))
            if transition.get("from_state") != current:
                issues.append(_issue("reveal_state_rollback", f"transition {transition_id} does not start from current state", path))
            current = transition.get("to_state")
        # An omitted transition is valid when before == after; a changed state
        # requires at least one owned transition and exact final state.
        if before_state != after_state and not transitions_by_info[info_id]:
            issues.append(_issue("reveal_transition_missing", f"state change for {info_id} has no transition", path))
        elif transitions_by_info[info_id] and current != after_state:
            issues.append(_issue("reveal_state_transition_mismatch", f"final reveal state mismatch for {info_id}", path))


def _validate_scene_handoff_contract(
    scene: Mapping[str, Any],
    scene_key: str,
    scenes: Mapping[str, Mapping[str, Any]],
    handoffs: Mapping[str, Mapping[str, Any]],
    handoff_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    path = f"scenes.{scene_key}"
    incoming = scene.get("incoming_handoff_anchor_id")
    outgoing = scene.get("outgoing_handoff_anchor_id")
    if incoming not in handoff_ids and incoming not in ("story-opening", "opening", None):
        issues.append(_issue("handoff_anchor_unknown", f"unknown incoming handoff: {incoming}", f"{path}.incoming_handoff_anchor_id"))
    if outgoing not in handoff_ids and outgoing not in ("story-ending", "ending", None):
        issues.append(_issue("handoff_anchor_unknown", f"unknown outgoing handoff: {outgoing}", f"{path}.outgoing_handoff_anchor_id"))
    if incoming in handoffs and _scene_key(handoffs[incoming].get("consumer_scene_id")) != scene_key:
        issues.append(_issue("handoff_owner_mismatch", "incoming handoff consumer does not match scene", path))
    if outgoing in handoffs and _scene_key(handoffs[outgoing].get("owner_scene_id")) != scene_key:
        issues.append(_issue("handoff_owner_mismatch", "outgoing handoff producer does not match scene", path))


def _validate_scene_transition_contract(
    scene: Mapping[str, Any],
    scene_key: str,
    cues: Mapping[str, Mapping[str, Any]],
    cue_ids: set[str],
    scenes: Mapping[str, Mapping[str, Any]],
    scene_positions: Mapping[str, int],
    issues: list[ValidationIssue],
) -> None:
    path = f"scenes.{scene_key}.time_location_transition"
    transition = scene.get("time_location_transition")
    if not isinstance(transition, Mapping):
        issues.append(_issue("time_location_transition_missing", "time_location_transition is required", path))
        return
    time_of_day = transition.get("time_of_day")
    if not isinstance(time_of_day, str) or not time_of_day.strip():
        issues.append(_issue("time_of_day_missing", "time_of_day is required", f"{path}.time_of_day"))
    locations = transition.get("location_sequence")
    if not isinstance(locations, list) or not locations or any(not _is_id(location) for location in locations):
        issues.append(_issue("location_route_invalid", "location_sequence must contain one or more IDs", f"{path}.location_sequence"))
    required = bool(transition.get("transition_cue_required"))
    transition_cue_ids = _as_list(transition.get("transition_cue_ids"))
    for cue_id in transition_cue_ids:
        if cue_id not in cue_ids:
            issues.append(_issue("transition_cue_unknown", f"unknown transition cue: {cue_id}", f"{path}.transition_cue_ids"))
        elif _scene_key(cues[cue_id].get("owner_scene_id")) != scene_key:
            issues.append(_issue("transition_cue_owner_mismatch", f"cue {cue_id} belongs to another scene", path))
    if required and not transition_cue_ids:
        issues.append(_issue("time_transition_cue_missing", "a transition cue is required but none is declared", path))
    previous_scene = next(
        (candidate for candidate, pos in scene_positions.items() if pos == scene_positions.get(scene_key, 0) - 1),
        None,
    )
    if previous_scene is not None and previous_scene in scenes:
        previous_transition = scenes[previous_scene].get("time_location_transition") or {}
        previous_time = previous_transition.get("time_of_day")
        previous_locations = _as_list(previous_transition.get("location_sequence"))
        current_locations = _as_list(locations)
        time_changed = bool(previous_time and time_of_day != previous_time)
        location_changed = previous_locations != current_locations
        if (time_changed or location_changed) and not required:
            issues.append(
                _issue(
                    "time_transition_cue_missing",
                    "time/location discontinuity must declare transition_cue_required",
                    path,
                )
            )
        if (time_changed or location_changed) and not transition_cue_ids:
            issues.append(
                _issue(
                    "time_transition_cue_missing",
                    "time/location discontinuity requires a cue",
                    path,
                )
            )
        for cue_id in transition_cue_ids:
            cue = cues.get(str(cue_id))
            if not isinstance(cue, Mapping):
                continue
            if (
                cue.get("from_time_of_day") != previous_time
                or cue.get("to_time_of_day") != time_of_day
            ):
                issues.append(
                    _issue(
                        "time_transition_cue_missing",
                        f"cue {cue_id} time endpoints do not match adjacent scenes",
                        path,
                    )
                )
            if location_changed and (
                list(cue.get("from_location_ids") or []) != previous_locations
                or list(cue.get("to_location_ids") or []) != current_locations
            ):
                issues.append(
                    _issue(
                        "time_transition_cue_missing",
                        f"cue {cue_id} location endpoints do not match adjacent scenes",
                        path,
                    )
                )


def _validate_scene_source_and_causal_contract(
    scene: Mapping[str, Any],
    scene_key: str,
    source_ids: set[str],
    evidence_ids: set[str],
    issues: list[ValidationIssue],
    beat_ids: set[str],
) -> None:
    path = f"scenes.{scene_key}"
    element_ids = _element_ids(scene)
    for index, element in enumerate(_as_list(scene.get("non_replaceable_elements"))):
        if not isinstance(element, Mapping):
            issues.append(_issue("output_contract_invalid", "non_replaceable_elements entry must be an object", f"{path}.non_replaceable_elements[{index}]"))
            continue
        element_id = element.get("element_id")
        element_path = f"{path}.non_replaceable_elements[{index}]"
        if not _is_id(element_id):
            continue
        _validate_id_list(element.get("source_ref_ids"), source_ids, f"{element_path}.source_ref_ids", issues, unknown_reason="source_ref_missing")
        _validate_id_list(element.get("required_evidence_ids"), evidence_ids, f"{element_path}.required_evidence_ids", issues, unknown_reason="scene_event_missing_source_grounding")
        if not _as_list(element.get("source_ref_ids")):
            issues.append(_issue("source_ref_missing", f"element {element_id} has no source ref", element_path))
        if not _as_list(element.get("required_evidence_ids")):
            issues.append(_issue("scene_event_missing_non_replaceable_elements", f"element {element_id} has no required evidence", element_path))
    causal = scene.get("causal_proof_contract")
    if not isinstance(causal, Mapping):
        issues.append(_issue("causal_proof_weak", "causal_proof_contract is required", f"{path}.causal_proof_contract"))
        return
    cause = causal.get("cause_beat_id")
    action = causal.get("action_beat_id")
    if cause not in beat_ids or action not in beat_ids:
        issues.append(_issue("causal_proof_weak", "causal proof references an unknown beat", f"{path}.causal_proof_contract"))
    if not _is_id(causal.get("result_state_id")):
        issues.append(_issue("causal_proof_weak", "result_state_id is required", f"{path}.causal_proof_contract.result_state_id"))
    _validate_id_list(causal.get("required_evidence_ids"), evidence_ids, f"{path}.causal_proof_contract.required_evidence_ids", issues, unknown_reason="scene_event_missing_source_grounding")
    if not _as_list(causal.get("required_evidence_ids")):
        issues.append(_issue("causal_proof_weak", "causal proof requires visible evidence", f"{path}.causal_proof_contract.required_evidence_ids"))


def validate_scene_draft(
    draft: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    scene_id: str | int | None = None,
) -> ValidationResult:
    """Validate one ``scene_draft_v1`` against its frozen contract slice."""

    if not isinstance(draft, Mapping):
        return _result([_issue("output_contract_invalid", "scene draft must be an object")], status="failed")
    issues: list[ValidationIssue] = []
    draft_required_keys = {
        "schema_version",
        "generation_id",
        "scene_id",
        "contract_digest",
        "scene_slice_digest",
        "scene_intent",
        "scene_event",
        "participants",
        "handoff_refs",
    }
    for key in sorted(draft_required_keys - set(draft)):
        issues.append(_issue("output_contract_missing_key", f"scene draft is missing required key: {key}", key))
    for key in sorted(set(draft) - draft_required_keys):
        issues.append(_issue("output_contract_unknown_key", f"unknown scene draft key: {key}", key))
    if draft.get("schema_version") != SCENE_DRAFT_VERSION:
        issues.append(_issue("unsupported_scene_draft_version", "scene draft schema version is unsupported", "schema_version"))
    target_scene_id = scene_id if scene_id is not None else draft.get("scene_id")
    scene = _find_scene(contract, target_scene_id)
    if scene is None:
        issues.append(_issue("scene_unknown", f"unknown scene_id: {target_scene_id}", "scene_id"))
        return _result(issues, status="failed")
    if _scene_key(draft.get("scene_id")) != _scene_key(scene.get("scene_id")):
        issues.append(_issue("scene_id_mismatch", "draft scene_id does not match contract", "scene_id"))
    if draft.get("generation_id") != contract.get("generation_id"):
        issues.append(_issue("generation_id_mismatch", "draft generation_id does not match contract", "generation_id"))
    expected_contract_digest = digest_contract(contract)
    if draft.get("contract_digest") != expected_contract_digest:
        issues.append(_issue("contract_digest_mismatch", "draft contract digest is stale", "contract_digest"))
    try:
        expected_slice_digest = digest_scene_slice(contract, scene.get("scene_id"))
    except (KeyError, TypeError):
        expected_slice_digest = None
    if expected_slice_digest and draft.get("scene_slice_digest") != expected_slice_digest:
        issues.append(_issue("scene_slice_digest_mismatch", "draft scene slice digest is stale", "scene_slice_digest"))

    sequence = ((draft.get("scene_event") or {}).get("event_sequence") if isinstance(draft.get("scene_event"), Mapping) else None)
    if not isinstance(sequence, list):
        issues.append(_issue("output_contract_invalid", "scene_event.event_sequence must be a list", "scene_event.event_sequence"))
        sequence = []
    specs = [item for item in _as_list(scene.get("required_beat_specs")) if isinstance(item, Mapping)]
    expected_beat_ids = [item.get("beat_id") for item in specs]
    actual_beat_ids = [item.get("beat_id") for item in sequence if isinstance(item, Mapping)]
    if actual_beat_ids != expected_beat_ids:
        issues.append(_issue("scene_event_canonical_order_broken", "draft event_sequence must exactly mirror required beat order", "scene_event.event_sequence"))
    event_ids = set(_as_list(scene.get("owned_event_ids")))
    evidence_ids = _contract_evidence_ids(contract)
    transitions = _contract_reveal_transition_ids(contract)
    handoff_ids = _contract_handoff_ids(contract)
    cue_ids = _contract_cue_ids(contract)
    beat_map = {str(item.get("beat_id")): item for item in specs}
    for index, beat in enumerate(sequence):
        path = f"scene_event.event_sequence[{index}]"
        if not isinstance(beat, Mapping):
            issues.append(_issue("output_contract_invalid", "event beat must be an object", path))
            continue
        beat_id = beat.get("beat_id")
        spec = beat_map.get(str(beat_id))
        if spec is None:
            issues.append(_issue("beat_unknown", f"unknown beat: {beat_id}", f"{path}.beat_id"))
            continue
        incoming_handoff_ids = [
            str(item.get("anchor_id"))
            for item in _as_list(contract.get("handoff_chain"))
            if isinstance(item, Mapping)
            and _scene_key(item.get("consumer_scene_id")) == _scene_key(scene.get("scene_id"))
            and item.get("consumer_beat_id") == beat_id
        ]
        outgoing_handoff_ids = [
            str(item.get("anchor_id"))
            for item in _as_list(contract.get("handoff_chain"))
            if isinstance(item, Mapping)
            and _scene_key(item.get("owner_scene_id")) == _scene_key(scene.get("scene_id"))
            and item.get("producer_beat_id") == beat_id
        ]
        transition_cue_ids = [
            str(item.get("transition_cue_id"))
            for item in _as_list(contract.get("transition_cues"))
            if isinstance(item, Mapping)
            and _scene_key(item.get("owner_scene_id")) == _scene_key(scene.get("scene_id"))
            and item.get("owner_beat_id") == beat_id
        ]
        reveal_transition_ids = [
            str(transition.get("reveal_transition_id"))
            for ledger in _as_list(contract.get("reveal_ledger"))
            if isinstance(ledger, Mapping)
            for transition in _as_list(ledger.get("transitions"))
            if isinstance(transition, Mapping)
            and _scene_key(transition.get("owner_scene_id"))
            == _scene_key(scene.get("scene_id"))
            and transition.get("owner_beat_id") == beat_id
        ]
        expected_refs = (
            ("source_event_ids", spec.get("source_event_ids"), event_ids, "scene_event_canonical_event_missing"),
            ("role_ids", spec.get("required_role_ids"), set(_role_ids(scene)), "role_coverage_missing"),
            ("participant_character_ids", spec.get("required_character_ids"), _character_ids(scene), "role_coverage_missing"),
            ("evidence_ids", spec.get("required_evidence_ids"), evidence_ids, "scene_event_missing_source_grounding"),
            ("transition_cue_ids", transition_cue_ids, cue_ids, "transition_cue_unknown"),
            ("incoming_handoff_anchor_ids", incoming_handoff_ids, handoff_ids, "handoff_anchor_unknown"),
            ("outgoing_handoff_anchor_ids", outgoing_handoff_ids, handoff_ids, "handoff_anchor_unknown"),
            ("reveal_transition_ids", reveal_transition_ids, transitions, "reveal_transition_unknown"),
            (
                "required_non_replaceable_element_ids",
                spec.get("required_non_replaceable_element_ids"),
                _element_ids(scene),
                "scene_event_missing_non_replaceable_elements",
            ),
        )
        for key, expected, known, unknown_reason in expected_refs:
            actual = _as_list(beat.get(key))
            if list(actual) != list(expected):
                issues.append(_issue("scene_draft_reference_mismatch", f"{key} must exactly match frozen contract", f"{path}.{key}"))
            _validate_id_list(actual, set(known), f"{path}.{key}", issues, unknown_reason=unknown_reason)
            if key == "evidence_ids" and set(expected) - set(actual):
                issues.append(_issue("scene_event_missing_source_grounding", "beat omits required source-specific evidence", f"{path}.{key}"))
        expected_elements = spec.get("required_non_replaceable_element_ids") or []
        required_element_evidence: set[str] = set()
        for element in _as_list(scene.get("non_replaceable_elements")):
            if isinstance(element, Mapping) and element.get("element_id") in expected_elements:
                required_element_evidence.update(str(value) for value in _as_list(element.get("required_evidence_ids")))
        if required_element_evidence and not required_element_evidence.issubset(set(_as_list(beat.get("evidence_ids")))):
            issues.append(_issue("scene_event_missing_non_replaceable_elements", "beat omits required non-replaceable evidence", path))
        actual_transition_ids = set(_as_list(beat.get("reveal_transition_ids")))
        allowed_transition_ids = set(_as_list(scene.get("allowed_reveal_transition_ids")))
        if not actual_transition_ids.issubset(allowed_transition_ids):
            issues.append(_issue("reveal_transition_ownership_mismatch", "draft references a transition not allowed by scene", f"{path}.reveal_transition_ids"))
        if not actual_transition_ids.issubset(transitions):
            issues.append(_issue("reveal_transition_unknown", "draft references unknown reveal transition", f"{path}.reveal_transition_ids"))
        expected_result_state_id = (
            scene.get("causal_proof_contract", {}).get("result_state_id")
            if isinstance(scene.get("causal_proof_contract"), Mapping)
            else None
        )
        if beat.get("result_state_id") != expected_result_state_id:
            issues.append(
                _issue(
                    "causal_proof_weak",
                    "result_state_id must exactly match the frozen causal result",
                    f"{path}.result_state_id",
                )
            )

    participants = draft.get("participants")
    if not isinstance(participants, list):
        issues.append(_issue("output_contract_invalid", "participants must be a list", "participants"))
        participants = []
    participant_map: dict[str, Mapping[str, Any]] = {}
    for index, participant in enumerate(participants):
        path = f"participants[{index}]"
        if not isinstance(participant, Mapping):
            issues.append(_issue("output_contract_invalid", "participant must be an object", path))
            continue
        character_id = participant.get("character_id")
        if not _is_id(character_id):
            issues.append(_issue("character_id_invalid", "participant character_id is required", f"{path}.character_id"))
            continue
        if character_id in participant_map:
            issues.append(_issue("duplicate_id", f"duplicate participant: {character_id}", f"{path}.character_id"))
        participant_map[character_id] = participant
        if participant.get("visibility") not in _VISIBILITIES:
            issues.append(_issue("participant_visibility_invalid", "unsupported participant visibility", f"{path}.visibility"))
        _validate_id_list(participant.get("role_ids"), set(_role_ids(scene)), f"{path}.role_ids", issues, unknown_reason="role_unknown")
        _validate_id_list(participant.get("required_for_beat_ids"), set(expected_beat_ids), f"{path}.required_for_beat_ids", issues, unknown_reason="beat_unknown")
        _validate_id_list(participant.get("evidence_ids"), evidence_ids, f"{path}.evidence_ids", issues, unknown_reason="scene_event_missing_source_grounding")
    expected_participants: dict[str, dict[str, set[str]]] = {}
    for binding in _as_list(scene.get("role_bindings")):
        if not isinstance(binding, Mapping):
            continue
        role_id = str(binding.get("role_id") or "")
        required_beats = {
            str(value) for value in _as_list(binding.get("required_for_beat_ids"))
        }
        required_evidence = {
            str(evidence_id)
            for spec in specs
            if spec.get("beat_id") in required_beats
            for evidence_id in _as_list(spec.get("required_evidence_ids"))
        }
        for character_id in _as_list(binding.get("character_ids")):
            expected = expected_participants.setdefault(
                str(character_id),
                {"roles": set(), "beats": set(), "evidence": set()},
            )
            expected["roles"].add(role_id)
            expected["beats"].update(required_beats)
            expected["evidence"].update(required_evidence)
    if set(participant_map) != set(expected_participants):
        issues.append(
            _issue(
                "role_coverage_missing",
                "participants must exactly match frozen role-bound characters",
                "participants",
            )
        )
    for character_id, expected in expected_participants.items():
        participant = participant_map.get(character_id)
        if not isinstance(participant, Mapping):
            continue
        if (
            set(_as_list(participant.get("role_ids"))) != expected["roles"]
            or set(_as_list(participant.get("required_for_beat_ids")))
            != expected["beats"]
            or set(_as_list(participant.get("evidence_ids")))
            != expected["evidence"]
        ):
            issues.append(
                _issue(
                    "role_coverage_missing",
                    f"participant {character_id} does not exactly match role/evidence closure",
                    "participants",
                )
            )
    for spec in specs:
        for role_id in _as_list(spec.get("required_role_ids")):
            binding = next(
                (item for item in _as_list(scene.get("role_bindings")) if isinstance(item, Mapping) and item.get("role_id") == role_id),
                None,
            )
            expected_chars = _as_list(binding.get("character_ids")) if isinstance(binding, Mapping) else _as_list(spec.get("required_character_ids"))
            for character_id in expected_chars:
                participant = participant_map.get(character_id)
                if participant is None or participant.get("visibility") not in ("visible", "audible"):
                    issues.append(_issue("role_coverage_missing", f"required character {character_id} is not visible/audible", "participants"))
                elif spec.get("beat_id") not in _as_list(participant.get("required_for_beat_ids")):
                    issues.append(_issue("role_coverage_missing", f"participant {character_id} is not bound to beat {spec.get('beat_id')}", "participants"))

    handoff_refs = draft.get("handoff_refs")
    if not isinstance(handoff_refs, Mapping):
        issues.append(_issue("output_contract_invalid", "handoff_refs must be an object", "handoff_refs"))
        handoff_refs = {}
    for direction in ("incoming", "outgoing"):
        refs = handoff_refs.get(direction)
        if not isinstance(refs, list):
            issues.append(_issue("output_contract_invalid", f"handoff_refs.{direction} must be a list", f"handoff_refs.{direction}"))
            refs = []
        expected_anchor = scene.get("incoming_handoff_anchor_id" if direction == "incoming" else "outgoing_handoff_anchor_id")
        if expected_anchor in ("story-opening", "opening", "story-ending", "ending", None):
            if refs:
                issues.append(_issue("handoff_reference_mismatch", f"terminal scene must not declare {direction} handoff", f"handoff_refs.{direction}"))
        else:
            matching = [ref for ref in refs if isinstance(ref, Mapping) and ref.get("anchor_id") == expected_anchor]
            if len(matching) != 1:
                issues.append(_issue("handoff_reference_mismatch", f"{direction} handoff must contain exact anchor {expected_anchor}", f"handoff_refs.{direction}"))
            if matching:
                ref = matching[0]
                handoff = next((item for item in _as_list(contract.get("handoff_chain")) if isinstance(item, Mapping) and item.get("anchor_id") == expected_anchor), {})
                if ref.get("state_id") != handoff.get("state_id"):
                    issues.append(_issue("handoff_state_mismatch", f"{direction} handoff state does not match contract", f"handoff_refs.{direction}"))
                if list(ref.get("evidence_ids") or []) != list(handoff.get("evidence_ids") or []):
                    issues.append(_issue("handoff_evidence_mismatch", f"{direction} handoff evidence does not match contract", f"handoff_refs.{direction}"))
    return _result(
        issues,
        status="failed" if issues else "validated",
        metadata={
            "scene_id": scene.get("scene_id"),
            "contract_digest": expected_contract_digest,
            "scene_slice_digest": expected_slice_digest,
            "draft_digest": digest_scene_draft(draft),
        },
    )


def _contract_evidence_ids(contract: Mapping[str, Any]) -> set[str]:
    return {str(item.get("evidence_id")) for item in _as_list(contract.get("evidence_catalog")) if isinstance(item, Mapping) and _is_id(item.get("evidence_id"))}


def _contract_reveal_transition_ids(contract: Mapping[str, Any]) -> set[str]:
    return {
        str(transition.get("reveal_transition_id"))
        for ledger in _as_list(contract.get("reveal_ledger"))
        if isinstance(ledger, Mapping)
        for transition in _as_list(ledger.get("transitions"))
        if isinstance(transition, Mapping) and _is_id(transition.get("reveal_transition_id"))
    }


def _contract_handoff_ids(contract: Mapping[str, Any]) -> set[str]:
    return {str(item.get("anchor_id")) for item in _as_list(contract.get("handoff_chain")) if isinstance(item, Mapping) and _is_id(item.get("anchor_id"))}


def _contract_cue_ids(contract: Mapping[str, Any]) -> set[str]:
    return {str(item.get("transition_cue_id")) for item in _as_list(contract.get("transition_cues")) if isinstance(item, Mapping) and _is_id(item.get("transition_cue_id"))}


def validate_scene_set_preflight(
    contract: Mapping[str, Any],
    drafts: Sequence[Mapping[str, Any]] | Mapping[str | int, Mapping[str, Any]],
    *,
    source_artifacts: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Run contract, scene-local, and cross-scene checks before cut materialization."""

    contract_result = validate_scene_set_authoring_contract(contract, source_artifacts=source_artifacts)
    if contract_result.status == LEGACY_STATUS:
        return ValidationResult(True, (), LEGACY_STATUS, metadata={"preflight": "skipped"})
    if not contract_result.valid:
        return ValidationResult(False, contract_result.issues, "failed", metadata={"phase": "contract"})

    if isinstance(drafts, Mapping):
        draft_items = list(drafts.values())
    else:
        draft_items = list(drafts)
    draft_by_scene: dict[str, Mapping[str, Any]] = {}
    issues: list[ValidationIssue] = []
    for draft in draft_items:
        if isinstance(draft, Mapping):
            draft_scene_key = _scene_key(draft.get("scene_id"))
            if draft_scene_key in draft_by_scene:
                issues.append(
                    _issue(
                        "duplicate_scene_id",
                        f"duplicate scene draft: {draft_scene_key}",
                        "drafts",
                    )
                )
                continue
            draft_by_scene[draft_scene_key] = draft
    scenes, scene_positions = _scene_maps(contract)
    if len(draft_items) != len(scenes):
        issues.append(
            _issue(
                "scene_draft_missing",
                "scene draft count must exactly match contract scene count",
                "drafts",
            )
        )
    if set(draft_by_scene) != set(scenes):
        missing = sorted(set(scenes) - set(draft_by_scene))
        extra = sorted(set(draft_by_scene) - set(scenes))
        if missing:
            issues.append(_issue("scene_draft_missing", f"missing scene drafts: {', '.join(missing)}", "drafts"))
        if extra:
            issues.append(_issue("scene_draft_unknown", f"unknown scene drafts: {', '.join(extra)}", "drafts"))
    ordered_scene_keys = [scene_key for scene_key, _ in sorted(scene_positions.items(), key=lambda item: item[1])]
    draft_digests: list[str] = []
    for scene_key in ordered_scene_keys:
        draft = draft_by_scene.get(scene_key)
        if draft is None:
            continue
        result = validate_scene_draft(draft, contract, scene_id=scenes[scene_key].get("scene_id"))
        issues.extend(result.issues)
        draft_digests.append(result.metadata.get("draft_digest") or digest_scene_draft(draft))

    # Cross-scene handoff equality is checked again against the actual drafts.
    for anchor_id, handoff in _map_by_id(contract.get("handoff_chain"), "anchor_id")[0].items():
        producer_scene = _scene_key(handoff.get("owner_scene_id"))
        consumer_scene = _scene_key(handoff.get("consumer_scene_id"))
        producer = draft_by_scene.get(producer_scene)
        consumer = draft_by_scene.get(consumer_scene)
        if producer is None or consumer is None:
            continue
        outgoing = [ref for ref in _as_list((producer.get("handoff_refs") or {}).get("outgoing")) if isinstance(ref, Mapping) and ref.get("anchor_id") == anchor_id]
        incoming = [ref for ref in _as_list((consumer.get("handoff_refs") or {}).get("incoming")) if isinstance(ref, Mapping) and ref.get("anchor_id") == anchor_id]
        if len(outgoing) != 1 or len(incoming) != 1:
            continue  # scene-local validator reports the structural issue
        if outgoing[0].get("state_id") != incoming[0].get("state_id") or list(outgoing[0].get("evidence_ids") or []) != list(incoming[0].get("evidence_ids") or []):
            issues.append(_issue("handoff_state_mismatch", f"handoff {anchor_id} producer/consumer state differs", f"handoff_chain.{anchor_id}"))

    payload = {
        "generation_id": contract.get("generation_id"),
        "contract_digest": digest_contract(contract),
        "criterion_registry_sha256": criterion_registry_digest(),
        "source_digest": domain_separated_digest("toc.scene_acceptance.sources.v1", contract.get("source_bindings") or {}),
        "ordered_scene_draft_digests": draft_digests,
        "checks": [issue.to_dict() for issue in issues],
    }
    preflight_digest = digest_preflight(payload)
    return _result(
        issues,
        status="failed" if issues else "passed",
        metadata={
            "generation_id": contract.get("generation_id"),
            "contract_digest": digest_contract(contract),
            "criterion_registry_sha256": criterion_registry_digest(),
            "preflight_digest": preflight_digest,
            "draft_digests": draft_digests,
        },
    )


# Compatibility aliases used by callers that name the operation rather than the
# artifact type.  Keep these aliases intentionally boring and synchronous.
def validate_contract(
    artifact: Mapping[str, Any],
    *,
    source_artifacts: Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Validate either a direct contract or a script/document root.

    This is the integration-friendly name.  ``validate_scene_set_authoring_contract``
    remains the explicit canonical entry point and also resolves embedded roots.
    """

    return validate_scene_set_authoring_contract(artifact, source_artifacts=source_artifacts)


validate_scene_set_contract = validate_scene_set_authoring_contract
scene_set_preflight = validate_scene_set_preflight
scene_preflight = validate_scene_draft


__all__ = [
    "CONTRACT_DIGEST_DOMAIN",
    "CRITERION_REGISTRY_VERSION",
    "LEGACY_REASON_KEY_ALIASES",
    "PREFLIGHT_DIGEST_DOMAIN",
    "SCENE_ACCEPTANCE_CONTRACT_VERSION",
    "SCENE_ACCEPTANCE_CRITERIA",
    "SCENE_ACCEPTANCE_MARKER",
    "SCENE_DRAFT_VERSION",
    "SCENE_DRAFT_DIGEST_DOMAIN",
    "SCENE_SLICE_DIGEST_DOMAIN",
    "ValidationIssue",
    "ValidationResult",
    "build_scene_slice",
    "canonical_json_bytes",
    "criterion_registry_digest",
    "criterion_registry_payload",
    "digest_contract",
    "digest_preflight",
    "digest_scene_draft",
    "digest_scene_slice",
    "domain_separated_digest",
    "resolve_criterion",
    "scene_preflight",
    "scene_set_preflight",
    "validate_contract",
    "validate_scene_draft",
    "validate_scene_set_authoring_contract",
    "validate_scene_set_contract",
    "validate_scene_set_preflight",
]
