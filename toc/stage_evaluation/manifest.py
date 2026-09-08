"""Structural manifest validation exports.

Manifest checks cover YAML shape, IDs, declared provider fields, paths, and
duration values. Review reports, critic digests, rubric thresholds, and
approval state are intentionally not part of this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.story_duration import normalize_target_duration

from .common import (
    _cut_contract_structure_issues,
    _node_cut_contract,
    as_dict,
    as_dotted_str,
    as_list,
    make_stage,
    nested_get,
)
from .manifest_nodes import (
    _iter_manifest_nodes,
    _iter_manifest_nodes_with_selectors,
)
from .pipeline import (
    _manifest_checks,
    _minimum_cut_issues,
    check_manifest_scene_series,
    check_manifest_single,
)


def _manifest_selectors(manifest: dict[str, Any]) -> set[str]:
    return {selector for selector, _node in _iter_manifest_nodes_with_selectors(manifest)}


def _manifest_duration_summary(manifest: dict[str, Any]) -> tuple[float, float, int]:
    raw_target = nested_get(manifest, ["video_metadata", "target_duration_seconds"])
    target = float(raw_target) if isinstance(raw_target, (int, float)) else 0.0
    actual = 0.0
    count = 0
    for node in _iter_manifest_nodes(manifest):
        duration = node.get("duration_seconds")
        if not isinstance(duration, (int, float)):
            duration = nested_get(node, ["video_generation", "duration_seconds"])
        if isinstance(duration, (int, float)):
            actual += float(duration)
        count += 1
    return target, actual, count


def _script_selectors_from_run(run_dir: Path, *, script_data: dict[str, Any] | None = None) -> set[str]:
    if script_data is None:
        path = run_dir / "script.md"
        if not path.is_file():
            return set()
        _text, script_data = load_structured_document(path)
    if not isinstance(script_data, dict):
        return set()
    selectors: set[str] = set()
    scenes = as_list(script_data.get("scenes")) or as_list(nested_get(script_data, ["script", "scenes"], []))
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut in cuts:
                if isinstance(cut, dict) and as_dotted_str(cut.get("cut_id")):
                    selectors.add(f"scene{scene_id}_cut{as_dotted_str(cut.get('cut_id'))}")
        else:
            selectors.add(f"scene{scene_id}")
    return selectors


def _script_readiness_issues_from_run(
    run_dir: Path,
    *,
    script_data: dict[str, Any] | None = None,
) -> list[str]:
    if script_data is None:
        path = run_dir / "script.md"
        if not path.is_file():
            return ["script.md:missing"]
        _text, script_data = load_structured_document(path)
    if not isinstance(script_data, dict):
        return ["script.md:invalid"]
    scenes = as_list(script_data.get("scenes")) or as_list(nested_get(script_data, ["script", "scenes"], []))
    if not scenes:
        return ["script.scenes:missing"]
    issues: list[str] = []
    seen: set[str] = set()
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene{index}:type")
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if not scene_id:
            issues.append(f"scene{index}:scene_id")
        elif scene_id in seen:
            issues.append(f"scene{scene_id}:scene_id.duplicate")
        seen.add(scene_id or f"#{index}")
        cuts = scene.get("cuts")
        if cuts is not None and not isinstance(cuts, list):
            issues.append(f"scene{scene_id or index}:cuts.type")
    return issues


def _append_manifest_contract_checks(
    checks: list[dict[str, Any]],
    *,
    nodes_with_selectors: list[tuple[str, dict[str, Any]]],
    strict_cut_contract: bool = False,
    reveal_constraints: list[dict[str, str]] | None = None,
    human_change_issues: list[str] | None = None,
) -> None:
    """Append deterministic cut-contract shape checks.

    The keyword arguments are retained for callers that used the former mixed
    validator. Reveal and human-review verdicts are deliberately ignored.
    """

    del reveal_constraints, human_change_issues
    issues: list[str] = []
    for selector, node in nodes_with_selectors:
        if "cut_contract" not in node:
            if strict_cut_contract:
                issues.append(f"{selector}:cut_contract:missing")
            continue
        issues.extend(f"{selector}:{issue}" for issue in _cut_contract_structure_issues(node.get("cut_contract")))
    if issues:
        from .common import add_check

        add_check(checks, "manifest.cut_contract_structure", False, "declared cut contracts have valid structure" + f" (issues: {','.join(issues[:8])})")


def _append_immersive_manifest_checks(
    checks: list[dict[str, Any]],
    body_text: str,
    data: dict[str, Any],
    scenes: list[Any],
    *,
    profile: str = "standard",
    path_label: str = "manifest",
    is_production: bool = True,
    run_dir: Path | None = None,
    script_data: dict[str, Any] | None = None,
) -> None:
    del body_text, scenes, profile, is_production, run_dir, script_data
    _manifest_checks(checks, "", data, profile="standard", flow="immersive", path_label=path_label)


__all__ = [
    "_append_immersive_manifest_checks",
    "_append_manifest_contract_checks",
    "_iter_manifest_nodes",
    "_iter_manifest_nodes_with_selectors",
    "_manifest_duration_summary",
    "_manifest_selectors",
    "_minimum_cut_issues",
    "_script_readiness_issues_from_run",
    "_script_selectors_from_run",
    "check_manifest_scene_series",
    "check_manifest_single",
]
