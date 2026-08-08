"""Canonical manifest evaluation policy."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.immersive_manifest import dotted_id_sort_key, make_scene_cut_selector
from toc.review_loop import (
    CUT_BLUEPRINT_GATE_MARKERS,
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE,
    SCENE_DETAIL_GATE_MARKERS,
    SCENE_SET_GATE_MARKERS,
    aggregated_review_relpath,
    critic_relpath,
    review_critic_report_issues,
    review_input_digest,
    review_input_snapshot_issues,
)
from toc.story_duration import (
    MAX_TARGET_DURATION_SECONDS,
    MINIMUM_EFFECTIVE_RATIO,
    MIN_TARGET_DURATION_SECONDS,
    audit_duration,
    normalize_target_duration,
)

from .common import (
    IMAGE_API_PROMPT_ABSTRACT_TERM_RE,
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION_V2,
    MOTION_LEAK_TOKENS,
    P400_READINESS_CHECK_IDS,
    UNRESOLVED_GATE_VALUES,
    _append_grounding_checks,
    _append_rubric_findings,
    _contract_list_paths,
    _cut_contract_structure_issues,
    _node_cut_contract,
    _scene_cut_selector,
    add_check,
    as_dict,
    as_dotted_str,
    as_int,
    as_list,
    flatten_without_keys,
    has_todo,
    make_stage,
    nested_get,
    non_empty,
    scene_time_of_day_contract_marker,
    scene_time_of_day_contract_missing,
    scene_time_of_day_visual_basis_contract_marker,
    scene_time_of_day_visual_basis_issues,
    score_from_checks,
)
from .manifest_nodes import _iter_manifest_nodes, _iter_manifest_nodes_with_selectors
from .research_story import (
    _image_api_prompt_policy,
    _image_api_prompt_text,
    _image_api_prompt_v1_issues,
    _image_api_prompt_v2_issues,
    _manifest_rubric,
    _scene_shot_mix_plan_v1_issues,
    _scene_state_progression_plan_issues,
)
from .script import (
    _cinematic_min_cuts_for_scene,
    _coverage_authored_event_beat_ids,
    _coverage_authored_obligation_ids,
    _coverage_minimum_cut_count,
    _cut_has_blueprint,
    _review_status,
    _scene_cut_coverage_plan,
    _scene_cut_coverage_plan_issues,
    _scene_cut_handoff_issues,
    _scene_cut_redundancy_issues,
    _scene_emotion_film_issue_map,
    _scene_event_readiness_issues,
    _scene_readiness_issues,
    _scene_requires_emotion_film_contract,
    _triangulation_review_issues,
)

def _minimum_cut_issues(manifest: dict[str, Any], *, min_cuts_per_scene: int | None = None) -> list[str]:
    issues: list[str] = []
    semantic_floor_sum = 0
    for index, scene in enumerate(as_list(manifest.get("scenes")), start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene[{index}]:invalid")
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id")) or str(index)
        cuts = [
            cut
            for cut in as_list(scene.get("cuts"))
            if not (isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() == "deleted")
        ]
        scene_min = min_cuts_per_scene if min_cuts_per_scene is not None else _cinematic_min_cuts_for_scene(scene)
        if len(cuts) < scene_min:
            issues.append(f"scene{scene_id}:cut_count_below_calculated_floor:{len(cuts)}<{scene_min}")
        plan = _scene_cut_coverage_plan(scene)
        planned_min = _coverage_minimum_cut_count(plan) if plan else 0
        semantic_floor_sum += planned_min
        if planned_min and len(cuts) < planned_min:
            issues.append(f"scene{scene_id}:cut_count_below_coverage_plan:{len(cuts)}<{planned_min}")
        min_cut_count = as_dict(plan.get("min_cut_count")) if plan else {}
        authored_semantic_count = len(_coverage_authored_obligation_ids(plan)) if plan else 0
        authored_event_count = len(_coverage_authored_event_beat_ids(plan)) if plan else 0
        declared_semantic_count = as_int(min_cut_count.get("by_distinct_semantic_obligations"))
        declared_event_count = as_int(min_cut_count.get("by_event_beats"))
        if plan and declared_semantic_count != authored_semantic_count:
            issues.append(
                f"scene{scene_id}:coverage_plan_distinct_semantic_obligations_mismatch:"
                f"{declared_semantic_count}!={authored_semantic_count}"
            )
        if plan and declared_event_count != authored_event_count:
            issues.append(
                f"scene{scene_id}:coverage_plan_event_beats_mismatch:"
                f"{declared_event_count}!={authored_event_count}"
            )
        selected = as_int(min_cut_count.get("selected"))
        if plan and selected is None:
            issues.append(f"scene{scene_id}:coverage_plan_selected_missing")
        elif selected is not None and selected < planned_min:
            issues.append(f"scene{scene_id}:coverage_plan_selected_below_floor")
            issues.append(f"scene{scene_id}:coverage_plan_selected_mismatch:{selected}!={planned_min}")
        elif selected is not None and selected > planned_min:
            issues.append(f"scene{scene_id}:coverage_plan_selected_mismatch:{selected}!={planned_min}")
    video_metadata = as_dict(manifest.get("video_metadata"))
    if video_metadata:
        declared_aggregate = as_int(video_metadata.get("minimum_cut_count"))
        if declared_aggregate is None:
            issues.append("video_metadata.minimum_cut_count_missing")
        elif declared_aggregate != semantic_floor_sum:
            issues.append(
                "video_metadata.minimum_cut_count_mismatch:"
                f"{declared_aggregate}!={semantic_floor_sum}"
            )
    return issues


def _manifest_duration_summary(manifest: dict[str, Any]) -> tuple[float, float, int]:
    target = nested_get(manifest, ["video_metadata", "target_duration_seconds"])
    target_seconds = float(target) if isinstance(target, (int, float)) else 0.0
    actual_seconds = 0.0
    cut_count = 0
    for node in _iter_manifest_nodes(manifest):
        if str(node.get("cut_status") or "").strip().lower() == "deleted":
            continue
        duration = node.get("duration_seconds")
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        if not isinstance(duration, (int, float)):
            duration = video_generation.get("duration_seconds")
        if isinstance(duration, (int, float)):
            actual_seconds += float(duration)
        cut_count += 1
    return target_seconds, actual_seconds, cut_count


_SCRIPT_DATA_UNSET = object()


def _script_selectors_from_run(
    run_dir: Path,
    *,
    script_data: dict[str, Any] | None | object = _SCRIPT_DATA_UNSET,
) -> set[str]:
    if script_data is _SCRIPT_DATA_UNSET:
        path = run_dir / "script.md"
        if not path.exists():
            return set()
        _text, script_data = load_structured_document(path)
    if not isinstance(script_data, dict):
        return set()
    data = script_data
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    selectors: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip() == "reference":
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            explicit = str(cut.get("selector") or "").strip()
            if explicit:
                selectors.add(explicit)
                continue
            cut_id = as_dotted_str(cut.get("cut_id"))
            if cut_id is not None:
                selectors.add(make_scene_cut_selector(scene_id, cut_id))
    return selectors


def _script_readiness_issues_from_run(
    run_dir: Path,
    *,
    script_data: dict[str, Any] | None | object = _SCRIPT_DATA_UNSET,
) -> list[str]:
    if script_data is _SCRIPT_DATA_UNSET:
        path = run_dir / "script.md"
        if not path.exists():
            return ["script.md:missing"]
        _text, script_data = load_structured_document(path)
    if not isinstance(script_data, dict):
        return ["script.md:missing"]
    data = script_data
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    issues: list[str] = []
    if not scenes:
        issues.append("script.scenes:missing")
    readiness_issues = _scene_readiness_issues(scenes)
    issues.extend(readiness_issues)
    issues.extend(_scene_event_readiness_issues(scenes, prefix="script"))
    if _review_status(data, "cut_blueprint_review") not in {"approved", "passed"}:
        issues.append("script.cut_blueprint_review_approved")
    renderable_scenes = [scene for scene in scenes if isinstance(scene, dict) and str(scene.get("kind") or "").strip() != "reference"]
    missing_cuts = [
        as_dotted_str(scene.get("scene_id")) or str(index + 1)
        for index, scene in enumerate(renderable_scenes)
        if not as_list(scene.get("cuts"))
    ]
    if missing_cuts:
        issues.append("script.renderable_scenes_have_cuts")
    missing_blueprints: list[str] = []
    for scene in renderable_scenes:
        scene_id = as_dotted_str(scene.get("scene_id")) or "unknown"
        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            if not _cut_has_blueprint(cut):
                cut_id = as_dotted_str(cut.get("cut_id")) or "unknown"
                missing_blueprints.append(f"scene{scene_id}_cut{cut_id}")
    if missing_blueprints:
        issues.append("script.cut_blueprints")
    return issues


def _manifest_selectors(manifest: dict[str, Any]) -> set[str]:
    selectors: set[str] = set()
    for selector, node in _iter_manifest_nodes_with_selectors(manifest):
        if str(node.get("cut_status") or "").strip().lower() == "deleted":
            continue
        explicit = str(node.get("selector") or "").strip()
        selectors.add(explicit or selector)
    return selectors


def _review_report_status(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("status:"):
            return stripped.split(":", 1)[1].strip().strip("`\"'").lower()
        if stripped.lower().startswith("- status:"):
            return stripped.split(":", 1)[1].strip().strip("`\"'").lower()
    return ""


def _review_report_issues(run_dir: Path) -> list[str]:
    required_reports = {
        "scene_set_review.md": ("status",),
        "scene_detail_review.md": ("status",),
        "cut_blueprint_review.md": ("status",),
        "script_review.md": ("status",),
        "production_readiness_review.md": ("Structure", "Duration", "Quality", "Design Owner Patch Brief"),
    }
    issues: list[str] = []
    for filename, markers in required_reports.items():
        path = run_dir / filename
        if not path.exists():
            issues.append(f"{filename}:missing")
            continue
        text = path.read_text(encoding="utf-8")
        if _review_report_status(text) not in {"passed", "approved"}:
            issues.append(f"{filename}:status")
        for marker in markers:
            if marker not in text:
                issues.append(f"{filename}:missing:{marker}")
    readiness_path = run_dir / "production_readiness_review.md"
    if readiness_path.exists():
        text = readiness_path.read_text(encoding="utf-8").lower()
        forbidden = ("p700", "後続", "defer", "later", "実尺 gate")
        if any(token in text for token in forbidden):
            issues.append("production_readiness_review.md:duration_deferred")
    return issues


def _review_loop_integrity_issues(run_dir: Path, stages: tuple[str, ...] = ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness")) -> list[str]:
    issues: list[str] = []
    source_fingerprint_cache: dict[tuple[object, ...], Any] = {}

    def marker_value_resolved(text: str, marker: str) -> bool:
        if marker.startswith("##"):
            return True
        for line in text.splitlines():
            if marker not in line:
                continue
            if ":" not in line:
                return True
            value = line.split(":", 1)[1].strip().strip("`").lower()
            return value not in UNRESOLVED_GATE_VALUES and "todo" not in value
        return False

    for stage in stages:
        round_dir = run_dir / "logs" / "eval" / stage / "round_01"
        if not round_dir.exists():
            issues.append(f"{stage}:round_01_missing")
            continue
        expected_critic_paths = [
            run_dir / critic_relpath(stage, 1, index)
            for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
        ]
        critic_report_paths = sorted(round_dir.glob("critic_*.md"))
        if {path.resolve() for path in critic_report_paths} != {
            path.resolve() for path in expected_critic_paths
        }:
            issues.append(f"{stage}:critic_inventory_mismatch")
        critic_reports: list[str] = []
        for path in expected_critic_paths:
            if not path.exists():
                issues.append(f"{stage}:{path.name}_missing")
                continue
            critic_reports.append(path.read_text(encoding="utf-8"))
        snapshot_issues = review_input_snapshot_issues(
            run_dir=run_dir,
            stage=stage,
            round_number=1,
            source_fingerprint_cache=source_fingerprint_cache,
        )
        issues.extend(f"{stage}:snapshot:{issue}" for issue in snapshot_issues)
        expected_digest = ""
        if not snapshot_issues:
            try:
                expected_digest = review_input_digest(run_dir=run_dir, stage=stage, round_number=1)
            except ValueError as exc:
                issues.append(f"{stage}:snapshot:{exc}")
        if len(critic_reports) == REVIEW_LOOP_CRITIC_COUNT:
            critic_issues, derived_status, _statuses = review_critic_report_issues(
                critic_reports=critic_reports,
                expected_input_digest=expected_digest or None,
            )
            issues.extend(f"{stage}:critic:{issue}" for issue in critic_issues)
            if derived_status != "passed":
                issues.append(f"{stage}:critics_not_passed")
        stage_focus = REVIEW_LOOP_CRITIC_FOCUS_BY_STAGE.get(stage, {})
        for critic_number, (focus_name, _) in stage_focus.items():
            prompt_path = round_dir / "prompts" / f"critic_{critic_number}.prompt.md"
            if not prompt_path.exists():
                issues.append(f"{stage}:critic_{critic_number}_prompt_missing")
            elif focus_name not in prompt_path.read_text(encoding="utf-8"):
                issues.append(f"{stage}:critic_{critic_number}_prompt_missing_focus:{focus_name}")
            report_path = round_dir / f"critic_{critic_number}.md"
            if report_path.exists() and focus_name not in report_path.read_text(encoding="utf-8"):
                issues.append(f"{stage}:critic_{critic_number}_report_missing_focus:{focus_name}")
        aggregate = run_dir / aggregated_review_relpath(stage, 1)
        if not aggregate.exists():
            issues.append(f"{stage}:aggregated_review_missing")
            continue
        aggregate_text = aggregate.read_text(encoding="utf-8")
        if _review_report_status(aggregate_text) != "passed":
            issues.append(f"{stage}:aggregated_review_status")
        aggregate_digest_match = re.search(
            r"(?m)^-\s*review_input_digest:\s*([0-9a-f]{64})\s*$",
            aggregate_text,
        )
        if not expected_digest or aggregate_digest_match is None or aggregate_digest_match.group(1) != expected_digest:
            issues.append(f"{stage}:aggregated_review_input_digest")
        for index, report in enumerate(critic_reports, start=1):
            expected_hash = hashlib.sha256(report.encode("utf-8")).hexdigest()
            if not re.search(
                rf"(?m)^\s*-\s*critic_{index}:\s*{expected_hash}\s*$",
                aggregate_text,
            ):
                issues.append(f"{stage}:aggregated_review_critic_{index}_sha256")
        required_sections = ("## Blocking Findings", "## Recommended Changes", "## Rejected Suggestions", "## Round Summary")
        for section in required_sections:
            if section not in aggregate_text:
                issues.append(f"{stage}:missing:{section}")
        patch_heading = "## Design Owner Patch Brief" if stage == "production_readiness" else "## Generator Patch Brief"
        if patch_heading not in aggregate_text:
            issues.append(f"{stage}:missing:{patch_heading}")
        if stage_focus:
            if stage == "scene_set":
                markers = SCENE_SET_GATE_MARKERS
            elif stage == "scene_detail":
                markers = SCENE_DETAIL_GATE_MARKERS
            else:
                markers = CUT_BLUEPRINT_GATE_MARKERS
            for marker in markers:
                if marker not in aggregate_text:
                    issues.append(f"{stage}:missing:{marker}")
                elif not marker_value_resolved(aggregate_text, marker):
                    issues.append(f"{stage}:unresolved:{marker}")
    return issues


def _selector_sort_key(selector: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    raw = str(selector or "").strip()
    if not raw.startswith("scene"):
        return ((10**9,), (10**9,))
    body = raw[len("scene") :]
    if "_cut" in body:
        scene_part, cut_part = body.split("_cut", 1)
    else:
        scene_part, cut_part = body, None
    return (
        dotted_id_sort_key(scene_part),
        dotted_id_sort_key(cut_part) if cut_part is not None else (0,),
    )


def _load_script_reveal_constraints(
    run_dir: Path,
    *,
    script_data: dict[str, Any] | None | object = _SCRIPT_DATA_UNSET,
) -> list[dict[str, str]]:
    if script_data is _SCRIPT_DATA_UNSET:
        script_path = run_dir / "script.md"
        if not script_path.exists():
            return []
        _, script_data = load_structured_document(script_path)
    if not isinstance(script_data, dict):
        return []
    data = script_data
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    raw_items = contract.get("reveal_constraints")
    if not isinstance(raw_items, list):
        return []
    constraints: list[dict[str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = {
            "subject_type": str(raw.get("subject_type") or "").strip(),
            "subject_id": str(raw.get("subject_id") or "").strip(),
            "rule": str(raw.get("rule") or "").strip(),
            "selector": str(raw.get("selector") or "").strip(),
        }
        if all(item.values()):
            constraints.append(item)
    return constraints


def _load_script_change_request_contract(
    run_dir: Path,
    *,
    script_data: dict[str, Any] | None | object = _SCRIPT_DATA_UNSET,
) -> dict[str, Any]:
    if script_data is _SCRIPT_DATA_UNSET:
        script_path = run_dir / "script.md"
        if not script_path.exists():
            return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
        _, script_data = load_structured_document(script_path)
    if not isinstance(script_data, dict):
        return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
    data = script_data

    issues: list[str] = []
    expected_request_ids: set[str] = set()
    request_ids_by_selector: dict[str, set[str]] = {}

    for scene in as_list(data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue

        scene_review = scene.get("human_review") if isinstance(scene.get("human_review"), dict) else {}
        scene_status = str(scene_review.get("status") or "").strip().lower() if isinstance(scene_review, dict) else ""
        scene_request_ids = {str(item).strip() for item in as_list(scene_review.get("change_request_ids")) if str(item).strip()}
        if scene_status == "changes_requested":
            selector = make_scene_cut_selector(scene_id)
            if not scene_request_ids:
                issues.append(f"human_change_request_missing_request_id:{selector}")
            expected_request_ids.update(scene_request_ids)
            request_ids_by_selector.setdefault(selector, set()).update(scene_request_ids)

        for cut in as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            cut_id = as_dotted_str(cut.get("cut_id"))
            if cut_id is None:
                continue
            review = cut.get("human_review") if isinstance(cut.get("human_review"), dict) else {}
            status = str(review.get("status") or "").strip().lower() if isinstance(review, dict) else ""
            request_ids = {str(item).strip() for item in as_list(review.get("change_request_ids")) if str(item).strip()}
            if status != "changes_requested":
                continue
            selector = make_scene_cut_selector(scene_id, cut_id)
            if not request_ids:
                issues.append(f"human_change_request_missing_request_id:{selector}")
                continue
            expected_request_ids.update(request_ids)
            request_ids_by_selector.setdefault(selector, set()).update(request_ids)

    request_map = {
        str(item.get("request_id") or "").strip(): item
        for item in as_list(data.get("human_change_requests"))
        if isinstance(item, dict) and str(item.get("request_id") or "").strip()
    }
    for selector, request_ids in request_ids_by_selector.items():
        for request_id in sorted(request_ids):
            if request_id not in request_map:
                issues.append(f"human_change_request_missing_definition:{selector}:{request_id}")

    return {
        "expected_request_ids": expected_request_ids,
        "request_ids_by_selector": request_ids_by_selector,
        "issues": issues,
    }


def _human_change_request_issues(
    manifest: dict[str, Any],
    *,
    run_dir: Path | None = None,
    script_data: dict[str, Any] | None | object = _SCRIPT_DATA_UNSET,
) -> list[str]:
    issues: list[str] = []
    script_contract = (
        _load_script_change_request_contract(run_dir, script_data=script_data)
        if run_dir
        else {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
    )
    issues.extend(list(script_contract.get("issues") or []))
    raw_requests = manifest.get("human_change_requests")
    manifest_request_map: dict[str, dict[str, Any]] = {}
    if isinstance(raw_requests, list):
        for raw in raw_requests:
            if not isinstance(raw, dict):
                continue
            status = str(raw.get("status") or "").strip().lower()
            request_id = str(raw.get("request_id") or "<unknown>").strip()
            manifest_request_map[request_id] = raw
            if status not in {"verified", "waived"}:
                issues.append(f"human_change_request_unresolved:{request_id}")
    for request_id in sorted(script_contract.get("expected_request_ids") or set()):
        if request_id not in manifest_request_map:
            issues.append(f"human_change_request_missing_from_manifest:{request_id}")

    for selector, node in _iter_manifest_nodes_with_selectors(manifest):
        implementation_trace = node.get("implementation_trace") if isinstance(node.get("implementation_trace"), dict) else {}
        source_request_ids = [str(item).strip() for item in as_list(implementation_trace.get("source_request_ids")) if str(item).strip()]
        trace_status = str(implementation_trace.get("status") or "").strip().lower()
        expected_request_ids = set((script_contract.get("request_ids_by_selector") or {}).get(selector, set()))
        combined_request_ids = sorted(set(source_request_ids) | expected_request_ids)
        if expected_request_ids and not source_request_ids:
            issues.append(f"human_change_request_trace_missing:{selector}")
        if source_request_ids and trace_status not in {"implemented", "verified", "waived"}:
            issues.append(f"human_change_request_trace_missing:{selector}")

        for key, path in (
            ("audio", ["narration", "applied_request_ids"]),
            ("image_generation", ["applied_request_ids"]),
            ("video_generation", ["applied_request_ids"]),
        ):
            cur: Any = node.get(key) if isinstance(node.get(key), dict) else {}
            for part in path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(part)
            applied_ids = [str(item).strip() for item in as_list(cur) if str(item).strip()]
            if combined_request_ids and not set(combined_request_ids).issubset(set(applied_ids)):
                issues.append(f"human_change_request_trace_missing:{selector}:{key}")

        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        if image_generation:
            if "location_ids" in image_generation and not isinstance(image_generation.get("location_ids"), list):
                issues.append(f"dotted_selector_invalid:{selector}:location_ids")
            if "location_variant_ids" in image_generation and not isinstance(image_generation.get("location_variant_ids"), list):
                issues.append(f"dotted_selector_invalid:{selector}:location_variant_ids")

        still_assets = node.get("still_assets")
        if still_assets is None:
            continue
        if not isinstance(still_assets, list):
            issues.append(f"still_asset_missing:{selector}")
            continue
        known_asset_ids = {
            str(asset.get("asset_id") or "").strip()
            for asset in still_assets
            if isinstance(asset, dict) and str(asset.get("asset_id") or "").strip()
        }
        for asset in still_assets:
            if not isinstance(asset, dict):
                issues.append(f"still_asset_missing:{selector}")
                continue
            asset_id = str(asset.get("asset_id") or "<unknown>").strip()
            if not isinstance(asset.get("image_generation"), dict):
                issues.append(f"still_asset_missing:{selector}:{asset_id}")
            for dep_key in ("derived_from_asset_ids", "reference_asset_ids"):
                for dep in [str(item).strip() for item in as_list(asset.get(dep_key)) if str(item).strip()]:
                    if dep not in known_asset_ids:
                        issues.append(f"still_asset_dependency_missing:{selector}:{asset_id}:{dep}")
            for usage in as_list(asset.get("reference_usage")):
                if not isinstance(usage, dict):
                    continue
                target_asset_id = str(usage.get("asset_id") or "").strip()
                if target_asset_id and target_asset_id not in known_asset_ids:
                    issues.append(f"reference_usage_target_missing:{selector}:{asset_id}:{target_asset_id}")

        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        referenced_video_asset_ids = [
            str(item).strip()
            for item in as_list(video_generation.get("reference_asset_ids"))
            if str(item).strip()
        ]
        for key in ("input_asset_id", "first_frame_asset_id", "last_frame_asset_id"):
            value = str(video_generation.get(key) or "").strip()
            if value and value not in known_asset_ids:
                issues.append(f"video_asset_reference_missing:{selector}:{key}:{value}")
        for ref_id in referenced_video_asset_ids:
            if ref_id not in known_asset_ids:
                issues.append(f"video_asset_reference_missing:{selector}:reference_asset_ids:{ref_id}")

    return sorted(set(issues))


def _group_issue_messages(issues: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for issue in issues:
        code = str(issue).split(":", 1)[0].strip()
        if not code:
            continue
        grouped.setdefault(code, []).append(issue)
    return grouped


def _append_immersive_manifest_checks(
    checks: list[dict[str, Any]],
    body_text: str,
    data: dict[str, Any],
    scenes: list[Any],
    *,
    profile: str,
    path_label: str,
    is_production: bool,
) -> None:
    experience = nested_get(data, ["video_metadata", "experience"])
    prompt_mentions_text_rule = ("画面内テキスト" in body_text) or ("No on-screen text" in body_text)
    minimum_cut_issues = _minimum_cut_issues(data)
    add_check(checks, f"{path_label}.experience", non_empty(experience), "immersive manifest records video_metadata.experience", kind="rubric")
    add_check(checks, f"{path_label}.no_onscreen_text_rule", prompt_mentions_text_rule, "immersive manifest includes no on-screen text invariant", kind="rubric")
    add_check(
        checks,
        f"{path_label}.minimum_scene_cuts",
        not minimum_cut_issues,
        "immersive manifest covers each authored semantic/event cut obligation without duration-only filler"
        + (f" (issues: {', '.join(minimum_cut_issues[:8])})" if minimum_cut_issues else ""),
        kind="rubric",
    )
    if profile == "standard":
        shot_mix_issues = _scene_shot_mix_plan_v1_issues(scenes)
        add_check(
            checks,
            f"{path_label}.scene_shot_mix_plan",
            not shot_mix_issues,
            "image_api_prompt_v1 scenes declare scene_shot_mix_plan and avoid repetitive adjacent shot role/scale"
            + (f" (issues: {', '.join(shot_mix_issues[:8])})" if shot_mix_issues else ""),
            kind="rubric",
        )
        scene_state_progression_issues = _scene_state_progression_plan_issues(scenes)
        add_check(
            checks,
            f"{path_label}.scene_state_progression_plan",
            not scene_state_progression_issues,
            "image_api_prompt_v1 scenes declare scene_state_progression_plan and keep sequential cuts from reverting to the scene start"
            + (f" (issues: {', '.join(scene_state_progression_issues[:8])})" if scene_state_progression_issues else ""),
            kind="rubric",
        )
        coverage_issues: list[str] = []
        redundancy_issues: list[str] = []
        handoff_issues: list[str] = []
        emotion_film_issues: list[str] = []
        composite_issues: list[str] = []
        triangulation_issues: list[str] = []
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
                continue
            scene_id = as_dotted_str(scene.get("scene_id")) or str(index)
            cuts = [
                cut
                for cut in as_list(scene.get("cuts"))
                if isinstance(cut, dict) and str(cut.get("cut_status") or "").strip().lower() != "deleted"
            ]
            coverage_issues.extend(_scene_cut_coverage_plan_issues(scene, scene_id=scene_id, cuts=cuts))
            redundancy_issues.extend(_scene_cut_redundancy_issues(scene, scene_id=scene_id, cuts=cuts))
            handoff_issues.extend(_scene_cut_handoff_issues(scene, scene_id=scene_id, cuts=cuts))
            if _scene_requires_emotion_film_contract(scene):
                for values in _scene_emotion_film_issue_map(scene).values():
                    emotion_film_issues.extend(values)
            if is_production:
                composite = as_dict(scene.get("scene_composite_review"))
                if not composite or str(composite.get("status") or "").strip().lower() not in {"passed", "approved"}:
                    composite_issues.append(f"scene{scene_id}:scene_composite_review")
                else:
                    for key in (
                        "scene_obligation_covered_by_cut_group",
                        "no_duplicate_story_fact_without_new_evidence",
                        "scene_meaning_visualized_across_cuts",
                    ):
                        if composite.get(key) is not True:
                            composite_issues.append(f"scene{scene_id}:scene_composite_review.{key}")
                for cut in cuts:
                    selector = _scene_cut_selector(scene_id, cut) or str(cut.get("cut_id") or "cut")
                    triangulation_issues.extend(_triangulation_review_issues(cut, selector=selector))
        add_check(
            checks,
            f"{path_label}.scene_cut_coverage_plan",
            not coverage_issues,
            "scene_cut_coverage_plan assigns every scene obligation to real cuts"
            + (f" (issues: {', '.join(coverage_issues[:8])})" if coverage_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            f"{path_label}.scene_cut_redundancy",
            not redundancy_issues,
            "anti_redundancy_key is present and unique, and adjacent movable cuts do not repeat canonical motion plus end state"
            + (f" (issues: {', '.join(redundancy_issues[:8])})" if redundancy_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            f"{path_label}.cut_handoff_chain",
            not handoff_issues,
            "adjacent cuts connect by explicit handoff anchors"
            + (f" (issues: {', '.join(handoff_issues[:8])})" if handoff_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            f"{path_label}.character_emotion_film_grammar",
            not emotion_film_issues,
            "scenes and cuts include character emotion continuity plus film grammar contracts"
            + (f" (issues: {', '.join(emotion_film_issues[:8])})" if emotion_film_issues else ""),
            kind="rubric",
        )
        if is_production:
            add_check(
                checks,
                f"{path_label}.scene_composite_review",
                not composite_issues,
                "production scenes have passed scene_composite_review gates"
                + (f" (issues: {', '.join(composite_issues[:8])})" if composite_issues else ""),
                kind="rubric",
            )
            add_check(
                checks,
                f"{path_label}.triangulation_review",
                not triangulation_issues,
                "production cuts pass image/narration/video triangulation review"
                + (f" (issues: {', '.join(triangulation_issues[:8])})" if triangulation_issues else ""),
                kind="rubric",
            )


def _manifest_checks(checks: list[dict[str, Any]], body_text: str, data: dict[str, Any], *, profile: str, flow: str, path_label: str) -> None:
    add_check(checks, f"{path_label}.structured", bool(data), f"{path_label} contains structured YAML output")
    if not data:
        return

    scenes = as_list(data.get("scenes"))
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    video_metadata = data.get("video_metadata") if isinstance(data.get("video_metadata"), dict) else {}
    expected_story_time = str(video_metadata.get("time") or "").strip()
    prompt_context_by_node_id: dict[int, tuple[str | None, str | None]] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        expected_time_of_day = str(scene.get("time_of_day") or "").strip()
        scene_nodes = [
            cut
            for cut in as_list(scene.get("cuts"))
            if isinstance(cut, dict)
            and str(cut.get("cut_status") or "").strip().lower() != "deleted"
        ]
        if not scene_nodes:
            scene_nodes = [scene]
        for scene_node in scene_nodes:
            prompt_context_by_node_id[id(scene_node)] = (
                expected_story_time,
                expected_time_of_day,
            )
    manifest_phase = str(data.get("manifest_phase") or "production").strip().lower()
    is_production = manifest_phase == "production"
    experience_value = str(nested_get(data, ["video_metadata", "experience"]) or "").strip().lower()
    strict_cut_contract = profile == "standard" and (flow == "immersive" or experience_value == "cinematic_story")
    add_check(checks, f"{path_label}.scenes", len(scenes) >= 1, f"{path_label} contains scenes", kind="rubric")
    add_check(checks, f"{path_label}.nodes", len(nodes) >= 1, f"{path_label} exposes renderable nodes", kind="rubric")
    time_contract_declared, time_contract_valid = scene_time_of_day_contract_marker(
        data, artifact="manifest"
    )
    if time_contract_declared:
        add_check(
            checks,
            f"{path_label}.scene_time_of_day_contract",
            time_contract_valid,
            "video_metadata.scene_time_of_day_contract is required_v1",
            kind="rubric",
        )
    missing_time_of_day = scene_time_of_day_contract_missing(data, artifact="manifest")
    if missing_time_of_day is not None:
        add_check(
            checks,
            f"{path_label}.scene_time_of_day",
            not missing_time_of_day,
            "all newly authored manifest scenes include non-empty time_of_day"
            + (f" (missing: {', '.join(missing_time_of_day[:8])})" if missing_time_of_day else ""),
            kind="rubric",
        )
    basis_contract_declared, basis_contract_valid = (
        scene_time_of_day_visual_basis_contract_marker(data, artifact="manifest")
    )
    if basis_contract_declared:
        add_check(
            checks,
            f"{path_label}.scene_time_of_day_visual_basis_contract",
            basis_contract_valid,
            "video_metadata.scene_time_of_day_visual_basis_contract is required_v1",
            kind="rubric",
        )
    basis_issues = scene_time_of_day_visual_basis_issues(data, artifact="manifest")
    if basis_issues is not None:
        add_check(
            checks,
            f"{path_label}.scene_time_of_day_visual_basis",
            not basis_issues,
            "all newly authored manifest scenes define lighting evidence for 光源, 明るさ, 影, 色温度"
            + (f" (issues: {', '.join(basis_issues[:8])})" if basis_issues else ""),
            kind="rubric",
        )

    if profile == "standard":
        add_check(checks, f"{path_label}.no_todo", not has_todo(body_text), f"{path_label} does not contain TODO/TBD markers", kind="rubric")

    duration_ok = True
    narration_field_ok = True
    narration_text_ok = True
    ids_ok = True
    prompt_motion_leak_issues: list[str] = []
    api_prompt_v1_issues: list[str] = []
    for node in nodes:
        video_generation = node.get("video_generation") if isinstance(node, dict) else None
        image_generation = node.get("image_generation") if isinstance(node, dict) else None
        audio = node.get("audio") if isinstance(node, dict) else None

        if isinstance(video_generation, dict):
            duration = video_generation.get("duration_seconds")
            if isinstance(duration, int) and duration > 15:
                duration_ok = False

        if isinstance(image_generation, dict):
            if "character_ids" not in image_generation or "object_ids" not in image_generation:
                ids_ok = False
            selector = str(node.get("selector") or node.get("cut_id") or node.get("scene_id") or "node")
            prompt = _image_api_prompt_text(image_generation)
            api_prompt_v1_issues.extend(_image_api_prompt_v1_issues(selector, image_generation))
            node_story_time, node_time_of_day = prompt_context_by_node_id.get(
                id(node), (expected_story_time, None)
            )
            api_prompt_v1_issues.extend(
                _image_api_prompt_v2_issues(
                    selector,
                    image_generation,
                    expected_story_time=node_story_time,
                    expected_time_of_day=node_time_of_day,
                )
            )
            if any(token in prompt for token in MOTION_LEAK_TOKENS):
                prompt_motion_leak_issues.append(selector)

        narration = (audio or {}).get("narration") if isinstance(audio, dict) else None
        if not isinstance(narration, dict):
            narration_field_ok = False
            narration_text_ok = False
            continue
        if "text" not in narration:
            narration_field_ok = False
            narration_text_ok = False
            continue
        narration_tool = str(narration.get("tool") or "").strip().lower()
        silence_contract = narration.get("silence_contract") if isinstance(narration, dict) else None
        if narration_tool == "silent":
            if not (
                isinstance(silence_contract, dict)
                and bool(silence_contract.get("intentional"))
                and bool(silence_contract.get("confirmed_by_human"))
                and non_empty(silence_contract.get("kind"))
                and non_empty(silence_contract.get("reason"))
            ):
                narration_text_ok = False
        elif profile == "standard" and not non_empty(narration.get("text")):
            narration_text_ok = False

    add_check(checks, f"{path_label}.cut_duration", duration_ok, "cut duration is <= 15 seconds", kind="rubric")
    add_check(checks, f"{path_label}.narration_field", narration_field_ok, "each renderable node has audio.narration.text", kind="rubric")
    if profile == "standard":
        add_check(checks, f"{path_label}.narration_text", narration_text_ok, "spoken cuts have non-empty narration text and silent cuts declare silence_contract", kind="rubric")
    add_check(checks, f"{path_label}.asset_ids", ids_ok, "image_generation includes explicit character_ids/object_ids", kind="rubric")
    if profile == "standard":
        add_check(
            checks,
            f"{path_label}.prompt_leaks_motion_brief",
            not prompt_motion_leak_issues,
            "p600 image prompts do not leak p800 motion-only context"
            + (f" (issues: {', '.join(prompt_motion_leak_issues[:8])})" if prompt_motion_leak_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            f"{path_label}.api_prompt_v1_contract",
            not api_prompt_v1_issues,
            "image API prompt entries keep API prompts separate from debug/internal fields and satisfy their versioned drawable contracts"
            + (f" (issues: {', '.join(api_prompt_v1_issues[:8])})" if api_prompt_v1_issues else ""),
            kind="rubric",
        )

    if flow == "immersive":
        _append_immersive_manifest_checks(
            checks,
            body_text,
            data,
            scenes,
            profile=profile,
            path_label=path_label,
            is_production=is_production,
        )


def _append_manifest_contract_checks(
    checks: list[dict[str, Any]],
    *,
    nodes_with_selectors: list[tuple[str, dict[str, Any]]],
    strict_cut_contract: bool,
    reveal_constraints: list[dict[str, str]],
    human_change_issues: list[str],
) -> None:
    contract_missing = False
    contract_structure_issues: list[str] = []
    must_show_failed = False
    must_avoid_failed = False
    reveal_failed = False
    for selector, node in nodes_with_selectors:
        image_generation_for_prompt = (node.get("image_generation") or {}) if isinstance(node.get("image_generation"), dict) else {}
        combined = "\n".join(
            [
                _image_api_prompt_text(image_generation_for_prompt),
                str(((node.get("video_generation") or {}) if isinstance(node.get("video_generation"), dict) else {}).get("motion_prompt") or ""),
                str(((((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration") or {}) if isinstance(((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration"), dict) else {}).get("text") or ""),
            ]
        )
        contract = _node_cut_contract(node, allow_legacy=not strict_cut_contract)
        if not contract:
            contract_missing = True
            continue
        if isinstance(node.get("cut_contract"), dict):
            for issue in _cut_contract_structure_issues(contract):
                contract_structure_issues.append(f"{selector}:{issue}")
        elif strict_cut_contract:
            contract_missing = True
        must_show = _contract_list_paths(contract, "must_show", "viewer_contract.must_show")
        if _image_api_prompt_policy(image_generation_for_prompt) in {
            IMAGE_API_PROMPT_POLICY_VERSION,
            IMAGE_API_PROMPT_POLICY_VERSION_V2,
        }:
            must_show = [term for term in must_show if not IMAGE_API_PROMPT_ABSTRACT_TERM_RE.search(str(term))]
        must_avoid = _contract_list_paths(contract, "must_avoid", "viewer_contract.must_avoid", "motion_contract.must_not_add")
        if must_show and not all(term in combined for term in must_show):
            must_show_failed = True
        if must_avoid and any(term in combined for term in must_avoid):
            must_avoid_failed = True
        if reveal_constraints:
            image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
            declared_character_ids = set(as_list(image_generation.get("character_ids"))) if isinstance(image_generation, dict) else set()
            prompt = _image_api_prompt_text(image_generation) if isinstance(image_generation, dict) else ""
            for constraint in reveal_constraints:
                if constraint["rule"] != "must_not_appear_before":
                    continue
                if _selector_sort_key(selector) >= _selector_sort_key(constraint["selector"]):
                    continue
                if constraint["subject_type"] == "character":
                    subject_id = constraint["subject_id"]
                    if subject_id in declared_character_ids or subject_id in prompt:
                        reveal_failed = True
    if contract_missing:
        add_check(checks, "manifest.contract_missing", False, "one or more scene/cut nodes are missing cut_contract or legacy scene_contract.", kind="rubric")
    if contract_structure_issues:
        add_check(
            checks,
            "manifest.cut_contract_structure",
            False,
            "one or more cut_contract nodes are missing required viewer/first-frame/motion/narration fields"
            + (f" (issues: {', '.join(contract_structure_issues[:8])})" if contract_structure_issues else ""),
            kind="rubric",
        )
    if must_show_failed:
        add_check(checks, "manifest.contract_must_show_unmet", False, "scene/cut contract must_show items are not fully represented.", kind="rubric")
    if must_avoid_failed:
        add_check(checks, "manifest.contract_must_avoid_violated", False, "scene/cut contract must_avoid items are still present.", kind="rubric")
    if reveal_failed:
        add_check(checks, "manifest.reveal_constraints_violated", False, "one or more scene/cut nodes violate script reveal_constraints.", kind="rubric")
    if human_change_issues:
        for reason_key, grouped_issues in sorted(_group_issue_messages(human_change_issues).items()):
            add_check(
                checks,
                f"manifest.{reason_key}",
                False,
                f"{reason_key} remains unresolved: " + ", ".join(sorted(grouped_issues)[:8]),
                kind="rubric",
            )


def check_manifest_single(
    run_dir: Path,
    profile: str,
    flow: str,
    *,
    require_review_artifacts: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "video_manifest.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    add_check(checks, "manifest.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("manifest", path.name, checks), updates

    text, data = load_structured_document(path)
    script_path = run_dir / "script.md"
    script_data: dict[str, Any] | None = None
    if script_path.exists():
        _script_text, loaded_script_data = load_structured_document(script_path)
        if isinstance(loaded_script_data, dict):
            script_data = loaded_script_data
    body_text = flatten_without_keys(data, excluded={"cut_contract", "scene_contract", "review_contract", "evaluation_contract"}) or text
    _append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    raw_manifest_phase = data.get("manifest_phase")
    manifest_phase = str(raw_manifest_phase or "production").strip().lower()
    add_check(checks, "manifest.phase", manifest_phase == "production", f"video_manifest.md is production phase (got {manifest_phase or '(unset)'})", kind="rubric")
    _manifest_checks(checks, body_text, data, profile=profile, flow=flow, path_label="manifest")
    if flow == "immersive":
        add_check(
            checks,
            "p400.skeleton_manifest_phase",
            non_empty(raw_manifest_phase) and manifest_phase in {"skeleton", "production"},
            f"p400 manifest explicitly declares skeleton or promoted production phase (got {str(raw_manifest_phase or '').strip() or '(unset)'})",
            kind="rubric",
        )
        target_seconds, actual_seconds, cut_count = _manifest_duration_summary(data)
        raw_target_seconds = nested_get(data, ["video_metadata", "target_duration_seconds"])
        try:
            normalized_target_seconds = (
                normalize_target_duration(raw_target_seconds)
                if raw_target_seconds is not None
                else None
            )
        except ValueError:
            normalized_target_seconds = None
        duration_audit = (
            audit_duration(
                target_seconds=normalized_target_seconds,
                actual_seconds=actual_seconds,
                measurement_layer="planned_manifest",
            )
            if normalized_target_seconds is not None
            else None
        )
        add_check(
            checks,
            "p400.target_duration_range",
            normalized_target_seconds is not None,
            f"p400 target duration is {MIN_TARGET_DURATION_SECONDS // 60}-{MAX_TARGET_DURATION_SECONDS // 60} minutes "
            f"(got {target_seconds:.0f}s)",
            kind="rubric",
        )
        add_check(
            checks,
            "p400.duration_coverage",
            duration_audit is not None and duration_audit.passed,
            f"p400 cut durations cover at least {MINIMUM_EFFECTIVE_RATIO:.0%} of target "
            f"({actual_seconds:g}/{target_seconds:g}s across {cut_count} cuts)",
            kind="rubric",
        )
        script_selectors = _script_selectors_from_run(
            run_dir,
            script_data=script_data,
        )
        manifest_selectors = _manifest_selectors(data)
        selector_mismatch = sorted((script_selectors - manifest_selectors) | (manifest_selectors - script_selectors))
        script_readiness_issues = _script_readiness_issues_from_run(
            run_dir,
            script_data=script_data,
        )
        manifest_scene_event_issues = _scene_event_readiness_issues(as_list(data.get("scenes")), prefix="manifest")
        script_readiness_issues.extend(manifest_scene_event_issues)
        add_check(
            checks,
            "p400.script_readiness_contract",
            not script_readiness_issues,
            "p400 script scene readiness contract is satisfied before downstream stages"
            + (f" (issues: {', '.join(script_readiness_issues[:8])})" if script_readiness_issues else ""),
            kind="rubric",
        )
        add_check(
            checks,
            "p400.script_manifest_selector_match",
            bool(script_selectors) and not selector_mismatch,
            "p450 manifest selectors correspond exactly to script.md scene/cut selectors"
            + (f" (mismatch: {', '.join(selector_mismatch[:8])})" if selector_mismatch else ""),
            kind="rubric",
        )
        if require_review_artifacts:
            review_issues = _review_report_issues(run_dir)
            add_check(
                checks,
                "p400.review_report_integrity",
                not review_issues,
                "p400 review reports have required passed status, p435 council sections, and no duration deferral"
                + (f" (issues: {', '.join(review_issues[:8])})" if review_issues else ""),
                kind="rubric",
            )
            loop_issues = _review_loop_integrity_issues(run_dir)
            add_check(
                checks,
                "p400.review_loop_integrity",
                not loop_issues,
                "p400 review loops include five critic reports, aggregate report, and required patch brief sections"
                + (f" (issues: {', '.join(loop_issues[:8])})" if loop_issues else ""),
                kind="rubric",
            )
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    experience_value = str(nested_get(data, ["video_metadata", "experience"]) or "").strip().lower()
    strict_cut_contract = profile == "standard" and (flow == "immersive" or experience_value == "cinematic_story")
    reveal_constraints = _load_script_reveal_constraints(
        run_dir,
        script_data=script_data,
    )
    human_change_issues = _human_change_request_issues(
        data,
        run_dir=run_dir,
        script_data=script_data,
    )
    _append_manifest_contract_checks(
        checks,
        nodes_with_selectors=nodes_with_selectors,
        strict_cut_contract=strict_cut_contract,
        reveal_constraints=reveal_constraints,
        human_change_issues=human_change_issues,
    )
    rubric_scores = _manifest_rubric(nodes, body_text)
    _append_rubric_findings(checks=checks, stage="manifest", rubric_scores=rubric_scores)
    updates["eval.manifest.score"] = f"{score_from_checks(checks):.4f}"
    if flow == "immersive":
        p400_gate_checks = [check for check in checks if check["id"] in P400_READINESS_CHECK_IDS or check["id"].startswith("p400.")]
        p400_ready = bool(p400_gate_checks) and all(check["passed"] for check in p400_gate_checks)
        updates["eval.p400_readiness.status"] = "approved" if p400_ready else "changes_requested"
        updates["eval.p400_readiness.reason_keys"] = ",".join(check["id"] for check in p400_gate_checks if not check["passed"])
    return make_stage("manifest", path.name, checks, rubric_scores=rubric_scores), updates


def check_manifest_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    manifest_paths = [scene_dir / "video_manifest.md" for scene_dir in scene_dirs]

    add_check(checks, "manifest.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "manifest.scene_files", all(path.exists() for path in manifest_paths), "each scene has video_manifest.md")
    _append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    if not scene_dirs or not all(path.exists() for path in manifest_paths):
        return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}), {
            "eval.manifest.score": f"{score_from_checks(checks):.4f}"
        }

    nested_ok = True
    phase_ok = True
    for path in manifest_paths:
        text, data = load_structured_document(path)
        local_checks: list[dict[str, Any]] = []
        body_text = flatten_without_keys(data, excluded={"cut_contract", "scene_contract", "review_contract", "evaluation_contract"}) or text
        if str(data.get("manifest_phase") or "production").strip().lower() != "production":
            phase_ok = False
        _manifest_checks(local_checks, body_text, data, profile=profile, flow="scene-series", path_label=path.name)
        if not all(check["passed"] for check in local_checks):
            nested_ok = False
    add_check(checks, "manifest.scene_phase", phase_ok, "scene manifests are in production phase", kind="rubric")
    add_check(checks, "manifest.scene_contracts", nested_ok, "scene manifests satisfy render contract checks", kind="rubric")
    rubric_scores = {
        "beat_clarity": 1.0 if nested_ok else 0.4,
        "visual_specificity": 1.0 if nested_ok else 0.4,
        "continuity_readiness": 1.0 if nested_ok else 0.4,
        "narration_alignment": 1.0 if nested_ok else 0.4,
        "production_readiness": 1.0 if nested_ok else 0.4,
    }
    _append_rubric_findings(checks=checks, stage="manifest", rubric_scores=rubric_scores)
    updates = {"eval.manifest.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}, rubric_scores=rubric_scores), updates
