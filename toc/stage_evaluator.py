"""Reusable stage evaluator helpers for research/script/manifest/video reviews."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from toc.grounding import grounding_validation
from toc.harness import append_state_snapshot, load_structured_document, parse_state_file
from toc.immersive_manifest import dotted_id_sort_key, make_scene_cut_selector, normalize_dotted_id


STAGE_RUBRIC_WEIGHTS = {
    "research": {
        "source_grounding": 0.25,
        "coverage": 0.20,
        "conflict_readiness": 0.20,
        "structure_readiness": 0.15,
        "scene_mapping": 0.20,
    },
    "script": {
        "arc_coverage": 0.25,
        "scene_specificity": 0.20,
        "reference_grounding": 0.20,
        "anti_todo": 0.15,
        "production_readiness": 0.20,
    },
    "manifest": {
        "beat_clarity": 0.25,
        "visual_specificity": 0.20,
        "continuity_readiness": 0.20,
        "narration_alignment": 0.15,
        "production_readiness": 0.20,
    },
    "video": {
        "render_integrity": 0.25,
        "asset_completeness": 0.20,
        "review_readiness": 0.15,
        "audio_packaging": 0.20,
        "publish_readiness": 0.20,
    },
}

STAGE_RUBRIC_THRESHOLDS = {
    "research": {
        "source_grounding": 0.60,
        "coverage": 0.60,
        "conflict_readiness": 0.55,
        "structure_readiness": 0.60,
        "scene_mapping": 0.70,
    },
    "script": {
        "arc_coverage": 0.60,
        "scene_specificity": 0.60,
        "reference_grounding": 0.55,
        "anti_todo": 0.70,
        "production_readiness": 0.60,
    },
    "manifest": {
        "beat_clarity": 0.60,
        "visual_specificity": 0.60,
        "continuity_readiness": 0.60,
        "narration_alignment": 0.55,
        "production_readiness": 0.60,
    },
    "video": {
        "render_integrity": 0.70,
        "asset_completeness": 0.60,
        "review_readiness": 0.60,
        "audio_packaging": 0.55,
        "publish_readiness": 0.60,
    },
}


def has_todo(text: str) -> bool:
    upper = text.upper()
    return "TODO" in upper or "TBD" in upper


def non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return value is not None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def as_dotted_str(value: Any) -> str | None:
    return normalize_dotted_id(value)


def nested_get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(flatten_text(v) for v in value)
    return ""


def flatten_without_keys(value: Any, *, excluded: set[str]) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten_without_keys(v, excluded=excluded) for k, v in value.items() if str(k) not in excluded)
    if isinstance(value, list):
        return "\n".join(flatten_without_keys(v, excluded=excluded) for v in value)
    return ""


def contract_list(contract: dict[str, Any], key: str) -> list[str]:
    value = contract.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def score_from_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 1.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, message: str, *, kind: str = "deterministic") -> None:
    checks.append({"id": check_id, "passed": passed, "kind": kind, "message": message})


def score_from_checks(checks: list[dict[str, Any]]) -> float:
    if not checks:
        return 0.0
    passed = sum(1 for check in checks if check["passed"])
    return round(passed / len(checks), 4)


def make_stage(
    stage: str,
    artifact: str,
    checks: list[dict[str, Any]],
    *,
    details: dict[str, Any] | None = None,
    rubric_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    score = score_from_checks(checks)
    rubric_scores = rubric_scores or {}
    overall_rubric = round(
        sum(rubric_scores.get(key, 0.0) * STAGE_RUBRIC_WEIGHTS[stage][key] for key in STAGE_RUBRIC_WEIGHTS.get(stage, {})),
        4,
    ) if rubric_scores else score
    return {
        "stage": stage,
        "artifact": artifact,
        "passed": all(check["passed"] for check in checks),
        "score": score,
        "overall_rubric": overall_rubric,
        "rubric_scores": rubric_scores,
        "reason_keys": [check["id"] for check in checks if not check["passed"]],
        "checks": checks,
        "details": details or {},
    }


def _append_grounding_checks(checks: list[dict[str, Any]], *, run_dir: Path, stage: str) -> None:
    validation = grounding_validation(run_dir, stage)
    report = validation.get("report") or {}
    report_path = validation.get("report_path")
    readset_path = validation.get("readset_path")
    audit_path = validation.get("audit_path")
    add_check(
        checks,
        f"{stage}.grounding_report",
        bool(validation.get("report_exists")),
        f"grounding report exists for {stage} (got {report_path or '(missing)'})",
        kind="rubric",
    )
    if validation.get("report_exists"):
        add_check(
            checks,
            f"{stage}.grounding_ready",
            bool(validation.get("report_ready")),
            f"grounding report status is ready (got {report.get('status', '(unset)')})",
            kind="rubric",
        )
    add_check(
        checks,
        f"{stage}.grounding_state",
        validation.get("state_status") == "ready",
        f"state records stage grounding as ready (got {validation.get('state_status') or '(unset)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.readset_report",
        bool(validation.get("readset_exists")),
        f"readset report exists for {stage} (got {readset_path or '(missing)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.audit_report",
        bool(validation.get("audit_exists")),
        f"audit report exists for {stage} (got {audit_path or '(missing)'})",
        kind="rubric",
    )
    add_check(
        checks,
        f"{stage}.readset_state",
        bool(validation.get("state_readset")),
        f"state records readset report for {stage} (got {validation.get('state_readset') or '(unset)'})",
        kind="rubric",
    )
    if validation.get("audit_exists"):
        add_check(
            checks,
            f"{stage}.audit_passed",
            bool(validation.get("audit_passed")),
            f"audit report status is passed (got {(validation.get('audit') or {}).get('status', '(unset)')})",
            kind="rubric",
        )
    add_check(
        checks,
        f"{stage}.audit_state",
        validation.get("state_audit_status") == "passed",
        f"state records stage audit as passed (got {validation.get('state_audit_status') or '(unset)'})",
        kind="rubric",
    )


def detect_flow(run_dir: Path) -> str:
    if (run_dir / "scenes").exists():
        return "scene-series"
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _, data = load_structured_document(manifest_path)
        if nested_get(data, ["video_metadata", "experience"]):
            return "immersive"
    return "toc-run"


def _append_rubric_findings(*, checks: list[dict[str, Any]], stage: str, rubric_scores: dict[str, float]) -> None:
    for key, threshold in STAGE_RUBRIC_THRESHOLDS.get(stage, {}).items():
        passed = rubric_scores.get(key, 0.0) >= threshold
        add_check(checks, f"{stage}.rubric.{key}", passed, f"{key} rubric is >= {threshold:.2f} (got {rubric_scores.get(key, 0.0):.2f})", kind="rubric")


def _research_rubric(data: dict[str, Any], *, sources: list[Any], scene_plan: list[Any], beat_sheet: list[Any], conflict_topics: list[str]) -> dict[str, float]:
    confidence = nested_get(data, ["metadata", "confidence_score"])
    confidence_score = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    return {
        "source_grounding": score_from_ratio(len(sources), 12),
        "coverage": round((score_from_ratio(len(scene_plan), 20) + score_from_ratio(len(beat_sheet), 20)) / 2, 4),
        "conflict_readiness": round((1.0 if conflict_topics else 0.9), 4),
        "structure_readiness": round((1.0 if nested_get(data, ["story_baseline", "canonical_synopsis", "short_summary"]) else 0.5) * max(confidence_score, 0.5), 4),
        "scene_mapping": 1.0,
    }


def _script_rubric(text: str, data: dict[str, Any], *, scenes: list[Any]) -> dict[str, float]:
    phases = {str(scene.get("phase") or "").strip() for scene in scenes if isinstance(scene, dict) and str(scene.get("phase") or "").strip()}
    reference_grounding = 1.0
    if scenes:
        reference_grounding = score_from_ratio(
            sum(1 for scene in scenes if isinstance(scene, dict) and as_list(scene.get("research_refs"))),
            len(scenes),
        )
    meaningful_len = len("".join(text.split()))
    return {
        "arc_coverage": score_from_ratio(len(phases), 3),
        "scene_specificity": score_from_ratio(meaningful_len, 160),
        "reference_grounding": reference_grounding,
        "anti_todo": 0.0 if has_todo(text) else 1.0,
        "production_readiness": 1.0 if meaningful_len >= 80 else 0.4,
    }


def _manifest_rubric(nodes: list[dict[str, Any]], body_text: str) -> dict[str, float]:
    if not nodes:
        return {key: 0.0 for key in STAGE_RUBRIC_WEIGHTS["manifest"]}
    prompt_lengths = []
    ids_with_values = 0
    narration_count = 0
    contract_count = 0
    for node in nodes:
        image_generation = node.get("image_generation") if isinstance(node, dict) and isinstance(node.get("image_generation"), dict) else {}
        audio = node.get("audio") if isinstance(node, dict) and isinstance(node.get("audio"), dict) else {}
        video_generation = node.get("video_generation") if isinstance(node, dict) and isinstance(node.get("video_generation"), dict) else {}
        combined_node_text = "\n".join(
            [
                str(image_generation.get("prompt") or "").strip(),
                str(video_generation.get("motion_prompt") or "").strip(),
                str((((audio or {}).get("narration") or {}) if isinstance((audio or {}).get("narration"), dict) else {}).get("text") or "").strip(),
            ]
        )
        prompt_lengths.append(len(combined_node_text))
        if image_generation.get("character_ids") is not None and image_generation.get("object_ids") is not None:
            ids_with_values += 1
        narration = (audio or {}).get("narration") if isinstance(audio, dict) else {}
        if isinstance(narration, dict):
            narration_text = str(narration.get("text") or "").strip()
            silence_contract = narration.get("silence_contract") if isinstance(narration.get("silence_contract"), dict) else {}
            is_intentional_silence = (
                str(narration.get("tool") or "").strip().lower() == "silent"
                and bool(silence_contract.get("intentional"))
                and bool(silence_contract.get("confirmed_by_human"))
                and non_empty(silence_contract.get("kind"))
                and non_empty(silence_contract.get("reason"))
            )
            if narration_text or is_intentional_silence:
                narration_count += 1
        if isinstance(node.get("scene_contract"), dict):
            contract_count += 1
        if isinstance(video_generation, dict) and video_generation.get("duration_seconds"):
            pass
    avg_prompt_length = sum(prompt_lengths) / len(prompt_lengths)
    return {
        "beat_clarity": score_from_ratio(contract_count, len(nodes)),
        "visual_specificity": score_from_ratio(avg_prompt_length, 150),
        "continuity_readiness": score_from_ratio(ids_with_values, len(nodes)),
        "narration_alignment": score_from_ratio(narration_count, len(nodes)),
        "production_readiness": 0.0 if has_todo(body_text) else 1.0,
    }


def _video_rubric(run_dir: Path, state: dict[str, str], checks: list[dict[str, Any]]) -> dict[str, float]:
    passed_map = {check["id"]: bool(check["passed"]) for check in checks}
    narration_list = run_dir / "video_narration_list.txt"
    return {
        "render_integrity": 1.0 if passed_map.get("video.file_exists") and passed_map.get("video.render_status") else 0.3,
        "asset_completeness": 1.0 if (run_dir / "video.mp4").exists() else 0.3,
        "review_readiness": 1.0 if state.get("review.video.status", "").strip().lower() in {"pending", "approved", "changes_requested"} else 0.3,
        "audio_packaging": 1.0 if (not narration_list.exists() or passed_map.get("video.narration_list", False)) else 0.4,
        "publish_readiness": score_from_ratio(sum(1 for check in checks if check["passed"]), len(checks)),
    }


def check_research(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "research.md"
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}

    add_check(checks, "research.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("research", path.name, checks), updates

    text, data = load_structured_document(path)
    if profile == "standard":
        add_check(checks, "research.no_todo", not has_todo(text), "research.md does not contain TODO/TBD markers", kind="rubric")
    _append_grounding_checks(checks, run_dir=run_dir, stage="research")

    sources = as_list(data.get("sources"))
    scene_plan = nested_get(data, ["scene_plan", "scenes"], [])
    beat_sheet = nested_get(data, ["story_baseline", "canonical_synopsis", "beat_sheet"], [])
    conflicts = data.get("conflicts")
    conflict_topics = [str(item.get("topic") or "").strip() for item in as_list(conflicts) if isinstance(item, dict) and str(item.get("topic") or "").strip()]
    confidence = nested_get(data, ["metadata", "confidence_score"])
    synopsis = nested_get(data, ["story_baseline", "canonical_synopsis", "short_summary"]) or nested_get(
        data, ["story_baseline", "canonical_synopsis", "one_liner"]
    )
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    flattened = flatten_without_keys(data, excluded={"evaluation_contract"})

    details["sources"] = len(sources)
    details["scene_count"] = len(as_list(scene_plan))
    details["beat_count"] = len(as_list(beat_sheet))

    add_check(checks, "research.structured", bool(data), "research.md contains structured YAML output")
    if not contract:
        add_check(checks, "research.contract_missing", False, "evaluation_contract is missing for research stage.", kind="rubric")
    else:
        target_questions = contract_list(contract, "target_questions")
        must_cover = contract_list(contract, "must_cover")
        must_resolve = contract_list(contract, "must_resolve_conflicts")
        if target_questions and not all(question in flattened for question in target_questions):
            add_check(checks, "research.contract_target_questions_unmet", False, "research does not yet address all target_questions.", kind="rubric")
        if must_cover and not all(term in flattened for term in must_cover):
            add_check(checks, "research.contract_must_cover_unmet", False, "research does not yet cover all required anchors.", kind="rubric")
        if must_resolve and not all(term in "\n".join(conflict_topics) for term in must_resolve):
            add_check(checks, "research.contract_conflict_unmet", False, "research conflicts do not yet cover all required conflict topics.", kind="rubric")
    add_check(checks, "research.sources", len(sources) >= 12, f"sources >= 12 (got {len(sources)})", kind="rubric")
    add_check(checks, "research.scene_plan", len(as_list(scene_plan)) >= 20, f"scene plan covers >= 20 scenes (got {len(as_list(scene_plan))})", kind="rubric")
    add_check(checks, "research.synopsis", non_empty(synopsis), "canonical synopsis is present", kind="rubric")
    add_check(checks, "research.beat_sheet", len(as_list(beat_sheet)) >= 20, f"beat sheet has >= 20 beats (got {len(as_list(beat_sheet))})", kind="rubric")
    add_check(checks, "research.conflicts_field", conflicts is not None, "conflicts field is present", kind="rubric")

    scene_mapping_ok = True
    for beat in as_list(beat_sheet):
        if isinstance(beat, dict) and not as_list(beat.get("scene_ids")):
            scene_mapping_ok = False
            break
    add_check(checks, "research.scene_mapping", scene_mapping_ok, "beat sheet entries are mapped to scene_ids", kind="rubric")

    confidence_ok = isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
    add_check(checks, "research.confidence", confidence_ok, "metadata.confidence_score is between 0.0 and 1.0", kind="rubric")
    rubric_scores = _research_rubric(data, sources=sources, scene_plan=as_list(scene_plan), beat_sheet=as_list(beat_sheet), conflict_topics=conflict_topics)
    if not scene_mapping_ok:
        rubric_scores["scene_mapping"] = 0.0
    _append_rubric_findings(checks=checks, stage="research", rubric_scores=rubric_scores)
    updates["eval.research.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("research", path.name, checks, details=details, rubric_scores=rubric_scores), updates


def _script_text_quality_checks(checks: list[dict[str, Any]], text: str, data: dict[str, Any], profile: str) -> None:
    meaningful_len = len("".join(text.split()))
    add_check(checks, "script.content_length", meaningful_len >= 80, f"script content length is meaningful (got {meaningful_len} chars)", kind="rubric")
    if profile == "standard":
        add_check(checks, "script.no_todo", not has_todo(text), "script does not contain TODO/TBD markers", kind="rubric")

    scenes = []
    if isinstance(data.get("scenes"), list):
        scenes = as_list(data.get("scenes"))
    elif isinstance(nested_get(data, ["script", "scenes"], []), list):
        scenes = as_list(nested_get(data, ["script", "scenes"], []))
    if scenes:
        add_check(checks, "script.structured_scenes", len(scenes) >= 1, "structured script includes scene list", kind="rubric")


def check_script_single(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "script.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}

    add_check(checks, "script.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("script", path.name, checks), updates

    text, data = load_structured_document(path)
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")
    contract = data.get("evaluation_contract") if isinstance(data.get("evaluation_contract"), dict) else {}
    body_text = flatten_without_keys(data, excluded={"evaluation_contract"}) or text
    _script_text_quality_checks(checks, body_text, data, profile)
    scenes = as_list(data.get("scenes")) or as_list(nested_get(data, ["script", "scenes"], []))
    flattened = body_text
    if not contract:
        add_check(checks, "script.contract_missing", False, "evaluation_contract is missing for script stage.", kind="rubric")
    else:
        must_cover = contract_list(contract, "must_cover")
        must_avoid = contract_list(contract, "must_avoid")
        target_arc = [part.strip() for part in str(contract.get("target_arc") or "").split(",") if part.strip()]
        phases = {str(scene.get("phase") or "").strip() for scene in scenes if isinstance(scene, dict)}
        if must_cover and not all(term in flattened for term in must_cover):
            add_check(checks, "script.contract_must_cover_unmet", False, "script does not yet cover all required beats or anchors.", kind="rubric")
        if must_avoid and any(term in flattened for term in must_avoid):
            add_check(checks, "script.contract_must_avoid_violated", False, "script still includes a forbidden beat or phrase from the contract.", kind="rubric")
        if target_arc and not all(phase in phases for phase in target_arc):
            add_check(checks, "script.contract_target_arc_unmet", False, "script phases do not yet satisfy target_arc.", kind="rubric")
    rubric_scores = _script_rubric(body_text, data, scenes=scenes)
    _append_rubric_findings(checks=checks, stage="script", rubric_scores=rubric_scores)
    updates["eval.script.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("script", path.name, checks, rubric_scores=rubric_scores), updates


def check_script_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    script_paths = [scene_dir / "script.md" for scene_dir in scene_dirs]

    add_check(checks, "script.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "script.scene_files", all(path.exists() for path in script_paths), "each scene has script.md")
    _append_grounding_checks(checks, run_dir=run_dir, stage="script")

    all_no_todo = True
    for path in script_paths:
        if not path.exists():
            all_no_todo = False
            continue
        text = path.read_text(encoding="utf-8")
        if profile == "standard" and has_todo(text):
            all_no_todo = False
    if profile == "standard":
        add_check(checks, "script.scene_no_todo", all_no_todo, "scene scripts do not contain TODO/TBD markers", kind="rubric")

    updates = {"eval.script.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("script", "scenes/*/script.md", checks, details={"scene_count": len(scene_dirs)}), updates


def _iter_manifest_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for scene in as_list(manifest.get("scenes")):
        if isinstance(scene, dict) and str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = as_list(scene.get("cuts")) if isinstance(scene, dict) else []
        if cuts:
            nodes.extend([cut for cut in cuts if isinstance(cut, dict)])
        elif isinstance(scene, dict):
            nodes.append(scene)
    return nodes


def _iter_manifest_nodes_with_selectors(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for scene in as_list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = as_dotted_str(scene.get("scene_id"))
        if scene_id is None:
            continue
        cuts = as_list(scene.get("cuts"))
        if cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cut_id = as_dotted_str(cut.get("cut_id"))
                if cut_id is None:
                    continue
                items.append((make_scene_cut_selector(scene_id, cut_id), cut))
        else:
            items.append((make_scene_cut_selector(scene_id), scene))
    return items


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


def _load_script_reveal_constraints(run_dir: Path) -> list[dict[str, str]]:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        return []
    _, data = load_structured_document(script_path)
    if not isinstance(data, dict):
        return []
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


def _load_script_change_request_contract(run_dir: Path) -> dict[str, Any]:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
    _, data = load_structured_document(script_path)
    if not isinstance(data, dict):
        return {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}

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


def _human_change_request_issues(manifest: dict[str, Any], *, run_dir: Path | None = None) -> list[str]:
    issues: list[str] = []
    script_contract = _load_script_change_request_contract(run_dir) if run_dir else {"expected_request_ids": set(), "request_ids_by_selector": {}, "issues": []}
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


def _manifest_checks(checks: list[dict[str, Any]], body_text: str, data: dict[str, Any], *, profile: str, flow: str, path_label: str) -> None:
    add_check(checks, f"{path_label}.structured", bool(data), f"{path_label} contains structured YAML output")
    if not data:
        return

    scenes = as_list(data.get("scenes"))
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    add_check(checks, f"{path_label}.scenes", len(scenes) >= 1, f"{path_label} contains scenes", kind="rubric")
    add_check(checks, f"{path_label}.nodes", len(nodes) >= 1, f"{path_label} exposes renderable nodes", kind="rubric")

    if profile == "standard":
        add_check(checks, f"{path_label}.no_todo", not has_todo(body_text), f"{path_label} does not contain TODO/TBD markers", kind="rubric")

    duration_ok = True
    narration_field_ok = True
    narration_text_ok = True
    ids_ok = True
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

    if flow == "immersive":
        experience = nested_get(data, ["video_metadata", "experience"])
        prompt_mentions_text_rule = ("画面内テキスト" in body_text) or ("No on-screen text" in body_text)
        add_check(checks, f"{path_label}.experience", non_empty(experience), "immersive manifest records video_metadata.experience", kind="rubric")
        add_check(checks, f"{path_label}.no_onscreen_text_rule", prompt_mentions_text_rule, "immersive manifest includes no on-screen text invariant", kind="rubric")


def check_manifest_single(run_dir: Path, profile: str, flow: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "video_manifest.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    add_check(checks, "manifest.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("manifest", path.name, checks), updates

    text, data = load_structured_document(path)
    body_text = flatten_without_keys(data, excluded={"scene_contract", "review_contract", "evaluation_contract"}) or text
    _append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    manifest_phase = str(data.get("manifest_phase") or "production").strip().lower()
    add_check(checks, "manifest.phase", manifest_phase == "production", f"video_manifest.md is production phase (got {manifest_phase or '(unset)'})", kind="rubric")
    _manifest_checks(checks, body_text, data, profile=profile, flow=flow, path_label="manifest")
    nodes = _iter_manifest_nodes(data)
    nodes_with_selectors = _iter_manifest_nodes_with_selectors(data)
    reveal_constraints = _load_script_reveal_constraints(run_dir)
    human_change_issues = _human_change_request_issues(data, run_dir=run_dir)
    contract_missing = False
    must_show_failed = False
    must_avoid_failed = False
    target_beat_failed = False
    reveal_failed = False
    for selector, node in nodes_with_selectors:
        combined = "\n".join(
            [
                str(((node.get("image_generation") or {}) if isinstance(node.get("image_generation"), dict) else {}).get("prompt") or ""),
                str(((node.get("video_generation") or {}) if isinstance(node.get("video_generation"), dict) else {}).get("motion_prompt") or ""),
                str(((((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration") or {}) if isinstance(((node.get("audio") or {}) if isinstance(node.get("audio"), dict) else {}).get("narration"), dict) else {}).get("text") or ""),
            ]
        )
        contract = node.get("scene_contract") if isinstance(node.get("scene_contract"), dict) else {}
        if not contract:
            contract_missing = True
            continue
        must_show = contract_list(contract, "must_show")
        must_avoid = contract_list(contract, "must_avoid")
        target_beat = str(contract.get("target_beat") or "").strip()
        if must_show and not all(term in combined for term in must_show):
            must_show_failed = True
        if must_avoid and any(term in combined for term in must_avoid):
            must_avoid_failed = True
        if target_beat and target_beat not in combined:
            target_beat_failed = True
        if reveal_constraints:
            image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
            declared_character_ids = set(as_list(image_generation.get("character_ids"))) if isinstance(image_generation, dict) else set()
            prompt = str(image_generation.get("prompt") or "") if isinstance(image_generation, dict) else ""
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
        add_check(checks, "manifest.contract_missing", False, "one or more scene/cut nodes are missing scene_contract.", kind="rubric")
    if must_show_failed:
        add_check(checks, "manifest.contract_must_show_unmet", False, "scene/cut contract must_show items are not fully represented.", kind="rubric")
    if must_avoid_failed:
        add_check(checks, "manifest.contract_must_avoid_violated", False, "scene/cut contract must_avoid items are still present.", kind="rubric")
    if target_beat_failed:
        add_check(checks, "manifest.contract_target_beat_unmet", False, "scene/cut contract target_beat is not clearly represented.", kind="rubric")
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
    rubric_scores = _manifest_rubric(nodes, body_text)
    _append_rubric_findings(checks=checks, stage="manifest", rubric_scores=rubric_scores)
    updates["eval.manifest.score"] = f"{score_from_checks(checks):.4f}"
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
        body_text = flatten_without_keys(data, excluded={"scene_contract", "review_contract", "evaluation_contract"}) or text
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


def _probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None or not path.exists():
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _video_checks(checks: list[dict[str, Any]], *, video_path: Path, state: dict[str, str], run_dir: Path) -> None:
    video_exists = video_path.exists()
    add_check(checks, "video.file_exists", video_exists, f"{video_path.name} exists")
    if not video_exists:
        return

    render_status = state.get("runtime.render.status", "").strip().lower()
    add_check(checks, "video.render_status", render_status in {"success", "started", ""}, f"render status is set to success/started (got {render_status or '(unset)'})", kind="rubric")

    review_status = state.get("review.video.status", "").strip().lower()
    add_check(checks, "video.review_status", review_status in {"pending", "approved", "changes_requested"}, f"review.video.status is present (got {review_status or '(unset)'})", kind="rubric")

    report_exists = (run_dir / "run_report.md").exists()
    if report_exists:
        add_check(checks, "video.run_report", True, "run_report.md exists", kind="rubric")

    narration_list = run_dir / "video_narration_list.txt"
    if narration_list.exists():
        audio_paths = [Path(line.strip()) for line in narration_list.read_text(encoding="utf-8").splitlines() if line.strip()]
        resolved = [(path if path.is_absolute() else run_dir / path) for path in audio_paths]
        add_check(checks, "video.narration_list", all(path.exists() for path in resolved), "all narration files in video_narration_list.txt exist", kind="rubric")

    video_duration = _probe_duration(video_path)
    if video_duration is not None:
        add_check(checks, "video.duration", video_duration > 0.0, f"video duration is positive ({video_duration:.2f}s)", kind="rubric")


def check_video_single(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    _video_checks(checks, video_path=run_dir / "video.mp4", state=state, run_dir=run_dir)
    manifest_path = run_dir / "video_manifest.md"
    contract = {}
    if manifest_path.exists():
        _, manifest = load_structured_document(manifest_path)
        quality_check = manifest.get("quality_check") if isinstance(manifest.get("quality_check"), dict) else {}
        contract = quality_check.get("review_contract") if isinstance(quality_check.get("review_contract"), dict) else {}
    if not contract:
        add_check(checks, "video.contract_missing", False, "quality_check.review_contract is missing for the video stage.", kind="rubric")
    else:
        must_have = contract_list(contract, "must_have_artifacts")
        if must_have and not all((run_dir / item).exists() for item in must_have):
            add_check(checks, "video.contract_must_have_unmet", False, "video review contract requires artifacts that are still missing.", kind="rubric")
    rubric_scores = _video_rubric(run_dir, state, checks)
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "video.mp4", checks, rubric_scores=rubric_scores), updates


def check_video_scene_series(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    checks: list[dict[str, Any]] = []
    add_check(checks, "video.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    video_paths = [scene_dir / "video.mp4" for scene_dir in scene_dirs]
    add_check(checks, "video.scene_files", all(path.exists() for path in video_paths), "each scene has video.mp4")
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    rubric_scores = {
        "render_integrity": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "asset_completeness": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "review_readiness": 0.8,
        "audio_packaging": 0.8,
        "publish_readiness": score_from_ratio(sum(1 for check in checks if check["passed"]), len(checks)),
    }
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "scenes/*/video.mp4", checks, details={"scene_count": len(scene_dirs)}, rubric_scores=rubric_scores), updates


def evaluate_stage(run_dir: Path, *, stage: str, profile: str, flow: str | None = None) -> tuple[dict[str, Any], dict[str, str], str]:
    resolved_flow = flow or detect_flow(run_dir)
    if stage == "research":
        result, updates = check_research(run_dir, profile)
    elif stage == "script":
        if resolved_flow == "scene-series":
            result, updates = check_script_scene_series(run_dir, profile)
        else:
            result, updates = check_script_single(run_dir, profile)
    elif stage == "manifest":
        if resolved_flow == "scene-series":
            result, updates = check_manifest_scene_series(run_dir, profile)
        else:
            result, updates = check_manifest_single(run_dir, profile, resolved_flow)
    elif stage == "video":
        if resolved_flow == "scene-series":
            result, updates = check_video_scene_series(run_dir)
        else:
            result, updates = check_video_single(run_dir)
    else:
        raise ValueError(f"Unsupported stage: {stage}")
    return result, updates, resolved_flow


def render_stage_review(*, run_dir: Path, stage_result: dict[str, Any], stage: str, flow: str, profile: str) -> str:
    failed = [check for check in stage_result["checks"] if not check["passed"]]
    lines = [
        f"# {stage.title()} Evaluator Review",
        "",
        f"- run_dir: `{run_dir}`",
        f"- flow: `{flow}`",
        f"- profile: `{profile}`",
        f"- stage: `{stage}`",
        f"- status: `{'approved' if stage_result['passed'] else 'changes_requested'}`",
        f"- score: `{stage_result['score']:.4f}`",
        f"- overall_rubric: `{stage_result.get('overall_rubric', 0.0):.4f}`",
        f"- findings: `{len(failed)}`",
        "",
    ]
    if stage_result.get("rubric_scores"):
        lines.append("## Rubric")
        lines.append("")
        for key, value in stage_result["rubric_scores"].items():
            lines.append(f"- {key}: `{value:.4f}`")
        lines.append("")
    if stage_result.get("details"):
        lines.append("## Details")
        lines.append("")
        for key, value in stage_result["details"].items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    lines.append("## Checks")
    lines.append("")
    for check in stage_result["checks"]:
        lines.append(f"- [{'PASS' if check['passed'] else 'FAIL'}] `{check['id']}`: {check['message']}")
    return "\n".join(lines) + "\n"


def append_stage_review_state(*, run_dir: Path, stage: str, stage_result: dict[str, Any], updates: dict[str, str], report_path: Path) -> None:
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        return
    finding_count = sum(1 for check in stage_result["checks"] if not check["passed"])
    artifact_key_map = {
        "research": "artifact.research_review",
        "script": "artifact.script_review",
        "manifest": "artifact.manifest_review",
        "video": "artifact.video_review_report",
    }
    state_updates = dict(updates)
    state_updates[f"eval.{stage}.status"] = "approved" if stage_result["passed"] else "changes_requested"
    state_updates[f"eval.{stage}.findings"] = str(finding_count)
    state_updates[f"eval.{stage}.reason_keys"] = ",".join(stage_result.get("reason_keys") or [])
    state_updates[f"eval.{stage}.overall_rubric"] = f"{float(stage_result.get('overall_rubric', 0.0)):.4f}"
    for key, value in dict(stage_result.get("rubric_scores") or {}).items():
        state_updates[f"eval.{stage}.rubric.{key}"] = f"{float(value):.4f}"
    state_updates[artifact_key_map[stage]] = str(report_path.resolve())
    append_state_snapshot(state_path, state_updates)
