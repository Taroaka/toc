#!/usr/bin/env python3
"""Freeze current p750 narration and completed p860 BGM/SE into render inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.image_gen_app import (
    RenderFreezeRequest,
    RenderInputItem,
    _dict_value,
    _float_value,
    _freeze_render_inputs,
    _int_value,
    _manifest_scene_targets,
    _read_manifest_data,
    _require_narration_ready_for_video,
)
from toc.runtime_locks import sync_file_lock


def freeze_approved_render_inputs(run_dir: Path, *, output: str) -> dict:
    lock_path = run_dir / ".locks" / "run_artifacts.lock"
    with sync_file_lock(lock_path):
        _require_narration_ready_for_video(run_dir)
        _manifest_path, _original, data = _read_manifest_data(run_dir)
        items: list[RenderInputItem] = []
        for target in _manifest_scene_targets(data):
            node = _dict_value(target.get("cut"))
            render = _dict_value(node.get("render"))
            generation = _dict_value(node.get("video_generation"))
            duration = _int_value(
                render.get("video_duration_seconds") or generation.get("duration_seconds"),
            )
            if duration <= 0:
                raise ValueError(f"p750 timeline has no positive duration: {target['selector']}")
            items.append(
                RenderInputItem(
                    item_id=str(target["selector"]),
                    video_path=None,
                    narration_path=None,
                    video_duration_seconds=duration,
                    narration_offset_seconds=_float_value(render.get("narration_offset_seconds")),
                )
            )
        if not items:
            raise ValueError("p750 timeline has no renderable narration cuts")
        request = RenderFreezeRequest(run_id=run_dir.name, items=items, output=output)
        return _freeze_render_inputs(run_dir, request, snapshot_id=uuid.uuid4().hex)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default="video.mp4")
    parser.add_argument("--check-sound-only", action="store_true", help="Return 3 while p860 needs user action; do not freeze")
    parser.add_argument("--verify-sound-snapshot", type=Path, help="Verify that rendered BGM/SE still matches the current approved inputs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not (run_dir / "video_manifest.md").is_file():
        raise SystemExit(f"video_manifest.md not found: {run_dir}")
    if args.verify_sound_snapshot:
        from server.sound_design_api import freeze as freeze_sound
        snapshot = json.loads(args.verify_sound_snapshot.read_text())
        current = freeze_sound(run_dir, _read_manifest_data(run_dir)[2])
        if snapshot["sound_hash"] != current["sound_hash"]:
            raise SystemExit("BGM・SEまたは動画がレンダー中に変更されました。再結合してください")
        return 0
    if args.check_sound_only:
        from server.sound_design_api import read_status
        from toc.harness import append_state_snapshot
        status = read_status(run_dir)
        if not status["ready"]:
            append_state_snapshot(run_dir / "state.txt", {
                "status": "P860", "runtime.stage": "sound_design",
                "slot.p860.status": "awaiting_approval", "slot.p860.requirement": "required",
                "slot.p860.note": status["blockedReason"] or "BGM・SEの設定確定を待っています",
            })
        print(json.dumps({"ready": status["ready"], "message": status["blockedReason"] or "p860 BGM・SEを確認してください"}, ensure_ascii=False))
        return 0 if status["ready"] else 3
    try:
        result = freeze_approved_render_inputs(run_dir, output=args.output)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
