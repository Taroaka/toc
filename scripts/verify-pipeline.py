#!/usr/bin/env python3
"""Verify ToC pipeline artifacts and generate machine/human-readable reports."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageFilter  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    Image = None
    ImageFilter = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import grounding_validation  # noqa: E402
from toc.harness import (  # noqa: E402
    append_state_snapshot,
    eval_report_path,
    load_structured_document,
    now_iso,
    parse_state_file,
    run_report_path,
    sync_run_status,
    write_json,
)
from toc.stage_evaluator import check_manifest_single as shared_check_manifest_single  # noqa: E402
from toc.stage_evaluator import check_visual_value  # noqa: E402


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


STORY_REQUIRED_SCENE_FIELDS = [
    "purpose",
    "conflict",
    "turn",
    "affect",
    "visualizable_action",
    "grounding_note",
]


def compact_research_pack_ok(
    *,
    sources: list[Any],
    passage_count: int,
    canonical_story: Any,
    conflict_items: list[Any],
    handoff_to_story: Any,
) -> bool:
    """Accept focused research when it is grounded enough to avoid count padding."""
    has_canonical = non_empty(canonical_story)
    has_conflict_or_handoff = bool(conflict_items) or non_empty(handoff_to_story)
    has_source_grounding = len(sources) >= 3 or (len(sources) >= 1 and passage_count >= 5)
    return has_canonical and has_source_grounding and passage_count >= 3 and has_conflict_or_handoff


def dense_story_scene_count(scenes: list[Any]) -> int:
    return sum(
        1
        for scene in scenes
        if isinstance(scene, dict)
        and all(non_empty(scene.get(field)) for field in STORY_REQUIRED_SCENE_FIELDS)
        and bool(as_list(scene.get("research_refs")))
    )


def story_scene_coverage_ok(scenes: list[Any]) -> bool:
    return len(scenes) >= 20 or dense_story_scene_count(scenes) >= 8


def nested_get(data: dict[str, Any], path: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, message: str, *, kind: str = "deterministic") -> None:
    checks.append(
        {
            "id": check_id,
            "passed": passed,
            "kind": kind,
            "message": message,
        }
    )


def score_from_checks(checks: list[dict[str, Any]]) -> float:
    if not checks:
        return 0.0
    passed = sum(1 for check in checks if check["passed"])
    return round(passed / len(checks), 4)


def make_stage(stage: str, artifact: str, checks: list[dict[str, Any]], *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    score = score_from_checks(checks)
    return {
        "stage": stage,
        "artifact": artifact,
        "passed": all(check["passed"] for check in checks),
        "score": score,
        "checks": checks,
        "details": details or {},
    }


def append_grounding_checks(checks: list[dict[str, Any]], *, run_dir: Path, stage: str) -> None:
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
    append_grounding_checks(checks, run_dir=run_dir, stage="research")

    sources = as_list(data.get("source_inventory") or data.get("sources"))
    story_materials = data.get("story_materials")
    chronological_events = nested_get(data, ["story_materials", "chronological_events"], [])
    source_passages = as_list(data.get("source_passages"))
    primary_sources = as_list(data.get("primary_sources"))
    legacy_passages: list[Any] = []
    for source in primary_sources:
        if isinstance(source, dict):
            legacy_passages.extend(as_list(source.get("key_passages")))
    beat_sheet = nested_get(data, ["story_baseline", "canonical_synopsis", "beat_sheet"], [])
    conflicts = data.get("conflicts")
    conflict_items = as_list(conflicts)
    facts_value = data.get("facts")
    facts = as_list(facts_value.get("items")) if isinstance(facts_value, dict) else as_list(facts_value)
    handoff_to_story = data.get("handoff_to_story")
    confidence = nested_get(data, ["metadata", "confidence_score"])
    synopsis = nested_get(data, ["story_baseline", "canonical_synopsis", "short_summary"]) or nested_get(
        data, ["story_baseline", "canonical_synopsis", "one_liner"]
    )
    canonical_story_dump = nested_get(data, ["story_materials", "canonical_story_dump"])
    canonical_story = canonical_story_dump or synopsis

    details["sources"] = len(sources)
    details["event_count"] = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    details["source_passage_count"] = len(source_passages) or len(legacy_passages)
    details["fact_count"] = len(as_list(facts))

    add_check(checks, "research.structured", bool(data), "research.md contains structured YAML output")
    story_materials_ok = bool(story_materials) or non_empty(synopsis)
    passage_count = len(source_passages) or len(legacy_passages)
    compact_pack_ok = compact_research_pack_ok(
        sources=sources,
        passage_count=passage_count,
        canonical_story=canonical_story,
        conflict_items=conflict_items,
        handoff_to_story=handoff_to_story,
    )
    source_coverage_ok = len(sources) >= 12 or compact_pack_ok
    add_check(
        checks,
        "research.sources",
        source_coverage_ok,
        f"sources meet broad target >= 12 or compact grounded pack is present (got sources={len(sources)}, passages={passage_count})",
        kind="rubric",
    )
    add_check(
        checks,
        "research.story_materials",
        story_materials_ok,
        "story_materials or legacy story baseline is present",
        kind="rubric",
    )
    add_check(
        checks,
        "research.canonical_story",
        non_empty(canonical_story),
        "canonical story dump or legacy synopsis is present",
        kind="rubric",
    )
    event_count = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    add_check(
        checks,
        "research.chronological_events",
        event_count >= 20 or compact_pack_ok,
        f"chronological coverage meets broad target >= 20 or compact grounded pack is present (got events={event_count}, passages={passage_count})",
        kind="rubric",
    )
    add_check(
        checks,
        "research.source_passages",
        passage_count >= 1,
        f"source passages are present (got {passage_count})",
        kind="rubric",
    )
    add_check(
        checks,
        "research.facts",
        len(as_list(facts)) >= 10 or compact_pack_ok,
        f"facts meet broad target >= 10 or compact grounded pack is present (got facts={len(as_list(facts))}, passages={passage_count})",
        kind="rubric",
    )
    add_check(checks, "research.conflicts_field", conflicts is not None, "conflicts field is present", kind="rubric")
    add_check(checks, "research.handoff_to_story", bool(handoff_to_story), "handoff_to_story is present", kind="rubric")

    confidence_ok = isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0
    add_check(checks, "research.confidence", confidence_ok, "metadata.confidence_score is between 0.0 and 1.0", kind="rubric")

    updates["eval.research.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("research", path.name, checks, details=details), updates


def check_story(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "story.md"
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}

    add_check(checks, "story.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("story", path.name, checks), updates

    text, data = load_structured_document(path)
    if profile == "standard":
        add_check(checks, "story.no_todo", not has_todo(text), "story.md does not contain TODO/TBD markers", kind="rubric")
    append_grounding_checks(checks, run_dir=run_dir, stage="story")

    selection = nested_get(data, ["selection"], {})
    candidates = as_list(selection.get("candidates")) if isinstance(selection, dict) else []
    chosen_id = selection.get("chosen_candidate_id") if isinstance(selection, dict) else None
    rationale = selection.get("rationale") if isinstance(selection, dict) else None
    scenes = as_list(nested_get(data, ["script", "scenes"], []))
    hybrid_status = nested_get(data, ["hybridization", "approval_status"])

    details["candidate_count"] = len(candidates)
    details["scene_count"] = len(scenes)
    details["chosen_candidate_id"] = chosen_id

    add_check(checks, "story.structured", bool(data), "story.md contains structured YAML output")
    add_check(checks, "story.candidates", 2 <= len(candidates) <= 4, f"selection has 2-4 candidates (got {len(candidates)})", kind="rubric")
    add_check(checks, "story.choice", non_empty(chosen_id), "chosen_candidate_id is set", kind="rubric")
    add_check(checks, "story.rationale", non_empty(rationale), "selection rationale is present", kind="rubric")
    add_check(
        checks,
        "story.scenes",
        story_scene_coverage_ok(scenes),
        f"story has >= 20 scenes or >= 8 dense grounded scenes (got scenes={len(scenes)}, dense_grounded={dense_story_scene_count(scenes)})",
        kind="rubric",
    )

    for field in STORY_REQUIRED_SCENE_FIELDS:
        missing = [
            str(scene.get("scene_id") or index + 1)
            for index, scene in enumerate(scenes)
            if not isinstance(scene, dict) or not non_empty(scene.get(field))
        ]
        if missing:
            details[f"missing_{field}_scene_ids"] = ",".join(missing[:20])
        add_check(checks, f"story.scene_{field}", not missing, f"all scripted scenes include {field}", kind="rubric")

    research_refs_missing = [
        str(scene.get("scene_id") or index + 1)
        for index, scene in enumerate(scenes)
        if not isinstance(scene, dict) or not as_list(scene.get("research_refs"))
    ]
    if research_refs_missing:
        details["missing_research_refs_scene_ids"] = ",".join(research_refs_missing[:20])
    add_check(checks, "story.research_refs", not research_refs_missing, "scripted scenes keep research_refs", kind="rubric")

    hybrid_ok = hybrid_status in {None, "", "not_needed", "approved", "rejected"}
    add_check(checks, "story.hybrid_gate", hybrid_ok, "hybridization approval is not left pending", kind="rubric")

    updates["eval.story.score"] = f"{score_from_checks(checks):.4f}"
    if candidates:
        updates["selection.story.candidate_count"] = str(len(candidates))
    if non_empty(chosen_id):
        updates["selection.story.chosen_id"] = str(chosen_id)
    return make_stage("story", path.name, checks, details=details), updates


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
    append_grounding_checks(checks, run_dir=run_dir, stage="script")
    _script_text_quality_checks(checks, text, data, profile)
    updates["eval.script.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("script", path.name, checks), updates


def check_script_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    script_paths = [scene_dir / "script.md" for scene_dir in scene_dirs]

    add_check(checks, "script.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "script.scene_files", all(path.exists() for path in script_paths), "each scene has script.md")
    append_grounding_checks(checks, run_dir=run_dir, stage="script")

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
        cuts = as_list(scene.get("cuts")) if isinstance(scene, dict) else []
        if cuts:
            nodes.extend([cut for cut in cuts if isinstance(cut, dict)])
        elif isinstance(scene, dict):
            nodes.append(scene)
    return nodes


def _manifest_checks(checks: list[dict[str, Any]], text: str, data: dict[str, Any], *, profile: str, flow: str, path_label: str) -> None:
    add_check(checks, f"{path_label}.structured", bool(data), f"{path_label} contains structured YAML output")
    if not data:
        return

    scenes = as_list(data.get("scenes"))
    nodes = _iter_manifest_nodes(data)
    add_check(checks, f"{path_label}.scenes", len(scenes) >= 1, f"{path_label} contains scenes", kind="rubric")
    add_check(checks, f"{path_label}.nodes", len(nodes) >= 1, f"{path_label} exposes renderable nodes", kind="rubric")

    if profile == "standard":
        add_check(checks, f"{path_label}.no_todo", not has_todo(text), f"{path_label} does not contain TODO/TBD markers", kind="rubric")

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
        rendered_text = narration.get("tts_text") if narration_tool == "elevenlabs" and "tts_text" in narration else narration.get("text")
        if profile == "standard" and narration_tool != "silent" and not non_empty(rendered_text):
            narration_text_ok = False

    add_check(checks, f"{path_label}.cut_duration", duration_ok, "cut duration is <= 15 seconds", kind="rubric")
    add_check(checks, f"{path_label}.narration_field", narration_field_ok, "each renderable node has audio.narration.text", kind="rubric")
    if profile == "standard":
        add_check(checks, f"{path_label}.narration_text", narration_text_ok, "narration text/tts_text is non-empty for final manifests unless tool is silent", kind="rubric")
    add_check(checks, f"{path_label}.asset_ids", ids_ok, "image_generation includes explicit character_ids/object_ids", kind="rubric")

    if flow == "immersive":
        experience = nested_get(data, ["video_metadata", "experience"])
        prompt_mentions_text_rule = ("画面内テキスト" in text) or ("No on-screen text" in text)
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
    append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    manifest_phase = str(data.get("manifest_phase") or "production").strip().lower()
    add_check(checks, "manifest.phase", manifest_phase == "production", f"video_manifest.md is production phase (got {manifest_phase or '(unset)'})", kind="rubric")
    _manifest_checks(checks, text, data, profile=profile, flow=flow, path_label="manifest")
    updates["eval.manifest.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("manifest", path.name, checks), updates


def check_manifest_scene_series(run_dir: Path, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    manifest_paths = [scene_dir / "video_manifest.md" for scene_dir in scene_dirs]

    add_check(checks, "manifest.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    add_check(checks, "manifest.scene_files", all(path.exists() for path in manifest_paths), "each scene has video_manifest.md")
    append_grounding_checks(checks, run_dir=run_dir, stage="manifest")
    if not scene_dirs or not all(path.exists() for path in manifest_paths):
        return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}), {
            "eval.manifest.score": f"{score_from_checks(checks):.4f}"
        }

    nested_ok = True
    phase_ok = True
    for path in manifest_paths:
        text, data = load_structured_document(path)
        local_checks: list[dict[str, Any]] = []
        if str(data.get("manifest_phase") or "production").strip().lower() != "production":
            phase_ok = False
        _manifest_checks(local_checks, text, data, profile=profile, flow="scene-series", path_label=path.name)
        if not all(check["passed"] for check in local_checks):
            nested_ok = False
    add_check(checks, "manifest.scene_phase", phase_ok, "scene manifests are in production phase", kind="rubric")
    add_check(checks, "manifest.scene_contracts", nested_ok, "scene manifests satisfy render contract checks", kind="rubric")

    updates = {"eval.manifest.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("manifest", "scenes/*/video_manifest.md", checks, details={"scene_count": len(scene_dirs)}), updates


def _manifest_data_for_outputs(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "video_manifest.md"
    if not path.exists():
        return {}
    _, data = load_structured_document(path)
    return data


def _node_output_paths(run_dir: Path, *, field_path: list[str]) -> list[Path]:
    outputs: list[Path] = []
    for node in _iter_manifest_nodes(_manifest_data_for_outputs(run_dir)):
        value: Any = node
        for key in field_path:
            value = value.get(key) if isinstance(value, dict) else None
        if not non_empty(value):
            continue
        output_path = Path(str(value))
        outputs.append(output_path if output_path.is_absolute() else run_dir / output_path)
    return outputs


def _existing_media_files(path: Path, suffixes: set[str]) -> list[Path]:
    if not path.exists():
        return []
    return [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in suffixes]


def _slot_number(value: str | None, *, default: int) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        return default
    try:
        return int(match.group(1))
    except Exception:
        return default


def _asset_entries(asset_plan: dict[str, Any]) -> list[dict[str, Any]]:
    assets = asset_plan.get("assets")
    if isinstance(assets, list):
        return [item for item in assets if isinstance(item, dict)]
    if not isinstance(assets, dict):
        return []

    entries: list[dict[str, Any]] = []
    for category in ("characters", "objects", "locations", "setpieces", "reusable_stills"):
        for item in as_list(assets.get(category)):
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("_category", category)
                entries.append(copied)
    return entries


def _entry_generation_plan(entry: dict[str, Any]) -> dict[str, Any]:
    plan = entry.get("generation_plan")
    return plan if isinstance(plan, dict) else {}


def _entry_review(entry: dict[str, Any]) -> dict[str, Any]:
    review = entry.get("review")
    return review if isinstance(review, dict) else {}


def _entry_asset_id(entry: dict[str, Any]) -> str:
    return str(entry.get("asset_id") or "").strip()


def _entry_asset_type(entry: dict[str, Any]) -> str:
    return str(entry.get("asset_type") or "").strip()


def _entry_required_views(entry: dict[str, Any]) -> list[str]:
    views = _entry_generation_plan(entry).get("required_views")
    return [str(item).strip().lower() for item in as_list(views) if str(item).strip()]


def _entry_reference_inputs(entry: dict[str, Any]) -> list[str]:
    references = _entry_generation_plan(entry).get("reference_inputs")
    return [str(item).strip() for item in as_list(references) if str(item).strip()]


def _entry_outputs(entry: dict[str, Any]) -> list[str]:
    outputs: list[str] = []
    for raw in as_list(entry.get("existing_outputs")):
        text = str(raw).strip()
        if text:
            outputs.append(text)
    plan = _entry_generation_plan(entry)
    for key in ("output", "output_path"):
        text = str(plan.get(key) or "").strip()
        if text and text not in outputs:
            outputs.append(text)
    return outputs


def _resolve_run_relpath(run_dir: Path, rel: str) -> Path:
    return (run_dir / rel).resolve()


def _output_exists(run_dir: Path, rel: str) -> bool:
    path = _resolve_run_relpath(run_dir, rel)
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return False
    return path.exists() and path.is_file()


def _image_generation_provenance_by_destination(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return latest app-server image-generation log payload by run-relative destination."""

    log_path = run_dir / "logs" / "image_generation_prompts.jsonl"
    if not log_path.exists():
        return {}
    by_destination: dict[str, dict[str, Any]] = {}
    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        destination = str(payload.get("destination") or "").strip()
        if not destination:
            continue
        by_destination[destination] = payload
    return by_destination


