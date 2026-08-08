"""Pipeline-specific stage evaluation policy.

This module preserves the p-slot gate schema independently from canonical stage
reviews. Callers inject semantic-review and duration-probe seams where the
legacy script exposes module-level monkeypatch points.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from toc.harness import load_structured_document, parse_state_file
from toc.story_duration import MINIMUM_EFFECTIVE_RATIO, audit_duration, normalize_target_duration

from .common import (
    STORY_REQUIRED_SCENE_FIELDS,
    _append_grounding_checks as append_grounding_checks,
    add_check,
    as_list,
    has_todo,
    nested_get,
    non_empty,
    scene_time_of_day_contract_missing,
)

SemanticReviewAppender = Callable[..., None]
DurationProbe = Callable[[Path], float | None]

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

    missing_time_of_day = scene_time_of_day_contract_missing(data, artifact="story")
    if missing_time_of_day is not None:
        if missing_time_of_day:
            details["missing_time_of_day_scene_ids"] = ",".join(missing_time_of_day[:20])
        add_check(
            checks,
            "story.scene_time_of_day",
            not missing_time_of_day,
            "all newly authored story scenes include non-empty time_of_day"
            + (f" (missing: {', '.join(missing_time_of_day[:8])})" if missing_time_of_day else ""),
            kind="rubric",
        )

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


def check_script_single(
    run_dir: Path,
    profile: str,
    *,
    append_semantic_review: SemanticReviewAppender,
    target_slot: str = "p450",
) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "script.md"
    checks: list[dict[str, Any]] = []
    updates: dict[str, str] = {}
    target_number = _slot_number(target_slot, default=450)

    add_check(checks, "script.file_exists", path.exists(), f"{path.name} exists")
    if not path.exists():
        return make_stage("script", path.name, checks), updates

    text, data = load_structured_document(path)
    append_grounding_checks(checks, run_dir=run_dir, stage="script")
    _script_text_quality_checks(checks, text, data, profile)
    missing_time_of_day = scene_time_of_day_contract_missing(data, artifact="script")
    if missing_time_of_day is not None:
        add_check(
            checks,
            "script.scene_time_of_day",
            not missing_time_of_day,
            "all newly authored script scenes include non-empty time_of_day"
            + (f" (missing: {', '.join(missing_time_of_day[:8])})" if missing_time_of_day else ""),
            kind="rubric",
        )
    details: dict[str, Any] = {}
    require_scene_semantic = target_number in {410, 420} or target_number >= 500
    append_semantic_review(checks, details, run_dir=run_dir, stage="scene_set", required=require_scene_semantic)
    append_semantic_review(
        checks,
        details,
        run_dir=run_dir,
        stage="scene_detail",
        required=require_scene_semantic,
        allow_localized_partial=True,
        require_generation_receipt=target_number >= 680,
    )
    append_semantic_review(
        checks,
        details,
        run_dir=run_dir,
        stage="cut_blueprint",
        required=target_number == 420 or target_number >= 500,
        allow_localized_partial=True,
        require_generation_receipt=target_number >= 680,
    )
    updates["eval.script.score"] = f"{score_from_checks(checks):.4f}"
    return make_stage("script", path.name, checks, details=details), updates


def check_script_scene_series(
    run_dir: Path,
    profile: str,
    *,
    append_semantic_review: SemanticReviewAppender,
    target_slot: str = "p450",
) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    target_number = _slot_number(target_slot, default=450)
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

    details: dict[str, Any] = {"scene_count": len(scene_dirs)}
    require_scene_semantic = target_number in {410, 420} or target_number >= 500
    append_semantic_review(checks, details, run_dir=run_dir, stage="scene_set", required=require_scene_semantic)
    append_semantic_review(
        checks,
        details,
        run_dir=run_dir,
        stage="scene_detail",
        required=require_scene_semantic,
        allow_localized_partial=True,
        require_generation_receipt=target_number >= 680,
    )
    append_semantic_review(
        checks,
        details,
        run_dir=run_dir,
        stage="cut_blueprint",
        required=target_number == 420 or target_number >= 500,
        allow_localized_partial=True,
        require_generation_receipt=target_number >= 680,
    )
    updates = {"eval.script.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("script", "scenes/*/script.md", checks, details=details), updates


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


def _slot_number(value: str | None, *, default: int) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        return default
    try:
        return int(match.group(1))
    except Exception:
        return default


def append_video_checks(
    checks: list[dict[str, Any]],
    *,
    video_path: Path,
    state: dict[str, str],
    run_dir: Path,
    duration_probe: DurationProbe,
) -> None:
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

    video_duration = duration_probe(video_path)
    if video_duration is not None:
        add_check(checks, "video.duration", video_duration > 0.0, f"video duration is positive ({video_duration:.2f}s)", kind="rubric")

    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _manifest_text, manifest = load_structured_document(manifest_path)
    else:
        manifest = {}
    raw_target_seconds = nested_get(manifest, ["video_metadata", "target_duration_seconds"])
    try:
        target_seconds = (
            normalize_target_duration(raw_target_seconds)
            if raw_target_seconds is not None
            else None
        )
    except ValueError:
        target_seconds = None
    add_check(
        checks,
        "video.target_duration",
        target_seconds is not None,
        "final video verification requires a valid manifest target_duration_seconds (300-1200)",
        kind="rubric",
    )
    if video_duration is not None:
        try:
            duration_audit = (
                audit_duration(
                    target_seconds=target_seconds,
                    actual_seconds=video_duration,
                    measurement_layer="final_media_ffprobe",
                )
                if target_seconds is not None
                else None
            )
        except ValueError:
            duration_audit = None
        add_check(
            checks,
            "video.duration_fit",
            duration_audit is not None and duration_audit.passed,
            f"final media ffprobe duration reaches at least {MINIMUM_EFFECTIVE_RATIO:.0%} of manifest target without adding audio/render layers"
            + (
                f" ({duration_audit.actual_seconds:g}/{duration_audit.target_seconds}s)"
                if duration_audit is not None
                else " (manifest target is missing/invalid)"
            ),
            kind="rubric",
        )


def check_video_single(
    run_dir: Path,
    *,
    append_semantic_review: SemanticReviewAppender,
    duration_probe: DurationProbe,
    target_slot: str = "p930",
) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    target_number = _slot_number(target_slot, default=930)
    append_grounding_checks(checks, run_dir=run_dir, stage="video")
    append_video_checks(
        checks,
        video_path=run_dir / "video.mp4",
        state=state,
        run_dir=run_dir,
        duration_probe=duration_probe,
    )
    append_semantic_review(
        checks,
        details,
        run_dir=run_dir,
        stage="video_motion",
        required=target_number >= 820,
        check_id="video.motion_semantic_review_subagent_passed",
    )
    return make_stage("video", "video.mp4", checks, details=details), {}


def check_video_scene_series(
    run_dir: Path,
    *,
    append_semantic_review: SemanticReviewAppender,
    target_slot: str = "p930",
) -> tuple[dict[str, Any], dict[str, str]]:
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {"scene_count": len(scene_dirs)}
    target_number = _slot_number(target_slot, default=930)
    add_check(checks, "video.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    video_paths = [scene_dir / "video.mp4" for scene_dir in scene_dirs]
    add_check(checks, "video.scene_files", all(path.exists() for path in video_paths), "each scene has video.mp4")
    append_grounding_checks(checks, run_dir=run_dir, stage="video")
    append_semantic_review(checks, details, run_dir=run_dir, stage="video_motion", required=target_number >= 820)
    return make_stage("video", "scenes/*/video.mp4", checks, details=details), {}

