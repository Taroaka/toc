#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.immersive_manifest import default_story_scene_start, story_scene_ids


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def _as_int(v) -> int | None:
    try:
        return int(v)
    except Exception:
        return None


def _load_scene_ids(manifest_path: Path) -> list[dict]:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    data = yaml.safe_load(y)
    if not isinstance(data, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    raw_scenes = data.get("scenes") or []
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")
    return [scene for scene in raw_scenes if isinstance(scene, dict)]


def _parse_scene_ids(scene_ids_csv: str | None) -> list[int] | None:
    if not scene_ids_csv:
        return None
    out: list[int] = []
    for raw in scene_ids_csv.split(","):
        s = raw.strip()
        if not s:
            continue
        out.append(int(s))
    return out or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare per-scene narration scratch files for immersive manifests (multi-agent safe).")
    parser.add_argument("--run-dir", required=True, help="Existing immersive run dir (contains video_manifest.md).")
    parser.add_argument("--scene-ids", default=None, help='Comma-separated scene ids to prepare (default: auto from manifest).')
    parser.add_argument(
        "--start-scene-id",
        type=int,
        default=None,
        help="Prepare scenes with id >= this (default: auto-detect from manifest story scenes).",
    )
    parser.add_argument("--min-cuts", type=int, default=3, help="Default number of cuts per scene (used only when scratch is created).")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest_scenes = _load_scene_ids(manifest_path)
    available_story_scene_ids = set(story_scene_ids(manifest_scenes))
    requested = _parse_scene_ids(args.scene_ids)
    scene_ids = requested if requested is not None else sorted(available_story_scene_ids)
    start_scene_id = (
        int(args.start_scene_id)
        if args.start_scene_id is not None
        else default_story_scene_start(manifest_scenes)
    )
    targets = sorted({sid for sid in scene_ids if int(sid) >= start_scene_id and int(sid) in available_story_scene_ids})
    if not targets:
        raise SystemExit("No target scenes found. Check --scene-ids / --start-scene-id.")

    scratch_dir = run_dir / "scratch" / "narration"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    for sid in targets:
        p = scratch_dir / f"scene{sid:02d}.yaml"
        if p.exists():
            continue
        skeleton = {
            "scene_id": int(sid),
            "cuts": [{"cut_id": i, "narration_text": ""} for i in range(1, int(args.min_cuts) + 1)],
            "notes": [
                "narration_text は TTS にそのまま送られる。TODO/メタ情報を書かない。",
                "1カット=1ナレーション。main=5–15秒、sub=3–15秒を目安に短く。",
            ],
        }
        if yaml is None:
            lines: list[str] = []
            lines.append(f"scene_id: {sid}")
            lines.append("cuts:")
            for i in range(1, int(args.min_cuts) + 1):
                lines += [f"  - cut_id: {i}", "    narration_text: \"\""]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            p.write_text(yaml.safe_dump(skeleton, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print(f"Run dir: {run_dir}")
    print(f"Prepared scratch: {scratch_dir}")
    print("Targets:", ",".join(str(s) for s in targets))
    print("次（並列）: scene担当は scratch/narration/sceneXX.yaml を編集する。")
    print("次（single-writer）:")
    print(f'  python scripts/ai/merge-immersive-narration.py --run-dir "{run_dir}"')


if __name__ == "__main__":
    main()
