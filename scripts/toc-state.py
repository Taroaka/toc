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
    now_iso,
    parse_state_file,
    resolve_artifact_path as _resolve_artifact_path,
    safe_load_yaml,
    sync_run_status,
)


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
            "gate.video_review": "required",
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


def cmd_approve_video(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    updates: dict[str, str] = {
        "review.video.status": "approved",
        "review.video.at": now_iso(),
    }
    if args.note:
        updates["review.video.note"] = str(args.note).replace("\n", " ").strip()
    append_state_snapshot(state_path, updates)
    return 0


def cmd_approve_image_prompts(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    updates: dict[str, str] = {
        "gate.image_prompt_review": "required",
        "review.image_prompt.status": "approved",
        "review.image_prompt.at": now_iso(),
    }
    if args.note:
        updates["review.image_prompt.note"] = str(args.note).replace("\n", " ").strip()
    append_state_snapshot(state_path, updates)
    return 0


def cmd_approve_hybridization(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    updates: dict[str, str] = {
        "gate.hybridization_review": "required",
        "review.hybridization.status": "approved",
        "review.hybridization.at": now_iso(),
    }
    if args.note:
        updates["review.hybridization.note"] = str(args.note).replace("\n", " ").strip()
    append_state_snapshot(state_path, updates)
    return 0


def cmd_reject_hybridization(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        raise SystemExit(f"state.txt not found: {state_path} (run ensure first)")
    updates: dict[str, str] = {
        "gate.hybridization_review": "required",
        "review.hybridization.status": "rejected",
        "review.hybridization.at": now_iso(),
    }
    if args.note:
        updates["review.hybridization.note"] = str(args.note).replace("\n", " ").strip()
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
    hybrid_gate = state.get("gate.hybridization_review", "")
    hybrid_status = state.get("review.hybridization.status", "")
    hybrid_at = state.get("review.hybridization.at", "")
    hybrid_note = state.get("review.hybridization.note", "")
    image_prompt_gate = state.get("gate.image_prompt_review", "")
    image_prompt_status = state.get("review.image_prompt.status", "")
    image_prompt_at = state.get("review.image_prompt.at", "")
    image_prompt_note = state.get("review.image_prompt.note", "")
    review_status = state.get("review.video.status", "")
    review_at = state.get("review.video.at", "")
    review_note = state.get("review.video.note", "")
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
    if hybrid_gate or hybrid_status:
        s = f"Hybridization gate: {hybrid_gate or '(unset)'}"
        if hybrid_status:
            s += f" / review={hybrid_status}"
        if hybrid_at:
            s += f" at {hybrid_at}"
        print(s)
        if hybrid_note:
            print(f"Hybridization note: {hybrid_note}")
    if image_prompt_gate or image_prompt_status:
        s = f"Image prompt gate: {image_prompt_gate or '(unset)'}"
        if image_prompt_status:
            s += f" / review={image_prompt_status}"
        if image_prompt_at:
            s += f" at {image_prompt_at}"
        print(s)
        if image_prompt_note:
            print(f"Image prompt note: {image_prompt_note}")
    print(f"Video: {artifact_video} ({'exists' if video_exists else 'missing'})")
    if review_status:
        s = f"Review: {review_status}"
        if review_at:
            s += f" at {review_at}"
        print(s)
        if review_note:
            print(f"Review note: {review_note}")
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

    p_approve = sub.add_parser("approve-video", help="Mark video as human-approved.")
    p_approve.add_argument("--run-dir", required=True)
    p_approve.add_argument("--note", default=None)
    p_approve.set_defaults(fn=cmd_approve_video)

    p_ip_approve = sub.add_parser("approve-image-prompts", help="Mark image prompts as human-reviewed and approved.")
    p_ip_approve.add_argument("--run-dir", required=True)
    p_ip_approve.add_argument("--note", default=None)
    p_ip_approve.set_defaults(fn=cmd_approve_image_prompts)

    p_h_approve = sub.add_parser("approve-hybridization", help="Approve narrative hybridization (human gate).")
    p_h_approve.add_argument("--run-dir", required=True)
    p_h_approve.add_argument("--note", default=None)
    p_h_approve.set_defaults(fn=cmd_approve_hybridization)

    p_h_reject = sub.add_parser("reject-hybridization", help="Reject narrative hybridization (human gate).")
    p_h_reject.add_argument("--run-dir", required=True)
    p_h_reject.add_argument("--note", default=None)
    p_h_reject.set_defaults(fn=cmd_reject_hybridization)

    p_show = sub.add_parser("show", help="Show current state summary.")
    p_show.add_argument("--run-dir", required=True)
    p_show.set_defaults(fn=cmd_show)

    p_sync = sub.add_parser("sync", help="Regenerate run_status.json from state.txt (+ eval report if present).")
    p_sync.add_argument("--run-dir", required=True)
    p_sync.set_defaults(fn=cmd_sync)

    args = parser.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
