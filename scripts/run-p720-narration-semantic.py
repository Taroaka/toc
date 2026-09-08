#!/usr/bin/env python3
"""Compatibility entrypoint for deterministic narration validation.

No semantic reviewer, critic, aggregate, or report is run here. The command
delegates to the p720 shape validator so older automation can be upgraded
without reintroducing the removed production review loop.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _l3_module():
    path = REPO_ROOT / "scripts" / "run-p720-narration-l3.py"
    spec = importlib.util.spec_from_file_location("toc_p720_narration_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load narration contract validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_semantic_review(
    *,
    run_dir: Path,
    manifest_path: Path,
    timeout_seconds: int = 0,
    max_concurrency: int = 1,
) -> str:
    del timeout_seconds, max_concurrency
    module = _l3_module()
    return module.run_p720_l3(
        run_dir=run_dir,
        manifest_path=manifest_path,
        script_path=run_dir / "script.md",
        round_number=1,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--max-concurrency", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--fail-on-findings", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else run_dir / "video_manifest.md"
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    try:
        status = run_semantic_review(
            run_dir=run_dir,
            manifest_path=manifest_path,
            timeout_seconds=args.timeout_seconds,
            max_concurrency=args.max_concurrency,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(f"p720 narration contract validation: {status}")
    return 1 if args.fail_on_findings and status != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