def _image_generation_provenance_failures(
    run_dir: Path,
    outputs: list[str],
    *,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    records = provenance if provenance is not None else _image_generation_provenance_by_destination(run_dir)
    failures: list[str] = []
    for output in outputs:
        rel = str(output or "").strip()
        if not rel:
            continue
        record = records.get(rel)
        if not record:
            failures.append(f"{rel}: missing app-server generation provenance")
            continue
        source = str(record.get("source") or "").strip().lower()
        status = str(record.get("status") or "").strip().lower()
        saved_path = str(record.get("savedPath") or "").strip()
        error = str(record.get("error") or "").strip()
        if "local_raster" in source:
            failures.append(f"{rel}: unsupported local raster fallback source={source}")
        elif status not in {"completed", "success"}:
            failures.append(f"{rel}: generation status {status or '(missing)'}")
        elif not saved_path:
            failures.append(f"{rel}: missing savedPath in generation provenance")
        elif error:
            failures.append(f"{rel}: generation log contains error")
    return failures


def _asset_manifest_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("asset_generation_manifest"), dict):
        items = data["asset_generation_manifest"].get("items")
        return [item for item in as_list(items) if isinstance(item, dict)]
    if isinstance(data.get("assets"), list):
        return [item for item in data.get("assets", []) if isinstance(item, dict)]
    if isinstance(data.get("items"), list):
        return [item for item in data.get("items", []) if isinstance(item, dict)]
    return []


