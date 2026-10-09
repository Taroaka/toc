#!/usr/bin/env python3
"""Author source-bound p300 visual notes using the shared Codex runtime."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client
from scripts.world_walk_source import directory_identity_nofollow, read_regular_file_nofollow
from toc.story_author_runtime import DEFAULT_STORY_AUTHOR_MODEL
from toc.visual_value_authoring import author_visual_value


def prepare_grounding(run_dir: Path) -> str:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/prepare-stage-context.py"),
        "--stage", "visual_value", "--run-dir", str(run_dir), "--flow", "immersive"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    readset = json.loads(read_regular_file_nofollow(run_dir, "logs/grounding/visual_value.json"))
    if readset.get("missing_paths"):
        raise RuntimeError("visual value grounding inputs are missing")
    parts = []
    for group in ("global_docs", "docs", "templates"):
        for record in readset["resolved_paths"].get(group, []):
            path = Path(record["resolved_path"]).resolve()
            path.relative_to(REPO_ROOT)
            parts.append(f"\n--- {record['path']} ---\n" + path.read_text(encoding="utf-8"))
    if not parts:
        raise RuntimeError("visual value grounding readset is empty")
    return "\n".join(parts)


async def run(args):
    run_dir = Path(os.path.abspath(args.run_dir))
    directory_identity_nofollow(run_dir)
    grounding = prepare_grounding(run_dir)
    def factory():
        return create_codex_app_server_client(cwd=run_dir, scrub_sensitive_env=True,
            require_chatgpt_account=True, require_chatgpt_pro=True)
    await author_visual_value(run_dir=run_dir, grounding=grounding, client_factory=factory,
        model=args.model, timeout_seconds=args.timeout_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("TOC_VISUAL_VALUE_AUTHOR_MODEL") or DEFAULT_STORY_AUTHOR_MODEL)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    asyncio.run(run(args))
    print(json.dumps({"status": "passed", "output": str(args.run_dir / "visual_value.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
