#!/usr/bin/env python3
"""Import a Codex built-in generated image into the workspace."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def default_generated_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "generated_images"


def iter_image_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def resolve_source(args: argparse.Namespace) -> Path:
    if args.source:
        source = Path(args.source).expanduser()
        if not source.exists() or not source.is_file():
            raise SystemExit(f"Source image not found: {source}")
        return source

    root = Path(args.generated_root).expanduser()
    candidates = iter_image_files(root)
    if not candidates:
        raise SystemExit(
            "No generated images found. Pass --source explicitly or ensure "
            f"Codex built-in output exists under {root}."
        )
    return candidates[0]


def versioned_destination(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    for index in range(2, 1000):
        candidate = dest.with_name(f"{stem}-v{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise SystemExit(f"Could not find available versioned destination for {dest}")


def import_image(source: Path, dest: Path, *, move: bool, overwrite: bool) -> Path:
    final_dest = dest if overwrite else versioned_destination(dest)
    final_dest.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(source), str(final_dest))
    else:
        shutil.copy2(str(source), str(final_dest))
    return final_dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import the latest Codex built-in generated image into the workspace."
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Workspace destination path for the imported image.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Explicit source image path. If omitted, use the latest image under generated root.",
    )
    parser.add_argument(
        "--generated-root",
        default=str(default_generated_root()),
        help="Directory to search when --source is omitted.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move the generated image instead of copying it.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the destination if it already exists.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    source = resolve_source(args)
    dest = Path(args.dest).expanduser()
    final_dest = import_image(source, dest, move=args.move, overwrite=args.overwrite)
    print(final_dest)


if __name__ == "__main__":
    main()
