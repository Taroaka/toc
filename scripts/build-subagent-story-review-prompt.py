#!/usr/bin/env python3
"""Build a pasteable prompt for a contextless subagent story-stage review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import detect_flow
from toc.harness import append_state_snapshot, now_iso


def story_review_prompt_relpath() -> Path:
    return Path("logs") / "review" / "story.subagent_prompt.md"


def story_review_prompt_path(run_dir: Path) -> Path:
    return run_dir / story_review_prompt_relpath()


def build_subagent_story_review_prompt(*, run_dir: Path, flow: str | None = None) -> str:
    resolved_run_dir = run_dir.resolve()
    resolved_flow = flow or detect_flow(resolved_run_dir)

    story_path = resolved_run_dir / "story.md"
    research_path = resolved_run_dir / "research.md"
    story_review_path = resolved_run_dir / "story_review.md"
    state_path = resolved_run_dir / "state.txt"
    grounding_report_path = resolved_run_dir / "logs" / "grounding" / "story.json"
    readset_path = resolved_run_dir / "logs" / "grounding" / "story.readset.json"
    audit_path = resolved_run_dir / "logs" / "grounding" / "story.audit.json"
    story_doc_path = REPO_ROOT / "docs" / "story-creation.md"
    affect_doc_path = REPO_ROOT / "docs" / "affect-design.md"
    template_path = REPO_ROOT / "workflow" / "story-template.yaml"

    lines = [
        "You are a contextless, judgment-only subagent for ToC p230 story-stage review.",
        "",
        f"Review the completed p200 story artifact in run dir `{resolved_run_dir}`.",
        f"Flow: `{resolved_flow}`.",
        "",
        "Do not edit files, do not generate replacement story content, and do not rely on parent conversation context.",
        "Your role is semantic scoring and review, not deterministic schema validation.",
        "",
        "First inspect these files directly:",
        f"- `{story_doc_path}`",
        f"- `{affect_doc_path}`",
        f"- `{template_path}`",
        f"- `{research_path}`",
        f"- `{story_path}`",
        f"- `{grounding_report_path}`",
        f"- `{readset_path}`",
        f"- `{audit_path}`",
        f"- `{state_path}`",
        "",
        "Evaluate the story using these rules:",
        "- p200 is only a 20-scene story skeleton, not cut-level script writing.",
        "- Each scene must still be dense enough for downstream script, narration, and visual planning.",
        "- Judge required scene fields: purpose, conflict, turn, affect, visualizable_action, grounding_note.",
        "- Treat creative_inventions as optional and only required where the story adds invented symbols, dialogue, or psychology.",
        "- Treat grounding_note as the place where confidence/verification/uncertainty is summarized, not copied raw.",
        "- Score selection candidates yourself; do not accept author self-scoring as final.",
        "",
        "Return markdown suitable for writing to `story_review.md` with this compact structure:",
        "# Story Evaluator Review",
        "",
        "- status: approved|changes_requested",
        "- overall_score: 0.0-1.0",
        "- candidate_scores: [{candidate_id, engagement, coherence, production_fit, grounding_safety, notes}]",
        "- chosen_candidate_assessment: pass|weak|fail",
        "",
        "## Scene Findings",
        "- For each weak scene, include: scene_id, severity, finding, missing_or_weak_fields, downstream_risk, suggested_direction.",
        "",
        "## Summary",
        "- Include the top 3 changes needed before script/visual planning.",
    ]
    return dedent("\n".join(lines)).strip()


def write_story_review_prompt(*, run_dir: Path, prompt: str) -> Path:
    path = story_review_prompt_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{prompt}\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pasteable prompt for contextless subagent story review.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    prompt = build_subagent_story_review_prompt(run_dir=run_dir, flow=args.flow)
    prompt_path = write_story_review_prompt(run_dir=run_dir.resolve(), prompt=prompt)
    append_state_snapshot(
        run_dir.resolve() / "state.txt",
        {
            "review.story.subagent.prompt": str(prompt_path.relative_to(run_dir.resolve())),
            "review.story.subagent.prompt.generated_at": now_iso(),
        },
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
