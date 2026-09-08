from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_narration_quality_reviewer_entrypoint_is_removed() -> None:
    assert not (REPO_ROOT / "scripts" / "review-narration-text-quality.py").exists()
