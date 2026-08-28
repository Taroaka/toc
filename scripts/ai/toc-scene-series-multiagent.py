#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    append_state_snapshot(state_path, kv)


def tmux_send_two_calls(target: str, message: str) -> None:
    subprocess.run(["tmux", "send-keys", "-t", target, message], check=True)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare ToC scene-series workflow for multi-agent (scratch-first, merge-by-one, then scene-parallel)."
    )
    parser.add_argument("topic", help="Video topic.")
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM).")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument("--workers", type=int, default=8, help="Number of ashigaru workers (default: 8).")
    parser.add_argument("--min-seconds", type=int, default=30)
    parser.add_argument("--max-seconds", type=int, default=60)
    parser.add_argument("--write-command", action="store_true", help="Write queue/shogun_to_karo.yaml command entry.")
    parser.add_argument("--wake-karo", action="store_true", help="tmux send-keys to wake karo after writing command.")

    args = parser.parse_args()

    repo_root = Path.cwd()
    topic_raw = args.topic
    ts = args.timestamp or default_timestamp()
    topic_slug = sanitize_topic(topic_raw)

    run_dir = Path(args.run_dir) if args.run_dir else (repo_root / args.base / f"{topic_slug}_{ts}")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    scratch_root = run_dir / "scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)
    for i in range(1, max(1, int(args.workers)) + 1):
        d = scratch_root / f"ashigaru{i}"
        d.mkdir(parents=True, exist_ok=True)
        rn = d / "research_notes.md"
        sn = d / "story_notes.md"
        if not rn.exists():
            rn.write_text("# Research Notes\n\n- TBD\n", encoding="utf-8")
        if not sn.exists():
            sn.write_text("# Story/Scene Notes\n\n- TBD\n", encoding="utf-8")

    # Ensure shared artifacts exist (single-writer merge target)
    research_path = run_dir / "research.md"
    story_path = run_dir / "story.md"
    if not research_path.exists():
        research_path.write_text("# Research Output\n\nTBD\n", encoding="utf-8")
    if not story_path.exists():
        story_path.write_text("# Story Script Output\n\nTBD\n", encoding="utf-8")

    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "multiagent_prepare",
            },
        )

    if args.write_command:
        queue_dir = repo_root / "queue"
        if not queue_dir.exists():
            raise SystemExit(f"queue/ not found at {queue_dir}. Run multi-agent launcher first (it creates/symlinks queue/).")

        cmd_id = f"toc_scene_series_multiagent_{ts}"
        cmd = {
            "id": cmd_id,
            "timestamp": now_iso(),
            "command": (
                "ToC scene-series multiagent: Phase1=parallel research to scratch/*/research_notes.md, "
                "then ONE merge to research.md; Phase2=parallel story/scene notes to scratch/*/story_notes.md, "
                "then ONE merge to story.md (or script.md); Phase3=ONE runs scripts/toc-scene-series.py to scaffold; "
                "Phase4=parallel per-scene completion under scenes/sceneXX/; Phase5=ONE summarizes results. "
                "Use improve workflow loop (plan→implement→verify) and avoid multi-writer edits on shared files."
            ),
            "project": "toc",
            "priority": "high",
            "status": "pending",
            "params": {
                "topic": topic_raw,
                "run_dir": str(run_dir),
                "scratch_root": str(scratch_root),
                "workers": int(args.workers),
                "min_seconds": int(args.min_seconds),
                "max_seconds": int(args.max_seconds),
                "playbook": str((repo_root / "workflow/multiagent-scene-series-playbook.md").resolve()),
            },
        }

        # Minimal YAML serialization (intentionally simple).
        yaml_lines = [
            "queue:",
            f"  - id: {cmd['id']}",
            f'    timestamp: "{cmd["timestamp"]}"',
            f'    command: "{cmd["command"]}"',
            f"    project: {cmd['project']}",
            f"    priority: {cmd['priority']}",
            f"    status: {cmd['status']}",
            "    params:",
            f'      topic: "{cmd["params"]["topic"]}"',
            f'      run_dir: "{cmd["params"]["run_dir"]}"',
            f'      scratch_root: "{cmd["params"]["scratch_root"]}"',
            f"      workers: {cmd['params']['workers']}",
            f"      min_seconds: {cmd['params']['min_seconds']}",
            f"      max_seconds: {cmd['params']['max_seconds']}",
            f'      playbook: "{cmd["params"]["playbook"]}"',
            "",
        ]

        (queue_dir / "shogun_to_karo.yaml").write_text("\n".join(yaml_lines), encoding="utf-8")

        if args.wake_karo:
            if os.system("tmux has-session -t multiagent 2>/dev/null") != 0:
                raise SystemExit("tmux session 'multiagent' not found. Start multi-agent first.")
            tmux_send_two_calls("multiagent:0.0", "queue/shogun_to_karo.yaml に新しい指示がある。確認して実行せよ。")

    print(f"Prepared run dir: {run_dir}")
    print(f"Scratch root: {scratch_root}")
    print("Next:")
    print(f"  - Edit/produce research/story under: {run_dir}")
    print("  - Then scaffold scenes with:")
    print(f"      python scripts/toc-scene-series.py \"{topic_raw}\" --run-dir \"{run_dir}\" --dry-run")


if __name__ == "__main__":
    main()
