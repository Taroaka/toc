#!/usr/bin/env python3
"""Check whether actual audio-synced runtime meets the minimum duration target."""

from __future__ import annotations

import argparse
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


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_minimum_seconds(
    *,
    run_dir: Path,
    state: dict[str, str],
    manifest_data: dict[str, object],
    script_data: dict[str, object],
    explicit: int | None,
) -> int:
    if explicit is not None:
        return max(0, explicit)

    for key in ("runtime.duration_gate.minimum_seconds", "runtime.target_video_seconds"):
        value = _as_int(state.get(key))
        if value is not None:
            return max(0, value)

    video_metadata = manifest_data.get("video_metadata")
    if isinstance(video_metadata, dict):
        for key in ("minimum_duration_seconds", "target_duration_seconds"):
            value = _as_int(video_metadata.get(key))
            if value is not None:
                return max(0, value)
        experience = str(video_metadata.get("experience") or "").strip().lower()
        if experience == "cinematic_story":
            return 300

    script_metadata = script_data.get("script_metadata")
    if isinstance(script_metadata, dict):
        value = _as_int(script_metadata.get("target_duration"))
        if value is not None:
            return max(0, value)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check actual audio runtime against the minimum target duration.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--run-dir", default=None, help="Run dir (default: manifest parent)")
    parser.add_argument("--min-seconds", type=int, default=None, help="Override minimum required duration in seconds.")
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
    actual_seconds = _as_int(video_metadata.get("duration_seconds"))
    if actual_seconds is None:
        raise SystemExit("Manifest video_metadata.duration_seconds is missing or invalid.")

    minimum_seconds = _resolve_minimum_seconds(
        run_dir=run_dir,
        state=state,
        manifest_data=manifest_data,
        script_data=script_data,
        explicit=args.min_seconds,
    )
    flow = args.flow or detect_flow(run_dir.resolve())

    if minimum_seconds <= 0:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.duration_fit.status": "skipped",
                "review.duration_fit.actual_seconds": str(actual_seconds),
                "review.duration_fit.minimum_seconds": str(minimum_seconds),
                "review.duration_fit.note": "no minimum runtime target configured",
                "review.duration_fit.at": now_iso(),
                "slot.p540.status": "skipped",
                "slot.p540.requirement": "optional",
                "slot.p550.status": "skipped",
                "slot.p560.status": "skipped",
                "slot.p570.status": "pending",
            },
        )
        print(f"[skip] no minimum runtime target configured (actual={actual_seconds}s)")
        return 0

    if actual_seconds >= minimum_seconds:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.duration_fit.status": "passed",
                "review.duration_fit.actual_seconds": str(actual_seconds),
                "review.duration_fit.minimum_seconds": str(minimum_seconds),
                "review.duration_fit.note": "actual audio-driven runtime satisfies the minimum target",
                "review.duration_fit.at": now_iso(),
                "slot.p540.status": "done",
                "slot.p540.requirement": "required",
                "slot.p550.status": "skipped",
                "slot.p550.requirement": "optional",
                "slot.p560.status": "skipped",
                "slot.p560.requirement": "optional",
                "slot.p570.status": "pending",
            },
        )
        print(f"[pass] actual runtime {actual_seconds}s meets minimum {minimum_seconds}s")
        return 0

    scene_prompt = build_duration_scene_review_prompt(
        run_dir=run_dir,
        minimum_seconds=minimum_seconds,
        actual_seconds=actual_seconds,
        flow=flow,
    )
    scene_prompt_path = write_review_prompt(run_dir=run_dir.resolve(), kind="scene", prompt=scene_prompt)
    narration_prompt = build_duration_narration_review_prompt(
        run_dir=run_dir,
        minimum_seconds=minimum_seconds,
        actual_seconds=actual_seconds,
        flow=flow,
    )
    narration_prompt_path = write_review_prompt(run_dir=run_dir.resolve(), kind="narration", prompt=narration_prompt)

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.duration_fit.status": "changes_requested",
            "review.duration_fit.actual_seconds": str(actual_seconds),
            "review.duration_fit.minimum_seconds": str(minimum_seconds),
            "review.duration_fit.note": "actual audio-driven runtime is below the minimum target; run scene and narration stretch review before human review",
            "review.duration_fit.at": now_iso(),
            "review.duration_fit.scene_prompt": str(scene_prompt_path.relative_to(run_dir.resolve())),
            "review.duration_fit.scene_prompt.generated_at": now_iso(),
            "review.duration_fit.narration_prompt": str(narration_prompt_path.relative_to(run_dir.resolve())),
            "review.duration_fit.narration_prompt.generated_at": now_iso(),
            "slot.p540.status": "failed",
            "slot.p540.requirement": "required",
            "slot.p550.status": "pending",
            "slot.p550.requirement": "required",
            "slot.p560.status": "pending",
            "slot.p560.requirement": "required",
            "slot.p570.status": "blocked",
        },
    )
    print(
        f"[fail] actual runtime {actual_seconds}s is below minimum {minimum_seconds}s\n"
        f"  scene prompt: {scene_prompt_path}\n"
        f"  narration prompt: {narration_prompt_path}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