def _asset_manifest_item_id(item: dict[str, Any]) -> str:
    return str(item.get("asset_id") or item.get("selector") or "").strip()


def _has_template_placeholder(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in ("TODO", "TBD", "REPLACE_ME", "EXAMPLE_ONLY", "TEMPLATE_ONLY"))


def _asset_inventory_schema_issues(inventory_root: Any) -> list[str]:
    if not isinstance(inventory_root, dict):
        return ["asset_inventory root missing"]
    issues: list[str] = []
    source_artifacts = inventory_root.get("source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        issues.append("source_artifacts[] missing")
    coverage_scope = inventory_root.get("coverage_scope")
    if not isinstance(coverage_scope, dict):
        issues.append("coverage_scope missing")
    else:
        for key in ("characters", "story_specific_items", "locations", "setpieces", "reusable_stills"):
            if key not in coverage_scope or not isinstance(coverage_scope.get(key), list):
                issues.append(f"coverage_scope.{key}[] missing")
    items = inventory_root.get("items")
    if not isinstance(items, list) or not items:
        issues.append("items[] missing")
    else:
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                issues.append(f"items[{idx}] is not mapping")
                continue
            for key in ("item_id", "category", "source_script_selectors", "story_purpose", "reusable_reason", "recommended_asset_type"):
                value = item.get(key)
                if key == "source_script_selectors":
                    if not isinstance(value, list) or not value:
                        issues.append(f"items[{idx}].{key}[] missing")
                elif not str(value or "").strip():
                    issues.append(f"items[{idx}].{key} missing")
    return issues


def _request_sections_by_asset_id(text: str) -> dict[str, dict[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading or current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, current_lines))

    out: dict[str, dict[str, str]] = {}
    field_pattern = re.compile(r"^\s*-\s+([A-Za-z0-9_.]+):\s*(.*?)\s*$")
    for heading, lines in sections:
        fields: dict[str, str] = {}
        for line in lines:
            match = field_pattern.match(line)
            if not match:
                continue
            value = match.group(2).strip()
            if value.startswith("`") and value.endswith("`") and len(value) >= 2:
                value = value[1:-1]
            fields[match.group(1)] = value
        asset_id = fields.get("asset_id") or heading
        asset_id = str(asset_id).strip("` ")
        if asset_id:
            out[asset_id] = fields
    return out


def _request_sections_with_references(text: str) -> list[dict[str, Any]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading or current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, current_lines))

    field_pattern = re.compile(r"^\s*-\s+([A-Za-z0-9_.]+):\s*(.*?)\s*$")
    backtick_pattern = re.compile(r"`([^`]+)`")
    out: list[dict[str, Any]] = []
    for heading, lines in sections:
        fields: dict[str, str] = {}
        references: list[str] = []
        in_references = False
        for line in lines:
            field_match = field_pattern.match(line)
            if field_match:
                key = field_match.group(1)
                raw_value = field_match.group(2).strip()
                value = raw_value
                if value.startswith("`") and value.endswith("`") and len(value) >= 2:
                    value = value[1:-1]
                fields[key] = value
                in_references = key == "references"
                if in_references and raw_value and raw_value != "[]":
                    references.extend(
                        candidate
                        for candidate in backtick_pattern.findall(raw_value)
                        if Path(candidate).suffix.lower() in VECTOR_GATE_IMAGE_SUFFIXES
                    )
                continue

            if in_references:
                if not line.startswith((" ", "\t")) or line.lstrip().startswith("- ") is False:
                    in_references = False
                    continue
                candidates = backtick_pattern.findall(line)
                for candidate in reversed(candidates):
                    if Path(candidate).suffix.lower() in VECTOR_GATE_IMAGE_SUFFIXES:
                        references.append(candidate)
                        break

        selector = (fields.get("selector") or fields.get("asset_id") or heading).strip("` ")
        if selector or fields or references:
            out.append({"selector": selector, "fields": fields, "references": references})
    return out


