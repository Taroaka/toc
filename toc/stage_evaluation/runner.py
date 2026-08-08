"""Canonical evaluator dispatch, report rendering, and state append."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from toc.harness import append_state_snapshot

from .common import detect_flow
from .manifest import check_manifest_scene_series, check_manifest_single
from .research_story import check_research, check_story, check_visual_value
from .script import check_script_scene_series, check_script_single
from .video import check_video_scene_series, check_video_single

def evaluate_stage(run_dir: Path, *, stage: str, profile: str, flow: str | None = None) -> tuple[dict[str, Any], dict[str, str], str]:
    resolved_flow = flow or detect_flow(run_dir)
    if stage == "research":
        result, updates = check_research(run_dir, profile)
    elif stage == "story":
        result, updates = check_story(run_dir, profile)
    elif stage == "visual_value":
        result, updates = check_visual_value(run_dir, profile)
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
        "story": "artifact.story_review",
        "script": "artifact.script_review",
        "manifest": "artifact.manifest_review",
        "video": "artifact.video_review_report",
    }
    state_updates = dict(updates)
    state_updates[f"eval.{stage}.status"] = "approved" if stage_result["passed"] else "changes_requested"
    if stage == "story":
        semantic_checks = {
            str(check.get("id") or ""): bool(check.get("passed"))
            for check in stage_result.get("checks", [])
            if isinstance(check, dict)
        }
        semantic_approved = (
            semantic_checks.get("story.semantic_review") is True
            and semantic_checks.get("story.semantic_review_current") is True
        )
        if semantic_approved and stage_result["passed"]:
            state_updates["review.story.status"] = "approved"
        elif stage_result["passed"]:
            state_updates["review.story.status"] = "deterministic_passed"
        else:
            state_updates["review.story.status"] = "changes_requested"
    state_updates[f"eval.{stage}.findings"] = str(finding_count)
    state_updates[f"eval.{stage}.reason_keys"] = ",".join(stage_result.get("reason_keys") or [])
    state_updates[f"eval.{stage}.warning_keys"] = ",".join(stage_result.get("warning_keys") or [])
    state_updates[f"eval.{stage}.overall_rubric"] = f"{float(stage_result.get('overall_rubric', 0.0)):.4f}"
    for key, value in dict(stage_result.get("rubric_scores") or {}).items():
        state_updates[f"eval.{stage}.rubric.{key}"] = f"{float(value):.4f}"
    state_updates[artifact_key_map[stage]] = str(report_path.resolve())
    append_state_snapshot(state_path, state_updates)


