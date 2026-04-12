#!/usr/bin/env python3
"""
Scaffold a run folder for the immersive (cinematic) workflow (/toc-immersive-ride).

This script is intentionally a helper:
- It creates output/<topic>_<timestamp>/ with standard files and folders
- It writes a draft video_manifest.md based on an experience-specific template in workflow/
- It does NOT call external generation APIs
"""

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
from toc.harness import append_state_snapshot

EXPERIENCE_TEMPLATES: dict[str, Path] = {
    "cinematic_story": Path("workflow/immersive-ride-video-manifest-template.md"),
    "cloud_island_walk": Path("workflow/immersive-cloud-island-walk-video-manifest-template.md"),
    # legacy alias (kept for backward compatibility; canonicalized to cinematic_story)
    "ride_action_boat": Path("workflow/immersive-ride-video-manifest-template.md"),
}
SCENE_CONTE_TEMPLATE = Path("workflow/scene-conte-template.md")
VISUAL_VALUE_TEMPLATE = Path("workflow/visual-value-template.yaml")


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    append_state_snapshot(state_path, kv)


def write_text(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def maybe_run_stage_grounding(run_dir: Path, stage: str, *, flow: str) -> None:
    run_stage_grounding(run_dir, stage, flow=flow, retries=1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold an immersive run folder.")
    parser.add_argument("--topic", required=True, help="Video topic (used for folder name).")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM).")
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument(
        "--experience",
        choices=sorted(EXPERIENCE_TEMPLATES.keys()),
        default="cloud_island_walk",
        help="Experience template to scaffold (default: cloud_island_walk).",
    )
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "seedance", "veo"],
        default="kling-omni",
        help='Video generation tool in manifest ("kling", "kling-omni", or "seedance"). "veo" is mapped to Kling for safety.',
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    parser.add_argument("--review-policy", choices=["strict", "drafts"], default="strict")
    parser.add_argument("--story-review", choices=["required", "optional"], default=None)
    parser.add_argument("--image-review", choices=["required", "optional"], default=None)
    parser.add_argument("--narration-review", choices=["required", "optional"], default=None)
    args = parser.parse_args()

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()

    experience = str(args.experience)
    if experience == "ride_action_boat":
        print("[warn] --experience ride_action_boat is deprecated; using cinematic_story.")
        experience = "cinematic_story"

    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}")
    run_dir.mkdir(parents=True, exist_ok=True)
    review_policy = resolve_review_policy(
        preset=args.review_policy,
        story_review=args.story_review,
        image_review=args.image_review,
        narration_review=args.narration_review,
    )

    # assets
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "objects").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "styles").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs" / "grounding").mkdir(parents=True, exist_ok=True)

    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "immersive_ride_scaffold",
                "gate.video_review": "required",
                "immersive.experience": str(experience),
                "runtime.review_policy": args.review_policy,
                **review_policy_state_entries(review_policy),
            },
        )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "research", flow="immersive")
    write_text(run_dir / "story.md", "# 物語（story）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "story", flow="immersive")
    if VISUAL_VALUE_TEMPLATE.exists():
        visual_value = (
            VISUAL_VALUE_TEMPLATE.read_text(encoding="utf-8")
            .replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "visual_value.md", visual_value, force=args.force)
    else:
        write_text(run_dir / "visual_value.md", "# 視覚化価値パート（visual value）\n\nTODO\n", force=args.force)
    write_text(run_dir / "script.md", "# 台本（没入型 / cinematic）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "script", flow="immersive")
    if SCENE_CONTE_TEMPLATE.exists():
        tmpl = SCENE_CONTE_TEMPLATE.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "scene_conte.md", tmpl, force=args.force)

    template_path = EXPERIENCE_TEMPLATES.get(str(experience))
    if template_path is None:
        raise SystemExit(f"Unknown --experience: {experience}")
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        if args.video_tool == "kling":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "kling_3_0"', tmpl)
        elif args.video_tool == "seedance":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "seedance"', tmpl)
        elif args.video_tool in {"kling-omni", "veo"}:
            if args.video_tool == "veo":
                print('[warn] --video-tool veo is disabled for safety; using kling_3_0_omni instead.')
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
        write_text(run_dir / "video_manifest.md", tmpl, force=args.force)
    else:
        write_text(run_dir / "video_manifest.md", "# Video Manifest\n\nTBD\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "image_prompt", flow="immersive")
    maybe_run_stage_grounding(run_dir, "video_generation", flow="immersive")

    append_state_block(
        state_path,
        {
            "timestamp": now_iso(),
            "topic": topic_raw,
            "status": "DONE",
            "runtime.stage": "immersive_ride_scaffolded",
            "immersive.experience": str(experience),
            "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
            "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
        },
    )

    print(f"Run dir: {run_dir.resolve()}")


if __name__ == "__main__":
    main()
