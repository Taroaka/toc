from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_runner_uses_llm_story_author_without_prose_fallback() -> None:
    source = (REPO_ROOT / "scripts/toc-immersive-frontend-run.py").read_text(
        encoding="utf-8"
    )

    assert "author-story-with-codex.py" in source
    assert "def _build_story(" not in source
    assert "_build_story(" not in source


def test_story_author_cli_declares_gpt6_role_models() -> None:
    source = (REPO_ROOT / "scripts/author-story-with-codex.py").read_text(
        encoding="utf-8"
    )

    assert "DEFAULT_STORY_AUTHOR_MODEL" in source
    assert "DEFAULT_SCENE_AUTHOR_MODEL" in source
    assert "DEFAULT_REPAIR_AUTHOR_MODEL" in source
    assert "TOC_STORY_AUTHOR_MODEL" in source
    assert "TOC_SCENE_AUTHOR_MODEL" in source
    assert "TOC_REPAIR_AUTHOR_MODEL" in source
