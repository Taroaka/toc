#!/usr/bin/env python3
"""
Sync cut/scene durations and timestamps in a `video_manifest.md` from actual narration audio lengths.

Intended workflow:
1) Generate audio-only:
   python scripts/generate-assets-from-manifest.py --manifest ... --skip-images --skip-videos
2) Sync durations:
   python scripts/sync-manifest-durations-from-audio.py --manifest ...
3) Generate images/videos using the updated durations.

Notes:
- Uses `ffprobe` to read audio duration.
- Updates `video_generation.duration_seconds` from `audio duration + padding` (ceil by default).
- Updates `scenes[].timestamp` sequentially (00:00-...).
"""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def replace_yaml_block(text: str, new_yaml: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    start, end = m.span(1)
    return text[:start] + new_yaml.rstrip("\n") + text[end:]


def _as_opt_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    return s if s.strip() != "" else None


def _resolve_path(base_dir: Path, maybe_path: str | None) -> Path | None:
    if not maybe_path:
        return None
    p = Path(maybe_path)
    return p if p.is_absolute() else (base_dir / p)


def _mmss(total_seconds: int) -> str:
    s = max(0, int(total_seconds))
    m = s // 60
    r = s % 60
    return f"{m:02d}:{r:02d}"


def _ffprobe_duration_seconds(path: Path) -> float:
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:  # pragma: no cover
        raise SystemExit("ffprobe not found. Please install ffmpeg (ffprobe).") from e
    except subprocess.CalledProcessError as e:
        raise SystemExit((e.stderr or "").strip() or f"ffprobe failed for: {path}") from e

    raw = (res.stdout or "").strip()
    try:
        return float(raw)
    except Exception as e:
        raise SystemExit(f"ffprobe returned invalid duration for {path}: {raw!r}") from e


def _role_bounds(*, role: str) -> tuple[int, int]:
    r = (role or "").strip().lower()
    if r == "sub":
        return (3, 15)
    return (5, 15)


def _infer_cut_role(*, cut: dict, cut_index: int, cut_count: int) -> str:
    v = _as_opt_str(cut.get("cut_role"))
    if v:
        return v
    # Default heuristic: single cut => main, otherwise first is main, rest sub.
    if cut_count <= 1:
        return "main"
    return "main" if cut_index == 0 else "sub"


def _padding_preset_seconds(*, preset: str, args: argparse.Namespace) -> float:
    p = (preset or "").strip().lower()
    if p in {"linger", "lingering", "余韻"}:
        return float(args.linger_padding_seconds)
    if p in {"tempo", "sub", "テンポ", "サブ"}:
        return float(args.sub_padding_seconds)
    return float(args.default_padding_seconds)


def _resolve_padding_seconds(*, container: dict, role: str, args: argparse.Namespace) -> float:
    explicit = container.get("duration_padding_seconds")
    if explicit is not None:
        try:
            return max(0.0, float(explicit))
        except Exception:
            raise SystemExit(f"Invalid duration_padding_seconds: {explicit!r}")

    preset = _as_opt_str(container.get("duration_padding_preset"))
    if preset:
        return _padding_preset_seconds(preset=preset, args=args)

    r = (role or "").strip().lower()
    if r in {"sub", "tempo"}:
        return float(args.sub_padding_seconds)
    if r in {"linger", "lingering"}:
        return float(args.linger_padding_seconds)
    return float(args.default_padding_seconds)


def _round_duration(seconds: float, *, mode: str) -> int:
    m = (mode or "").strip().lower()
    if m == "round":
        return int(round(seconds))
    if m == "floor":
        return int(math.floor(seconds))
    # default: ceil (never shorter than narration)
    return int(math.ceil(seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync manifest durations/timestamps from narration audio lengths.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--base-dir", default=None, help="Resolve relative asset paths from this dir (default: manifest dir).")
    parser.add_argument("--rounding", choices=["ceil", "round", "floor"], default="ceil")
    parser.add_argument(
        "--default-padding-seconds",
        type=float,
        default=1.0,
        help="Padding added to narration duration for normal/main cuts.",
    )
    parser.add_argument(
        "--sub-padding-seconds",
        type=float,
        default=0.5,
        help="Padding added to narration duration for sub/tempo cuts.",
    )
    parser.add_argument(
        "--linger-padding-seconds",
        type=float,
        default=1.5,
        help="Padding added to narration duration for lingering cuts.",
    )
    parser.add_argument("--no-backup", action="store_true", help="Do not create video_manifest.md.bak before writing.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes only; do not write.")
    parser.add_argument(
        "--skip-missing-audio",
        action="store_true",
        help="Skip cuts/scenes whose narration audio file is missing (default: error).",
    )
    args = parser.parse_args()

    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    base_dir = Path(args.base_dir) if args.base_dir else manifest_path.parent
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    manifest = yaml.safe_load(y)
    if not isinstance(manifest, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")

    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")

    cursor = 0
    total_video_seconds = 0
    changed = 0

    def update_one_duration(*, container: dict, role: str, audio_out: str, key_path: str) -> int | None:
        nonlocal changed
        audio_path = _resolve_path(base_dir, audio_out)
        if not audio_path:
            return None
        if not audio_path.exists():
            if args.skip_missing_audio:
                print(f"[skip] missing audio: {audio_path}")
                return None
            raise SystemExit(f"Missing narration audio: {audio_path}")

        dur_f = _ffprobe_duration_seconds(audio_path)
        min_s, max_s = _role_bounds(role=role)
        if dur_f > max_s:
            raise SystemExit(f"{key_path}: narration is {dur_f:.2f}s (> {max_s}s). Split into multiple cuts.")
        padding_seconds = _resolve_padding_seconds(container=container, role=role, args=args)
        target_f = max(0.0, dur_f + padding_seconds)
        dur_i = max(0, _round_duration(target_f, mode=args.rounding))
        if dur_i < min_s:
            # Allow padding the visual duration up to min.
            dur_i = min_s
        if dur_i > max_s:
            dur_i = max_s

        vg = container.get("video_generation")
        if not isinstance(vg, dict):
            # No video to sync.
            return None
        prev = vg.get("duration_seconds")
        if prev != dur_i:
            print(
                f"[update] {key_path}: duration_seconds {prev!r} -> {dur_i} "
                f"(audio={dur_f:.2f}s, padding={padding_seconds:.2f}s, role={role})"
            )
            vg["duration_seconds"] = int(dur_i)
            changed += 1
        return int(dur_i)

    for scene in scenes:
        if not isinstance(scene, dict):
            continue

        scene_start = cursor
        scene_video_seconds = 0

        raw_cuts = scene.get("cuts")
        if isinstance(raw_cuts, list) and raw_cuts:
            cut_count = len(raw_cuts)
            for idx, cut in enumerate(raw_cuts):
                if not isinstance(cut, dict):
                    continue

                audio = cut.get("audio")
                narration = audio.get("narration") if isinstance(audio, dict) else None
                narration_out = _as_opt_str(narration.get("output")) if isinstance(narration, dict) else None
                if not narration_out:
                    continue

                role = _infer_cut_role(cut=cut, cut_index=idx, cut_count=cut_count)
                sid = scene.get("scene_id")
                cid = cut.get("cut_id")
                dur = update_one_duration(
                    container=cut,
                    role=role,
                    audio_out=narration_out,
                    key_path=f"scene{sid}_cut{cid}",
                )
                if dur is not None:
                    scene_video_seconds += int(dur)
        else:
            audio = scene.get("audio")
            narration = audio.get("narration") if isinstance(audio, dict) else None
            narration_out = _as_opt_str(narration.get("output")) if isinstance(narration, dict) else None
            if narration_out:
                sid = scene.get("scene_id")
                dur = update_one_duration(container=scene, role="main", audio_out=narration_out, key_path=f"scene{sid}")
                if dur is not None:
                    scene_video_seconds += int(dur)

        if scene_video_seconds > 0:
            cursor += scene_video_seconds
            scene["timestamp"] = f"{_mmss(scene_start)}-{_mmss(cursor)}"
            total_video_seconds = cursor
        else:
            # Keep timestamp null/unchanged for non-video scenes (e.g. reference images).
            pass

    vm = manifest.get("video_metadata")
    if isinstance(vm, dict):
        prev_total = vm.get("duration_seconds")
        if prev_total != total_video_seconds:
            print(f"[update] video_metadata.duration_seconds {prev_total!r} -> {total_video_seconds}")
            vm["duration_seconds"] = int(total_video_seconds)
            changed += 1

    if args.dry_run:
        print(f"Planned changes: {changed}")
        return

    if changed == 0:
        print("No changes.")
        return

    new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    if not args.no_backup:
        shutil.copy2(manifest_path, manifest_path.with_suffix(".md.bak"))
    manifest_path.write_text(replace_yaml_block(md, new_yaml), encoding="utf-8")
    print(f"Updated manifest: {manifest_path}")


if __name__ == "__main__":
    main()
