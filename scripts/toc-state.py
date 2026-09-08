#!/usr/bin/env python3
"""
State file helper for ToC runs.

State format:
- Append-only key=value blocks separated by a line containing only "---".
- For backward compatibility, we interpret the "current state" as a merge of all keys
  in order (last write wins), even if older blocks were partial updates.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import (
    append_state_snapshot,
    extract_yaml_block,
    parse_state_file,
    resolve_artifact_path as _resolve_artifact_path,
    safe_load_yaml,
    sync_run_status,
)
from toc.run_index import SLOT_BY_CODE


VALID_SLOT_STATUSES = {
    "pending",
    "in_progress",
    "done",
    "skipped",
    "blocked",
    "awaiting_approval",
    "failed",
}
VALID_SLOT_REQUIREMENTS = {"required", "optional"}


def read_manifest_topic(manifest_path: Path) -> str:
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    data = safe_load_yaml(y)
    topic = None
    vm = data.get("video_metadata")
    if isinstance(vm, dict):
        topic = vm.get("topic")
    if topic is None:
        # Minimal fallback: find a top-level "topic:" scalar anywhere.
        m = re.search(r'(?m)^\s*topic:\s*("?)(.+?)\1\s*$', y)
        topic = m.group(2).strip() if m else None
    topic_s = str(topic).strip() if topic is not None else ""
    if not topic_s:
        raise SystemExit(f"Failed to read topic from manifest: {manifest_path}")
    return topic_s


def cmd_ensure(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    manifest = Path(args.manifest)
    state_path = run_dir / "state.txt"

    if state_path.exists():
        return 0

    if not manifest.exists():
        raise SystemExit(f"Manifest not found: {manifest}")

    topic = read_manifest_topic(manifest)
    append_state_snapshot(
        state_path,
        {
            "topic": topic,
            "status": "INIT",
            "runtime.stage": "init",
            "artifact.video_manifest": str(manifest.resolve()),
        },
    )
    return 0


def _parse_set_pairs(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            raise SystemExit(f"Invalid --set (expected key=value): {raw}")
        k, v = raw.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise SystemExit(f"Invalid --set (empty key): {raw}")
        out[k] = v
    return out


def cmd_append(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    updates = _parse_set_pairs(args.set or [])
    if not updates:
        raise SystemExit("--set is required")
    append_state_snapshot(state_path, updates)
    return 0


def cmd_set_slot(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    slot = str(args.slot).strip()
    if slot not in SLOT_BY_CODE:
        raise SystemExit(f"Invalid --slot (expected fixed workflow slot): {slot}")
    updates: dict[str, str] = {}
    if args.status:
        status = str(args.status).strip().lower()
        if status not in VALID_SLOT_STATUSES:
            raise SystemExit(f"Invalid --status for {slot}: {args.status}")
        updates[f"slot.{slot}.status"] = status
    if args.requirement:
        requirement = str(args.requirement).strip().lower()
        if requirement not in VALID_SLOT_REQUIREMENTS:
            raise SystemExit(f"Invalid --requirement for {slot}: {args.requirement}")
        updates[f"slot.{slot}.requirement"] = requirement
    if args.skip_reason:
        updates[f"slot.{slot}.skip_reason"] = str(args.skip_reason).replace("\n", " ").strip()
    if args.note:
        updates[f"slot.{slot}.note"] = str(args.note).replace("\n", " ").strip()
    if not updates:
        raise SystemExit("At least one of --status/--requirement/--skip-reason/--note is required")
    append_state_snapshot(state_path, updates)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path}")

    state = parse_state_file(state_path)
    topic = state.get("topic", "")
    stage = state.get("runtime.stage", "")
    render_status = state.get("runtime.render.status", "")
    last_error = state.get("last_error", "")

    artifact_video = _resolve_artifact_path(run_dir, state.get("artifact.video")) or (run_dir / "video.mp4")
    video_exists = artifact_video.exists()

    print(f"Run dir: {run_dir.resolve()}")
    print(f"State: {state_path.resolve()}")
    if topic:
        print(f"Topic: {topic}")
    if stage:
        print(f"Stage: {stage}")
    if render_status:
        print(f"Render: {render_status}")
    print(f"Video: {artifact_video} ({'exists' if video_exists else 'missing'})")
    if last_error:
        print(f"Last error: {last_error}")
    print(f"Run status: {sync_run_status(run_dir)}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path}")
    output = sync_run_status(run_dir)
    print(output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ToC state.txt helper (append-only snapshots).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ensure = sub.add_parser("ensure", help="Create state.txt with INIT block if missing.")
    p_ensure.add_argument("--run-dir", required=True)
    p_ensure.add_argument("--manifest", required=True)
    p_ensure.set_defaults(fn=cmd_ensure)

    p_append = sub.add_parser("append", help="Append a state snapshot (merge + updates).")
    p_append.add_argument("--run-dir", required=True)
    p_append.add_argument("--set", action="append", default=[], help="key=value (repeatable)")
    p_append.set_defaults(fn=cmd_append)

    p_slot = sub.add_parser("set-slot", help="Set fixed p-slot workflow state.")
    p_slot.add_argument("--run-dir", required=True)
    p_slot.add_argument("--slot", required=True, help="Fixed slot code, e.g. p540")
    p_slot.add_argument("--status", default=None)
    p_slot.add_argument("--requirement", default=None)
    p_slot.add_argument("--skip-reason", default=None)
    p_slot.add_argument("--note", default=None)
    p_slot.set_defaults(fn=cmd_set_slot)

    p_show = sub.add_parser("show", help="Show current state summary.")
    p_show.add_argument("--run-dir", required=True)
    p_show.set_defaults(fn=cmd_show)

    p_sync = sub.add_parser("sync", help="Regenerate run_status.json from state.txt.")
    p_sync.add_argument("--run-dir", required=True)
    p_sync.set_defaults(fn=cmd_sync)

    args = parser.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
