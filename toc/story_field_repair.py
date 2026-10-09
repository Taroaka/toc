"""Bounded, field-level repair for authored story scenes.

The story validator intentionally reports stable aggregate reason keys.  This
module turns those keys into concrete JSON Pointer leaves only when the
current scene proves that a bounded correction is possible.  It does not
attempt to repair prose, event ordering, causal relationships, or handoffs.

The provider-facing patch format is deliberately small:

``{"scene_id": ..., "base_digest": ..., "operations": [{"path": ..., "value": ...}]}``

``value`` is a string for a scalar field, an array of strings for a list field,
or ``null`` only for an explicitly diagnosed invalid list element that may be
removed.  Flexible mapping fields are represented by a JSON-encoded object
string because an open object in a structured-output schema would make the
patch boundary too broad.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
from typing import Any

from .story_authoring import _registry_for_validation, _registry_maps


class FieldPatchError(ValueError):
    """Raised when a field patch is outside the diagnosed repair boundary."""


_UNKNOWN_ID_ERRORS = frozenset(
    {
        "story.scene_unknown_id",
        "story.scene_id_list_invalid",
    }
)
_LIFECYCLE_ERROR = "story.scene_lifecycle_missing"
_OVERVIEW_ERROR = "story.scene_overview_missing"
_LOCATION_ERROR = "story.scene_location_invalid"
_VISUAL_BASIS_ERROR = "story.scene_time_of_day_visual_basis_invalid"
_TURNING_ERROR = "story.scene_turning_event_invalid"
_SOURCE_COVERAGE_ERROR = "story.scene_source_event_coverage"


# The names and categories mirror the reference taxonomy in
# ``story_authoring._validate_scene_references``.  They are intentionally
# explicit: a generic ``*_id`` walk would expose fields which the validator
# does not authorize for bounded repair.
_SOURCE_BASIS_SPECS: tuple[tuple[str, str], ...] = (
    ("event_ids", "events"),
    ("source_event_ids", "events"),
    ("owned_event_ids", "events"),
    ("owned_source_event_ids", "events"),
    ("passage_ids", "passages"),
    ("source_passage_ids", "passages"),
    ("source_ids", "sources"),
    ("character_ids", "characters"),
    ("place_ids", "places"),
    ("location_ids", "places"),
    ("world_rule_ids", "world_rules"),
    ("rule_ids", "world_rules"),
    ("symbol_ids", "symbols"),
    ("fact_ids", "facts"),
    ("conflict_ids", "conflicts"),
    ("variant_ids", "variants"),
)

_DIRECT_SCENE_SPECS: tuple[tuple[str, str], ...] = (
    ("character_ids", "characters"),
    ("place_ids", "places"),
    ("location_ids", "places"),
    ("world_rule_ids", "world_rules"),
    ("rule_ids", "world_rules"),
    ("symbol_ids", "symbols"),
    ("fact_ids", "facts"),
    ("source_ids", "sources"),
    ("passage_ids", "passages"),
)

_DIRECT_EVENT_SPECS: tuple[tuple[str, str], ...] = (
    ("event_ids", "events"),
    ("source_event_ids", "events"),
    ("owned_event_ids", "events"),
    ("owned_source_event_ids", "events"),
)

_BEAT_LIST_SPECS: tuple[tuple[str, str], ...] = (
    ("participants", "characters"),
    ("character_ids", "characters"),
    ("place_ids", "places"),
    ("location_ids", "places"),
    ("world_rule_ids", "world_rules"),
    ("rule_ids", "world_rules"),
    ("symbol_ids", "symbols"),
    ("fact_ids", "facts"),
    ("conflict_ids", "conflicts"),
    ("source_event_ids", "events"),
    ("event_ids", "events"),
    ("source_refs", "__all__"),
)

_BEAT_STRING_SPECS: tuple[tuple[str, str], ...] = (
    ("location_id", "places"),
    ("source_event_id", "events"),
)

_LIFECYCLE_MAP_FIELDS: tuple[str, ...] = (
    "scene_intent",
    "start_state",
    "turning_event",
    "end_state",
    "handoff_chain",
)

_OVERVIEW_REQUIRED_STRING_FIELDS: tuple[str, ...] = (
    "title",
    "phase",
    "purpose",
    "visualizable_action",
    "grounding_note",
    "time_of_day",
)

_OVERVIEW_TYPE_STRING_FIELDS: tuple[str, ...] = ("conflict", "turn")

_KNOWN_ROOT_FIELDS = frozenset(
    {
        "source_basis",
        "research_refs",
        "affect",
        "location",
        "time_of_day_visual_basis",
        "preservation",
        "reveal_contract",
        *_LIFECYCLE_MAP_FIELDS,
        *_OVERVIEW_REQUIRED_STRING_FIELDS,
        *_OVERVIEW_TYPE_STRING_FIELDS,
        *(field for field, _ in _DIRECT_SCENE_SPECS),
        *(field for field, _ in _DIRECT_EVENT_SPECS),
    }
)


def _text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    return str(value).strip()


def _pointer(*parts: object) -> str:
    """Build a pointer for the fixed field names used by this module."""

    return "/" + "/".join(
        str(part).replace("~", "~0").replace("/", "~1") for part in parts
    )


def _safe_value(value: Any) -> Any:
    """Return a JSON-serializable diagnostic snapshot without mutating input."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else repr(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_value(child) for child in value]
    return repr(value)


