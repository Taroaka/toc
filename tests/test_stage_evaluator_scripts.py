from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_verify_pipeline():
    spec = importlib.util.spec_from_file_location(
        "verify_pipeline_structural_tests",
        REPO_ROOT / "scripts" / "verify-pipeline.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _load_verify_pipeline()


def _write_yaml(path: Path, value: str) -> None:
    path.write_text(f"```yaml\n{value}\n```\n", encoding="utf-8")


def test_aggregate_verifier_does_not_add_review_or_score_fields(tmp_path: Path) -> None:
    report, updates = VERIFY.build_report(
        tmp_path,
        "toc-run",
        "standard",
        "p130",
    )

    assert updates == {}
    assert "score" not in report["overall"]
    assert not any(
        key.startswith(("review.", "eval.", "gate."))
        for key in updates
    )
    assert all("score" not in stage for stage in report["stages"].values())


def test_aggregate_verifier_accepts_structural_research_without_review_files(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "research.md",
        "source_inventory:\n  - source_id: S1\n"
        "story_materials:\n  canonical_story_dump: A story\n"
        "source_passages: []\n",
    )

    report, _updates = VERIFY.build_report(tmp_path, "scene-series", "standard", "p130")

    assert report["stages"]["research"]["passed"] is True, report


def test_asset_schema_and_provider_provenance_remain_structural(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "asset_inventory.md",
        "asset_inventory:\n"
        "  source_artifacts: [story.md]\n"
        "  coverage_scope:\n"
        "    characters: []\n"
        "    story_specific_items: []\n"
        "    locations: []\n"
        "    setpieces: []\n"
        "    reusable_stills: []\n"
        "  items: []\n",
    )
    _write_yaml(tmp_path / "asset_plan.md", "assets: []")

    result, updates = VERIFY.check_asset(tmp_path, target_slot="p530")

    assert updates == {}
    assert result["stage"] == "asset"
    assert not any("review" in check["id"] for check in result["checks"])


def test_narration_validator_only_checks_declared_media_files(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "video_manifest.md",
        "scenes:\n"
        "  - scene_id: 1\n"
        "    audio:\n"
        "      narration:\n"
        "        output: assets/audio/scene1.wav\n",
    )

    result, updates = VERIFY.check_narration(tmp_path)

    assert updates == {}
    ids = {check["id"] for check in result["checks"]}
    assert "narration.text_review" not in ids
    assert "narration.duration_fit" not in ids
    assert all("semantic" not in check_id for check_id in ids)
