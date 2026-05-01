"""Prompt builders for audio-duration fit review artifacts."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from toc.grounding import detect_flow


def review_prompt_relpath(kind: str) -> Path:
    normalized = kind.strip().lower()
    if normalized not in {"scene", "narration"}:
        raise ValueError(f"Unsupported duration review kind: {kind}")
    return Path("logs") / "review" / f"duration_{normalized}.subagent_prompt.md"


def review_prompt_path(run_dir: Path, kind: str) -> Path:
    return run_dir / review_prompt_relpath(kind)


def write_review_prompt(*, run_dir: Path, kind: str, prompt: str) -> Path:
    path = review_prompt_path(run_dir, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{prompt}\n", encoding="utf-8")
    return path


def build_duration_scene_review_prompt(
    *,
    run_dir: Path,
    minimum_seconds: int,
    actual_seconds: int,
    flow: str | None = None,
) -> str:
    resolved_run_dir = run_dir.resolve()
    resolved_flow = flow or detect_flow(resolved_run_dir)
    story_path = resolved_run_dir / "story.md"
    script_path = resolved_run_dir / "script.md"
    manifest_path = resolved_run_dir / "video_manifest.md"
    index_path = resolved_run_dir / "p000_index.md"

    lines = [
        "You are a contextless, read-only subagent for ToC scene-duration expansion review.",
        "",
        f"Review run dir `{resolved_run_dir}`.",
        f"Flow: `{resolved_flow}`.",
        f"Actual runtime after audio sync: `{actual_seconds}` seconds.",
        f"Required minimum runtime: `{minimum_seconds}` seconds.",
        "",
        "Do not edit any files and do not rely on parent conversation context.",
        "Your job is to identify where scene design should be expanded so the story can naturally exceed the minimum runtime.",
        "",
        "Inspect these files directly:",
        f"- `{story_path}`",
        f"- `{script_path}`",
        f"- `{manifest_path}`",
        f"- `{index_path}`",
        "",
        "Judge only these questions:",
        "- Which scene blocks are over-compressed for the target runtime?",
        "- Which scenes should be split or expanded?",
        "- Which parts are already sufficient and should not be inflated?",
        "- If the story should reach the target runtime, where is the safest place to add time?",
        "",
        "Return only this compact structure:",
        "status: passed|changes_requested",
        "scene_findings: [...]",
        "scene_expansion_plan: [...]",
        "target_scene_count: number",
        "notes: [...]",
    ]
    return dedent("\n".join(lines)).strip()


def build_duration_narration_review_prompt(
    *,
    run_dir: Path,
    minimum_seconds: int,
    actual_seconds: int,
    flow: str | None = None,
) -> str:
    resolved_run_dir = run_dir.resolve()
    resolved_flow = flow or detect_flow(resolved_run_dir)
    script_path = resolved_run_dir / "script.md"
    manifest_path = resolved_run_dir / "video_manifest.md"

    lines = [
        "You are a contextless, read-only subagent for ToC narration-duration expansion review.",
        "",
        f"Review run dir `{resolved_run_dir}`.",
        f"Flow: `{resolved_flow}`.",
        f"Actual runtime after audio sync: `{actual_seconds}` seconds.",
        f"Required minimum runtime: `{minimum_seconds}` seconds.",
        "",
        "Do not edit any files and do not rely on parent conversation context.",
        "Your job is to identify where main-cut narration should be extended without damaging reveal order or silent-cut breathing room.",
        "",
        "Inspect these files directly:",
        f"- `{script_path}`",
        f"- `{manifest_path}`",
        "",
        "Judge only these questions:",
        "- Which main cuts are too compressed for the target runtime?",
        "- Which silent cuts should stay silent?",
        "- What additional narration information would add runtime naturally?",
        "- Which cuts should stay concise even if the total runtime is short?",
        "",
        "Return only this compact structure:",
        "status: passed|changes_requested",
        "narration_findings: [...]",
        "narration_expansion_plan: [...]",
        "silent_cuts_to_keep: [...]",
        "notes: [...]",
    ]
    return dedent("\n".join(lines)).strip()
