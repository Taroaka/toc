#!/usr/bin/env python3
"""
Create a 9:16 vertical short (~60s) from an approved ToC run video (16:9).

This script:
- Reads approval from output/<topic>_<timestamp>/state.txt (review.video.status=approved)
- Uses timestamps from video_manifest.md (```yaml) to cut scene ranges from video.mp4
- Center-crops to 9:16 and scales to 1080x1920
- Concatenates segments into a single short mp4
- Appends artifact + stage to state.txt on success
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file as _parse_canonical_state


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def _safe_load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_timecode(s: str) -> int:
    s = s.strip()
    parts = s.split(":")
    if len(parts) == 2:
        mm, ss = parts
        return int(mm) * 60 + int(ss)
    if len(parts) == 3:
        hh, mm, ss = parts
        return int(hh) * 3600 + int(mm) * 60 + int(ss)
    raise ValueError(f"Unsupported timecode: {s}")


def parse_timestamp_range(ts_range: str) -> tuple[int, int]:
    raw = ts_range.strip().strip('"').strip("'")
    if "-" not in raw:
        raise ValueError(f"Unsupported timestamp range: {ts_range}")
    start_s, end_s = raw.split("-", 1)
    start = parse_timecode(start_s)
    end = parse_timecode(end_s)
    if end <= start:
        raise ValueError(f"Invalid timestamp range: {ts_range}")
    return start, end


def parse_state_file(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    return _parse_canonical_state(state_path)


def _resolve_artifact_path(run_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else (run_dir / p)


def require_approved(state: dict[str, str], run_dir: Path) -> None:
    hybrid_gate = state.get("gate.hybridization_review", "").strip().lower()
    hybrid_status = state.get("review.hybridization.status", "").strip().lower()
    if hybrid_gate == "required" and hybrid_status != "approved":
        msg = [
            f"Hybridization review required but not approved: review.hybridization.status={state.get('review.hybridization.status', '')!r}",
            "Approve it first, e.g.:",
            f"  python scripts/toc-state.py approve-hybridization --run-dir {run_dir} --note \"OK\"",
        ]
        raise SystemExit("\n".join(msg))

    status = state.get("review.video.status", "").strip().lower()
    if status != "approved":
        msg = [
            f"Not approved yet: review.video.status={state.get('review.video.status', '')!r}",
            "Approve it first, e.g.:",
            f"  python scripts/toc-state.py approve-video --run-dir {run_dir} --note \"OK\"",
        ]
        raise SystemExit("\n".join(msg))


def ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def load_scene_ranges(manifest_path: Path) -> dict[int, tuple[int, int]]:
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    data = _safe_load_yaml(y)
    scenes = data.get("scenes")
    out: dict[int, tuple[int, int]] = {}
    if not isinstance(scenes, list):
        return out
    for s in scenes:
        if not isinstance(s, dict):
            continue
        scene_id = s.get("scene_id")
        ts = s.get("timestamp")
        try:
            sid = int(scene_id)
        except Exception:
            continue
        if not ts:
            continue
        try:
            out[sid] = parse_timestamp_range(str(ts))
        except Exception:
            continue
    return out


def crop_filter_9x16_center() -> str:
    # Crop width = min(iw, ih*9/16) to be safe for non-16:9 inputs.
    # Center crop horizontally, keep full height.
    # Note: comma inside min() must be escaped as \, in ffmpeg expressions.
    return r"crop=min(iw\,ih*9/16):ih:(iw-min(iw\,ih*9/16))/2:0,scale=1080:1920"


def main() -> int:
    parser = argparse.ArgumentParser(description="Make a vertical (9:16) short from an approved run video.")
    parser.add_argument("--run-dir", required=True, help="output/<topic>_<timestamp> directory")
    parser.add_argument("--scene-ids", required=True, help="Comma-separated scene ids (e.g. 10,20,30)")
    parser.add_argument("--out", default=None, help="Output mp4 path (default: <run-dir>/shorts/short01.mp4)")
    parser.add_argument("--duration-seconds", type=int, default=60, help="Max total duration (default: 60)")
    parser.add_argument("--manifest", default=None, help="Manifest path (default: <run-dir>/video_manifest.md)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, do not call ffmpeg or write files.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    manifest_path = Path(args.manifest) if args.manifest else (run_dir / "video_manifest.md")
    state_path = run_dir / "state.txt"

    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    state = parse_state_file(state_path)
    require_approved(state, run_dir)

    video_path = _resolve_artifact_path(run_dir, state.get("artifact.video")) or (run_dir / "video.mp4")
    if not video_path.exists():
        raise SystemExit(f"Video not found: {video_path}")

    out_path = Path(args.out) if args.out else (run_dir / "shorts" / "short01.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scene_ids = [int(x.strip()) for x in str(args.scene_ids).split(",") if x.strip()]
    if not scene_ids:
        raise SystemExit("--scene-ids is required")

    ranges = load_scene_ranges(manifest_path)
    missing = [sid for sid in scene_ids if sid not in ranges]
    if missing:
        raise SystemExit(f"Missing timestamp for scene_id(s): {missing} in {manifest_path}")

    segments: list[dict] = []
    remaining = int(args.duration_seconds)
    for sid in scene_ids:
        start, end = ranges[sid]
        seg_len = end - start
        if remaining <= 0:
            break
        if seg_len > remaining:
            end = start + remaining
            seg_len = end - start
        segments.append({"scene_id": sid, "start": start, "end": end, "duration": seg_len})
        remaining -= seg_len

    if args.dry_run:
        print(json.dumps({"video": str(video_path), "out": str(out_path), "segments": segments}, ensure_ascii=False))
        return 0

    if not ffmpeg_exists():
        raise SystemExit("ffmpeg not found. Please install ffmpeg.")

    with tempfile.TemporaryDirectory(prefix="toc_short_") as td:
        tmp = Path(td)
        seg_files: list[Path] = []
        vf = crop_filter_9x16_center()

        for i, seg in enumerate(segments):
            seg_out = tmp / f"seg_{i:02d}.mp4"
            seg_files.append(seg_out)
            run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(video_path),
                    "-ss",
                    str(seg["start"]),
                    "-t",
                    str(seg["duration"]),
                    "-vf",
                    vf,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(seg_out),
                ]
            )

        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join([f"file '{p.as_posix()}'" for p in seg_files]) + "\n",
            encoding="utf-8",
        )

        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(out_path),
            ]
        )

    subprocess.run(
        [
            sys.executable,
            "scripts/toc-state.py",
            "append",
            "--run-dir",
            str(run_dir),
            "--set",
            "runtime.stage=shorts",
            "--set",
            f"artifact.video.short.01={out_path.resolve()}",
        ],
        check=True,
    )

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
