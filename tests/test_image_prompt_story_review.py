from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_image_prompt_reviewer_entrypoint_is_removed() -> None:
    assert not (REPO_ROOT / "scripts" / "review-image-prompt-story-consistency.py").exists()