def _request_field_value(fields: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(fields.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_int_field(value: str) -> int | None:
    try:
        return int(str(value or "").strip("` "))
    except Exception:
        return None


PRODUCTION_META_PATTERNS = (
    re.compile(r"物語「[^」]+」の\s*scene\d+", flags=re.IGNORECASE),
    re.compile(r"\bscene\d+[_-]cut\d+\b", flags=re.IGNORECASE),
    re.compile(r"この画像は物語「[^」]+」の一場面"),
    re.compile(r"後続\s*scene", flags=re.IGNORECASE),
)

VECTOR_LIKE_MIN_BYTES_PER_MEGAPIXEL = 60_000
VECTOR_LIKE_MIN_THUMBNAIL_COLORS = 1_800
VECTOR_LIKE_MIN_DENOISED_EDGE_MEAN = 1.2
VECTOR_LIKE_MIN_DENOISED_EDGE_DENSITY = 0.025
VECTOR_LIKE_MAX_QUANTIZED_TOP5_RATIO = 0.62
VECTOR_LIKE_MAX_FLAT_EDGE_MEAN = 1.4
VECTOR_GATE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _request_prompt_contains_production_meta(text: str) -> bool:
    prompt_blocks = re.findall(r"```text\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
    targets = prompt_blocks or [text]
    return any(pattern.search(block) for block in targets for pattern in PRODUCTION_META_PATTERNS)


def _image_complexity_stats(path: Path, *, run_dir: Path) -> dict[str, Any]:
    resolved_path = path.resolve()
    try:
        rel_path = str(resolved_path.relative_to(run_dir.resolve()))
    except ValueError:
        rel_path = str(resolved_path)
    stats: dict[str, Any] = {"path": rel_path}
    if Image is None:
        stats["issue"] = "Pillow is unavailable"
        return stats

    try:
        with Image.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                stats["issue"] = "invalid image dimensions"
                return stats
            rgb = image.convert("RGB")
            resampling = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
            thumb = rgb.resize((160, 90), resampling)
            colors = thumb.getcolors(maxcolors=160 * 90 + 1)
            unique_colors = (160 * 90 + 1) if colors is None else len(colors)
            quantized_top5_ratio = 0.0
            quantized = thumb.quantize(colors=16).convert("RGB")
            quantized_colors = quantized.getcolors(maxcolors=160 * 90 + 1) or []
            if quantized_colors:
                quantized_top5_ratio = sum(count for count, _color in sorted(quantized_colors, reverse=True)[:5]) / (160 * 90)
            denoised_edge_mean = 0.0
            denoised_edge_density = 0.0
            if ImageFilter is not None:
                denoised = thumb.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.5)).convert("L")
                pixels = list(denoised.getdata())
                edge_diffs: list[int] = []
                thumb_width, thumb_height = denoised.size
                for y in range(thumb_height):
                    row = y * thumb_width
                    for x in range(thumb_width - 1):
                        edge_diffs.append(abs(pixels[row + x] - pixels[row + x + 1]))
                for y in range(thumb_height - 1):
                    row = y * thumb_width
                    next_row = (y + 1) * thumb_width
                    for x in range(thumb_width):
                        edge_diffs.append(abs(pixels[row + x] - pixels[next_row + x]))
                if edge_diffs:
                    denoised_edge_mean = sum(edge_diffs) / len(edge_diffs)
                    denoised_edge_density = sum(diff > 8 for diff in edge_diffs) / len(edge_diffs)
    except Exception as exc:
        stats["issue"] = f"cannot inspect image: {exc}"
        return stats

    megapixels = max((width * height) / 1_000_000, 0.000001)
    bytes_per_megapixel = path.stat().st_size / megapixels
    stats.update(
        {
            "width": width,
            "height": height,
            "bytes_per_megapixel": round(bytes_per_megapixel, 1),
            "thumbnail_unique_colors": unique_colors,
            "quantized_top5_ratio": round(quantized_top5_ratio, 4),
            "denoised_edge_mean": round(denoised_edge_mean, 4),
            "denoised_edge_density": round(denoised_edge_density, 4),
        }
    )
    if (
        bytes_per_megapixel < VECTOR_LIKE_MIN_BYTES_PER_MEGAPIXEL
        and unique_colors < VECTOR_LIKE_MIN_THUMBNAIL_COLORS
    ):
        stats["issue"] = "vector-like or low-detail raster image"
    elif (
        unique_colors >= VECTOR_LIKE_MIN_THUMBNAIL_COLORS
        and denoised_edge_mean < VECTOR_LIKE_MIN_DENOISED_EDGE_MEAN
        and denoised_edge_density < VECTOR_LIKE_MIN_DENOISED_EDGE_DENSITY
    ):
        stats["issue"] = "noise-masked vector-like or low-structure raster image"
    elif (
        quantized_top5_ratio > VECTOR_LIKE_MAX_QUANTIZED_TOP5_RATIO
        and denoised_edge_mean < VECTOR_LIKE_MAX_FLAT_EDGE_MEAN
    ):
        stats["issue"] = "flat-region vector-like or cel-shaded raster image"
    return stats


def _asset_visual_quality_stats(run_dir: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: list[dict[str, Any]] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        for rel in _entry_outputs(entry):
            path = _resolve_run_relpath(run_dir, rel)
            if path.suffix.lower() not in VECTOR_GATE_IMAGE_SUFFIXES:
                continue
            if not path.exists() or not path.is_file():
                continue
            item_stats = _image_complexity_stats(path, run_dir=run_dir)
            item_stats["asset_id"] = asset_id
            stats.append(item_stats)
    return stats


def _scene_image_visual_quality_stats(
    run_dir: Path,
    request_items: list[dict[str, Any]],
    expected_outputs: list[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    output_stats: list[dict[str, Any]] = []
    reference_stats: list[dict[str, Any]] = []
    regeneration_plan: list[dict[str, Any]] = []
    seen_references: set[tuple[str, str]] = set()
    request_by_output: dict[Path, dict[str, Any]] = {}

    for item in request_items:
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        output_rel = _request_field_value(fields, "output")
        if output_rel:
            request_by_output[_resolve_run_relpath(run_dir, output_rel)] = item

    uninspected_outputs: list[str] = []
    for output_path in expected_outputs:
        if output_path.suffix.lower() not in VECTOR_GATE_IMAGE_SUFFIXES or not output_path.exists() or not output_path.is_file():
            continue
        item = request_by_output.get(output_path.resolve())
        fields = item.get("fields") if isinstance(item, dict) and isinstance(item.get("fields"), dict) else {}
        try:
            fallback_selector = output_path.relative_to(run_dir).as_posix()
        except ValueError:
            fallback_selector = str(output_path)
        selector = str((item or {}).get("selector") or fields.get("selector") or fallback_selector).strip() or fallback_selector
        output_rel = _request_field_value(fields, "output") or fallback_selector
        if item is None:
            uninspected_outputs.append(fallback_selector)
        scene_issue = False
        item_stats = _image_complexity_stats(output_path, run_dir=run_dir)
        item_stats["selector"] = selector
        output_stats.append(item_stats)
        scene_issue = bool(item_stats.get("issue"))

        item_reference_issues: list[dict[str, Any]] = []
        for reference_rel in as_list((item or {}).get("references")):
            reference_text = str(reference_rel).strip()
            if not reference_text:
                continue
            reference_path = _resolve_run_relpath(run_dir, reference_text)
            if reference_path.suffix.lower() not in VECTOR_GATE_IMAGE_SUFFIXES:
                continue
            if not reference_path.exists() or not reference_path.is_file():
                continue
            seen_key = (selector, str(reference_path.resolve()))
            if seen_key in seen_references:
                continue
            seen_references.add(seen_key)
            item_stats = _image_complexity_stats(reference_path, run_dir=run_dir)
            item_stats["selector"] = selector
            item_stats["reference"] = str(reference_text)
            reference_stats.append(item_stats)
            if item_stats.get("issue"):
                item_reference_issues.append(item_stats)

        if scene_issue:
            if item_reference_issues:
                regeneration_plan.append(
                    {
                        "selector": selector,
                        "output": output_rel,
                        "action": "regenerate_p500_reference_first",
                        "reason": "scene output is vector-like and one or more p500 reference images are also vector-like",
                        "vector_like_references": [stat.get("reference") or stat.get("path") for stat in item_reference_issues],
                    }
                )
            else:
                regeneration_plan.append(
                    {
                        "selector": selector,
                        "output": output_rel,
                        "action": "regenerate_p600_scene",
                        "reason": "scene output is vector-like but referenced p500 images are inspectable raster images",
                        "vector_like_references": [],
                    }
                )

    for stat in reference_stats:
        if stat.get("issue") and not any(
            plan.get("action") == "regenerate_p500_reference_first"
            and stat.get("selector") == plan.get("selector")
            and (stat.get("reference") or stat.get("path")) in as_list(plan.get("vector_like_references"))
            for plan in regeneration_plan
        ):
            regeneration_plan.append(
                {
                    "selector": stat.get("selector"),
                    "output": "",
                    "action": "regenerate_p500_reference_first",
                    "reason": "p600 request references a vector-like p500 image",
                    "vector_like_references": [stat.get("reference") or stat.get("path")],
                }
            )

    return output_stats, reference_stats, regeneration_plan, uninspected_outputs


def check_asset(run_dir: Path, *, target_slot: str = "p570") -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}
    target_number = _slot_number(target_slot, default=570)
    asset_inventory = run_dir / "asset_inventory.md"
    asset_plan = run_dir / "asset_plan.md"
    requests = run_dir / "asset_generation_requests.md"
    manifests = [
        run_dir / "asset_generation_manifest.md",
        run_dir / "location_asset_generation_manifest.md",
    ]

    append_grounding_checks(checks, run_dir=run_dir, stage="asset")
    add_check(checks, "asset.asset_inventory", target_number < 520 or asset_inventory.exists(), f"{asset_inventory.name} exists")
    add_check(checks, "asset.asset_plan", target_number < 530 or asset_plan.exists(), f"{asset_plan.name} exists")
    add_check(checks, "asset.generation_requests", target_number < 550 or requests.exists(), f"{requests.name} exists")

    inventory_text = ""
    inventory_data: dict[str, Any] = {}
    if asset_inventory.exists():
        inventory_text, inventory_data = load_structured_document(asset_inventory)
    inventory_root = inventory_data.get("asset_inventory") if isinstance(inventory_data.get("asset_inventory"), dict) else inventory_data
    inventory_items = as_list(inventory_root.get("items")) if isinstance(inventory_root, dict) else []
    inventory_schema_issues = _asset_inventory_schema_issues(inventory_root)
    if inventory_schema_issues:
        details["asset_inventory_schema_issues"] = inventory_schema_issues[:20]
    details["asset_inventory_item_count"] = len(inventory_items)
    add_check(
        checks,
        "asset.inventory_structured",
        target_number < 520 or bool(inventory_items),
        "asset_inventory.md contains reusable asset inventory data",
        kind="rubric",
    )
    add_check(
        checks,
        "asset.inventory_schema",
        target_number < 520 or not inventory_schema_issues,
        "asset_inventory.md includes source_artifacts, coverage_scope categories, and item metadata",
        kind="rubric",
    )
    add_check(
        checks,
        "asset.inventory_no_todo",
        target_number < 520 or not _has_template_placeholder(inventory_text),
        "asset_inventory.md does not contain TODO/TBD/template placeholder markers",
        kind="rubric",
    )

    plan_text = ""
    plan_data: dict[str, Any] = {}
    if asset_plan.exists():
        plan_text, plan_data = load_structured_document(asset_plan)
    entries = _asset_entries(plan_data)
    details["asset_plan_entry_count"] = len(entries)
    planned_asset_ids = {_entry_asset_id(entry) for entry in entries if _entry_asset_id(entry)}
    add_check(
        checks,
        "asset.plan_structured",
        target_number < 530 or (bool(plan_data.get("assets")) and bool(entries)),
        "asset_plan.md has structured assets entries",
        kind="rubric",
    )
    add_check(
        checks,
        "asset.no_todo",
        target_number < 530 or not has_todo(plan_text),
        "asset_plan.md does not contain TODO/TBD markers",
        kind="rubric",
    )
    coverage_scope = inventory_root.get("coverage_scope") if isinstance(inventory_root, dict) else {}
    required_inventory_ids = {
        str(asset_id).strip()
        for key in ("characters", "story_specific_items", "locations")
        for asset_id in as_list(coverage_scope.get(key) if isinstance(coverage_scope, dict) else [])
        if str(asset_id).strip()
    }
    missing_plan_coverage = sorted(required_inventory_ids - planned_asset_ids)
    if missing_plan_coverage:
        details["asset_plan_missing_inventory_coverage"] = missing_plan_coverage[:20]
    add_check(
        checks,
        "asset.plan_covers_inventory_scope",
        target_number < 530 or not missing_plan_coverage,
        "asset_plan.md includes every character/story-specific item/location declared in asset_inventory.coverage_scope",
        kind="rubric",
    )

    missing_core_fields = [
        _entry_asset_id(entry) or "<missing_asset_id>"
        for entry in entries
        if not (
            _entry_asset_id(entry)
            and _entry_asset_type(entry)
            and as_list(entry.get("source_script_selectors"))
            and non_empty(entry.get("story_purpose"))
            and isinstance(entry.get("visual_spec"), dict)
            and isinstance(entry.get("generation_plan"), dict)
        )
    ]
    if missing_core_fields:
        details["asset_missing_core_fields"] = missing_core_fields[:20]
    add_check(
        checks,
        "asset.required_fields",
        target_number < 530 or (bool(entries) and not missing_core_fields),
        "all asset plan entries include id/type/source selectors/story purpose/visual spec/generation plan",
        kind="rubric",
    )

    character_three_view_failures = [
        _entry_asset_id(entry) or "<missing_asset_id>"
        for entry in entries
        if "character" in _entry_asset_type(entry)
        and not {"front", "side", "back"}.issubset(set(_entry_required_views(entry)))
    ]
    if character_three_view_failures:
        details["character_three_view_failures"] = character_three_view_failures[:20]
    add_check(
        checks,
        "asset.character_three_views",
        target_number < 530 or not character_three_view_failures,
        "character_reference entries require full-body front/side/back views",
        kind="rubric",
    )

    lane_failures: list[str] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        plan = _entry_generation_plan(entry)
        lane = str(plan.get("execution_lane") or entry.get("execution_lane") or "").strip()
        reference_inputs = _entry_reference_inputs(entry)
        derived_from = str(plan.get("derived_from_asset_id") or "").strip()
        bootstrap_allowed = bool(plan.get("bootstrap_allowed") or entry.get("bootstrap_allowed"))
        if reference_inputs or derived_from:
            if lane != "standard":
                lane_failures.append(f"{asset_id}: expected standard with references/derived_from")
        else:
            if lane != "bootstrap_builtin":
                lane_failures.append(f"{asset_id}: expected bootstrap_builtin for no-reference bootstrap seed")
            if not bootstrap_allowed:
                lane_failures.append(f"{asset_id}: bootstrap_allowed must be true for no-reference seed")
    if lane_failures:
        details["asset_lane_failures"] = lane_failures[:20]
    add_check(
        checks,
        "asset.lane_consistency",
        target_number < 530 or not lane_failures,
        "execution_lane matches reference_inputs / bootstrap contract",
        kind="rubric",
    )

    review_failures = [
        _entry_asset_id(entry) or "<missing_asset_id>"
        for entry in entries
        if str(_entry_review(entry).get("status") or "").strip().lower() != "approved"
    ]
    if review_failures:
        details["asset_review_failures"] = review_failures[:20]
    add_check(
        checks,
        "asset.review_approved",
        target_number < 540 or (bool(entries) and not review_failures),
        "all planned asset entries are review approved before generation",
        kind="rubric",
    )

    output_failures: list[str] = []
    planned_outputs: list[str] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        outputs = _entry_outputs(entry)
        planned_outputs.extend(outputs)
        if not outputs:
            output_failures.append(f"{asset_id}: no output path")
            continue
        missing = [rel for rel in outputs if not _output_exists(run_dir, rel)]
        if missing:
            output_failures.append(f"{asset_id}: missing {', '.join(missing[:3])}")
    if output_failures:
        details["asset_output_failures"] = output_failures[:20]
    add_check(
        checks,
        "asset.output_files",
        target_number < 560 or (bool(entries) and not output_failures),
        "all approved/generated asset output files exist under the run directory",
        kind="rubric",
    )

    provenance = _image_generation_provenance_by_destination(run_dir)
    asset_provenance_failures = _image_generation_provenance_failures(run_dir, planned_outputs, provenance=provenance)
    if asset_provenance_failures:
        details["asset_generation_provenance_failures"] = asset_provenance_failures[:20]
    add_check(
        checks,
        "asset.generation_provenance_app_server",
        target_number < 560 or (bool(entries) and not asset_provenance_failures),
        "generated p500 asset images have Codex app-server provenance and are not local raster fallbacks",
        kind="rubric",
    )

    visual_quality_stats = _asset_visual_quality_stats(run_dir, entries) if target_number >= 560 and entries else []
    visual_quality_issues = [
        f"{stat.get('asset_id', '<missing_asset_id>')}: {stat.get('path', '(unknown)')} - {stat.get('issue')}"
        for stat in visual_quality_stats
        if stat.get("issue")
    ]
    if visual_quality_stats:
        details["asset_visual_quality_samples"] = visual_quality_stats[:20]
    if visual_quality_issues:
        details["asset_visual_quality_issues"] = visual_quality_issues[:20]
    add_check(
        checks,
        "asset.visual_not_vector_like",
        target_number < 560 or (bool(entries) and not visual_quality_issues),
        "generated p500 asset images are photorealistic/live-action candidates and not vector-like/low-detail",
        kind="rubric",
    )

    request_text = requests.read_text(encoding="utf-8") if requests.exists() else ""
    request_sections = _request_sections_by_asset_id(request_text) if request_text else {}
    metadata_failures: list[str] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry)
        if not asset_id:
            continue
        fields = request_sections.get(asset_id)
        if not fields:
            metadata_failures.append(f"{asset_id}: missing request section")
            continue
        for key in ("tool", "asset_type", "execution_lane", "reference_count", "output"):
            if not _request_field_value(fields, key):
                metadata_failures.append(f"{asset_id}: missing {key}")
        request_tool = _request_field_value(fields, "tool")
        if request_tool and request_tool != "codex_builtin_image":
            metadata_failures.append(f"{asset_id}: tool {request_tool} must be codex_builtin_image")
        if not _request_field_value(fields, "review_status", "review.status"):
            metadata_failures.append(f"{asset_id}: missing review_status/review.status")
        request_lane = _request_field_value(fields, "execution_lane")
        request_reference_count = _parse_int_field(_request_field_value(fields, "reference_count"))
        if request_reference_count is not None:
            expected_request_lane = "standard" if request_reference_count > 0 else "bootstrap_builtin"
            if request_lane != expected_request_lane:
                metadata_failures.append(f"{asset_id}: execution_lane {request_lane or '(missing)'} mismatches reference_count {request_reference_count}")
    if metadata_failures:
        details["asset_request_metadata_failures"] = metadata_failures[:20]
    add_check(
        checks,
        "asset.request_metadata",
        target_number < 550 or (bool(entries) and not metadata_failures),
        "asset_generation_requests.md includes asset id/type/lane/reference count/review status/output metadata",
        kind="rubric",
    )
    add_check(
        checks,
        "asset.request_prompt_no_production_meta",
        target_number < 550 or (bool(request_text.strip()) and not _request_prompt_contains_production_meta(request_text)),
        "asset_generation_requests.md prompt bodies omit production-only metadata such as story title + scene ids",
        kind="rubric",
    )

    manifest_items: list[dict[str, Any]] = []
    for manifest_path in manifests:
        if not manifest_path.exists():
            continue
        _, manifest_data = load_structured_document(manifest_path)
        manifest_items.extend(_asset_manifest_items(manifest_data))
    details["generation_manifest_item_count"] = len(manifest_items)
    manifest_ids = {_asset_manifest_item_id(item) for item in manifest_items if _asset_manifest_item_id(item)}
    expected_ids = {_entry_asset_id(entry) for entry in entries if _entry_asset_id(entry)}
    missing_manifest_ids = sorted(expected_ids - manifest_ids)
    if missing_manifest_ids:
        details["missing_asset_manifest_ids"] = missing_manifest_ids[:20]
    add_check(
        checks,
        "asset.manifest_items",
        target_number < 550 or (bool(manifest_items) and not missing_manifest_ids),
        "asset generation manifests include each planned asset id",
        kind="rubric",
    )

    generated_files = _existing_media_files(run_dir / "assets", {".png", ".jpg", ".jpeg", ".webp"})
    details["generated_asset_file_count"] = len(generated_files)
    details["generation_manifest_count"] = sum(1 for path in manifests if path.exists())
    add_check(
        checks,
        "asset.generated_or_manifested",
        target_number < 550 or bool(generated_files) or any(path.exists() for path in manifests),
        "asset generation produced reusable image files or generation manifests",
        kind="rubric",
    )

    updates["eval.asset.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("asset", "asset_inventory.md / asset_plan.md / asset_generation_requests.md", checks, details=details), updates


def check_image(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}
    requests = run_dir / "image_generation_requests.md"
    expected_outputs = _node_output_paths(run_dir, field_path=["image_generation", "output"])
    missing_outputs = [path for path in expected_outputs if not path.exists()]

    add_check(checks, "image.generation_requests", requests.exists(), f"{requests.name} exists")
    request_text = requests.read_text(encoding="utf-8") if requests.exists() else ""
    request_sections = _request_sections_by_asset_id(request_text) if request_text else {}
    request_items = _request_sections_with_references(request_text) if request_text else []
    image_tool_failures: list[str] = []
    for selector, fields in request_sections.items():
        request_tool = _request_field_value(fields, "tool")
        if not request_tool:
            image_tool_failures.append(f"{selector}: missing tool")
        elif request_tool != "codex_builtin_image":
            image_tool_failures.append(f"{selector}: tool {request_tool} must be codex_builtin_image")
    if image_tool_failures:
        details["image_request_tool_failures"] = image_tool_failures[:20]
    add_check(
        checks,
        "image.request_tool_codex_builtin",
        not request_sections or not image_tool_failures,
        "image_generation_requests.md uses codex_builtin_image for every scene image request",
        kind="rubric",
    )
    request_references_by_selector = {
        str(item.get("selector") or "").strip(): list(item.get("references") or [])
        for item in request_items
        if str(item.get("selector") or "").strip()
    }
    request_lane_failures: list[str] = []
    for selector, fields in request_sections.items():
        request_lane = _request_field_value(fields, "execution_lane")
        reference_count = _parse_int_field(_request_field_value(fields, "reference_count"))
        if not request_lane:
            request_lane_failures.append(f"{selector}: missing execution_lane")
        if reference_count is None:
            request_lane_failures.append(f"{selector}: missing reference_count")
            continue
        expected_lane = "standard" if reference_count > 0 else "bootstrap_builtin"
        if request_lane != expected_lane:
            request_lane_failures.append(
                f"{selector}: execution_lane {request_lane or '(missing)'} mismatches reference_count {reference_count}"
            )
        parsed_references = request_references_by_selector.get(selector)
        if parsed_references is not None and reference_count != len(parsed_references):
            request_lane_failures.append(
                f"{selector}: reference_count {reference_count} mismatches references[] count {len(parsed_references)}"
            )
    if request_lane_failures:
        details["image_request_lane_failures"] = request_lane_failures[:20]
    add_check(
        checks,
        "image.request_lane_consistency",
        not request_sections or not request_lane_failures,
        "image_generation_requests.md keeps reference_count=0 on bootstrap_builtin and reference_count>0 on standard",
        kind="rubric",
    )
    append_grounding_checks(checks, run_dir=run_dir, stage="scene_implementation")
    add_check(checks, "image.expected_outputs", bool(expected_outputs), "manifest declares image_generation.output paths", kind="rubric")
    add_check(
        checks,
        "image.output_files",
        bool(expected_outputs) and not missing_outputs,
        f"all declared image outputs exist (missing {len(missing_outputs)} of {len(expected_outputs)})",
        kind="rubric",
    )
    details["declared_image_outputs"] = len(expected_outputs)
    if missing_outputs:
        details["missing_image_outputs"] = [str(path.relative_to(run_dir)) if path.is_relative_to(run_dir) else str(path) for path in missing_outputs[:20]]

    visual_quality_stats, reference_quality_stats, regeneration_plan, uninspected_outputs = _scene_image_visual_quality_stats(
        run_dir,
        request_items,
        expected_outputs,
    )
    scene_output_relpaths = [
        str(path.relative_to(run_dir))
        for path in expected_outputs
        if path.exists() and path.is_file() and path.suffix.lower() in VECTOR_GATE_IMAGE_SUFFIXES
    ]
    provenance = _image_generation_provenance_by_destination(run_dir)
    scene_provenance_failures = _image_generation_provenance_failures(run_dir, scene_output_relpaths, provenance=provenance)
    if scene_provenance_failures:
        details["image_generation_provenance_failures"] = scene_provenance_failures[:20]
    visual_quality_issues = [
        f"{stat.get('selector', '<missing_selector>')}: {stat.get('path', '(unknown)')} - {stat.get('issue')}"
        for stat in visual_quality_stats
        if stat.get("issue")
    ]
    reference_quality_issues = [
        f"{stat.get('selector', '<missing_selector>')}: {stat.get('reference') or stat.get('path', '(unknown)')} - {stat.get('issue')}"
        for stat in reference_quality_stats
        if stat.get("issue")
    ]
    if visual_quality_stats:
        details["image_visual_quality_samples"] = visual_quality_stats[:20]
    if reference_quality_stats:
        details["image_reference_quality_samples"] = reference_quality_stats[:20]
    if visual_quality_issues:
        details["image_visual_quality_issues"] = visual_quality_issues[:20]
    if reference_quality_issues:
        details["image_reference_quality_issues"] = reference_quality_issues[:20]
    if regeneration_plan:
        details["image_regeneration_plan"] = regeneration_plan[:20]
    if uninspected_outputs:
        details["uninspected_image_outputs"] = uninspected_outputs[:20]
    add_check(
        checks,
        "image.visual_outputs_inspected",
        not uninspected_outputs and len(visual_quality_stats) == len([path for path in expected_outputs if path.suffix.lower() in VECTOR_GATE_IMAGE_SUFFIXES and path.exists()]),
        "every manifest-declared scene image output is inspected by the visual quality gate",
        kind="rubric",
    )
    add_check(
        checks,
        "image.generation_provenance_app_server",
        bool(expected_outputs) and not scene_provenance_failures,
        "generated p600 scene images have Codex app-server provenance and are not local raster fallbacks",
        kind="rubric",
    )
    add_check(
        checks,
        "image.visual_not_vector_like",
        bool(expected_outputs) and not uninspected_outputs and not visual_quality_issues,
        "generated p600 scene images are photorealistic/live-action candidates and not vector-like/low-detail",
        kind="rubric",
    )
    add_check(
        checks,
        "image.references_not_vector_like",
        not reference_quality_issues,
        "p600 reference images are photorealistic/live-action candidates; vector-like references route regeneration back to p500",
        kind="rubric",
    )

    updates["eval.image.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("image", "image_generation_requests.md / assets/scenes/**", checks, details=details), updates


def check_narration(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    updates: dict[str, str] = {}
    review = run_dir / "narration_text_review.md"
    expected_outputs = _node_output_paths(run_dir, field_path=["audio", "narration", "output"])
    missing_outputs = [path for path in expected_outputs if not path.exists()]
    duration_status = state.get("review.duration_fit.status", "").strip().lower()

    add_check(checks, "narration.text_review", review.exists(), f"{review.name} exists")
    append_grounding_checks(checks, run_dir=run_dir, stage="narration")
    add_check(checks, "narration.expected_outputs", bool(expected_outputs), "manifest declares audio.narration.output paths", kind="rubric")
    add_check(
        checks,
        "narration.output_files",
        bool(expected_outputs) and not missing_outputs,
        f"all declared narration audio outputs exist (missing {len(missing_outputs)} of {len(expected_outputs)})",
        kind="rubric",
    )
    add_check(
        checks,
        "narration.duration_fit",
        duration_status in {"passed", "skipped"},
        f"duration-fit gate is passed/skipped before video generation (got {duration_status or '(unset)'})",
        kind="rubric",
    )
    details["declared_audio_outputs"] = len(expected_outputs)
    if missing_outputs:
        details["missing_audio_outputs"] = [str(path.relative_to(run_dir)) if path.is_relative_to(run_dir) else str(path) for path in missing_outputs[:20]]

    updates["eval.narration.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("narration", "narration_text_review.md / assets/audio/**", checks, details=details), updates


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
        audio_paths = [
            Path(line.strip())
            for line in narration_list.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        resolved = [(path if path.is_absolute() else run_dir / path) for path in audio_paths]
        add_check(checks, "video.narration_list", all(path.exists() for path in resolved), "all narration files in video_narration_list.txt exist", kind="rubric")

    video_duration = _probe_duration(video_path)
    if video_duration is not None:
        add_check(checks, "video.duration", video_duration > 0.0, f"video duration is positive ({video_duration:.2f}s)", kind="rubric")


def check_video_single(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    append_grounding_checks(checks, run_dir=run_dir, stage="video")
    _video_checks(checks, video_path=run_dir / "video.mp4", state=state, run_dir=run_dir)
    return make_stage("video", "video.mp4", checks), {}


def check_video_scene_series(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    checks: list[dict[str, Any]] = []
    add_check(checks, "video.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    video_paths = [scene_dir / "video.mp4" for scene_dir in scene_dirs]
    add_check(checks, "video.scene_files", all(path.exists() for path in video_paths), "each scene has video.mp4")
    append_grounding_checks(checks, run_dir=run_dir, stage="video")
    return make_stage("video", "scenes/*/video.mp4", checks, details={"scene_count": len(scene_dirs)}), {}


def _required_orchestration_buckets(stage_target: str) -> list[str]:
    slot_number = _slot_number(stage_target, default=930)
    if slot_number < 100:
        return []
    terminal_bucket = min(900, max(100, (slot_number // 100) * 100))
    return [f"p{bucket}" for bucket in range(100, terminal_bucket + 1, 100)]


def _progress_has_event(progress_text: str, *, bucket: str, event: str) -> bool:
    for raw_line in progress_text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[1] == bucket and cells[3] == event:
            return True
    return False


TERMINAL_SLOT_STATUSES = {"done", "skipped", "awaiting_approval"}


def _slot_number_from_code(slot: Any) -> int | None:
    if not isinstance(slot, str):
        return None
    match = re.fullmatch(r"p(\d{3})", slot.strip())
    if not match:
        return None
    return int(match.group(1))


def _is_slot_in_bucket(slot: Any, bucket: str) -> bool:
    slot_number = _slot_number_from_code(slot)
    bucket_number = _slot_number_from_code(bucket)
    if slot_number is None or bucket_number is None:
        return False
    return bucket_number <= slot_number <= bucket_number + 99


def _relative_required_artifact_path(run_dir: Path, value: Any) -> tuple[Path | None, str]:
    if not isinstance(value, str) or not value.strip():
        return None, "<missing>"
    raw_path = Path(value.strip())
    resolved = raw_path if raw_path.is_absolute() else run_dir / raw_path
    try:
        relative = resolved.resolve().relative_to(run_dir.resolve())
    except ValueError:
        return None, value.strip()
    return run_dir / relative, str(relative)


def _supervisor_result_issues(path: Path, *, run_dir: Path, bucket: str, state: dict[str, str]) -> list[str]:
    if not path.exists():
        return [f"{bucket}:result_missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [f"{bucket}:result_invalid_json"]
    issues: list[str] = []
    if payload.get("bucket") != bucket:
        issues.append(f"{bucket}:result_bucket_mismatch")
    if payload.get("status") != "done":
        issues.append(f"{bucket}:result_status_not_done")
    completed_slots = payload.get("completed_slots")
    if not isinstance(completed_slots, list) or not completed_slots:
        issues.append(f"{bucket}:completed_slots_missing")
    elif not all(_is_slot_in_bucket(slot, bucket) for slot in completed_slots):
        issues.append(f"{bucket}:completed_slots_outside_bucket")
    else:
        non_terminal_slots = [
            f"{slot}:{state.get(f'slot.{slot}.status') or '(unset)'}"
            for slot in completed_slots
            if state.get(f"slot.{slot}.status", "").strip().lower() not in TERMINAL_SLOT_STATUSES
        ]
        if non_terminal_slots:
            issues.append(f"{bucket}:completed_slots_not_terminal")

    required_artifacts = payload.get("required_artifacts")
    if not isinstance(required_artifacts, list):
        issues.append(f"{bucket}:required_artifacts_missing")
    elif not required_artifacts:
        issues.append(f"{bucket}:required_artifacts_empty")
    else:
        for item in required_artifacts:
            if not isinstance(item, dict):
                issues.append(f"{bucket}:required_artifact_invalid")
                continue
            required_path, display_path = _relative_required_artifact_path(run_dir, item.get("path"))
            if required_path is None:
                issues.append(f"{bucket}:required_artifact_invalid_path:{display_path}")
                continue
            if item.get("exists") is False or not required_path.exists():
                issues.append(f"{bucket}:required_artifact_not_found:{display_path}")

    state_keys = payload.get("state_keys")
    if not isinstance(state_keys, dict):
        issues.append(f"{bucket}:state_keys_missing")
    elif not state_keys:
        issues.append(f"{bucket}:state_keys_empty")
    else:
        for key, value in state_keys.items():
            if not isinstance(key, str) or not key.strip():
                issues.append(f"{bucket}:state_key_invalid")
                continue
            actual = state.get(key)
            expected = str(value)
            if actual != expected:
                issues.append(f"{bucket}:state_key_mismatch:{key}")
    return issues


def check_orchestration(run_dir: Path, *, stage_target: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    buckets = _required_orchestration_buckets(stage_target)
    state = parse_state_file(run_dir / "state.txt")
    progress_path = run_dir / "logs" / "orchestration" / "l2_supervisor_progress.md"
    add_check(checks, "orchestration.progress_memo", progress_path.exists(), f"{progress_path.relative_to(run_dir)} exists")
    progress_text = progress_path.read_text(encoding="utf-8") if progress_path.exists() else ""

    missing_invocations = [bucket for bucket in buckets if not _progress_has_event(progress_text, bucket=bucket, event="invoked")]
    add_check(
        checks,
        "orchestration.l2_invoked",
        not missing_invocations,
        "L1 recorded invoked events for every required L2 P-Bucket Supervisor"
        + (f" (missing: {', '.join(missing_invocations)})" if missing_invocations else ""),
        kind="rubric",
    )

    missing_returned_state: list[str] = []
    for bucket in buckets:
        prefix = f"orchestration.{bucket}.supervisor"
        call_status = state.get(f"{prefix}.call_status")
        supervisor_status = state.get(f"{prefix}.status")
        finished_at = state.get(f"{prefix}.finished_at")
        if call_status != "returned" or supervisor_status != "done" or not finished_at:
            missing_returned_state.append(
                f"{bucket}:call_status={call_status or '(unset)'},status={supervisor_status or '(unset)'},finished_at={finished_at or '(unset)'}"
            )
    add_check(
        checks,
        "orchestration.state_terminal",
        not missing_returned_state,
        "state.txt records every required L2 P-Bucket Supervisor as returned and done"
        + (f" (missing/non-terminal: {', '.join(missing_returned_state)})" if missing_returned_state else ""),
        kind="rubric",
    )

    result_issues: list[str] = []
    for bucket in buckets:
        result_issues.extend(
            _supervisor_result_issues(
                run_dir / "logs" / "orchestration" / f"{bucket}.supervisor_result.json",
                run_dir=run_dir,
                bucket=bucket,
                state=state,
            )
        )
    add_check(
        checks,
        "orchestration.supervisor_results",
        not result_issues,
        "required L2 supervisor result JSON files exist and report status=done"
        + (f" (issues: {', '.join(result_issues[:8])})" if result_issues else ""),
        kind="rubric",
    )

    details = {"required_buckets": buckets}
    updates["eval.orchestration.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("orchestration", "logs/orchestration/l2_supervisor_progress.md / logs/orchestration/pXXX.supervisor_result.json", checks, details=details), updates


STAGE_TARGETS = {
    "p130": ["research"],
    "p230": ["research", "story"],
    "p330": ["research", "story", "visual_value"],
    "p450": ["research", "story", "visual_value", "script", "manifest"],
    "p570": ["research", "story", "visual_value", "script", "manifest", "asset"],
    "p680": ["research", "story", "visual_value", "script", "manifest", "asset", "image"],
    "p750": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"],
    "p850": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"],
    "p930": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"],
}
for _slot in range(110, 931, 10):
    _bucket = (_slot // 100) * 100
    if _slot < 200:
        _stages = ["research"]
    elif _slot < 300:
        _stages = ["research", "story"]
    elif _slot < 400:
        _stages = ["research", "story", "visual_value"]
    elif _slot < 500:
        _stages = ["research", "story", "visual_value", "script", "manifest"]
    elif _slot < 600:
        _stages = ["research", "story", "visual_value", "script", "manifest", "asset"]
    elif _slot < 700:
        _stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image"]
    elif _slot < 900:
        _stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"]
    else:
        _stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"]
    STAGE_TARGETS.setdefault(f"p{_slot}", _stages)

STAGE_TARGET_ALIASES = {
    "100": "p130",
    "p100": "p130",
    "research": "p130",
    "200": "p230",
    "p200": "p230",
    "story": "p230",
    "300": "p330",
    "p300": "p330",
    "visual": "p330",
    "visual_value": "p330",
    "400": "p450",
    "p400": "p450",
    "450": "p450",
    "script": "p450",
    "500": "p570",
    "p500": "p570",
    "asset": "p570",
    "600": "p680",
    "p600": "p680",
    "image": "p680",
    "image_generation": "p680",
    "scene_implementation": "p680",
    "700": "p750",
    "p700": "p750",
    "narration": "p750",
    "800": "p850",
    "p800": "p850",
    "video_generation": "p850",
    "900": "p930",
    "p900": "p930",
    "render": "p930",
    "video": "p930",
    "done": "p930",
}


def normalize_stage_target(value: str | None) -> str:
    if not value:
        return "p930"
    normalized = value.strip().lower()
    if normalized.isdigit():
        normalized = f"p{normalized}"
    if normalized in STAGE_TARGET_ALIASES:
        return STAGE_TARGET_ALIASES[normalized]
    if normalized in STAGE_TARGETS:
        return normalized
    raise ValueError(f"Unsupported stage target: {value}")


def build_report(run_dir: Path, flow: str, profile: str, stage_target: str = "p900") -> tuple[dict[str, Any], dict[str, str]]:
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_snapshot(
            state_path,
            {
                "topic": run_dir.name,
                "status": "INIT",
                "runtime.stage": "verify",
            },
        )

    stage_updates: dict[str, str] = {}
    stages: list[dict[str, Any]] = []
    target = normalize_stage_target(stage_target)
    enabled_stages = set(STAGE_TARGETS[target])

    if flow != "scene-series":
        orchestration_stage, updates = check_orchestration(run_dir, stage_target=target)
        stages.append(orchestration_stage)
        stage_updates.update(updates)

    if "research" in enabled_stages:
        research_stage, updates = check_research(run_dir, profile)
        stages.append(research_stage)
        stage_updates.update(updates)

    if "story" in enabled_stages:
        story_stage, updates = check_story(run_dir, profile)
        stages.append(story_stage)
        stage_updates.update(updates)

    if "visual_value" in enabled_stages:
        target_slot_number = int(target.removeprefix("p"))
        forbid_p300_production = 300 <= target_slot_number < 400
        visual_value_stage, updates = check_visual_value(
            run_dir,
            profile,
            forbid_production_artifacts=forbid_p300_production,
        )
        stages.append(visual_value_stage)
        stage_updates.update(updates)

    if "script" in enabled_stages:
        if flow == "scene-series":
            script_stage, updates = check_script_scene_series(run_dir, profile)
        else:
            script_stage, updates = check_script_single(run_dir, profile)
        stages.append(script_stage)
        stage_updates.update(updates)

    if "manifest" in enabled_stages:
        if flow == "scene-series":
            manifest_stage, updates = check_manifest_scene_series(run_dir, profile)
        else:
            manifest_stage, updates = shared_check_manifest_single(run_dir, profile, flow)
        stages.append(manifest_stage)
        stage_updates.update(updates)

    if "asset" in enabled_stages:
        asset_stage, updates = check_asset(run_dir, target_slot=target)
        stages.append(asset_stage)
        stage_updates.update(updates)

    if "image" in enabled_stages:
        image_stage, updates = check_image(run_dir)
        stages.append(image_stage)
        stage_updates.update(updates)

    if "narration" in enabled_stages:
        narration_stage, updates = check_narration(run_dir)
        stages.append(narration_stage)
        stage_updates.update(updates)

    if "video" in enabled_stages:
        if flow == "scene-series":
            video_stage, updates = check_video_scene_series(run_dir)
        else:
            video_stage, updates = check_video_single(run_dir)
        stages.append(video_stage)
        stage_updates.update(updates)

    overall_score = round(sum(stage["score"] for stage in stages) / len(stages), 4) if stages else 0.0
    overall_passed = all(stage["passed"] for stage in stages)
    report = {
        "generated_at": now_iso(),
        "run_dir": str(run_dir.resolve()),
        "flow": flow,
        "profile": profile,
        "stage_target": target,
        "overall": {
            "passed": overall_passed,
            "score": overall_score,
            "failed_stages": [stage["stage"] for stage in stages if not stage["passed"]],
        },
        "stages": {stage["stage"]: stage for stage in stages},
    }
    return report, stage_updates


def render_run_report(report: dict[str, Any], state: dict[str, str], run_dir: Path) -> str:
    overall = report["overall"]
    lines = [
        "# Run Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Flow: `{report['flow']}`",
        f"- Profile: `{report['profile']}`",
        f"- Stage target: `{report.get('stage_target', 'p900')}`",
        f"- Overall: `{'PASS' if overall['passed'] else 'FAIL'}` ({overall['score']:.2%})",
        f"- Run dir: `{run_dir}`",
        f"- Run status: `{run_dir / 'run_status.json'}`",
        f"- Eval report: `{run_dir / 'eval_report.json'}`",
        "",
        "## Stage Summary",
        "",
        "| Stage | Result | Score |",
        "| --- | --- | --- |",
    ]

    for stage_name in ["orchestration", "research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"]:
        stage = report["stages"].get(stage_name)
        if not stage:
            continue
        result = "PASS" if stage["passed"] else "FAIL"
        lines.append(f"| {stage_name} | {result} | {stage['score']:.2%} |")

    pending = sync_run_status(run_dir)
    lines += [
        "",
        "## Findings",
        "",
    ]

    for stage_name in ["orchestration", "research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"]:
        stage = report["stages"].get(stage_name)
        if not stage:
            continue
        lines.append(f"### {stage_name}")
        for check in stage["checks"]:
            mark = "PASS" if check["passed"] else "FAIL"
            lines.append(f"- [{mark}] `{check['id']}`: {check['message']}")
        lines.append("")

    pending_gates = state.get("gate.hybridization_review") or state.get("gate.video_review")
    if pending_gates:
        lines += [
            "## Review Gates",
            "",
            f"- See `{pending}` for machine-readable pending gate state.",
            "",
        ]

    if overall["failed_stages"]:
        lines += [
            "## Next Actions",
            "",
        ]
        for stage_name in overall["failed_stages"]:
            lines.append(
                f"- Fix `{stage_name}` findings, then rerun `python scripts/verify-pipeline.py --run-dir {run_dir} --flow {report['flow']} --profile {report['profile']} --stage-target {report.get('stage_target', 'p900')}`."
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ToC run artifacts and write eval/report outputs.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>/")
    parser.add_argument("--flow", required=True, choices=["toc-run", "scene-series", "immersive"])
    parser.add_argument("--profile", default="standard", choices=["fast", "standard"])
    parser.add_argument("--stage-target", "--p-slot", default="p900", help="Verify artifacts only through this p-slot/stage target (for example p300).")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    try:
        stage_target = normalize_stage_target(args.stage_target)
    except ValueError as exc:
        parser.error(str(exc))
    report, updates = build_report(run_dir, args.flow, args.profile, stage_target)

    report_path = eval_report_path(run_dir)
    write_json(report_path, report)

    updates["artifact.eval_report"] = str(report_path.resolve())
    state = append_state_snapshot(run_dir / "state.txt", updates)

    report_md = render_run_report(report, state, run_dir)
    run_report = run_report_path(run_dir)
    run_report.write_text(report_md + "\n", encoding="utf-8")
    sync_run_status(run_dir)

    print(run_report)
    print(report_path)
    return 0 if report["overall"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
