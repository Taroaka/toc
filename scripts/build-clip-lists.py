#!/usr/bin/env python3
"""
Build ffmpeg concat lists from a video manifest.

Outputs:
- <base>_clips.txt
- <base>_narration_list.txt
"""
import argparse
import glob
import os
import re
from pathlib import Path

def parse_manifest(path: Path):
    clips = []
    narrations = []
    stack = []  # list of (indent, key)

    def push(indent, key):
        nonlocal stack
        while stack and indent <= stack[-1][0]:
            stack.pop()
        stack.append((indent, key))

    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue

            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()

            # Handle list items like "- key: value"
            if stripped.startswith("- "):
                stripped = stripped[2:].strip()

            if ":" not in stripped:
                continue

            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            push(indent, key)

            if key != "output":
                continue

            # Remove surrounding quotes if present
            if (value.startswith("\"") and value.endswith("\"")) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            if not value:
                continue

            if value.lower() in {"null", "~", "none"}:
                continue

            context_keys = [k for _, k in stack]

            if "video_generation" in context_keys:
                clips.append(value)
            elif "narration" in context_keys:
                narrations.append(value)

    return clips, narrations


def write_concat_list(paths, out_path: Path, dry_run: bool):
    lines = [f"file '{p}'" for p in paths]
    if dry_run:
        return
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build ffmpeg concat lists from manifest(s).")
    parser.add_argument("--manifest", action="append", default=[], help="Manifest file path. Can be used multiple times.")
    parser.add_argument("--dir", default=None, help="Directory to search for manifests.")
    parser.add_argument("--story-dir", default=None, help="Story folder containing a single manifest.")
    parser.add_argument("--pattern", default="*_manifest.md", help="Glob pattern for manifest search.")
    parser.add_argument("--out-dir", default=None, help="Directory to write output lists (default: manifest dir).")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no files written.")

    args = parser.parse_args()

    manifest_paths = [Path(p) for p in args.manifest]

    if args.story_dir:
        story_dir = Path(args.story_dir)
        matches = list(story_dir.glob(args.pattern))
        if len(matches) == 0:
            raise SystemExit(f"No manifest found in {story_dir} with pattern {args.pattern}.")
        if len(matches) > 1:
            names = ", ".join(str(p) for p in matches)
            raise SystemExit(f"Multiple manifests found in {story_dir}. Use --manifest to pick one. Found: {names}")
        manifest_paths.append(matches[0])

    if args.dir:
        manifest_paths.extend(Path(p) for p in glob.glob(str(Path(args.dir) / args.pattern)))

    # De-duplicate
    manifest_paths = list(dict.fromkeys(manifest_paths))

    if not manifest_paths:
        raise SystemExit("No manifest files found. Use --manifest, --story-dir, or --dir.")

    for manifest in manifest_paths:
        clips, narrations = parse_manifest(manifest)

        base = manifest.stem
        if base.endswith("_manifest"):
            base = base[: -len("_manifest")]

        out_dir = Path(args.out_dir) if args.out_dir else manifest.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        clips_path = out_dir / f"{base}_clips.txt"
        narration_path = out_dir / f"{base}_narration_list.txt"

        write_concat_list(clips, clips_path, args.dry_run)
        write_concat_list(narrations, narration_path, args.dry_run)

        print(f"Manifest: {manifest}")
        print(f"  clips: {clips_path} ({len(clips)} entries)")
        print(f"  narration: {narration_path} ({len(narrations)} entries)")


if __name__ == "__main__":
    main()
