#!/usr/bin/env python3
"""
Scaffold a run folder for the immersive ride POV workflow (/toc-immersive-ride).

This script is intentionally a helper:
- It creates output/<topic>_<timestamp>/ with standard files and folders
- It writes a draft video_manifest.md based on an experience-specific template in workflow/
- It does NOT call external generation APIs
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

EXPERIENCE_TEMPLATES: dict[str, Path] = {
    "ride_action_boat": Path("workflow/immersive-ride-video-manifest-template.md"),
    "cloud_island_walk": Path("workflow/immersive-cloud-island-walk-video-manifest-template.md"),
}
SCENE_CONTE_TEMPLATE = Path("workflow/scene-conte-template.md")


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
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    block = "\n".join(lines) + "\n---\n"
    with state_path.open("a", encoding="utf-8") as f:
        f.write(block)


def write_text(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold an immersive ride POV run folder.")
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
    args = parser.parse_args()

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()

    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # assets
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "objects").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "styles").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "immersive_ride_scaffold",
                "immersive.experience": str(args.experience),
            },
        )

    write_text(run_dir / "research.md", "# Research Output\n\nTBD\n", force=args.force)
    write_text(run_dir / "story.md", "# Story Script Output\n\nTBD\n", force=args.force)
    write_text(run_dir / "script.md", "# Script Output (Immersive Ride POV)\n\nTBD\n", force=args.force)
    if SCENE_CONTE_TEMPLATE.exists():
        tmpl = SCENE_CONTE_TEMPLATE.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "scene_conte.md", tmpl, force=args.force)

    template_path = EXPERIENCE_TEMPLATES.get(str(args.experience))
    if template_path is None:
        raise SystemExit(f"Unknown --experience: {args.experience}")
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

    append_state_block(
        state_path,
        {
            "timestamp": now_iso(),
            "topic": topic_raw,
            "status": "DONE",
            "runtime.stage": "immersive_ride_scaffolded",
            "immersive.experience": str(args.experience),
            "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
        },
    )

    print(f"Run dir: {run_dir.resolve()}")


if __name__ == "__main__":
    main()
