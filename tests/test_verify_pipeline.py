from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_verify_pipeline():
    spec = importlib.util.spec_from_file_location(
        "verify_pipeline_tests",
        REPO_ROOT / "scripts" / "verify-pipeline.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = _load_verify_pipeline()


def _write_yaml(path: Path, value: str) -> None:
    path.write_text(f"```yaml\n{value}\n```\n", encoding="utf-8")


def test_stage_target_aliases_remain_available() -> None:
    assert VERIFY.normalize_stage_target("research") == "p130"
    assert VERIFY.normalize_stage_target("p600") == "p680"
    assert VERIFY.normalize_stage_target("900") == "p930"


def test_build_report_has_no_review_evidence_dependency(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "research.md",
        "source_inventory:\n  - source_id: S1\n"
        "story_materials:\n  canonical_story_dump: A story\n"
        "source_passages: []\n",
    )

    report, updates = VERIFY.build_report(tmp_path, "scene-series", "standard", "p130")

    assert updates == {}
    assert report["stages"]["research"]["passed"] is True
    assert "score" not in report["overall"]
    assert all("review" not in key.lower() for key in updates)


def test_manifest_output_path_validation_rejects_escape(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "video_manifest.md",
        "manifest_phase: production\n"
        "scenes:\n"
        "  - scene_id: 1\n"
        "    audio:\n"
        "      narration:\n"
        "        output: ../outside.wav\n",
    )

    result, _updates = VERIFY.shared_check_manifest_single(tmp_path, "standard", "toc-run")

    assert result["passed"] is False
    assert any(check["id"] == "manifest.output_paths" and not check["passed"] for check in result["checks"])


def test_main_writes_structural_report_without_eval_state(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "research.md",
        "source_inventory:\n  - source_id: S1\n"
        "story_materials:\n  canonical_story_dump: A story\n",
    )

    # The process entry point is exercised by the shell integration tests; this
    # unit test only verifies the report shape produced by the same builder.
    report, _updates = VERIFY.build_report(tmp_path, "scene-series", "standard", "p130")
    assert not any("score" in stage for stage in report["stages"].values())
