#!/usr/bin/env python3
"""Check a stage grounding report/readset for interactive diagnostics.

This command is retained for old automation that invokes its filename.  It no
longer writes an audit certificate or state gate; stage readiness comes from
the resolved report and readset produced by the grounding command.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import (  # noqa: E402
    load_grounding_contract,
    load_grounding_readset,
    load_grounding_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check stage grounding artifacts after preflight.")
    parser.add_argument("--stage", required=True, help="Stage name.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    contract = load_grounding_contract()
    report, report_path = load_grounding_report(run_dir, args.stage, contract)
    readset, readset_path = load_grounding_readset(run_dir, args.stage, contract)
    if not report or not readset:
        missing = []
        if not report:
            missing.append("grounding_report")
        if not readset:
            missing.append("readset_report")
        raise SystemExit(f"Missing required grounding artifacts: {', '.join(missing)}")

    del readset_path
    print(report_path or run_dir / "logs" / "grounding" / f"{args.stage}.json")
    return 0 if report.get("status") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
