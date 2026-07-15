#!/usr/bin/env python3
"""Check whether actual audio-synced runtime meets the minimum duration target."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.duration_fit_review import (  # noqa: E402
    build_duration_narration_review_prompt,
    build_duration_scene_review_prompt,
    write_review_prompt,
)
from toc.grounding import detect_flow  # noqa: E402
from toc.harness import append_state_snapshot, load_structured_document, now_iso, parse_state_file  # noqa: E402
from toc.story_duration import (  # noqa: E402
    MINIMUM_EFFECTIVE_RATIO,
    ManifestRuntimeMeasurement,
    audit_duration,
    measure_manifest_runtime,
)


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: float | int) -> str:
    numeric = float(value)
    if math.isfinite(numeric) and numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.6f}".rstrip("0").rstrip(".")


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


def _ffprobe_duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        duration = float(result.stdout.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, TypeError, ValueError):
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def _resolve_target_seconds(
    *,
    state: dict[str, str],
    manifest_data: dict[str, object],
    script_data: dict[str, object],
    explicit: int | None,
) -> int:
    if explicit is not None:
        return max(0, explicit)

    video_metadata = manifest_data.get("video_metadata")
    if isinstance(video_metadata, dict):
        value = _as_int(video_metadata.get("target_duration_seconds"))
        if value is not None:
            return max(0, value)

    for key in (
        "runtime.target_video_seconds",
        "runtime.duration_gate.target_seconds",
    ):
        value = _as_int(state.get(key))
        if value is not None:
            return max(0, value)

    script_metadata = script_data.get("script_metadata")
    if isinstance(script_metadata, dict):
        for key in ("target_duration_seconds", "target_duration"):
            value = _as_int(script_metadata.get(key))
            if value is not None:
                return max(0, value)

    if isinstance(video_metadata, dict):
        target = _target_from_legacy_minimum(video_metadata.get("minimum_duration_seconds"))
        if target is not None:
            return target

    target = _target_from_legacy_minimum(state.get("runtime.duration_gate.minimum_seconds"))
    if target is not None:
        return target

    if isinstance(video_metadata, dict):
        experience = str(video_metadata.get("experience") or "").strip().lower()
        if experience == "cinematic_story":
            return 300

    return 0


def _measurement_state(
    measurement: ManifestRuntimeMeasurement,
    *,
    target_seconds: int,
    minimum_seconds: float,
    ratio: float,
) -> dict[str, str]:
    return {
        "review.duration_fit.target_seconds": str(target_seconds),
        "review.duration_fit.minimum_seconds": _format_number(minimum_seconds),
        "review.duration_fit.actual_seconds": _format_number(measurement.effective_seconds),
        "review.duration_fit.ratio": _format_number(ratio),
        "review.duration_fit.measurement_layer": "manifest_runtime",
        "review.duration_fit.measurement_complete": str(bool(measurement.complete)).lower(),
        "review.duration_fit.spoken_audio_seconds": _format_number(measurement.spoken_audio_seconds),
        "review.duration_fit.intentional_silence_seconds": _format_number(measurement.intentional_silence_seconds),
        "review.duration_fit.audio_timeline_seconds": _format_number(measurement.audio_timeline_seconds),
        "review.duration_fit.video_timeline_seconds": _format_number(measurement.video_timeline_seconds),
        "review.duration_fit.video_timeline_source": str(measurement.video_timeline_source),
        "review.duration_fit.missing_items": json.dumps(measurement.missing_items, ensure_ascii=False),
        "review.duration_fit.invalid_items": json.dumps(measurement.invalid_items, ensure_ascii=False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check actual audio runtime against the minimum target duration.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--run-dir", default=None, help="Run dir (default: manifest parent)")
    parser.add_argument("--target-seconds", type=int, default=None, help="Override target duration in seconds.")
    parser.add_argument(
        "--min-seconds",
        type=int,
        default=None,
        help="Deprecated alias for --target-seconds; the gate minimum is always 80%% of this target.",
    )
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    run_dir = Path(args.run_dir) if args.run_dir else manifest_path.parent
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    _, manifest_data = load_structured_document(manifest_path)
    if not manifest_data:
        raise SystemExit(f"Failed to parse manifest YAML: {manifest_path}")
    _, script_data = load_structured_document(run_dir / "script.md")
    state = parse_state_file(run_dir / "state.txt")

    video_metadata = manifest_data.get("video_metadata")
    if not isinstance(video_metadata, dict):
        raise SystemExit("Manifest is missing video_metadata.")
    if args.target_seconds is not None and args.min_seconds is not None:
        raise SystemExit("Use either --target-seconds or --min-seconds, not both.")
    target_seconds = _resolve_target_seconds(
        state=state,
        manifest_data=manifest_data,
        script_data=script_data,
        explicit=args.target_seconds if args.target_seconds is not None else args.min_seconds,
    )
    measurement = measure_manifest_runtime(
        manifest_data,
        base_dir=manifest_path.parent,
        probe=_ffprobe_duration_seconds,
    )
    actual_seconds = measurement.effective_seconds
    minimum_seconds = target_seconds * MINIMUM_EFFECTIVE_RATIO if target_seconds > 0 else 0.0
    ratio = actual_seconds / target_seconds if target_seconds > 0 else 0.0
    measurement_state = _measurement_state(
        measurement,
        target_seconds=target_seconds,
        minimum_seconds=minimum_seconds,
        ratio=ratio,
    )
    flow = args.flow or detect_flow(run_dir.resolve())

    if target_seconds <= 0:
        if measurement.complete:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    **measurement_state,
                    "review.duration_fit.status": "skipped",
                    "review.duration_fit.note": "no minimum runtime target configured",
                    "review.duration_fit.at": now_iso(),
                    "slot.p740.status": "skipped",
                    "slot.p740.requirement": "optional",
                    "slot.p750.status": "pending",
                },
            )
            print(f"[skip] no minimum runtime target configured (actual={_format_number(actual_seconds)}s)")
            return 0
        audit_passed = False
    else:
        try:
            audit = audit_duration(
                target_seconds=target_seconds,
                actual_seconds=actual_seconds,
                measurement_layer="manifest_runtime",
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        audit_passed = audit.passed

    if measurement.complete and audit_passed:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **measurement_state,
                "review.duration_fit.status": "passed",
                "review.duration_fit.note": "actual audio-driven runtime satisfies the minimum target",
                "review.duration_fit.at": now_iso(),
                "slot.p740.status": "done",
                "slot.p740.requirement": "required",
                "slot.p750.status": "pending",
            },
        )
        print(
            f"[pass] actual runtime {_format_number(actual_seconds)}s meets minimum "
            f"{_format_number(minimum_seconds)}s"
        )
        return 0

    scene_prompt = build_duration_scene_review_prompt(
        run_dir=run_dir,
        minimum_seconds=int(minimum_seconds) if minimum_seconds.is_integer() else minimum_seconds,
        actual_seconds=int(actual_seconds) if actual_seconds.is_integer() else actual_seconds,
        flow=flow,
    )
    scene_prompt_path = write_review_prompt(run_dir=run_dir.resolve(), kind="scene", prompt=scene_prompt)
    narration_prompt = build_duration_narration_review_prompt(
        run_dir=run_dir,
        minimum_seconds=int(minimum_seconds) if minimum_seconds.is_integer() else minimum_seconds,
        actual_seconds=int(actual_seconds) if actual_seconds.is_integer() else actual_seconds,
        flow=flow,
    )
    narration_prompt_path = write_review_prompt(run_dir=run_dir.resolve(), kind="narration", prompt=narration_prompt)

    append_state_snapshot(
        run_dir / "state.txt",
        {
            **measurement_state,
            "review.duration_fit.status": "changes_requested",
            "review.duration_fit.note": (
                "manifest runtime measurement is incomplete"
                if not measurement.complete
                else "actual audio-driven runtime is below the minimum target; run scene and narration stretch review before human review"
            ),
            "review.duration_fit.at": now_iso(),
            "review.duration_fit.scene_prompt": str(scene_prompt_path.relative_to(run_dir.resolve())),
            "review.duration_fit.scene_prompt.generated_at": now_iso(),
            "review.duration_fit.narration_prompt": str(narration_prompt_path.relative_to(run_dir.resolve())),
            "review.duration_fit.narration_prompt.generated_at": now_iso(),
            "slot.p740.status": "failed",
            "slot.p740.requirement": "required",
            "slot.p750.status": "blocked",
        },
    )
    reason = (
        f"measurement is incomplete (missing={len(measurement.missing_items)}, invalid={len(measurement.invalid_items)})"
        if not measurement.complete
        else f"actual runtime {_format_number(actual_seconds)}s is below minimum {_format_number(minimum_seconds)}s"
    )
    print(f"[fail] {reason}\n  scene prompt: {scene_prompt_path}\n  narration prompt: {narration_prompt_path}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
