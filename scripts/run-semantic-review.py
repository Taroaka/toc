#!/usr/bin/env python3
"""Run contextless semantic review for one ToC stage."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import CodexAppServerClient  # noqa: E402
from toc.harness import append_state_snapshot  # noqa: E402
from toc.semantic_review import (  # noqa: E402
    IMAGE_PROMPT_JUDGMENT_REPORT,
    SEMANTIC_REVIEW_STAGES,
    check_image_prompt_judgment,
    check_semantic_review,
    review_status_to_state,
    semantic_review_relpaths,
)


async def run_review(run_dir: Path, stage: str, *, timeout_seconds: int, build_only: bool = False) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build-semantic-review-pack.py"),
            "--run-dir",
            str(run_dir),
            "--stage",
            stage,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
        return completed.returncode
    if build_only:
        return 0

    paths = semantic_review_relpaths(stage)
    prompt = (run_dir / paths["prompt"]).read_text(encoding="utf-8")
    client = CodexAppServerClient(cwd=REPO_ROOT)
    try:
        thread_id = await client.start_thread(cwd=REPO_ROOT, approval_policy="never")
        await client.run_turn(thread_id=thread_id, text=prompt, cwd=REPO_ROOT, timeout_seconds=timeout_seconds)
    finally:
        await client.stop()

    if stage == "image_prompt" and (run_dir / paths["report"]).exists():
        (run_dir / IMAGE_PROMPT_JUDGMENT_REPORT).write_text((run_dir / paths["report"]).read_text(encoding="utf-8"), encoding="utf-8")
    result = check_image_prompt_judgment(run_dir) if stage == "image_prompt" else check_semantic_review(run_dir, stage)
    updates = review_status_to_state(stage, result)
    if stage == "image_prompt":
        updates.update(
            {
                "review.image_prompt.judgment.status": result.status or "failed",
                "review.image_prompt.judgment.error_count": str(len(result.errors)),
            }
        )
    append_state_snapshot(run_dir / "state.txt", updates)
    if not result.passed:
        sys.stderr.write(f"semantic review failed for {stage}: {'; '.join(result.errors)}\n")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and run a contextless semantic review agent for one stage.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(SEMANTIC_REVIEW_STAGES))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run_review(Path(args.run_dir).resolve(), args.stage, timeout_seconds=args.timeout_seconds, build_only=args.build_only))


if __name__ == "__main__":
    raise SystemExit(main())
