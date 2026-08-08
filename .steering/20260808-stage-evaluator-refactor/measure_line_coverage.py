#!/usr/bin/env python3
"""Measure target-module line coverage with Python 3.12 sys.monitoring.

The executable-line denominator intentionally reuses ``trace``'s standard-
library parser, while ``sys.monitoring`` supplies lower-overhead line events.
"""

from __future__ import annotations

import argparse
import json
import sys
import trace
from collections import defaultdict
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS = sorted((REPO_ROOT / "toc" / "stage_evaluation").glob("*.py")) + [
    REPO_ROOT / "toc" / "stage_review_cli.py"
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum", type=float, default=80.0)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    pytest_args = list(args.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    target_by_filename: dict[str, Path] = {}
    for path in TARGETS:
        resolved = path.resolve()
        target_by_filename[str(resolved)] = resolved
        target_by_filename[str(path)] = resolved
        target_by_filename[str(path.relative_to(REPO_ROOT))] = resolved
    executed: dict[Path, set[int]] = defaultdict(set)

    def record_line(code: object, line_number: int) -> None:
        filename = str(getattr(code, "co_filename"))
        target = target_by_filename.get(filename)
        if target is not None:
            executed[target].add(line_number)

    def enable_target_lines(code: object, instruction_offset: int) -> object:
        del instruction_offset
        filename = str(getattr(code, "co_filename"))
        if filename in target_by_filename:
            sys.monitoring.set_local_events(tool_id, code, sys.monitoring.events.LINE)
        return sys.monitoring.DISABLE

    tool_id = sys.monitoring.COVERAGE_ID
    sys.monitoring.use_tool_id(tool_id, "toc-stage-evaluator-coverage")
    sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, record_line)
    sys.monitoring.register_callback(
        tool_id,
        sys.monitoring.events.PY_START,
        enable_target_lines,
    )
    sys.monitoring.set_events(tool_id, sys.monitoring.events.PY_START)
    try:
        pytest_exit = int(pytest.main(pytest_args))
    finally:
        sys.monitoring.set_events(tool_id, 0)
        sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, None)
        sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, None)
        sys.monitoring.free_tool_id(tool_id)

    modules: dict[str, dict[str, int | float]] = {}
    total_executable = 0
    total_covered = 0
    for path in TARGETS:
        resolved = path.resolve()
        executable = set(trace._find_executable_linenos(str(resolved)))
        covered = executable & executed.get(resolved, set())
        total_executable += len(executable)
        total_covered += len(covered)
        modules[str(path.relative_to(REPO_ROOT))] = {
            "covered": len(covered),
            "executable": len(executable),
            "percent": round(100.0 * len(covered) / len(executable), 2)
            if executable
            else 100.0,
        }

    aggregate = round(100.0 * total_covered / total_executable, 2)
    report = {
        "engine": "sys.monitoring target-local line events + trace._find_executable_linenos",
        "pytest_exit_code": pytest_exit,
        "covered": total_covered,
        "executable": total_executable,
        "percent": aggregate,
        "minimum_percent": args.minimum,
        "passed": pytest_exit == 0 and aggregate >= args.minimum,
        "modules": modules,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if pytest_exit != 0:
        return pytest_exit
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
