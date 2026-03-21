#!/usr/bin/env python3
"""Export reviewable image prompt collections from a manifest."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


def load_manifest_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*)\n```", text, re.S)
    if not match:
        raise SystemExit(f"YAML block not found in manifest: {path}")
    return yaml.safe_load(match.group(1))


def render_collection(data: dict, *, mode_filter: str) -> str:
    lines = [
        "# Image Prompt Collection",
        "",
        f"抽出対象: `still_image_plan.mode == {mode_filter}`",
        "",
    ]
    count = 0
    for scene in data.get("scenes", []):
        sid = scene.get("scene_id")
        if "cuts" not in scene or not isinstance(sid, int) or sid <= 0:
            continue
        for cut in scene["cuts"]:
            plan = cut.get("still_image_plan") or {}
            if str(plan.get("mode") or "") != mode_filter:
                continue
            count += 1
            cid = cut.get("cut_id")
            image_generation = cut.get("image_generation") or {}
            narration = ((cut.get("audio") or {}).get("narration") or {}).get("text", "")
            lines.extend(
                [
                    f"## scene{sid:02d}_cut{cid:02d}",
                    "",
                    f"- output: `{image_generation.get('output', '')}`",
                    f"- narration: `{narration}`" if narration else "- narration: `(silent)`",
                    f"- rationale: `{plan.get('rationale', '')}`",
                    "",
                    "```text",
                    str(image_generation.get("prompt", "")).rstrip(),
                    "```",
                    "",
                ]
            )
    lines.insert(3, f"件数: `{count}`")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export image prompt collection from a manifest.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--out", default=None, help="Output markdown path (default: <manifest_dir>/image_prompt_collection.md)")
    parser.add_argument("--mode", default="generate_still", help="still_image_plan.mode filter (default: generate_still)")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out) if args.out else manifest_path.with_name("image_prompt_collection.md")
    data = load_manifest_yaml(manifest_path)
    out_path.write_text(render_collection(data, mode_filter=args.mode), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
