#!/usr/bin/env python3
"""Materialize render lists from the current revision-aware p750 approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


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
        return _freeze_render_inputs(run_dir, request)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default="video.mp4")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not (run_dir / "video_manifest.md").is_file():
        raise SystemExit(f"video_manifest.md not found: {run_dir}")
    try:
        result = freeze_approved_render_inputs(run_dir, output=args.output)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
