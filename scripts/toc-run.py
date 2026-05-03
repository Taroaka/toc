#!/usr/bin/env python3
"""Scaffold a standard ToC run folder for /toc-run style dry runs."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import resolve_review_policy, review_policy_state_entries, run_stage_grounding
from toc.harness import append_state_snapshot, now_iso


MANIFEST_TEMPLATE = Path("workflow/video-manifest-template.md")
VISUAL_VALUE_TEMPLATE = Path("workflow/visual-value-template.yaml")


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def write_text(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def maybe_run_stage_grounding(run_dir: Path, stage: str, *, flow: str) -> None:
    run_stage_grounding(run_dir, stage, flow=flow, retries=1)


def ensure_skeleton_manifest(manifest_text: str) -> str:
    if "manifest_phase:" in manifest_text:
        return manifest_text
    return manifest_text.replace("```yaml\n", "```yaml\nmanifest_phase: skeleton\n", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a standard ToC run dir.")
    parser.add_argument("topic", help="Run topic.")
    parser.add_argument("--dry-run", action="store_true", help="Scaffold only (default behavior).")
    parser.add_argument("--config", default=None, help="Reserved for future config override support.")
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--base", default="output")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--review-policy", choices=["strict", "drafts"], default="strict")
    parser.add_argument("--story-review", choices=["required", "optional"], default=None)
    parser.add_argument("--image-review", choices=["required", "optional"], default=None)
    parser.add_argument("--narration-review", choices=["required", "optional"], default=None)
    args = parser.parse_args()

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()
    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}")
    run_dir.mkdir(parents=True, exist_ok=True)
    review_policy = resolve_review_policy(
        preset=args.review_policy,
        story_review=args.story_review,
        image_review=args.image_review,
        narration_review=args.narration_review,
    )

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "topic": topic_raw,
            "status": "INIT",
            "runtime.stage": "toc_run_scaffold",
            "gate.video_review": "required",
            "runtime.review_policy": args.review_policy,
            **review_policy_state_entries(review_policy),
        },
    )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", args.force)
    maybe_run_stage_grounding(run_dir, "research", flow="toc-run")
    write_text(run_dir / "story.md", "# 物語（story）\n\nTODO\n", args.force)
    maybe_run_stage_grounding(run_dir, "story", flow="toc-run")
    if VISUAL_VALUE_TEMPLATE.exists():
        visual_value = (
            VISUAL_VALUE_TEMPLATE.read_text(encoding="utf-8")
            .replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
    else:
        visual_value = "# 視覚化価値パート（visual value）\n\nTODO\n"
    write_text(run_dir / "visual_value.md", visual_value, args.force)
    maybe_run_stage_grounding(run_dir, "visual_value", flow="toc-run")
    write_text(run_dir / "script.md", "# 台本（script）\n\nTODO\n", args.force)
    maybe_run_stage_grounding(run_dir, "script", flow="toc-run")

    if MANIFEST_TEMPLATE.exists():
        manifest = (
            MANIFEST_TEMPLATE.read_text(encoding="utf-8")
            .replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
    else:
        manifest = "```yaml\nmanifest_phase: skeleton\nvideo_metadata:\n  topic: \"<topic>\"\nscenes: []\n```\n"
    manifest = ensure_skeleton_manifest(manifest)
    write_text(run_dir / "video_manifest.md", manifest, args.force)
    maybe_run_stage_grounding(run_dir, "narration", flow="toc-run")

    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "objects").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "styles").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs" / "grounding").mkdir(parents=True, exist_ok=True)

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "topic": topic_raw,
            "status": "SCRIPT" if args.dry_run else "DONE",
            "runtime.stage": "toc_run_scaffolded",
            "artifact.research": str((run_dir / "research.md").resolve()),
            "artifact.story": str((run_dir / "story.md").resolve()),
            "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
            "artifact.script": str((run_dir / "script.md").resolve()),
            "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
        },
    )

    print(f"Run dir: {run_dir.resolve()}")


if __name__ == "__main__":
    main()
