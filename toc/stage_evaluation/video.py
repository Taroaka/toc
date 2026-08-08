"""Canonical video evaluation policy."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document, parse_state_file

from .common import (
    _append_grounding_checks,
    _append_rubric_findings,
    add_check,
    contract_list,
    make_stage,
    score_from_checks,
    score_from_ratio,
)
from .research_story import _video_rubric

def _probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None or not path.exists():
        return None
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
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _video_checks(checks: list[dict[str, Any]], *, video_path: Path, state: dict[str, str], run_dir: Path) -> None:
    video_exists = video_path.exists()
    add_check(checks, "video.file_exists", video_exists, f"{video_path.name} exists")
    if not video_exists:
        return

    render_status = state.get("runtime.render.status", "").strip().lower()
    add_check(checks, "video.render_status", render_status in {"success", "started", ""}, f"render status is set to success/started (got {render_status or '(unset)'})", kind="rubric")

    review_status = state.get("review.video.status", "").strip().lower()
    add_check(checks, "video.review_status", review_status in {"pending", "approved", "changes_requested"}, f"review.video.status is present (got {review_status or '(unset)'})", kind="rubric")

    report_exists = (run_dir / "run_report.md").exists()
    if report_exists:
        add_check(checks, "video.run_report", True, "run_report.md exists", kind="rubric")

    narration_list = run_dir / "video_narration_list.txt"
    if narration_list.exists():
        audio_paths = [Path(line.strip()) for line in narration_list.read_text(encoding="utf-8").splitlines() if line.strip()]
        resolved = [(path if path.is_absolute() else run_dir / path) for path in audio_paths]
        add_check(checks, "video.narration_list", all(path.exists() for path in resolved), "all narration files in video_narration_list.txt exist", kind="rubric")

    video_duration = _probe_duration(video_path)
    if video_duration is not None:
        add_check(checks, "video.duration", video_duration > 0.0, f"video duration is positive ({video_duration:.2f}s)", kind="rubric")


def check_video_single(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    state = parse_state_file(run_dir / "state.txt")
    checks: list[dict[str, Any]] = []
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    _video_checks(checks, video_path=run_dir / "video.mp4", state=state, run_dir=run_dir)
    manifest_path = run_dir / "video_manifest.md"
    contract = {}
    if manifest_path.exists():
        _, manifest = load_structured_document(manifest_path)
        quality_check = manifest.get("quality_check") if isinstance(manifest.get("quality_check"), dict) else {}
        contract = quality_check.get("review_contract") if isinstance(quality_check.get("review_contract"), dict) else {}
    if not contract:
        add_check(checks, "video.contract_missing", False, "quality_check.review_contract is missing for the video stage.", kind="rubric")
    else:
        must_have = contract_list(contract, "must_have_artifacts")
        if must_have and not all((run_dir / item).exists() for item in must_have):
            add_check(checks, "video.contract_must_have_unmet", False, "video review contract requires artifacts that are still missing.", kind="rubric")
    rubric_scores = _video_rubric(run_dir, state, checks)
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "video.mp4", checks, rubric_scores=rubric_scores), updates


def check_video_scene_series(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    scene_dirs = sorted((run_dir / "scenes").glob("scene*"))
    checks: list[dict[str, Any]] = []
    add_check(checks, "video.scene_dirs", len(scene_dirs) >= 1, f"scene-series has scene directories (got {len(scene_dirs)})")
    video_paths = [scene_dir / "video.mp4" for scene_dir in scene_dirs]
    add_check(checks, "video.scene_files", all(path.exists() for path in video_paths), "each scene has video.mp4")
    _append_grounding_checks(checks, run_dir=run_dir, stage="video")
    rubric_scores = {
        "render_integrity": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "asset_completeness": 1.0 if all(path.exists() for path in video_paths) else 0.3,
        "review_readiness": 0.8,
        "audio_packaging": 0.8,
        "publish_readiness": score_from_ratio(sum(1 for check in checks if check["passed"]), len(checks)),
    }
    _append_rubric_findings(checks=checks, stage="video", rubric_scores=rubric_scores)
    updates = {"eval.video.score": f"{score_from_checks(checks):.4f}"}
    return make_stage("video", "scenes/*/video.mp4", checks, details={"scene_count": len(scene_dirs)}, rubric_scores=rubric_scores), updates


