import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from server import image_gen_app as api
from toc.providers.higgsfield import KLING_IMAGE_MODEL


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate-assets-from-manifest.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("generate_assets_for_higgsfield_parity", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
cli = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = cli
SCRIPT_SPEC.loader.exec_module(cli)


def _higgsfield_target(**generation_overrides):
    generation = {
        "tool": "higgsfield",
        "model": KLING_IMAGE_MODEL,
        "native_audio": {"mode": "natural_sound"},
        **generation_overrides,
    }
    return SimpleNamespace(
        selector="scene10_cut1",
        video_tool="higgsfield",
        video_generation_contract=generation,
    )


def test_cli_higgsfield_options_match_server_binding_and_use_model_default_resolution():
    target = _higgsfield_target()
    args = SimpleNamespace()
    with patch.object(api, "load_env_files"):
        server_options = api._server_video_execution_options(
            tool="higgsfield",
            has_first_frame=True,
            has_reference_images=False,
            native_audio_mode="natural_sound",
            model=KLING_IMAGE_MODEL,
        )
    cli_options = cli._video_execution_options(
        target=target,
        args=args,
        has_first_frame=True,
        has_reference_images=False,
        evolink_enabled=False,
        kling_extra_payload=None,
        kling_omni_extra_payload=None,
        ark_extra_payload=None,
    )

    assert cli_options == server_options
    assert cli_options["model"] == KLING_IMAGE_MODEL
    assert cli._video_quality_for_target(
        target=target,
        args=SimpleNamespace(video_resolution=None),
        execution_options=cli_options,
    ) is None

    for requested_resolution in ("720p", "1080p"):
        with pytest.raises(SystemExit, match="does not accept --video-resolution"):
            cli._video_quality_for_target(
                target=target,
                args=SimpleNamespace(video_resolution=requested_resolution),
                execution_options=cli_options,
            )

    with pytest.raises(SystemExit, match="does not support a resolution override"):
        cli._video_quality_for_target(
            target=_higgsfield_target(quality="720p"),
            args=SimpleNamespace(video_resolution=None),
            execution_options=cli_options,
        )

    legacy_args = SimpleNamespace(video_resolution=None)
    legacy_target = SimpleNamespace(video_tool="seedance", video_generation_contract={}, video_quality=None)
    assert cli._video_quality_for_target(
        target=legacy_target,
        args=legacy_args,
        execution_options={"model": "seedance-1-0-lite-i2v-250428"},
    ) == "1080p"
    legacy_args.video_resolution = "720p"
    assert cli._video_quality_for_target(
        target=legacy_target,
        args=legacy_args,
        execution_options={"model": "seedance-1-0-lite-i2v-250428"},
    ) == "720p"


def test_cli_dispatch_sends_server_bound_higgsfield_options_without_paid_requests(tmp_path):
    with patch.object(api, "load_env_files"):
        server_options = api._server_video_execution_options(
            tool="higgsfield",
            has_first_frame=True,
            has_reference_images=False,
            native_audio_mode="natural_sound",
            model=KLING_IMAGE_MODEL,
        )
    payload = {
        "provider_request_binding": {
            "duration_seconds": 5,
            "quality": None,
            "aspect_ratio": "16:9",
            "first_frame": "assets/start.png",
            "last_frame": "assets/end.png",
            "references": [],
            "execution_options": server_options,
        }
    }
    calls = []

    class FakeHiggsfieldClient:
        def generate_video(self, **kwargs):
            calls.append(kwargs.copy())
            kwargs["out_path"].write_bytes(b"mock-video")
            return {"status": "completed", "request_id": "mock-higgsfield-request"}

    call_args = dict(
        selector="scene10_cut1",
        tool="higgsfield",
        api_prompt_payload=payload,
        prompt="move carefully",
        negative_prompt="",
        input_image=tmp_path / "start.png",
        last_frame_image=tmp_path / "end.png",
        reference_images=[],
        out_path=tmp_path / "clip.mp4",
        log_dir=tmp_path / "logs",
        poll_every=0.01,
        timeout_seconds=10,
        force=False,
        dry_run=False,
        gemini_client=None,
        kling_client=None,
        evolink_client=None,
        seedance_client=None,
        higgsfield_client=FakeHiggsfieldClient(),
    )
    cli._dispatch_video_provider_call(**call_args)

    first_call = calls[0]
    first_journal = first_call["journal_path"]
    first_journal.write_text("uncertain journal stays available", encoding="utf-8")
    cli._dispatch_video_provider_call(**(call_args | {"prompt": "move quickly", "force": True}))
    second_call = calls[1]

    assert first_call["model"] == server_options["model"] == KLING_IMAGE_MODEL
    assert first_call["resolution"] is None
    assert first_call["generate_audio"] is True
    assert first_call["multi_shots"] is False
    assert first_call["elements"] is None
    assert first_call["duration_seconds"] == 5
    assert first_call["request_digest"] in first_journal.name
    assert second_call["request_digest"] in second_call["journal_path"].name
    assert second_call["request_digest"] != first_call["request_digest"]
    assert second_call["journal_path"] != first_journal
    assert first_journal.read_text(encoding="utf-8") == "uncertain journal stays available"
    assert (tmp_path / "clip.mp4").read_bytes() == b"mock-video"


def test_cli_prompt_compiler_binds_kling_model_and_null_quality():
    target = SimpleNamespace(
        selector="scene10_cut1",
        parent_selector=None,
        unit_id=None,
        source_scenes=[],
        source_cut_ids=[],
        video_cut_contract={},
        video_input_mode="image_to_video",
        video_first_frame="assets/start.png",
        video_input_image="assets/start.png",
        video_last_frame="assets/end.png",
        duration_seconds=5,
        video_references=[],
        video_tool="higgsfield",
        video_quality=None,
        video_aspect_ratio=None,
        video_generation_contract={
            "tool": "higgsfield",
            "model": KLING_IMAGE_MODEL,
            "native_audio": {"mode": "natural_sound"},
        },
        video_prompt_authoring_source="move carefully",
        video_motion_prompt="move carefully",
        video_reference_roles=[],
        image_first_frame_visual_plan={},
        scene_time_of_day="",
        story_time="",
        scene_time_of_day_visual_basis=None,
        scene_location_mode="",
        scene_location_sequence=[],
        scene_location_segments=[],
        scene_visualizable_action=None,
    )
    with patch.object(cli, "_video_contract_for_target", return_value={}):
        payload = cli._video_api_prompt_payload_for_target(
            target,
            prefix="",
            suffix="",
            quality=None,
            aspect_ratio="16:9",
            execution_options={
                "backend": "higgsfield",
                "model": KLING_IMAGE_MODEL,
                "generate_audio": True,
                "multi_shots": False,
            },
        )

    binding = payload["provider_request_binding"]
    assert binding["quality"] is None
    assert binding["execution_options"]["model"] == KLING_IMAGE_MODEL
    assert binding["execution_options"]["multi_shots"] is False
