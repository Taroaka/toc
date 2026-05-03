#!/usr/bin/env python3
"""Verify ToC pipeline artifacts and generate machine/human-readable reports."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


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

    details["sources"] = len(sources)
    details["event_count"] = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    details["source_passage_count"] = len(source_passages) or len(legacy_passages)
    details["fact_count"] = len(as_list(facts))

    add_check(checks, "research.structured", bool(data), "research.md contains structured YAML output")
    add_check(checks, "research.sources", len(sources) >= 12, f"sources >= 12 (got {len(sources)})", kind="rubric")
    story_materials_ok = bool(story_materials) or non_empty(synopsis)
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
        non_empty(canonical_story_dump) or non_empty(synopsis),
        "canonical story dump or legacy synopsis is present",
        kind="rubric",
    )
    event_count = len(as_list(chronological_events)) or len(as_list(beat_sheet))
    add_check(
        checks,
        "research.chronological_events",
        event_count >= 20,
        f"chronological events or legacy beats >= 20 (got {event_count})",
        kind="rubric",
    )
    passage_count = len(source_passages) or len(legacy_passages)
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
        len(as_list(facts)) >= 10,
        f"facts >= 10 (got {len(as_list(facts))})",
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
    add_check(checks, "story.scenes", len(scenes) >= 20, f"story includes at least 20 scenes (got {len(scenes)})", kind="rubric")

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


def build_report(run_dir: Path, flow: str, profile: str) -> tuple[dict[str, Any], dict[str, str]]:
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

    research_stage, updates = check_research(run_dir, profile)
    stages.append(research_stage)
    stage_updates.update(updates)

    story_stage, updates = check_story(run_dir, profile)
    stages.append(story_stage)
    stage_updates.update(updates)

    if flow == "scene-series":
        script_stage, updates = check_script_scene_series(run_dir, profile)
        manifest_stage, updates2 = check_manifest_scene_series(run_dir, profile)
        video_stage, updates3 = check_video_scene_series(run_dir)
        stage_updates.update(updates)
        stage_updates.update(updates2)
        stage_updates.update(updates3)
    else:
        script_stage, updates = check_script_single(run_dir, profile)
        manifest_stage, updates2 = check_manifest_single(run_dir, profile, flow)
        video_stage, updates3 = check_video_single(run_dir)
        stage_updates.update(updates)
        stage_updates.update(updates2)
        stage_updates.update(updates3)

    stages.extend([script_stage, manifest_stage, video_stage])

    overall_score = round(sum(stage["score"] for stage in stages) / len(stages), 4) if stages else 0.0
    overall_passed = all(stage["passed"] for stage in stages)
    report = {
        "generated_at": now_iso(),
        "run_dir": str(run_dir.resolve()),
        "flow": flow,
        "profile": profile,
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

    for stage_name in ["research", "story", "script", "manifest", "video"]:
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

    for stage_name in ["research", "story", "script", "manifest", "video"]:
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
            lines.append(f"- Fix `{stage_name}` findings, then rerun `python scripts/verify-pipeline.py --run-dir {run_dir} --flow {report['flow']} --profile {report['profile']}`.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ToC run artifacts and write eval/report outputs.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>/")
    parser.add_argument("--flow", required=True, choices=["toc-run", "scene-series", "immersive"])
    parser.add_argument("--profile", default="standard", choices=["fast", "standard"])
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    report, updates = build_report(run_dir, args.flow, args.profile)

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