def _dedupe_sorted(values: Sequence[Any] | set[Any]) -> list[str]:
    result = {_text(value) for value in values if _text(value)}
    return sorted(result)


def _maps_for_registry(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    normalized = _registry_for_validation(registry if isinstance(registry, Mapping) else {})
    return _registry_maps(normalized)


def scene_digest(scene: Mapping[str, Any]) -> str:
    """Return the stable SHA-256 digest used to bind a patch to one scene."""

    if not isinstance(scene, Mapping):
        raise FieldPatchError("scene must be a mapping")
    try:
        payload = json.dumps(
            dict(scene),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FieldPatchError("scene cannot be represented as canonical JSON") from exc
    return hashlib.sha256(payload).hexdigest()


def _issue(
    issues: dict[str, dict[str, Any]],
    *,
    path: str,
    code: str,
    expected_type: str,
    current: Any,
    exists: bool,
    message: str,
    allowed_values: Sequence[str] | None = None,
    allow_remove: bool = False,
) -> None:
    if path in issues:
        return
    record: dict[str, Any] = {
        "path": path,
        "code": code,
        "expected_type": expected_type,
        "current": _safe_value(current),
        "exists": bool(exists),
        "message": str(message),
    }
    if allowed_values is not None:
        record["allowed_values"] = _dedupe_sorted(allowed_values)
    if allow_remove:
        record["allow_remove"] = True
    issues[path] = record


def _all_ids(maps: Mapping[str, Mapping[str, Any]]) -> set[str]:
    result: set[str] = set()
    for category in maps.values():
        result.update(_text(key) for key in category if _text(key))
    return result


def _sequence(scene: Mapping[str, Any]) -> tuple[str, list[Any]] | None:
    for field in ("event_sequence", "events", "beats"):
        value = scene.get(field)
        if isinstance(value, list):
            return field, value
        # Story validation accepts tuples as legacy input.  A tuple cannot be
        # leaf-patched in place, so it will be diagnosed as a malformed field
        # only when a specific beat field is itself reported.
        if isinstance(value, tuple):
            return field, list(value)
    return None


def _planned_event_ids(scene_plan: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(scene_plan, Mapping):
        return []
    value = scene_plan.get("source_event_ids")
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value if _text(item)]


def _scene_event_ids(scene: Mapping[str, Any]) -> list[str]:
    sequence = _sequence(scene)
    if sequence is None:
        return []
    _, beats = sequence
    result: list[str] = []
    for beat in beats:
        if not isinstance(beat, Mapping):
            continue
        value = beat.get("source_event_ids", beat.get("event_ids"))
        if isinstance(value, (list, tuple)):
            result.extend(_text(item) for item in value if _text(item))
        elif "source_event_id" in beat and _text(beat.get("source_event_id")):
            result.append(_text(beat.get("source_event_id")))
    return result


def _valid_values(
    maps: Mapping[str, Mapping[str, Any]],
    category: str,
    all_source_ids: set[str],
) -> set[str]:
    if category == "__all__":
        return set(all_source_ids)
    return {
        _text(item_id)
        for item_id in maps.get(category, {})
        if _text(item_id)
    }


def _allowed_id(value: str, allowed: set[str], category: str) -> bool:
    """Match the validator's special handling for dotted research refs."""

    return value in allowed or (category == "__all__" and value.startswith("research."))


def _id_list_issue(
    issues: dict[str, dict[str, Any]],
    *,
    container: Mapping[str, Any],
    field: str,
    path_prefix: Sequence[object],
    category: str,
    maps: Mapping[str, Mapping[str, Any]],
    all_source_ids: set[str],
    unknown_error: bool,
    malformed_error: bool,
) -> None:
    if field not in container or not (unknown_error or malformed_error):
        return
    value = container.get(field)
    path = _pointer(*path_prefix, field)
    allowed = _valid_values(maps, category, all_source_ids)

    # A scalar or a tuple is a malformed JSON-array field.  Replacing the
    # whole field is bounded because the validator has already identified its
    # exact owner and the schema accepts only strings in the replacement.
    if not isinstance(value, list):
        _issue(
            issues,
            path=path,
            code="story.scene_id_list_invalid",
            expected_type="strings",
            current=value,
            exists=True,
            allowed_values=sorted(allowed),
            message=f"{path} must be an array of allowed string IDs",
        )
        return

    # A list with one malformed or unknown element is still repaired at the
    # scalar leaf.  This keeps valid neighbours immutable and gives the
    # author the safe option of removing an unregistered descriptive value.
    # Whole-list replacement remains reserved for a malformed outer field.
    for index, item in enumerate(value):
        item_path = _pointer(*path_prefix, field, index)
        malformed_item = type(item) is not str or not item.strip()
        unknown_item = not malformed_item and not _allowed_id(item, allowed, category)
        if malformed_item:
            if not malformed_error:
                continue
            _issue(
                issues,
                path=item_path,
                code="story.scene_id_list_invalid",
                expected_type="string",
                current=item,
                exists=True,
                allowed_values=sorted(allowed),
                allow_remove=True,
                message=(
                    f"{item_path} is not a valid registered ID; if no registered ID matches, "
                    "null may remove only this exact list element"
                ),
            )
            continue
        if unknown_error and unknown_item:
            _issue(
                issues,
                path=item_path,
                code="story.scene_unknown_id",
                expected_type="string",
                current=item,
                exists=True,
                allowed_values=sorted(allowed),
                allow_remove=True,
                message=(
                    f"{item_path} is not a known ID; if no registered ID matches, "
                    "null may remove only this exact list element"
                ),
            )


def _id_string_issue(
    issues: dict[str, dict[str, Any]],
    *,
    container: Mapping[str, Any],
    field: str,
    path_prefix: Sequence[object],
    category: str,
    maps: Mapping[str, Mapping[str, Any]],
    all_source_ids: set[str],
    unknown_error: bool,
    malformed_error: bool,
) -> None:
    if field not in container or not (unknown_error or malformed_error):
        return
    value = container.get(field)
    path = _pointer(*path_prefix, field)
    allowed = _valid_values(maps, category, all_source_ids)
    if type(value) is not str or not value.strip():
        _issue(
            issues,
            path=path,
            code="story.scene_id_list_invalid",
            expected_type="string",
            current=value,
            exists=True,
            allowed_values=sorted(allowed),
            message=f"{path} must be one allowed string ID",
        )
        return
    if unknown_error and value not in allowed:
        _issue(
            issues,
            path=path,
            code="story.scene_unknown_id",
            expected_type="string",
            current=value,
            exists=True,
            allowed_values=sorted(allowed),
            message=f"{path} is not a known ID",
        )


def _diagnose_id_fields(
    issues: dict[str, dict[str, Any]],
    *,
    container: Mapping[str, Any],
    path_prefix: Sequence[object],
    specs: Sequence[tuple[str, str]],
    maps: Mapping[str, Mapping[str, Any]],
    all_source_ids: set[str],
    unknown_error: bool,
    malformed_error: bool,
) -> None:
    for field, category in specs:
        _id_list_issue(
            issues,
            container=container,
            field=field,
            path_prefix=path_prefix,
            category=category,
            maps=maps,
            all_source_ids=all_source_ids,
            unknown_error=unknown_error,
            malformed_error=malformed_error,
        )


def field_repair_issues(
    scene: Mapping[str, Any],
    registry: Mapping[str, Any],
    validation_errors: Sequence[str],
    scene_plan: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Diagnose only concrete, bounded repair paths in ``scene``.

    Validation errors are aggregate reason keys.  The returned diagnostics
    are computed from the scene itself; no path supplied by a model is ever
    trusted.  Empty output means the reported errors require scene-level
    authoring or cannot be safely localized.
    """

    if not isinstance(scene, Mapping):
        return []
    errors = {str(error) for error in validation_errors}
    if not errors:
        return []

    maps = _maps_for_registry(registry if isinstance(registry, Mapping) else {})
    all_source_ids = _all_ids(maps)
    unknown_error = "story.scene_unknown_id" in errors
    malformed_error = "story.scene_id_list_invalid" in errors
    issues: dict[str, dict[str, Any]] = {}

    basis = scene.get("source_basis")
    if isinstance(basis, Mapping):
        _diagnose_id_fields(
            issues,
            container=basis,
            path_prefix=("source_basis",),
            specs=_SOURCE_BASIS_SPECS,
            maps=maps,
            all_source_ids=all_source_ids,
            unknown_error=unknown_error,
            malformed_error=malformed_error,
        )
        if _SOURCE_COVERAGE_ERROR in errors and not any(
            field in basis
            for field in ("event_ids", "source_event_ids", "owned_event_ids", "owned_source_event_ids")
        ):
            expected_events = _planned_event_ids(scene_plan) or _scene_event_ids(scene)
            if expected_events:
                _issue(
                    issues,
                    path=_pointer("source_basis", "event_ids"),
                    code=_SOURCE_COVERAGE_ERROR,
                    expected_type="strings",
                    current=None,
                    exists=False,
                    allowed_values=sorted(_valid_values(maps, "events", all_source_ids)),
                    message="/source_basis/event_ids is required for the frozen scene event ownership",
                )
    elif _SOURCE_COVERAGE_ERROR in errors:
        # A missing source_basis cannot be repaired by inventing a complete
        # object.  If the frozen plan supplies the exact event ownership,
        # expose just the required list field; apply_field_patch creates the
        # one missing parent mapping as part of that diagnosed operation.
        expected_events = _planned_event_ids(scene_plan) or _scene_event_ids(scene)
        if expected_events:
            _issue(
                issues,
                path=_pointer("source_basis", "event_ids"),
                code=_SOURCE_COVERAGE_ERROR,
                expected_type="strings",
                current=None,
                exists=False,
                allowed_values=sorted(_valid_values(maps, "events", all_source_ids)),
                message="/source_basis/event_ids is required for the frozen scene event ownership",
            )

    if unknown_error or malformed_error:
        _diagnose_id_fields(
            issues,
            container=scene,
            path_prefix=(),
            specs=_DIRECT_SCENE_SPECS,
            maps=maps,
            all_source_ids=all_source_ids,
            unknown_error=unknown_error,
            malformed_error=malformed_error,
        )

    sequence = _sequence(scene)
    if sequence is not None and (unknown_error or malformed_error):
        sequence_field, beats = sequence
        for index, beat in enumerate(beats):
            if not isinstance(beat, Mapping):
                continue
            _diagnose_id_fields(
                issues,
                container=beat,
                path_prefix=(sequence_field, index),
                specs=_BEAT_LIST_SPECS,
                maps=maps,
                all_source_ids=all_source_ids,
                unknown_error=unknown_error,
                malformed_error=malformed_error,
            )
            for field, category in _BEAT_STRING_SPECS:
                _id_string_issue(
                    issues,
                    container=beat,
                    field=field,
                    path_prefix=(sequence_field, index),
                    category=category,
                    maps=maps,
                    all_source_ids=all_source_ids,
                    unknown_error=unknown_error,
                    malformed_error=malformed_error,
                )

    if (unknown_error or malformed_error) and "research_refs" in scene:
        _id_list_issue(
            issues,
            container=scene,
            field="research_refs",
            path_prefix=(),
            category="__all__",
            maps=maps,
            all_source_ids=all_source_ids,
            unknown_error=unknown_error,
            malformed_error=malformed_error,
        )

    if _LIFECYCLE_ERROR in errors:
        for field in _LIFECYCLE_MAP_FIELDS:
            if not isinstance(scene.get(field), Mapping):
                _issue(
                    issues,
                    path=_pointer(field),
                    code=_LIFECYCLE_ERROR,
                    expected_type="object",
                    current=scene.get(field),
                    exists=field in scene,
                    message=f"/{field} must be a mapping for the scene lifecycle",
                )
        if not isinstance(scene.get("preservation"), Mapping) and not isinstance(
            scene.get("reveal_contract"), Mapping
        ):
            # ``preservation`` is the canonical output field.  If the
            # alternate contract is already a mapping it is deliberately not
            # exposed, because the validator accepts that existing contract.
            _issue(
                issues,
                path=_pointer("preservation"),
                code=_LIFECYCLE_ERROR,
                expected_type="object",
                current=scene.get("preservation"),
                exists="preservation" in scene,
                message="/preservation or /reveal_contract must be a mapping",
            )

    if _OVERVIEW_ERROR in errors:
        for field in _OVERVIEW_REQUIRED_STRING_FIELDS:
            value = scene.get(field)
            if not _text(value):
                _issue(
                    issues,
                    path=_pointer(field),
                    code=_OVERVIEW_ERROR,
                    expected_type="string",
                    current=value,
                    exists=field in scene,
                    message=f"/{field} must be a non-empty string",
                )
        for field in _OVERVIEW_TYPE_STRING_FIELDS:
            if not isinstance(scene.get(field), str):
                _issue(
                    issues,
                    path=_pointer(field),
                    code=_OVERVIEW_ERROR,
                    expected_type="string",
                    current=scene.get(field),
                    exists=field in scene,
                    message=f"/{field} must be a string",
                )
        if not isinstance(scene.get("affect"), Mapping):
            _issue(
                issues,
                path=_pointer("affect"),
                code=_OVERVIEW_ERROR,
                expected_type="object",
                current=scene.get("affect"),
                exists="affect" in scene,
                message="/affect must be an object",
            )

    if _LOCATION_ERROR in errors:
        location = scene.get("location")
        if not isinstance(location, Mapping):
            _issue(
                issues,
                path=_pointer("location"),
                code=_LOCATION_ERROR,
                expected_type="object",
                current=location,
                exists="location" in scene,
                message="/location must be an object",
            )
        elif not _text(location.get("name")):
            _issue(
                issues,
                path=_pointer("location", "name"),
                code=_LOCATION_ERROR,
                expected_type="string",
                current=location.get("name"),
                exists="name" in location,
                message="/location/name must be a non-empty string",
            )

    if _VISUAL_BASIS_ERROR in errors:
        basis_text = scene.get("time_of_day_visual_basis")
        required_dimensions = ("光源", "明るさ", "影", "色温度")
        if type(basis_text) is not str or not basis_text.strip() or any(
            dimension not in basis_text for dimension in required_dimensions
        ):
            _issue(
                issues,
                path=_pointer("time_of_day_visual_basis"),
                code=_VISUAL_BASIS_ERROR,
                expected_type="string",
                current=basis_text,
                exists="time_of_day_visual_basis" in scene,
                message="/time_of_day_visual_basis must contain 光源, 明るさ, 影, and 色温度",
            )

    if _TURNING_ERROR in errors and sequence is not None:
        sequence_field, beats = sequence
        beat_ids = {
            _text(beat.get("beat_id"))
            for beat in beats
            if isinstance(beat, Mapping) and _text(beat.get("beat_id"))
        }
        turning = scene.get("turning_event")
        if isinstance(turning, Mapping) and beat_ids:
            for field in ("beat_id", "event_beat_id"):
                if field not in turning:
                    continue
                value = turning.get(field)
                if type(value) is str and value in beat_ids:
                    continue
                if type(value) is str and value.strip():
                    _issue(
                        issues,
                        path=_pointer("turning_event", field),
                        code=_TURNING_ERROR,
                        expected_type="string",
                        current=value,
                        exists=True,
                        allowed_values=sorted(beat_ids),
                        message=f"/turning_event/{field} must identify a beat in {sequence_field}",
                    )

    return list(issues.values())


def _issue_paths(issues: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for issue in issues:
        if not isinstance(issue, Mapping):
            raise FieldPatchError("field repair issues must be objects")
        path = issue.get("path")
        if not isinstance(path, str) or not path.startswith("/") or path == "/":
            raise FieldPatchError(f"invalid diagnosed field path: {path!r}")
        if path in result:
            raise FieldPatchError(f"duplicate diagnosed field path: {path}")
        expected_type = issue.get("expected_type")
        if expected_type not in {"string", "strings", "object"}:
            raise FieldPatchError(f"invalid expected_type for {path}: {expected_type!r}")
        if not _supported_path(path):
            raise FieldPatchError(f"unsupported diagnosed field path: {path}")
        result[path] = issue
    if not result:
        raise FieldPatchError("field repair has no diagnosed paths")
    return result


def _supported_path(path: str) -> bool:
    """Check the fixed path grammar without normalizing the caller's path."""

    if not path.startswith("/") or "~" in path:
        return False
    parts = path.split("/")[1:]
    if any(part == "" for part in parts):
        return False
    root = parts[0] if parts else ""

    def is_index(value: str) -> bool:
        return value == "0" or (value.isdigit() and not value.startswith("0"))

    if root == "turning_event":
        return len(parts) == 2 and parts[1] in {"beat_id", "event_beat_id"}
    if (
        root in _LIFECYCLE_MAP_FIELDS
        or root in _OVERVIEW_REQUIRED_STRING_FIELDS
        or root in _OVERVIEW_TYPE_STRING_FIELDS
    ):
        return len(parts) == 1
    if root in {"affect", "location", "preservation", "reveal_contract", "time_of_day_visual_basis"}:
        if root == "location":
            return parts == ["location"] or parts == ["location", "name"]
        return len(parts) == 1
    if root == "research_refs":
        return len(parts) == 1 or (len(parts) == 2 and is_index(parts[1]))
    if root == "source_basis":
        fields = {field for field, _ in _SOURCE_BASIS_SPECS}
        return len(parts) in {2, 3} and parts[1] in fields and (
            len(parts) == 2 or is_index(parts[2])
        )
    direct_fields = {field for field, _ in _DIRECT_SCENE_SPECS}
    if root in direct_fields:
        return len(parts) in {1, 2} and (len(parts) == 1 or is_index(parts[1]))
    if root == "event_sequence" or root == "events" or root == "beats":
        if len(parts) < 3 or not is_index(parts[1]):
            return False
        field = parts[2]
        if field in {name for name, _ in _BEAT_LIST_SPECS}:
            return len(parts) in {3, 4} and (len(parts) == 3 or is_index(parts[3]))
        if field in {name for name, _ in _BEAT_STRING_SPECS}:
            return len(parts) == 3
        return False
    return False


def build_field_patch_schema(
    scene: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the closed provider schema for one exact scene and issue set."""

    if not isinstance(scene, Mapping):
        raise FieldPatchError("scene must be a mapping")
    scene_id = scene.get("scene_id")
    if type(scene_id) is not str:
        raise FieldPatchError("scene.scene_id must be a string")
    paths = _issue_paths(issues)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scene_id", "base_digest", "operations"],
        "properties": {
            "scene_id": {"type": "string", "enum": [scene_id]},
            "base_digest": {"type": "string", "enum": [scene_digest(scene)]},
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path", "value"],
                    "properties": {
                        "path": {"type": "string", "enum": list(paths)},
                        "value": {
                            "anyOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "null"},
                            ]
                        },
                    },
                },
            },
        },
    }


_MISSING = object()
_REMOVE = object()


def _is_index(segment: str) -> bool:
    return segment == "0" or (segment.isdigit() and not segment.startswith("0"))


def _decode_path_segment(segment: str) -> str:
    # Generated paths never require escaping.  Refusing escape sequences keeps
    # ``/a/~1b`` from becoming a normalized alternate path at apply time.
    if "~" in segment:
        raise FieldPatchError(f"path escape sequences are not allowed: {segment!r}")
    return segment


def _read_pointer(root: Any, path: str) -> Any:
    current = root
    for segment in path.split("/")[1:]:
        segment = _decode_path_segment(segment)
        if isinstance(current, Mapping):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list):
            if not _is_index(segment) or int(segment) >= len(current):
                return _MISSING
            current = current[int(segment)]
        else:
            return _MISSING
    return current


def _write_pointer(root: dict[str, Any], path: str, value: Any) -> None:
    parts = [_decode_path_segment(part) for part in path.split("/")[1:]]
    if not parts or any(part == "" for part in parts):
        raise FieldPatchError(f"invalid patch path: {path}")
    current: Any = root
    for offset, segment in enumerate(parts[:-1]):
        next_segment = parts[offset + 1]
        if isinstance(current, Mapping):
            if segment not in current or not isinstance(current[segment], (Mapping, list)):
                # The one missing parent permitted by field diagnostics is
                # source_basis for its diagnosed event_ids list.
                if offset == 0 and segment == "source_basis":
                    current[segment] = {}
                else:
                    raise FieldPatchError(f"cannot traverse missing patch parent: {path}")
            current = current[segment]
        elif isinstance(current, list):
            if not _is_index(segment) or int(segment) >= len(current):
                raise FieldPatchError(f"patch array index is out of range: {path}")
            current = current[int(segment)]
        else:
            raise FieldPatchError(f"cannot traverse patch parent: {path}")
        if isinstance(current, list) and not _is_index(next_segment):
            raise FieldPatchError(f"patch array index is required: {path}")
    final = parts[-1]
    if isinstance(current, Mapping):
        current[final] = value
    elif isinstance(current, list):
        if not _is_index(final) or int(final) >= len(current):
            raise FieldPatchError(f"patch array index is out of range: {path}")
        current[int(final)] = value
    else:
        raise FieldPatchError(f"cannot write patch path: {path}")


def _paths_overlap(first: str, second: str) -> bool:
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def _list_leaf_parent(path: str) -> tuple[str, int] | None:
    """Return the original list pointer and index for a diagnosed list leaf."""

    parts = path.split("/")[1:]
    if not parts or not _is_index(parts[-1]):
        return None
    index = int(parts[-1])
    if parts[0] == "source_basis" and len(parts) == 3:
        if parts[1] in {field for field, _ in _SOURCE_BASIS_SPECS}:
            return "/" + "/".join(parts[:-1]), index
    if parts[0] == "research_refs" and len(parts) == 2:
        return "/research_refs", index
    if parts[0] in {field for field, _ in _DIRECT_SCENE_SPECS} and len(parts) == 2:
        return "/" + parts[0], index
    if parts[0] in {"event_sequence", "events", "beats"} and len(parts) == 4:
        if parts[2] in {field for field, _ in _BEAT_LIST_SPECS} and _is_index(parts[1]):
            return "/" + "/".join(parts[:-1]), index
    return None


def _id_value_allowed(value: str, issue: Mapping[str, Any], path: str) -> bool:
    allowed = issue.get("allowed_values")
    if not isinstance(allowed, (list, tuple, set, frozenset)):
        return True
    allowed_text = {_text(item) for item in allowed}
    if value in allowed_text:
        return True
    # Dotted research pointers are explicitly accepted by the story
    # validator for source_refs/research_refs and cannot be exhaustively
    # enumerated in an issue's allowed_values list.
    if (path.endswith("/source_refs") or path.endswith("/research_refs")) and value.startswith("research."):
        return True
    if "/source_refs/" in path or "/research_refs/" in path:
        return value.startswith("research.")
    return False


def _object_value(value: Any, path: str) -> dict[str, Any]:
    if type(value) is not str:
        raise FieldPatchError(f"object patch value for {path} must be a JSON string")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, child in pairs:
            if key in decoded:
                raise ValueError(f"duplicate object key: {key}")
            decoded[key] = child
        return decoded

    def reject_nonfinite(token: str) -> Any:
        raise ValueError(f"non-finite JSON number: {token}")

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FieldPatchError(f"object patch value for {path} is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise FieldPatchError(f"object patch value for {path} must decode to an object")
    return decoded


def _coerce_patch_value(value: Any, issue: Mapping[str, Any], path: str) -> Any:
    if value is None:
        if issue.get("allow_remove") is True and _list_leaf_parent(path) is not None:
            return _REMOVE
        raise FieldPatchError(f"null removal is not allowed for {path}")
    expected = issue.get("expected_type")
    if expected == "object":
        return _object_value(value, path)
    if expected == "string":
        if type(value) is not str or not value.strip():
            raise FieldPatchError(f"patch value for {path} must be a non-empty string")
        if not _id_value_allowed(value, issue, path):
            raise FieldPatchError(f"patch value for {path} is outside allowed_values")
        return value
    if expected == "strings":
        if type(value) is not list or any(type(item) is not str or not item.strip() for item in value):
            raise FieldPatchError(f"patch value for {path} must be an array of non-empty strings")
        for item in value:
            if not _id_value_allowed(item, issue, path):
                raise FieldPatchError(f"patch value for {path} contains an ID outside allowed_values")
        return list(value)
    raise FieldPatchError(f"unsupported expected_type for {path}: {expected!r}")


def apply_field_patch(
    scene: Mapping[str, Any],
    response: Mapping[str, Any],
    issues: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply a strict field patch to a deep copy of ``scene``."""

    if not isinstance(scene, Mapping):
        raise FieldPatchError("scene must be a mapping")
    if not isinstance(response, Mapping):
        raise FieldPatchError("field patch response must be an object")
    issue_by_path = _issue_paths(issues)
    if set(response) != {"scene_id", "base_digest", "operations"}:
        raise FieldPatchError("field patch response has unexpected top-level properties")
    if type(response.get("scene_id")) is not str or response.get("scene_id") != scene.get("scene_id"):
        raise FieldPatchError("field patch scene_id does not match the original scene")
    expected_digest = scene_digest(scene)
    if type(response.get("base_digest")) is not str or response.get("base_digest") != expected_digest:
        raise FieldPatchError("field patch base_digest does not match the original scene")
    operations = response.get("operations")
    if type(operations) is not list or not operations:
        raise FieldPatchError("field patch operations must be a non-empty array")

    operation_paths: list[str] = []
    for operation in operations:
        if not isinstance(operation, Mapping) or set(operation) != {"path", "value"}:
            raise FieldPatchError("each field patch operation must contain only path and value")
        path = operation.get("path")
        if not isinstance(path, str) or path not in issue_by_path:
            raise FieldPatchError(f"patch path is not in the diagnosed allowlist: {path!r}")
        if path in operation_paths:
            raise FieldPatchError(f"duplicate patch path: {path}")
        operation_paths.append(path)

    for index, first in enumerate(operation_paths):
        for second in operation_paths[index + 1 :]:
            if _paths_overlap(first, second):
                raise FieldPatchError(f"overlapping patch paths: {first} and {second}")

    # Validate and resolve every operation against the untouched original.
    # Removal indices are therefore stable even when one list has several
    # removals; writes happen first and removals happen in descending order.
    replacements: list[tuple[str, Any]] = []
    removal_groups: dict[str, list[int]] = {}
    for operation in operations:
        path = operation["path"]
        issue = issue_by_path[path]
        current = _read_pointer(scene, path)
        diagnosed_exists = issue.get("exists")
        if diagnosed_exists is False:
            if current is not _MISSING:
                raise FieldPatchError(f"diagnosed field is no longer missing: {path}")
        elif current is _MISSING:
            raise FieldPatchError(f"diagnosed field leaf does not exist: {path}")
        elif "current" in issue and _safe_value(current) != issue.get("current"):
            raise FieldPatchError(f"diagnosed field value changed before patch: {path}")

        value = _coerce_patch_value(operation.get("value"), issue, path)
        if value is _REMOVE:
            parent_info = _list_leaf_parent(path)
            if parent_info is None or issue.get("allow_remove") is not True:
                raise FieldPatchError(f"null removal is not allowed for {path}")
            parent_path, index = parent_info
            parent = _read_pointer(scene, parent_path)
            if not isinstance(parent, list) or index >= len(parent):
                raise FieldPatchError(f"removal list element does not exist: {path}")
            current_item = parent[index]
            # A malicious or stale issue must not turn a registered ID into a
            # deletion.  Dotted research refs are valid IDs under the same
            # rule used by the validator.
            if type(current_item) is str and _id_value_allowed(current_item, issue, path):
                raise FieldPatchError(f"cannot remove a valid registered ID: {path}")
            removal_groups.setdefault(parent_path, []).append(index)
            continue

        if current is not _MISSING and current == value:
            raise FieldPatchError(f"patch operation is a no-op: {path}")
        replacements.append((path, value))

    for parent_path, indexes in removal_groups.items():
        parent = _read_pointer(scene, parent_path)
        if not isinstance(parent, list):
            raise FieldPatchError(f"removal parent is not a list: {parent_path}")
        if len(parent) - len(indexes) <= 0:
            raise FieldPatchError(
                f"removal would empty the diagnosed ID list: {parent_path}"
            )

    patched = deepcopy(dict(scene))
    for path, value in replacements:
        _write_pointer(patched, path, value)
    for parent_path, indexes in removal_groups.items():
        parent = _read_pointer(patched, parent_path)
        if not isinstance(parent, list):
            raise FieldPatchError(f"removal parent is not a list: {parent_path}")
        for index in sorted(indexes, reverse=True):
            del parent[index]

    if patched == dict(scene):
        raise FieldPatchError("field patch makes no changes")
    return patched


__all__ = [
    "FieldPatchError",
    "apply_field_patch",
    "build_field_patch_schema",
    "field_repair_issues",
    "scene_digest",
]
