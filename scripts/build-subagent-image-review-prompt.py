#!/usr/bin/env python3
"""Build a pasteable prompt for a contextless subagent image-prompt judgment review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import detect_flow  # noqa: E402
from toc.harness import append_state_snapshot, now_iso  # noqa: E402


def review_prompt_relpath(review_kind: str = "image_prompt") -> Path:
    return Path("logs") / "review" / f"{review_kind}.subagent_prompt.md"


def review_prompt_path(run_dir: Path, review_kind: str = "image_prompt") -> Path:
    return run_dir / review_prompt_relpath(review_kind)


def write_review_prompt(*, run_dir: Path, review_kind: str, prompt: str) -> Path:
    path = review_prompt_path(run_dir, review_kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{prompt}\n", encoding="utf-8")
    return path


def build_subagent_image_review_prompt(*, run_dir: Path, flow: str | None = None) -> str:
    resolved_run_dir = run_dir.resolve()
    resolved_flow = flow or detect_flow(resolved_run_dir)

    manifest_path = resolved_run_dir / "video_manifest.md"
    story_path = resolved_run_dir / "story.md"
    script_path = resolved_run_dir / "script.md"
    hard_review_path = resolved_run_dir / "image_prompt_story_review.md"
    prompt_collection_path = resolved_run_dir / "image_prompt_collection.md"
    state_path = resolved_run_dir / "state.txt"
    global_doc_path = REPO_ROOT / "docs" / "system-architecture.md"
    image_doc_path = REPO_ROOT / "docs" / "implementation" / "image-prompting.md"

    lines = [
        "You are a contextless, judgment-only subagent for ToC image prompt quality review.",
        "",
        f"Review the image prompt quality for run dir `{resolved_run_dir}`.",
        f"Flow: `{resolved_flow}`.",
        "",
        "Do not generate images, do not edit content artifacts, and do not rely on parent conversation context.",
        "Your role is not schema validation; the hard function review already handles structural checks.",
        "Your job is to judge semantic quality, visual specificity, reveal safety, and production usefulness.",
        "",
        "First run these commands in order:",
        f"`python scripts/export-image-prompt-collection.py --manifest {manifest_path}`",
        f"`python scripts/review-image-prompt-story-consistency.py --manifest {manifest_path}`",
        "",
        "Then inspect these files directly:",
        f"- `{global_doc_path}`",
        f"- `{image_doc_path}`",
        f"- `{story_path}`",
        f"- `{script_path}`",
        f"- `{manifest_path}`",
        f"- `{prompt_collection_path}`",
        f"- `{hard_review_path}`",
        f"- `{state_path}`",
        "",
        "Judge only these questions:",
        "- Are the prompts semantically aligned with the local story/script intent?",
        "- Do the prompts preserve reveal order and avoid leaking later information too early?",
        "- Are the main subjects visually specific enough to generate consistent images?",
        "- Are any prompts technically valid but artistically weak, generic, or over-constrained?",
        "- Which findings are true blockers versus revision suggestions?",
        "",
        "Treat these as hard blockers only if they would obviously produce the wrong image even when the hard review passed:",
        "- reveal order violation",
        "- main subject drift",
        "- missing core character/setpiece relationship",
        "- prompt too generic to preserve the intended subject",
        "",
        "Everything else should be reported as a revision suggestion, not a hard blocker.",
        "",
        "Return only this compact structure:",
        "status: passed|changes_requested|failed",
        "hard_blockers: [...]",
        "revision_suggestions: [...]",
        "strong_cuts: [...]",
        "notes: [...]",
    ]
    return dedent("\n".join(lines)).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pasteable prompt for contextless subagent image prompt review.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp> or a scene run directory.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    parser.add_argument("--review-kind", default="image_prompt", help="Review kind label used for artifact naming.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    prompt = build_subagent_image_review_prompt(run_dir=run_dir, flow=args.flow)
    prompt_path = write_review_prompt(run_dir=run_dir.resolve(), review_kind=args.review_kind, prompt=prompt)
    append_state_snapshot(
        run_dir.resolve() / "state.txt",
        {
            f"review.{args.review_kind}.subagent.prompt": str(prompt_path.relative_to(run_dir.resolve())),
            f"review.{args.review_kind}.subagent.prompt.generated_at": now_iso(),
        },
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
