"""Selector-scoped deterministic semantic repair patches.

Repair agents propose small compare-and-swap operations.  This module owns
scope resolution, stage policy, protected identities, atomic application, and
script-to-manifest reconciliation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any, Iterable

from toc.semantic_repair_reconciliation import (
    SemanticRepairReconciliationResult,
    reconcile_semantic_repair_documents,
)


PATCH_SCHEMA_VERSION = "semantic_repair_patch_v1"
MAX_PATCH_OPERATIONS = 64
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SCENE_ID_PATTERN = r"[0-9]+(?:\.[0-9]+)*"
_CUT_ID_PATTERN = r"[0-9]+(?:\.[0-9]+)*"
_SELECTOR_RE = re.compile(
    rf"scene:?({_SCENE_ID_PATTERN})\Z",
    re.IGNORECASE,
)
_CUT_SELECTOR_RE = re.compile(
    rf"scene:?({_SCENE_ID_PATTERN})_cut:?({_CUT_ID_PATTERN})\Z",
    re.IGNORECASE,
)
_SEGMENT_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"
    r"(?:\[(?P<selector_key>[A-Za-z_][A-Za-z0-9_-]*)="
    r"(?P<selector_value>[^\[\]]+)\])?"
)


SCENE_ALLOWED_ROOTS = frozenset(
    {
        "phase",
        "time_of_day",
        "time_of_day_visual_basis",
        "location_mode",
        "location_sequence",
        "location_segments",
        "importance",
        "target_duration_seconds",
        "estimated_duration_seconds",
        "research_refs",
        "handoff_to_next_scene",
        "terminal_resolution",
        "scene_generation",
        "scene_intent",
        "scene_event",
        "scene_character_state_timeline",
        "scene_film_coverage_plan",
        "scene_state_progression_plan",
        "semantic_contract",
        "scene_cut_coverage_plan",
        "scene_shot_mix_plan",
        "coverage_review",
    }
)
CUT_ALLOWED_ROOTS = frozenset(
    {
        "cut_blueprint",
        "cut_contract",
        "scene_contract",
        "visual_beat",
        "target_beat",
        "must_show",
    }
)
PATCH_STAGES = frozenset({"scene_set", "scene_detail", "cut_blueprint"})
_CUT_PATCH_STAGES = frozenset({"scene_detail", "cut_blueprint"})
_STAGE_SCENE_ALLOWED_ROOTS = {
    "scene_set": frozenset(
        {
            "phase",
            "time_of_day",
            "time_of_day_visual_basis",
            "location_mode",
            "location_sequence",
            "location_segments",
            "importance",
            "target_duration_seconds",
            "estimated_duration_seconds",
            "research_refs",
            "handoff_to_next_scene",
            "terminal_resolution",
            "scene_intent",
            "scene_event",
            "semantic_contract",
        }
    ),
    "scene_detail": SCENE_ALLOWED_ROOTS,
    "cut_blueprint": frozenset(
        {
            "scene_event",
            "scene_cut_coverage_plan",
            "scene_shot_mix_plan",
            "coverage_review",
        }
    ),
}
PROTECTED_KEYS = frozenset(
    {
        "scene_id",
        "canonical_scene_index",
        "cut_id",
        "selector",
        "beat_id",
        "event_id",
        "source_event_id",
        "source_event_ids",
        "source_event_beat_id",
        "source_event_beat_ids",
        "source_story_beat_ids",
        "story_event_ids",
        "source_ref_id",
        "source_ref_ids",
        "required_evidence_ids",
        "evidence_id",
        "evidence_ids",
        "story_information_revealed_ids",
        "story_information_hinted_ids",
        "source_story_information_revealed_ids",
        "source_story_information_hinted_ids",
        "allowed_info_ids",
        "allowed_reveal_info_ids",
        "allowed_reveal_transition_ids",
        "forbidden_info_ids",
        "forbidden_reveal_info_ids",
        "reveal_transition_ids",
        "generation_id",
        "contract_digest",
        "preflight_digest",
        "source_digest",
        "source_bindings",
        "canonical_events",
        "reveal_ledger",
        "scene_acceptance_draft",
        "scene_acceptance_binding",
        "schema_version",
        "policy_version",
        "status",
    }
)


class SemanticRepairPatchError(RuntimeError):
    """One deterministic patch rejection with a stable machine code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        operation_index: int | None = None,
    ) -> None:
        self.code = code
        self.operation_index = operation_index
        prefix = f"operation[{operation_index}] " if operation_index is not None else ""
        super().__init__(f"{code}: {prefix}{message}")


