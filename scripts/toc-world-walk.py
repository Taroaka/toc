#!/usr/bin/env python3
"""
Scaffold a world-walk immersive run from an existing ToC run.

This is a small convenience wrapper around scripts/toc-immersive-ride.py with
--experience world_walk and a required --source-run.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.world_walk_source import validate_world_walk_source_path


def derive_topic(source_run: Path) -> str:
    name = source_run.name.strip()
    base = re.sub(r"_\d{8}_\d{4}$", "", name).strip("_")
    base = base or name or "topic"
    return f"{base}の世界観を散歩してみた"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a /toc-world-walk run from an existing ToC run.")
    parser.add_argument("--source-run", required=True, help="Existing ToC run directory whose story/assets are referenced.")
    parser.add_argument("--topic", default=None, help="Output video topic. Defaults to '<source topic>の世界観を散歩してみた'.")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM).")
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument("--stage", default=None, help="Stop target passed through to toc-immersive-ride.py.")
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "seedance", "veo"],
        default=None,
        help="Video generation tool passed through to toc-immersive-ride.py.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    parser.add_argument("--review-policy", choices=["strict", "drafts"], default=None)
    parser.add_argument("--story-review", choices=["required", "optional"], default=None)
    parser.add_argument("--image-review", choices=["required", "optional"], default=None)
    parser.add_argument("--narration-review", choices=["required", "optional"], default=None)
    args = parser.parse_args()

    try:
        source_run, source_run_relative = validate_world_walk_source_path(REPO_ROOT, args.source_run)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    topic = args.topic or derive_topic(source_run)
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "toc-immersive-ride.py"),
        "--topic",
        topic,
        "--source-run",
        source_run_relative,
        "--experience",
        "world_walk",
        "--base",
        args.base,
    ]
    if args.timestamp:
        command.extend(["--timestamp", args.timestamp])
    if args.run_dir:
        command.extend(["--run-dir", args.run_dir])
    if args.stage:
        command.extend(["--stage", args.stage])
    if args.video_tool:
        command.extend(["--video-tool", args.video_tool])
    if args.force:
        command.append("--force")
    if args.review_policy:
        command.extend(["--review-policy", args.review_policy])
    if args.story_review:
        command.extend(["--story-review", args.story_review])
    if args.image_review:
        command.extend(["--image-review", args.image_review])
    if args.narration_review:
        command.extend(["--narration-review", args.narration_review])

    result = subprocess.run(command, cwd=REPO_ROOT)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
