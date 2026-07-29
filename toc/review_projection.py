"""Stage-scoped source fingerprints for review evidence.

Only ``scenes[].render_units`` is a post-p680 execution overlay.  Pre-p800
authoring reviews may exclude that one field; later reviews and unknown stages
remain bound to the exact file bytes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


ReviewKind = Literal["review_loop", "semantic"]

REVIEW_LOOP_MANIFEST_PROJECTION_STAGES = frozenset(
    {
        "script",
        "production_readiness",
        "scene_set",
        "scene_detail",
        "cut_blueprint",
        "asset",
        "scene_implementation_hard",
        "scene_implementation_judgment",
    }
)
SEMANTIC_MANIFEST_PROJECTION_STAGES = frozenset(
    {
        "scene_set",
        "scene_detail",
        "cut_blueprint",
        "asset_plan",
        "image_prompt",
    }
)
VIDEO_MANIFEST_RELPATH = "video_manifest.md"
VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA = (
    "toc.video_manifest.review_projection.v1"
)
RAW_REVIEW_SOURCE_FINGERPRINT_POLICY = "toc.review_source.raw_bytes.v1"
REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD = "fingerprint_policy"

_YAML_FENCE_RE = re.compile(
    r"^[ \t]*```yaml[ \t]*\r?\n(?P<body>.*?)^[ \t]*```[ \t]*(?:\r?\n|$)",
    flags=re.MULTILINE | re.DOTALL,
)
_YAML_FENCE_OPEN_RE = re.compile(
    r"^[ \t]*```yaml[ \t]*(?:\r?\n|$)",
    flags=re.MULTILINE,
)


_SafeLoaderBase = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_SafeDumper = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


class _StrictSafeLoader(_SafeLoaderBase):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _StrictSafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class ReviewProjectionError(ValueError):
    """Raised when a projected review source cannot be parsed safely."""


@dataclass(frozen=True)
class ReviewSourceFingerprint:
    sha256: str
    size_bytes: int
    projected: bool
    policy: str


def _manifest_yaml_text(text: str) -> str:
    matches = list(_YAML_FENCE_RE.finditer(text))
    openings = list(_YAML_FENCE_OPEN_RE.finditer(text))
    if openings:
        if len(openings) != 1 or len(matches) != 1:
            raise ReviewProjectionError(
                "video_manifest.md must contain exactly one complete YAML fence"
            )
        return matches[0].group("body")
    return text


def _load_video_manifest_projection_text(text: str) -> dict[str, object]:
    """Parse the projection from caller-owned text without reopening a path."""

    try:
        loaded = yaml.load(  # noqa: S506 - loader is a strict SafeLoader subclass.
            _manifest_yaml_text(text),
            Loader=_StrictSafeLoader,
        )
    except yaml.YAMLError as exc:
        raise ReviewProjectionError(
            f"video_manifest.md has invalid YAML: {exc}"
        ) from exc
    if not isinstance(loaded, dict):
        raise ReviewProjectionError(
            "video_manifest.md YAML root must be a mapping"
        )
    scenes = loaded.get("scenes")
    if not isinstance(scenes, list):
        raise ReviewProjectionError(
            "video_manifest.md scenes must be a list"
        )

    # Copy only the root, scene list, and direct scene mappings. Nested
    # objects stay shared, which preserves legitimate YAML alias structure
    # without mutating the loaded source graph.
    projected = dict(loaded)
    projected_scenes: list[dict[object, object]] = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise ReviewProjectionError(
                f"video_manifest.md scenes[{index}] must be a mapping"
            )
        # PyYAML preserves alias identity. Detach every direct scene mapping
        # before removing the overlay so an alias reachable elsewhere in the
        # manifest retains all of its fields in the projection.
        detached_scene = dict(scene)
        if "render_units" in detached_scene:
            render_units = detached_scene["render_units"]
            if not isinstance(render_units, list) or any(
                not isinstance(unit, dict) for unit in render_units
            ):
                raise ReviewProjectionError(
                    "video_manifest.md "
                    f"scenes[{index}].render_units must be a list of mappings"
                )
            detached_scene.pop("render_units")
        projected_scenes.append(detached_scene)
    projected["scenes"] = projected_scenes
    return projected


def _load_video_manifest_projection(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReviewProjectionError(
            f"could not read video_manifest.md for review projection: {exc}"
        ) from exc
    return _load_video_manifest_projection_text(text)


def video_manifest_review_projection_bytes(path: Path) -> bytes:
    """Return deterministic bytes excluding only direct scene render units."""

    payload = {
        "projection_schema": VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
        "video_manifest": _load_video_manifest_projection(path),
    }
    try:
        canonical = yaml.dump(
            payload,
            Dumper=_SafeDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
            width=2**31 - 1,
        )
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise ReviewProjectionError(
            f"video_manifest.md review projection is not serializable: {exc}"
        ) from exc
    return canonical.encode("utf-8")


def video_manifest_review_projection_bytes_from_bytes(
    content: bytes,
) -> bytes:
    """Project already-captured manifest bytes without reopening their path."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewProjectionError(
            f"video_manifest.md is not UTF-8: {exc}"
        ) from exc
    payload = {
        "projection_schema": VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
        "video_manifest": _load_video_manifest_projection_text(text),
    }
    try:
        canonical = yaml.dump(
            payload,
            Dumper=_SafeDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=True,
            width=2**31 - 1,
        )
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise ReviewProjectionError(
            f"video_manifest.md review projection is not serializable: {exc}"
        ) from exc
    return canonical.encode("utf-8")