@dataclass(frozen=True)
class SemanticRepairPatchResult:
    applied_operation_count: int
    changed_selectors: tuple[str, ...]
    reconciliation: SemanticRepairReconciliationResult


@dataclass(frozen=True)
class _PathSegment:
    key: str
    selector_key: str | None = None
    selector_value: str | None = None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _scene_id(scene: dict[str, Any]) -> str:
    return str(scene.get("scene_id") or "").strip()


def _normalize_scene_id(value: str) -> str:
    return ".".join(str(int(part)) for part in value.split("."))


def _normalize_cut_id(value: str) -> str:
    return ".".join(str(int(part)) for part in value.split("."))


def _split_path_segments(raw: str, *, operation_index: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    for character in raw:
        if character == "[":
            bracket_depth += 1
            if bracket_depth > 1:
                raise SemanticRepairPatchError(
                    "path_not_exact",
                    "nested list selectors are not supported",
                    operation_index=operation_index,
                )
        elif character == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                raise SemanticRepairPatchError(
                    "path_not_exact",
                    "unbalanced list selector",
                    operation_index=operation_index,
                )
        if character == "." and bracket_depth == 0:
            pieces.append("".join(current))
            current = []
        else:
            current.append(character)
    if bracket_depth != 0:
        raise SemanticRepairPatchError(
            "path_not_exact",
            "unbalanced list selector",
            operation_index=operation_index,
        )
    pieces.append("".join(current))
    return pieces


def _parse_path(path: Any, *, operation_index: int) -> tuple[_PathSegment, ...]:
    raw = str(path or "").strip()
    if not raw or "*" in raw or ".." in raw or "/" in raw:
        raise SemanticRepairPatchError(
            "path_not_exact",
            "path must identify one existing key without wildcard/traversal",
            operation_index=operation_index,
        )
    pieces = _split_path_segments(raw, operation_index=operation_index)
    segments: list[_PathSegment] = []
    for piece in pieces:
        match = _SEGMENT_RE.fullmatch(piece)
        if match is None:
            raise SemanticRepairPatchError(
                "path_not_exact",
                f"invalid path segment: {piece}",
                operation_index=operation_index,
            )
        segments.append(
            _PathSegment(
                key=match.group("key"),
                selector_key=match.group("selector_key"),
                selector_value=match.group("selector_value"),
            )
        )
    return tuple(segments)


def _resolve_root(
    document: dict[str, Any],
    selector: Any,
    *,
    stage: str,
    operation_index: int,
) -> tuple[dict[str, Any], str, bool]:
    raw = str(selector or "").strip()
    cut_match = _CUT_SELECTOR_RE.fullmatch(raw)
    if cut_match is not None:
        if stage not in _CUT_PATCH_STAGES:
            raise SemanticRepairPatchError(
                "selector_not_allowed",
                f"cut selector is not writable at {stage}",
                operation_index=operation_index,
            )
        scene_id = _normalize_scene_id(cut_match.group(1))
        cut_id = _normalize_cut_id(cut_match.group(2))
        for scene in _list(document.get("scenes")):
            if not isinstance(scene, dict) or _scene_id(scene) != scene_id:
                continue
            for cut in _list(scene.get("cuts")):
                if not isinstance(cut, dict):
                    continue
                current_cut_id = str(cut.get("cut_id") or "").strip()
                current_selector = str(cut.get("selector") or "").strip().lower()
                current_selector_match = _CUT_SELECTOR_RE.fullmatch(
                    current_selector
                )
                if (
                    (
                        re.fullmatch(_CUT_ID_PATTERN, current_cut_id)
                        is not None
                        and _normalize_cut_id(current_cut_id) == cut_id
                    )
                    or (
                        current_selector_match is not None
                        and _normalize_scene_id(
                            current_selector_match.group(1)
                        ) == scene_id
                        and _normalize_cut_id(
                            current_selector_match.group(2)
                        ) == cut_id
                    )
                ):
                    canonical = (
                        current_selector
                        if current_selector_match is not None
                        else f"scene{scene_id}_cut{cut_match.group(2)}"
                    )
                    return cut, canonical, True
        raise SemanticRepairPatchError(
            "selector_not_found",
            f"cut selector does not exist: {raw}",
            operation_index=operation_index,
        )
    scene_match = _SELECTOR_RE.fullmatch(raw)
    if scene_match is None:
        raise SemanticRepairPatchError(
            "selector_not_found",
            f"unsupported selector: {raw}",
            operation_index=operation_index,
        )
    scene_id = _normalize_scene_id(scene_match.group(1))
    for scene in _list(document.get("scenes")):
        if isinstance(scene, dict) and _scene_id(scene) == scene_id:
            return scene, f"scene:{scene_id}", False
    raise SemanticRepairPatchError(
        "selector_not_found",
        f"scene selector does not exist: {raw}",
        operation_index=operation_index,
    )


def _resolve_parent(
    root: dict[str, Any],
    segments: tuple[_PathSegment, ...],
    *,
    operation_index: int,
) -> tuple[dict[str, Any], str]:
    current: Any = root
    for segment in segments[:-1]:
        if not isinstance(current, dict) or segment.key not in current:
            raise SemanticRepairPatchError(
                "path_not_found",
                f"existing path key is missing: {segment.key}",
                operation_index=operation_index,
            )
        current = current[segment.key]
        if segment.selector_key is not None:
            if not isinstance(current, list):
                raise SemanticRepairPatchError(
                    "path_type_mismatch",
                    f"selected path is not a list: {segment.key}",
                    operation_index=operation_index,
                )
            matches = [
                item
                for item in current
                if isinstance(item, dict)
                and str(item.get(segment.selector_key) or "").strip()
                == str(segment.selector_value or "").strip()
            ]
            if len(matches) != 1:
                raise SemanticRepairPatchError(
                    "path_selector_mismatch",
                    f"path selector must resolve exactly once: {segment.key}",
                    operation_index=operation_index,
                )
            current = matches[0]
    final = segments[-1]
    if final.selector_key is not None:
        raise SemanticRepairPatchError(
            "path_not_exact",
            "the terminal path must be a mapping key, not a list selector",
            operation_index=operation_index,
        )
    if not isinstance(current, dict) or final.key not in current:
        raise SemanticRepairPatchError(
            "path_not_found",
            f"terminal key does not exist: {final.key}",
            operation_index=operation_index,
        )
    return current, final.key


def _frozen_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(
            (str(key), _frozen_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, list):
        return tuple(_frozen_value(item) for item in value)
    return value


def _is_protected_key(value: str) -> bool:
    return value in PROTECTED_KEYS or re.search(
        r"(?:^|_)(?:event_beat|story_beat)_ids?\Z",
        value,
    ) is not None


def _nested_protected_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key)
            if _is_protected_key(normalized):
                found.add(normalized)
            found.update(_nested_protected_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_nested_protected_keys(item))
    return found


def _protected_projection(document: dict[str, Any]) -> tuple[Any, ...]:
    protected: list[Any] = []

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
                normalized = str(key)
                child_path = (*path, normalized)
                if _is_protected_key(normalized):
                    protected.append((child_path, _frozen_value(item)))
                visit(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, (*path, f"[{index}]"))

    visit(document, ())
    return tuple(protected)


def _validate_patch_header(
    *,
    stage: str,
    expected_review_input_digest: str,
    patch: Any,
) -> list[dict[str, Any]]:
    if stage not in PATCH_STAGES:
        raise SemanticRepairPatchError(
            "stage_not_supported",
            f"patch repair is not enabled for stage: {stage}",
        )
    if not isinstance(patch, dict):
        raise SemanticRepairPatchError("patch_not_object", "patch must be an object")
    if patch.get("schema_version") != PATCH_SCHEMA_VERSION:
        raise SemanticRepairPatchError(
            "schema_version_mismatch",
            "unsupported semantic repair patch schema",
        )
    if patch.get("stage") != stage:
        raise SemanticRepairPatchError("stage_mismatch", "patch stage is stale")
    digest = patch.get("semantic_review_input_digest")
    if (
        not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
        or digest != expected_review_input_digest
    ):
        raise SemanticRepairPatchError(
            "review_digest_mismatch",
            "patch does not bind the current semantic review",
        )
    operations = patch.get("operations")
    if not isinstance(operations, list) or not operations:
        raise SemanticRepairPatchError("operations_empty", "operations must be nonempty")
    if len(operations) > MAX_PATCH_OPERATIONS:
        raise SemanticRepairPatchError(
            "operations_limit",
            f"operations exceed {MAX_PATCH_OPERATIONS}",
        )
    if not all(isinstance(operation, dict) for operation in operations):
        raise SemanticRepairPatchError(
            "operation_not_object",
            "every operation must be an object",
        )
    return operations


def _compatible_value_type(old: Any, new: Any) -> bool:
    if old is None:
        return new is None or isinstance(new, (str, int, float, bool, list, dict))
    if isinstance(old, bool):
        return isinstance(new, bool)
    if isinstance(old, (int, float)) and not isinstance(old, bool):
        return isinstance(new, (int, float)) and not isinstance(new, bool)
    return type(old) is type(new)


def _failure_scope(
    values: Iterable[str] | None,
) -> tuple[set[str], set[tuple[str, str]]]:
    scenes: set[str] = set()
    cuts: set[tuple[str, str]] = set()
    for value in values or ():
        raw = str(value or "").strip()
        cut_match = _CUT_SELECTOR_RE.fullmatch(raw)
        if cut_match is not None:
            cuts.add(
                (
                    _normalize_scene_id(cut_match.group(1)),
                    _normalize_cut_id(cut_match.group(2)),
                )
            )
            continue
        scene_match = _SELECTOR_RE.fullmatch(raw)
        if scene_match is not None:
            scenes.add(_normalize_scene_id(scene_match.group(1)))
    return scenes, cuts


def _selector_is_within_failure_scope(
    canonical_selector: str,
    *,
    is_cut: bool,
    allowed_scenes: set[str],
    allowed_cuts: set[tuple[str, str]],
) -> bool:
    if is_cut:
        match = _CUT_SELECTOR_RE.fullmatch(canonical_selector)
        if match is None:
            return False
        scene_id = _normalize_scene_id(match.group(1))
        cut = (scene_id, _normalize_cut_id(match.group(2)))
        return scene_id in allowed_scenes or cut in allowed_cuts
    match = _SELECTOR_RE.fullmatch(canonical_selector)
    return (
        match is not None
        and _normalize_scene_id(match.group(1)) in allowed_scenes
    )


def apply_semantic_repair_patch_documents(
    *,
    stage: str,
    expected_review_input_digest: str,
    patch: Any,
    script: dict[str, Any],
    manifest: dict[str, Any],
    asset_plan: dict[str, Any] | None = None,
    allowed_selectors: Iterable[str] | None = None,
) -> SemanticRepairPatchResult:
    """Validate and atomically apply a bounded repair patch."""

    operations = _validate_patch_header(
        stage=stage,
        expected_review_input_digest=expected_review_input_digest,
        patch=patch,
    )
    working_script = deepcopy(script)
    working_manifest = deepcopy(manifest)
    working_asset_plan = deepcopy(asset_plan if isinstance(asset_plan, dict) else {"assets": []})
    # The repair producer can only patch script.md.  Preserve its protected
    # ownership graph exactly; manifest metadata is projector-owned and may be
    # deterministically refreshed from the unchanged script identities.
    before_protected = _protected_projection(working_script)
    changed_selectors: list[str] = []
    allowed_scenes, allowed_cuts = _failure_scope(allowed_selectors)
    if not allowed_scenes and not allowed_cuts:
        raise SemanticRepairPatchError(
            "selector_scope_missing",
            "a nonempty canonical failure scope is required",
        )
    touched_paths: set[tuple[str, str]] = set()
    for operation_index, operation in enumerate(operations):
        if operation.get("op") != "replace":
            raise SemanticRepairPatchError(
                "operation_not_allowed",
                "only replace operations are supported",
                operation_index=operation_index,
            )
        if operation.get("artifact") != "script.md":
            raise SemanticRepairPatchError(
                "artifact_not_allowed",
                "this stage accepts patches only against script.md",
                operation_index=operation_index,
            )
        reason_key = operation.get("reason_key")
        if not isinstance(reason_key, str) or not reason_key.strip():
            raise SemanticRepairPatchError(
                "reason_key_missing",
                "reason_key must be a nonempty string",
                operation_index=operation_index,
            )
        root, canonical_selector, is_cut = _resolve_root(
            working_script,
            operation.get("selector"),
            stage=stage,
            operation_index=operation_index,
        )
        if not _selector_is_within_failure_scope(
            canonical_selector,
            is_cut=is_cut,
            allowed_scenes=allowed_scenes,
            allowed_cuts=allowed_cuts,
        ):
            raise SemanticRepairPatchError(
                "selector_outside_failure_scope",
                f"selector was not rejected by the current review: {canonical_selector}",
                operation_index=operation_index,
            )
        segments = _parse_path(
            operation.get("path"),
            operation_index=operation_index,
        )
        protected = [
            segment.key for segment in segments if _is_protected_key(segment.key)
        ]
        if protected:
            raise SemanticRepairPatchError(
                "protected_path",
                f"protected key cannot be repaired: {protected[0]}",
                operation_index=operation_index,
            )
        allowed_roots = (
            CUT_ALLOWED_ROOTS
            if is_cut
            else _STAGE_SCENE_ALLOWED_ROOTS[stage]
        )
        if segments[0].key not in allowed_roots:
            raise SemanticRepairPatchError(
                "path_not_allowed",
                f"root key is not writable at {stage}: {segments[0].key}",
                operation_index=operation_index,
            )
        parent, key = _resolve_parent(
            root,
            segments,
            operation_index=operation_index,
        )
        operation_path = (canonical_selector, str(operation.get("path") or ""))
        if operation_path in touched_paths:
            raise SemanticRepairPatchError(
                "duplicate_operation_path",
                "multiple operations target the same selector/path",
                operation_index=operation_index,
            )
        touched_paths.add(operation_path)
        current = parent[key]
        if current != operation.get("expected_old"):
            raise SemanticRepairPatchError(
                "expected_old_mismatch",
                "current value no longer equals expected_old",
                operation_index=operation_index,
            )
        replacement = operation.get("value")
        nested_protected = _nested_protected_keys(current)
        nested_protected.update(_nested_protected_keys(replacement))
        if nested_protected:
            raise SemanticRepairPatchError(
                "protected_path",
                "container replacement includes protected key: "
                + sorted(nested_protected)[0],
                operation_index=operation_index,
            )
        if not _compatible_value_type(current, replacement):
            raise SemanticRepairPatchError(
                "value_type_mismatch",
                f"replacement type differs for {key}",
                operation_index=operation_index,
            )
        parent[key] = deepcopy(replacement)
        if canonical_selector not in changed_selectors:
            changed_selectors.append(canonical_selector)

    reconciliation = reconcile_semantic_repair_documents(
        script=working_script,
        manifest=working_manifest,
        asset_plan=working_asset_plan,
    )
    after_protected = _protected_projection(working_script)
    if after_protected != before_protected:
        raise SemanticRepairPatchError(
            "protected_invariant_changed",
            "repair changed scene/cut/source ownership",
        )
    script.clear()
    script.update(working_script)
    manifest.clear()
    manifest.update(working_manifest)
    if isinstance(asset_plan, dict):
        asset_plan.clear()
        asset_plan.update(working_asset_plan)
    return SemanticRepairPatchResult(
        applied_operation_count=len(operations),
        changed_selectors=tuple(changed_selectors),
        reconciliation=reconciliation,
    )


__all__ = [
    "PATCH_SCHEMA_VERSION",
    "PATCH_STAGES",
    "SemanticRepairPatchError",
    "SemanticRepairPatchResult",
    "apply_semantic_repair_patch_documents",
]
