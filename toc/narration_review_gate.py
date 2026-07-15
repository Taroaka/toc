"""Shared deterministic narration-review gate predicates.

The frontend server and headless p720 runners must agree on the same active
cut inventory and the same explicit human-override semantics.  Keep this
module pure so callers can evaluate one locked manifest snapshot.
"""

from __future__ import annotations

from typing import Any, Iterator

from toc.immersive_manifest import (
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
)
from toc.narration_arc import narration_text_set_hash


REVISION_SCHEMA_VERSION = "narration_revision_v1"
_BAD_REVIEW_STATUSES = {
    "missing",
    "pending",
    "stale",
    "changes_requested",
    "failed",
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _selector(scene: dict[str, Any], node: dict[str, Any], *, is_cut: bool) -> str:
    raw_scene_id = scene.get("scene_id") or scene.get("id")
    scene_id = normalize_dotted_id(raw_scene_id) or str(raw_scene_id or "").strip() or "unknown"
    if not is_cut:
        return make_scene_cut_selector(scene_id)
    raw_cut_id = node.get("cut_id") or node.get("id")
    cut_id = normalize_dotted_id(raw_cut_id) or str(raw_cut_id or "").strip() or "unknown"
    return make_scene_cut_selector(scene_id, cut_id)


def iter_active_narration_nodes(
    manifest_data: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield canonical active scene/cut nodes in manifest order."""

    for raw_scene in _list(manifest_data.get("scenes")):
        if not isinstance(raw_scene, dict) or is_non_renderable_manifest_node(raw_scene):
            continue
        declared_cuts = raw_scene.get("cuts")
        if isinstance(declared_cuts, list) and declared_cuts:
            for raw_cut in declared_cuts:
                if not isinstance(raw_cut, dict) or is_non_renderable_manifest_node(raw_cut):
                    continue
                yield _selector(raw_scene, raw_cut, is_cut=True), raw_cut
            continue
        yield _selector(raw_scene, raw_scene, is_cut=False), raw_scene


def deterministic_narration_review_blockers(manifest_data: dict[str, Any]) -> list[str]:
    """Return cut-local/global blockers for the deterministic p720 half."""

    blockers: list[str] = []
    revision_aware = False
    for selector, node in iter_active_narration_nodes(manifest_data):
        narration = _dict(_dict(node.get("audio")).get("narration"))
        review = _dict(narration.get("review"))
        is_revision_aware = _dict(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION
        revision_aware = revision_aware or is_revision_aware
        agent_review_ok = review.get("agent_review_ok")
        human_override = review.get("human_review_ok") is True
        if is_revision_aware:
            valid_override = bool(
                agent_review_ok is False
                and human_override
                and str(review.get("human_review_reason") or "").strip()
            )
            if agent_review_ok is not True and not valid_override:
                blockers.append(selector)
                continue
            review_layers = [_dict(review.get("semantic")), _dict(review.get("delivery"))]
            if any(
                str(layer.get("status") or "").strip().lower() in _BAD_REVIEW_STATUSES
                for layer in review_layers
                if layer
            ):
                blockers.append(selector)
                continue
        elif agent_review_ok is False and not human_override:
            blockers.append(selector)
            continue

        local_arc = _dict(review.get("narration_arc_review") or review.get("arc"))
        arc_override = bool(
            local_arc.get("agent_review_ok") is False
            and local_arc.get("human_review_ok") is True
            and str(local_arc.get("human_review_reason") or "").strip()
        )
        if (
            local_arc.get("agent_review_ok") is False
            and not arc_override
        ) or str(local_arc.get("status") or "").strip().lower() in _BAD_REVIEW_STATUSES:
            blockers.append(selector)

    if revision_aware:
        workflow = _dict(manifest_data.get("narration_workflow"))
        arc_review = _dict(workflow.get("arc_review"))
        if (
            str(arc_review.get("status") or "").strip().lower() != "passed"
            or str(arc_review.get("narration_text_set_hash") or "") != narration_text_set_hash(manifest_data)
        ):
            blockers.append("full_run_arc")
    return blockers


def deterministic_narration_review_is_current(manifest_data: dict[str, Any]) -> bool:
    return not deterministic_narration_review_blockers(manifest_data)
