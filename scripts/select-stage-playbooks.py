#!/usr/bin/env python3
"""Select optional stage playbooks and persist the chosen set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StagePlaybookSelectionError, select_stage_playbooks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Select optional playbooks for one stage and write a report artifact.")
    parser.add_argument("--stage", required=True, help="Stage name (research, story, script, image_prompt, video_generation).")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    parser.add_argument("--select", action="append", default=[], help="Optional playbook path to select. May be repeated.")
    parser.add_argument("--select-all", action="store_true", help="Select all optional playbooks declared for the stage.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    try:
        payload = select_stage_playbooks(
            stage=args.stage,
            run_dir=run_dir,
            selected_paths=list(args.select or []),
            select_all=bool(args.select_all),
            flow=args.flow,
        )
    except StagePlaybookSelectionError as exc:
        payload = {
            "stage": exc.stage,
            "run_dir": str(run_dir.resolve()),
            "status": "invalid_selection",
            "invalid_paths": list(exc.invalid_paths),
            "available_paths": list(exc.available_paths),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        payload = {
            "stage": args.stage,
            "run_dir": str(run_dir.resolve()),
            "status": "error",
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
