from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pure_stage_review_clis_are_removed() -> None:
    for stage in ("research", "story", "script", "manifest", "video"):
        assert not (REPO_ROOT / "scripts" / f"review-{stage}-stage.py").exists()
    assert not (REPO_ROOT / "toc" / "stage_review_cli.py").exists()
