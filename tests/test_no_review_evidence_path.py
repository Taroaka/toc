from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.stage_evaluation import pipeline


def _load_verify_pipeline():
    path = REPO_ROOT / "scripts" / "verify-pipeline.py"
    spec = importlib.util.spec_from_file_location("verify_pipeline_no_review", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY_PIPELINE = _load_verify_pipeline()


def test_manifest_check_has_no_review_score_or_state_contract(tmp_path: Path) -> None:
    result, updates = pipeline.check_manifest_single(tmp_path, "standard", "immersive")

    assert "score" not in result
    assert "rubric_scores" not in result
    assert not any(
        key.startswith(("eval.", "review."))
        for key in updates
    )
    assert not any(
        "review" in str(check.get("id", "")).lower()
        for check in result.get("checks", [])
    )


def test_video_check_has_no_semantic_reviewer_hook(tmp_path: Path) -> None:
    result, updates = pipeline.check_video_single(tmp_path, duration_probe=lambda _path: None)

    assert result["stage"] == "video"
    assert not any(
        "semantic" in str(check.get("id", "")).lower()
        for check in result.get("checks", [])
    )
    assert not any(key.startswith(("eval.", "review.")) for key in updates)


def test_asset_and_narration_checks_do_not_require_review_artifacts(tmp_path: Path) -> None:
    asset_result, asset_updates = VERIFY_PIPELINE.check_asset(tmp_path)
    narration_result, narration_updates = VERIFY_PIPELINE.check_narration(tmp_path)

    all_checks = asset_result.get("checks", []) + narration_result.get("checks", [])
    check_ids = {str(check.get("id", "")) for check in all_checks}
    assert "asset.review_approved" not in check_ids
    assert "asset.plan_semantic_review_subagent_passed" not in check_ids
    assert "narration.text_review" not in check_ids
    assert "narration.duration_fit" not in check_ids
    assert "narration.semantic_review_subagent_passed" not in check_ids
    assert not any(
        key.startswith(("eval.", "review."))
        for key in (*asset_updates.keys(), *narration_updates.keys())
    )
