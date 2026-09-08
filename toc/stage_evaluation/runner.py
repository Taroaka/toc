"""Dispatch structural stage checks without creating review artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import detect_flow
from .manifest import check_manifest_scene_series, check_manifest_single
from .pipeline import (
    check_research,
    check_story,
    check_visual_value,
    check_script_scene_series,
    check_script_single,
    check_video_scene_series,
    check_video_single,
)


def evaluate_stage(
    run_dir: Path,
    *,
    stage: str,
    profile: str = "standard",
    flow: str | None = None,
) -> tuple[dict[str, Any], dict[str, str], str]:
    """Run a named structural check for compatibility with legacy callers."""

    resolved_flow = flow or detect_flow(run_dir)
    if stage == "research":
        result, updates = check_research(run_dir, profile)
    elif stage == "story":
        result, updates = check_story(run_dir, profile)
    elif stage == "visual_value":
        result, updates = check_visual_value(run_dir, profile)
    elif stage == "script":
        result, updates = (
            check_script_scene_series(run_dir, profile)
            if resolved_flow == "scene-series"
            else check_script_single(run_dir, profile)
        )
    elif stage == "manifest":
        result, updates = (
            check_manifest_scene_series(run_dir, profile)
            if resolved_flow == "scene-series"
            else check_manifest_single(run_dir, profile, resolved_flow)
        )
    elif stage == "video":
        result, updates = (
            check_video_scene_series(run_dir)
            if resolved_flow == "scene-series"
            else check_video_single(run_dir)
        )
    else:
        raise ValueError(f"Unsupported stage: {stage}")
    return result, updates, resolved_flow


__all__ = ["evaluate_stage"]
