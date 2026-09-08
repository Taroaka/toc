import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from server import image_gen_app as app


def test_create_media_runs_without_review_evidence(tmp_path: Path) -> None:
    events = []

    async def generate(*, run_dir, kind):
        events.append(f"generate:{kind}")

    def validate(run_dir, kind):
        events.append(f"validate:{kind}")

    async def scenes(*args, **kwargs):
        events.append("scenes")

    with (
        patch.object(app, "safe_run_dir", return_value=tmp_path),
        patch.object(app, "_assert_bound_run_root"),
        patch.object(app, "_set_create_job", new=AsyncMock()),
        patch.object(app, "_validate_pre_asset_provider_gate"),
        patch.object(app, "_generate_request_outputs", side_effect=generate),
        patch.object(app, "_validate_generated_outputs", side_effect=validate),
        patch.object(app, "_mark_asset_generation_handoff"),
        patch.object(app, "_mark_image_prompt_request_freeze_done"),
        patch.object(app, "_generate_scene_outputs_after_p650_preflight", side_effect=scenes),
    ):
        assert asyncio.run(app._generate_create_images("job", run_id="run")) is True

    assert events == ["generate:asset", "validate:asset", "scenes"]
    assert not (tmp_path / "logs/review").exists()
    assert not (tmp_path / "eval_report.json").exists()


def test_bad_asset_output_still_blocks_scene_generation(tmp_path: Path) -> None:
    scenes = AsyncMock()
    with (
        patch.object(app, "safe_run_dir", return_value=tmp_path),
        patch.object(app, "_assert_bound_run_root"),
        patch.object(app, "_set_create_job", new=AsyncMock()),
        patch.object(app, "_validate_pre_asset_provider_gate"),
        patch.object(app, "_generate_request_outputs", new=AsyncMock()),
        patch.object(app, "_validate_generated_outputs", side_effect=RuntimeError("invalid image bytes")),
        patch.object(app, "_generate_scene_outputs_after_p650_preflight", new=scenes),
    ):
        with pytest.raises(RuntimeError, match="invalid image bytes"):
            asyncio.run(app._generate_create_images("job", run_id="run"))
    scenes.assert_not_awaited()


def test_resume_classifies_actual_outputs_without_reading_eval_report(tmp_path: Path) -> None:
    output = tmp_path / "scene.png"
    output.write_bytes(b"image")
    (tmp_path / "eval_report.json").write_text("obsolete malformed review")
    item = SimpleNamespace(id="scene1_cut1", output="scene.png", references=[], prompt="prompt")
    with (
        patch.object(app, "_assert_bound_run_root"),
        patch.object(app, "load_request_items", side_effect=lambda run, kind: [item] if kind == "scene" else []),
        patch.object(app, "validate_image_bytes"),
        patch.object(app, "_has_completed_app_server_image_provenance", return_value=True),
    ):
        result = app._inspect_p680_regeneration_plan(
            tmp_path, current_request_paths={"asset": {}, "scene": {"scene.png": output}},
        )
        assert not result.errors
        assert not result.targets
    output.unlink()
    with (
        patch.object(app, "_assert_bound_run_root"),
        patch.object(app, "load_request_items", side_effect=lambda run, kind: [item] if kind == "scene" else []),
    ):
        result = app._inspect_p680_regeneration_plan(
            tmp_path, current_request_paths={"asset": {}, "scene": {"scene.png": output}},
        )
        assert result.targets == {"scene.png": output}
        assert result.actions == frozenset({"regenerate_p600_scene"})


def test_empty_request_set_cannot_complete_generation(tmp_path: Path) -> None:
    (tmp_path / "image_generation_request_snapshot.json").write_text("{}")
    with patch.object(app, "load_request_items", return_value=[]):
        with pytest.raises(RuntimeError, match="no scene requests"):
            app._validate_generated_outputs(tmp_path, "scene")


def test_request_freeze_uses_validator_signature_and_checks_revision(tmp_path: Path) -> None:
    with (
        patch.object(app, "_prepare_image_prompt_request_revision", return_value="revision-1"),
        patch.object(app, "_read_manifest_data", return_value=(None, "", {})),
        patch.object(app, "_validate_image_prompt_request_revision", autospec=True, return_value="revision-1"),
        patch.object(app, "_finalize_p600_supervisor_result"),
        patch.object(app, "append_state_snapshot") as state,
    ):
        app._mark_image_prompt_request_freeze_done(tmp_path, expected_request_revision="revision-1")
        assert state.call_args.args[1]["generation.image_prompt.request_freeze.request_revision"] == "revision-1"
        state.reset_mock()
        with pytest.raises(RuntimeError, match="revision"):
            app._mark_image_prompt_request_freeze_done(tmp_path, expected_request_revision="other")
        state.assert_not_called()


def test_missing_supervisor_cannot_publish_completed_state(tmp_path: Path) -> None:
    with (
        patch.object(app, "safe_run_dir", return_value=tmp_path),
        patch.object(app, "_validate_generated_outputs"),
        patch.object(app, "load_request_items", return_value=[SimpleNamespace(output="image.png")]),
        patch.object(app, "append_state_snapshot") as state,
    ):
        with pytest.raises(RuntimeError, match="supervisor result is missing"):
            app._mark_image_generation_review_ready("run")
        state.assert_not_called()


def test_scene_request_lock_covers_freeze_and_generation(tmp_path: Path) -> None:
    events = []
    locked = False

    @asynccontextmanager
    async def lock(*args):
        nonlocal locked
        locked = True
        yield
        locked = False

    def freeze(*args, **kwargs):
        assert locked
        events.append("freeze")

    async def generate(**kwargs):
        assert locked
        events.append("generate")

    with (
        patch.object(app, "_assert_bound_run_root"),
        patch.object(app, "_serialized_run_write", side_effect=lock),
        patch.object(app, "_mark_image_prompt_request_freeze_done", side_effect=freeze),
        patch.object(app, "_generate_request_outputs_unlocked", side_effect=generate),
        patch.object(app, "_validate_p650_run"),
        patch.object(app, "_validate_generated_outputs"),
        patch.object(app, "_validate_p680_visual_quality"),
        patch.object(app, "_mark_image_generation_review_ready"),
        patch.object(app, "_set_create_job", new=AsyncMock()),
        patch.object(app, "append_state_snapshot"),
    ):
        asyncio.run(app._generate_scene_outputs_after_p650_preflight("job", run_id="run", run_dir=tmp_path))
    assert events == ["freeze", "generate"]
