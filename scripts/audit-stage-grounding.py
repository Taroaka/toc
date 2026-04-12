#!/usr/bin/env python3
"""Audit a stage grounding report/readset and record the result."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import (  # noqa: E402
    build_stage_grounding_audit,
    load_grounding_contract,
    load_grounding_readset,
    load_grounding_report,
    write_stage_grounding_audit,
)
from toc.harness import append_state_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit stage grounding artifacts after preflight.")
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
        raise SystemExit(f"Missing required artifacts for audit: {', '.join(missing)}")

    audit = build_stage_grounding_audit(run_dir=run_dir, stage=args.stage, report=report, readset=readset, contract=contract)
    audit_path = write_stage_grounding_audit(run_dir=run_dir, stage=args.stage, audit=audit)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"stage.{args.stage}.audit.status": str(audit["status"]),
            f"stage.{args.stage}.audit.report": str(audit_path.relative_to(run_dir)),
            f"stage.{args.stage}.grounding.report": str(report_path.relative_to(run_dir)) if report_path else "",
            f"stage.{args.stage}.readset.report": str(readset_path.relative_to(run_dir)) if readset_path else "",
        },
    )
    print(audit_path)
    return 0 if audit["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
