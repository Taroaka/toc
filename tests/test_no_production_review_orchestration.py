from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def test_immersive_scaffold_does_not_materialize_production_review_artifacts() -> None:
    with tempfile.TemporaryDirectory(prefix="toc_no_review_scaffold_") as td:
        base = Path(td) / "output"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/toc-immersive-ride.py",
                "--topic",
                "no review",
                "--timestamp",
                "20990101_0000",
                "--base",
                str(base),
                "--stage",
                "p100",
                "--experience",
                "cinematic_story",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        run_dir = base / "no_review_20990101_0000"
        state = _state(run_dir / "state.txt")
        assert not any(key.startswith("review.") for key in state)
        assert not any(key.startswith("eval.") for key in state)
        assert not any(
            key.startswith("gate.") and "review" in key
            for key in state
        )
        assert not (run_dir / "logs" / "eval").exists()
        assert not (run_dir / "logs" / "review").exists()


def test_generation_entrypoint_contains_no_reviewer_subprocesses() -> None:
    source = (
        REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "review-image-prompt-story-consistency.py",
        "run-p720-narration-l3.py",
        "run-p720-narration-semantic.py",
        "--skip-image-prompt-review",
        "--skip-narration-review",
    ):
        assert forbidden not in source


def test_generation_entrypoint_does_not_gate_video_on_legacy_quality_reports() -> None:
    source = (
        REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
    ).read_text(encoding="utf-8")
    assert "quality_issues" not in source
    assert "_blocking_video_prompt_quality_issue_codes" not in source
    assert "_assert_video_prompt_quality_allows_provider_execution" not in source


def test_audio_duration_gate_has_only_deterministic_runtime_failure_path() -> None:
    source = (
        REPO_ROOT / "scripts" / "check-audio-duration-gate.py"
    ).read_text(encoding="utf-8")
    assert "toc.duration_fit_review" not in source
    assert "subagent_prompt" not in source
    assert "write_review_prompt" not in source


def test_vertical_recut_does_not_require_video_review_approval() -> None:
    module = _load_script("make-vertical-short.py")
    with tempfile.TemporaryDirectory(prefix="toc_no_review_short_") as td:
        run_dir = Path(td)
        (run_dir / "state.txt").write_text(
            "status=DONE\nartifact.video=video.mp4\n---\n",
            encoding="utf-8",
        )
        (run_dir / "video.mp4").write_bytes(b"placeholder")
        module.require_approved(_state(run_dir / "state.txt"), run_dir)
