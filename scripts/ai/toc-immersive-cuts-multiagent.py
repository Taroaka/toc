#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
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


CANONICAL_SEMANTIC_KEYS = frozenset(
    {
        "scene_event",
        "scene_cut_coverage_plan",
        "cut_contract",
        "source_event_contract",
        "event_context_for_cut",
        "first_frame_visual_plan",
        "drawable_prompt_ir",
    }
)
CANONICAL_ROUTE_HINT = (
    "Use the canonical p400/create route: /api/image-gen/runs/create or "
    "python scripts/toc-create-run-headless.py."
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    block = "\n".join(lines) + "\n---\n"
    if state_path.exists():
        state_path.write_text(state_path.read_text(encoding="utf-8") + block, encoding="utf-8")
        return
    state_path.write_text(block, encoding="utf-8")


def tmux_send(target: str, message: str) -> None:
    subprocess.run(["tmux", "send-keys", "-t", target, message], check=True)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], check=True)


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


def _load_manifest(manifest_path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    data = yaml.safe_load(y)
    if not isinstance(data, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")
    return data


def _canonical_semantic_paths(value: object, *, path: str = "$manifest") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in CANONICAL_SEMANTIC_KEYS:
                found.append(child_path)
            found.extend(_canonical_semantic_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_canonical_semantic_paths(child, path=f"{path}[{index}]"))
    return found


def _assert_legacy_manifest_allowed(manifest: dict, *, explicit_opt_in: bool) -> None:
    canonical_paths = _canonical_semantic_paths(manifest)
    if canonical_paths:
        markers = ", ".join(canonical_paths[:4])
        suffix = " ..." if len(canonical_paths) > 4 else ""
        raise SystemExit(
            "Canonical semantic manifest detected "
            f"({markers}{suffix}). This legacy raw-prompt scaffold cannot preserve "
            f"semantic cut projection or review contracts. {CANONICAL_ROUTE_HINT}"
        )
    if not explicit_opt_in:
        raise SystemExit(
            "This command is a legacy fixed-cut raw-prompt scaffold. Re-run with "
            "--legacy-fixed-cut-scaffold only for a non-canonical legacy manifest. "
            f"{CANONICAL_ROUTE_HINT}"
        )


def _default_cut_skeleton(scene_id: int, cut_id: int) -> dict:
    return {
        "cut_id": int(cut_id),
        "image_generation": {
            "tool": "codex_builtin_image",
            "character_ids": [],
            "object_ids": [],
            "prompt": (
                "[TODO]\n"
                f"Scene {scene_id} / Cut {cut_id}: 具体的でシネマティックな画像プロンプトを書く（日本語）。\n"
                "- 視点（POV/三人称）は目的に応じて選び、1カット内でブレさせない。\n"
                "- 目的/場所/アクション/構図/カメラを明示。\n"
                "- 画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。\n"
                "- 固定の乗り物/デバイスを前提にしない。\n"
            ),
            "output": f"assets/scenes/scene{scene_id:02d}_cut{cut_id:02d}.png",
            "aspect_ratio": "16:9",
            "image_size": "2K",
            "references": [],
        },
    }


def _validate_existing_scratch_count(
    path: Path,
    *,
    expected_scene_id: int,
    requested_cut_count: int,
) -> None:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Invalid existing scratch {path.name}: invalid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid existing scratch {path.name}: root must be a mapping")
    scene_id = data.get("scene_id")
    if isinstance(scene_id, bool) or not isinstance(scene_id, int):
        raise SystemExit(f"Invalid existing scratch {path.name}: scene_id must be an integer")
    if scene_id != expected_scene_id:
        raise SystemExit(
            f"Invalid existing scratch {path.name}: payload scene_id {scene_id} does not match "
            f"target scene_id {expected_scene_id}"
        )
    cuts = data.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise SystemExit(f"Invalid existing scratch {path.name}: cuts must be a non-empty list")
    if len(cuts) != requested_cut_count:
        raise SystemExit(
            f"Existing scratch {path.name} contains {len(cuts)} cuts but requested "
            f"--cut-count {requested_cut_count}. Preserve the file and rerun with its actual "
            "count, or move it aside before creating a new scaffold."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare legacy fixed-cut raw-prompt scratch files (non-canonical only)."
    )
    parser.add_argument("--run-dir", required=True, help="Existing immersive run dir (contains video_manifest.md).")
    parser.add_argument("--scene-ids", default=None, help='Comma-separated scene ids to prepare (default: auto from manifest).')
    parser.add_argument(
        "--start-scene-id",
        type=int,
        default=None,
        help="Prepare scenes with id >= this (default: auto-detect from manifest story scenes).",
    )
    parser.add_argument(
        "--legacy-fixed-cut-scaffold",
        action="store_true",
        help="Explicitly opt in to this non-canonical legacy raw-prompt workflow.",
    )
    parser.add_argument(
        "--cut-count",
        type=int,
        default=None,
        help="Required explicit number of legacy scratch cuts to create per scene.",
    )
    parser.add_argument("--write-command", action="store_true", help="Write queue/shogun_to_karo.yaml command entry.")
    parser.add_argument("--wake-karo", action="store_true", help="tmux send-keys to wake karo after writing command.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest = _load_manifest(manifest_path)
    _assert_legacy_manifest_allowed(
        manifest,
        explicit_opt_in=bool(args.legacy_fixed_cut_scaffold),
    )
    if args.cut_count is None or int(args.cut_count) < 1:
        raise SystemExit("--cut-count must be explicitly provided as a positive integer.")

    manifest_scenes = [scene for scene in manifest["scenes"] if isinstance(scene, dict)]
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

    scratch_dir = run_dir / "scratch" / "cuts"
    for sid in targets:
        existing_path = scratch_dir / f"scene{sid:02d}.yaml"
        if existing_path.exists():
            _validate_existing_scratch_count(
                existing_path,
                expected_scene_id=int(sid),
                requested_cut_count=int(args.cut_count),
            )
    scratch_dir.mkdir(parents=True, exist_ok=True)

    for sid in targets:
        p = scratch_dir / f"scene{sid:02d}.yaml"
        if p.exists():
            continue
        skeleton = {
            "scene_id": int(sid),
            "cuts": [
                _default_cut_skeleton(int(sid), int(cut_id))
                for cut_id in range(1, int(args.cut_count) + 1)
            ],
        }
        if yaml is None:
            # Minimal YAML without PyYAML (fallback). Keep it human-editable.
            lines: list[str] = []
            lines.append(f"scene_id: {sid}")
            lines.append("cuts:")
            for cut_id in range(1, int(args.cut_count) + 1):
                out = f"assets/scenes/scene{sid:02d}_cut{cut_id:02d}.png"
                lines.extend(
                    [
                        f"  - cut_id: {cut_id}",
                        "    image_generation:",
                        "      tool: codex_builtin_image",
                        "      character_ids: []",
                        "      object_ids: []",
                        "      prompt: |",
                        f"        [TODO] Scene {sid} / Cut {cut_id}: 具体的でシネマティックな画像プロンプトを書く（日本語）。",
                        "        - 視点（POV/三人称）は目的に応じて選び、1カット内でブレさせない。",
                        "        - 目的/場所/アクション/構図/カメラを明示。",
                        "        - 画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。",
                        "        - 固定の乗り物/デバイスを前提にしない。",
                        f"      output: {out}",
                        "      aspect_ratio: '16:9'",
                        "      image_size: 2K",
                        "      references: []",
                    ]
                )
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            p.write_text(yaml.safe_dump(skeleton, sort_keys=False, allow_unicode=True), encoding="utf-8")

    state_path = run_dir / "state.txt"
    if state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "runtime.stage": "immersive_cuts_prepare",
                "immersive.cuts.scratch_dir": str(scratch_dir),
                "immersive.cuts.targets": ",".join(str(s) for s in targets),
                "immersive.cuts.mode": "legacy_fixed_cut_scaffold",
                "immersive.cuts.legacy_cut_count": str(args.cut_count),
            },
        )

    if args.write_command:
        repo_root = Path.cwd().resolve()
        queue_dir = repo_root / "queue"
        if not queue_dir.exists():
            raise SystemExit(f"queue/ not found at {queue_dir}. Run scripts/ai/multiagent.sh first (it creates/symlinks queue/).")

        cmd_id = f"toc_immersive_cuts_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        playbook = (repo_root / "workflow/multiagent-immersive-cuts-playbook.md").resolve()
        yaml_lines = [
            "queue:",
            f"  - id: {cmd_id}",
            f'    timestamp: "{now_iso()}"',
            '    command: "Legacy/non-canonical ToC cuts scaffold: each agent owns one scene scratch/cuts/sceneXX.yaml. Single-writer runs the legacy merge script, then the user runs immersive generate."',
            "    project: toc",
            "    priority: high",
            "    status: pending",
            "    params:",
            f'      run_dir: "{str(run_dir)}"',
            f'      manifest: "{str(manifest_path)}"',
            f'      scratch_dir: "{str(scratch_dir)}"',
            f'      targets: "{",".join(str(s) for s in targets)}"',
            f'      legacy_cut_count: "{int(args.cut_count)}"',
            f'      playbook: "{str(playbook)}"',
            "",
        ]
        (queue_dir / "shogun_to_karo.yaml").write_text("\n".join(yaml_lines), encoding="utf-8")

        if args.wake_karo:
            if subprocess.run(["tmux", "has-session", "-t", "multiagent"], check=False).returncode != 0:
                raise SystemExit("tmux session 'multiagent' not found. Start multi-agent first.")
            tmux_send("multiagent:0.0", "queue/shogun_to_karo.yaml に新しい指示がある。確認して実行せよ。")

    print(f"Run dir: {run_dir}")
    print(f"Prepared scratch: {scratch_dir}")
    print("Targets:", ",".join(str(s) for s in targets))
    print("次（並列）: scene担当は scratch/cuts/sceneXX.yaml を編集する。")
    print("次（single-writer）:")
    print(
        "  python scripts/ai/merge-immersive-cuts.py "
        f'--run-dir "{run_dir}" --legacy-fixed-cut-scaffold'
    )


if __name__ == "__main__":
    main()