def video_manifest_review_projection_sha256(path: Path) -> str:
    return hashlib.sha256(
        video_manifest_review_projection_bytes(path)
    ).hexdigest()


def _uses_manifest_projection(
    *,
    artifact_relpath: str,
    review_kind: ReviewKind,
    stage: str,
) -> bool:
    if review_kind not in {"review_loop", "semantic"}:
        raise ValueError(f"unknown review kind: {review_kind}")
    if artifact_relpath != VIDEO_MANIFEST_RELPATH:
        return False
    allowlist = (
        REVIEW_LOOP_MANIFEST_PROJECTION_STAGES
        if review_kind == "review_loop"
        else SEMANTIC_MANIFEST_PROJECTION_STAGES
    )
    return stage in allowlist


def review_source_fingerprint(
    path: Path,
    *,
    artifact_relpath: str,
    review_kind: ReviewKind,
    stage: str,
) -> ReviewSourceFingerprint:
    """Fingerprint one source under an explicit review-stage policy."""

    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ReviewProjectionError(
            f"could not read review source {artifact_relpath}: {exc}"
        ) from exc
    return review_source_fingerprint_bytes(
        content,
        artifact_relpath=artifact_relpath,
        review_kind=review_kind,
        stage=stage,
    )


def review_source_fingerprint_bytes(
    content: bytes,
    *,
    artifact_relpath: str,
    review_kind: ReviewKind,
    stage: str,
) -> ReviewSourceFingerprint:
    """Fingerprint caller-captured source bytes under the stage policy."""

    projected = _uses_manifest_projection(
        artifact_relpath=artifact_relpath,
        review_kind=review_kind,
        stage=stage,
    )
    try:
        fingerprint_content = (
            video_manifest_review_projection_bytes_from_bytes(content)
            if projected
            else content
        )
    except ReviewProjectionError:
        raise
    return ReviewSourceFingerprint(
        sha256=hashlib.sha256(fingerprint_content).hexdigest(),
        size_bytes=len(fingerprint_content),
        projected=projected,
        policy=(
            VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA
            if projected
            else RAW_REVIEW_SOURCE_FINGERPRINT_POLICY
        ),
    )
