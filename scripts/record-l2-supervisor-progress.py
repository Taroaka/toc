#!/usr/bin/env python3
"""Append L2 P-Bucket Supervisor invocation progress for a ToC run."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso  # noqa: E402


VALID_BUCKETS = {f"p{index}00" for index in range(1, 10)}
EVENT_TO_CALL_STATUS = {
    "invoked": "invoked",
    "returned": "returned",
    "blocked": "blocked",
    "failed": "failed",
}
EVENT_TO_SUPERVISOR_STATUS = {
    "returned": "done",
    "blocked": "blocked",
    "failed": "failed",
}


def _escape_table_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


def progress_path(run_dir: Path) -> Path:
    return run_dir / "logs" / "orchestration" / "l2_supervisor_progress.md"


def append_progress(
    *,
    run_dir: Path,
    bucket: str,
    event: str,
    supervisor: str,
    stop_slot: str,
    result: str,
    note: str,
    at: str,
) -> Path:
    path = progress_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    "# L2 Supervisor Progress",
                    "",
                    "Only L2 P-Bucket Supervisor invocations are recorded here. L3 task/review agents are intentionally omitted.",
                    "",
                    "| at | bucket | supervisor | event | stop_slot | result | note |",
                    "| --- | --- | --- | --- | --- | --- | --- |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    row = [
        at,
        bucket,
        supervisor,
        event,
        stop_slot,
        result,
        note,
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("| " + " | ".join(_escape_table_cell(item) or "-" for item in row) + " |\n")
    return path


def build_state_updates(*, bucket: str, event: str, stop_slot: str, result: str, at: str) -> dict[str, str]:
    prefix = f"orchestration.{bucket}.supervisor"
    updates = {
        "artifact.l2_supervisor_progress": "logs/orchestration/l2_supervisor_progress.md",
        f"{prefix}.progress": "logs/orchestration/l2_supervisor_progress.md",
        f"{prefix}.call_status": EVENT_TO_CALL_STATUS[event],
        f"{prefix}.last_event_at": at,
    }
    if event == "invoked":
        updates[f"{prefix}.invoked_at"] = at
    if event in EVENT_TO_SUPERVISOR_STATUS:
        updates[f"{prefix}.status"] = EVENT_TO_SUPERVISOR_STATUS[event]
        updates[f"{prefix}.finished_at"] = at
    if stop_slot:
        updates[f"{prefix}.stop_slot"] = stop_slot
    if result:
        updates[f"{prefix}.result"] = result
    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description="Record an L2 P-Bucket Supervisor invocation/progress event.")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--bucket", required=True, choices=sorted(VALID_BUCKETS))
    parser.add_argument("--event", required=True, choices=sorted(EVENT_TO_CALL_STATUS))
    parser.add_argument("--supervisor", default="", help="Human-readable supervisor name. Defaults to '<bucket> P-Bucket Supervisor'.")
    parser.add_argument("--stop-slot", default="", help="Bucket stop slot, e.g. p680.")
    parser.add_argument("--result", default="", help="Relative supervisor result path when available.")
    parser.add_argument("--note", default="")
    parser.add_argument("--at", default="", help="ISO8601 timestamp override, mainly for tests.")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    at = args.at.strip() or now_iso()
    supervisor = args.supervisor.strip() or f"{args.bucket} P-Bucket Supervisor"
    if args.event in EVENT_TO_SUPERVISOR_STATUS and not args.result.strip():
        parser.error("--result is required for returned/blocked/failed events")
    progress = append_progress(
        run_dir=run_dir,
        bucket=args.bucket,
        event=args.event,
        supervisor=supervisor,
        stop_slot=args.stop_slot.strip(),
        result=args.result.strip(),
        note=args.note.strip(),
        at=at,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        build_state_updates(
            bucket=args.bucket,
            event=args.event,
            stop_slot=args.stop_slot.strip(),
            result=args.result.strip(),
            at=at,
        ),
    )
    print(progress)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
