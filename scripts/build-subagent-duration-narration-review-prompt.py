#!/usr/bin/env python3
"""Build a pasteable prompt for contextless narration-duration review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.duration_fit_review import (  # noqa: E402
    build_duration_narration_review_prompt,
    write_review_prompt,
)
from toc.harness import append_state_snapshot, now_iso  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pasteable prompt for contextless narration-duration review.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>.")
    parser.add_argument("--min-seconds", required=True, type=int, help="Minimum target runtime in seconds.")
    parser.add_argument("--actual-seconds", required=True, type=int, help="Actual runtime in seconds after audio sync.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    prompt = build_duration_narration_review_prompt(
        run_dir=run_dir,
        minimum_seconds=int(args.min_seconds),
        actual_seconds=int(args.actual_seconds),
        flow=args.flow,
    )
    prompt_path = write_review_prompt(run_dir=run_dir.resolve(), kind="narration", prompt=prompt)
    append_state_snapshot(
        run_dir.resolve() / "state.txt",
        {
            "review.duration_fit.narration_prompt": str(prompt_path.relative_to(run_dir.resolve())),
            "review.duration_fit.narration_prompt.generated_at": now_iso(),
        },
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
