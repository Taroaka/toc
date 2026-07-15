#!/usr/bin/env python3
"""Gate a rendered final video against the shared ToC duration contract."""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, load_structured_document, now_iso, parse_state_file  # noqa: E402
from toc.story_duration import MINIMUM_EFFECTIVE_RATIO, audit_duration, normalize_target_duration  # noqa: E402


def _format_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def _probe_duration_seconds(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found; install ffmpeg before final duration validation")
    result = subprocess.run(
        [
            ffprobe,
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
    try:
        return float((result.stdout or "").strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned invalid duration for {path}") from exc


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _target_from_legacy_minimum(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        minimum = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(minimum) or minimum < 0:
        return None
    if minimum == 0:
        return 0
    return int(math.ceil(minimum / MINIMUM_EFFECTIVE_RATIO))


def _manifest_target_seconds(run_dir: Path, explicit: int | None) -> int:
    if explicit is not None:
        return normalize_target_duration(explicit)
    _text, manifest = load_structured_document(run_dir / "video_manifest.md")
    metadata = manifest.get("video_metadata") if isinstance(manifest, dict) else None
    raw_target = metadata.get("target_duration_seconds") if isinstance(metadata, dict) else None
    if raw_target is not None:
        return normalize_target_duration(raw_target)

    state = parse_state_file(run_dir / "state.txt")
    for key in ("runtime.target_video_seconds", "runtime.duration_gate.target_seconds"):
        value = _as_int(state.get(key))
        if value is not None:
            return normalize_target_duration(value)

    script_path = run_dir / "script.md"
    if script_path.is_file():
        _script_text, script = load_structured_document(script_path)
    else:
        script = {}
    script_metadata = script.get("script_metadata") if isinstance(script, dict) else None
    if isinstance(script_metadata, dict):
        for key in ("target_duration_seconds", "target_duration"):
            value = _as_int(script_metadata.get(key))
            if value is not None:
                return normalize_target_duration(value)

    if isinstance(metadata, dict):
        target = _target_from_legacy_minimum(metadata.get("minimum_duration_seconds"))
        if target is not None:
            return normalize_target_duration(target)
    target = _target_from_legacy_minimum(state.get("runtime.duration_gate.minimum_seconds"))
    if target is not None:
        return normalize_target_duration(target)
    return normalize_target_duration(None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check final video runtime against 80% of the target duration.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--target-duration-seconds", type=int, default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    video_path = Path(args.video)
    if not video_path.is_absolute():
        video_path = run_dir / video_path
    if not video_path.is_file():
        raise SystemExit(f"Final video not found: {video_path}")

    try:
        target_seconds = _manifest_target_seconds(run_dir, args.target_duration_seconds)
        actual_seconds = _probe_duration_seconds(video_path)
        audit = audit_duration(
            target_seconds=target_seconds,
            actual_seconds=actual_seconds,
            measurement_layer="final_video",
        )
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc

    common = {
        "review.final.duration_fit.status": audit.status,
        "review.final.duration_fit.target_seconds": str(audit.target_seconds),
        "review.final.duration_fit.minimum_seconds": _format_seconds(audit.minimum_seconds),
        "review.final.duration_fit.actual_seconds": _format_seconds(audit.actual_seconds),
        "review.final.duration_fit.ratio": f"{audit.ratio:.6f}",
        "review.final.duration_fit.measurement_layer": audit.measurement_layer,
        "review.final.duration_fit.at": now_iso(),
    }
    if audit.passed:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **common,
                "status": "P930",
                "runtime.stage": "final_render_ready_for_qa",
                "slot.p920.status": "done",
                "slot.p920.note": "final video rendered and duration gate passed",
                "slot.p930.status": "awaiting_approval",
                "slot.p930.note": "final QA ready in frontend",
            },
        )
        print(
            f"[pass] final video {_format_seconds(actual_seconds)}s meets minimum "
            f"{_format_seconds(audit.minimum_seconds)}s"
        )
        return 0

    append_state_snapshot(
        run_dir / "state.txt",
        {
            **common,
            "runtime.stage": "final_render_duration_failed",
            "slot.p920.status": "failed",
            "slot.p920.note": "final video is shorter than 80% of target",
            "slot.p930.status": "blocked",
            "slot.p930.note": "blocked by final video duration gate",
        },
    )
    print(
        f"[fail] final video {_format_seconds(actual_seconds)}s is below minimum "
        f"{_format_seconds(audit.minimum_seconds)}s"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
