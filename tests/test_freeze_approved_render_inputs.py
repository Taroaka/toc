from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any
from unittest.mock import Mock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "freeze-approved-render-inputs.py"


def _load_module():
    name = "toc_test_freeze_approved_render_inputs"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _manifest() -> dict[str, Any]:
    return {
        "scenes": [
            {"scene_id": 0, "kind": "character_reference"},
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "video_generation": {"duration_seconds": 8},
                        "render": {
                            "video_duration_seconds": 10,
                            "narration_offset_seconds": 1.25,
                        },
                    },
                    {
                        "cut_id": 2,
                        "video_generation": {"duration_seconds": 12},
                        "render": {
                            "video_duration_seconds": 12,
                            "narration_offset_seconds": 0,
                        },
                    },
                    {"cut_id": 3, "cut_status": "deleted"},
                ],
            },
        ]
    }


def test_cli_freezer_builds_exact_canonical_p750_request(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    gate = Mock()
    captured: dict[str, Any] = {}

    def fake_freeze(supplied_run_dir: Path, request: Any) -> dict[str, Any]:
        captured["run_dir"] = supplied_run_dir
        captured["request"] = request
        return {"status": "frozen", "approvedAudioSetHash": "sha256:audio"}

    with patch.object(MODULE, "_require_narration_ready_for_video", gate), patch.object(
        MODULE,
        "_read_manifest_data",
        return_value=(run_dir / "video_manifest.md", "", _manifest()),
    ), patch.object(MODULE, "_freeze_render_inputs", side_effect=fake_freeze):
        result = MODULE.freeze_approved_render_inputs(run_dir, output="video.mp4")

    gate.assert_called_once_with(run_dir)
    request = captured["request"]
    assert captured["run_dir"] == run_dir
    assert request.run_id == "run"
    assert [item.item_id for item in request.items] == ["scene1_cut1", "scene1_cut2"]
    assert [item.video_duration_seconds for item in request.items] == [10, 12]
    assert [item.narration_offset_seconds for item in request.items] == [1.25, 0.0]
    assert all(item.video_path is None and item.narration_path is None for item in request.items)
    assert result["status"] == "frozen"


def test_cli_freezer_rejects_missing_approved_timeline_duration(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    data = _manifest()
    data["scenes"][1]["cuts"][0]["render"] = {}
    data["scenes"][1]["cuts"][0]["video_generation"] = {}

    with patch.object(MODULE, "_require_narration_ready_for_video"), patch.object(
        MODULE,
        "_read_manifest_data",
        return_value=(run_dir / "video_manifest.md", "", data),
    ):
        with pytest.raises(ValueError, match="no positive duration: scene1_cut1"):
            MODULE.freeze_approved_render_inputs(run_dir, output="video.mp4")
