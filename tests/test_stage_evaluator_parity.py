from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc import stage_evaluator
from toc.stage_evaluation import pipeline


def _write_yaml(path: Path, value: str) -> None:
    path.write_text(f"```yaml\n{value}\n```\n", encoding="utf-8")


def test_stage_evaluator_facade_exports_structural_checks() -> None:
    for name in (
        "check_research",
        "check_story",
        "check_script_single",
        "check_manifest_single",
        "check_video_single",
        "check_visual_value",
    ):
        assert callable(getattr(stage_evaluator, name, None))
    assert not hasattr(stage_evaluator, "render_stage_review")
    assert not hasattr(stage_evaluator, "append_stage_review_state")


def test_missing_artifacts_return_structural_result_without_scores(tmp_path: Path) -> None:
    result, updates = stage_evaluator.check_manifest_single(
        tmp_path,
        "standard",
        "toc-run",
    )

    assert set(result) == {"stage", "artifact", "passed", "reason_keys", "checks", "details"}
    assert result["passed"] is False
    assert updates == {}


def test_malformed_ids_are_reported_as_structural_failures(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "story.md",
        "script:\n  scenes:\n    - scene_id: 1\n      research_refs: []\n    - scene_id: 1\n      research_refs: []",
    )

    result, updates = pipeline.check_story(tmp_path, "standard")

    assert result["passed"] is False
    assert updates == {}
    assert any(
        check["id"] == "story.scene.ids" and not check["passed"]
        for check in result["checks"]
    )


def test_valid_manifest_does_not_need_review_artifacts(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "video_manifest.md",
        "manifest_phase: production\n"
        "video_metadata:\n"
        "  experience: cinematic_story\n"
        "scenes:\n"
        "  - scene_id: 1\n"
        "    cuts:\n"
        "      - cut_id: 1\n"
        "        image_generation:\n"
        "          character_ids: []\n"
        "          object_ids: []\n"
        "        video_generation:\n"
        "          duration_seconds: 5\n",
    )

    result, updates = pipeline.check_manifest_single(tmp_path, "standard", "immersive")

    assert result["passed"] is True, result
    assert updates == {}
    assert not any("review" in check["id"] for check in result["checks"])
