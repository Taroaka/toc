import asyncio
import os
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from server import image_gen_app as api
from server.app import app
from test_image_gen_server import write_valid_p650_artifacts
from toc.providers.higgsfield import IMAGE_MODEL, KLING_IMAGE_MODEL, REFERENCE_MODEL


def test_higgsfield_execution_options_keep_legacy_defaults_and_accept_explicit_models():
    with patch.object(api, "load_env_files"):
        legacy_image = api._server_video_execution_options(
            tool="higgsfield", has_first_frame=True
        )
        legacy_reference = api._server_video_execution_options(
            tool="higgsfield", has_first_frame=False, has_reference_images=True
        )
        selected_kling = api._server_video_execution_options(
            tool="higgsfield", has_first_frame=True, model=KLING_IMAGE_MODEL,
            multi_shots=False, elements=[],
        )
        selected_seedance = api._server_video_execution_options(
            tool="higgsfield", has_first_frame=True, model=IMAGE_MODEL
        )
        selected_ark_seedance = api._server_video_execution_options(
            tool="seedance", has_first_frame=True,
            model="seedance-1-0-lite-i2v-250428",
        )

    assert legacy_image["model"] == IMAGE_MODEL
    assert legacy_reference["model"] == REFERENCE_MODEL
    assert selected_kling["model"] == KLING_IMAGE_MODEL
    assert selected_kling["multi_shots"] is False
    assert selected_kling["elements"] == []
    assert selected_seedance["model"] == IMAGE_MODEL
    assert selected_ark_seedance["model"] == "seedance-1-0-lite-i2v-250428"


@pytest.mark.parametrize("unsupported", [{"multi_shots": True}, {"elements": ["hero"]}])
def test_higgsfield_selection_rejects_unimplemented_native_options(unsupported):
    with patch.object(api, "load_env_files"), pytest.raises(ValueError, match="not implemented"):
        api._server_video_execution_options(
            tool="higgsfield", has_first_frame=True, model=KLING_IMAGE_MODEL,
            **unsupported,
        )


def test_manifest_kling_model_and_options_are_bound_to_provider_send(tmp_path):
    run = write_valid_p650_artifacts(tmp_path, "kling_selection_run")
    manifest_path, original_text, manifest = api._read_manifest_data(run)
    cut = manifest["scenes"][0]["cuts"][0]
    cut["video_generation"] = {
        "tool": "higgsfield",
        "model": KLING_IMAGE_MODEL,
        "multi_shots": False,
        "elements": [],
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        "first_frame": "assets/characters/hero.png",
        "last_frame": "assets/characters/hero.png",
        "native_audio": {"mode": "natural_sound"},
        "prompt_authoring_source": "move carefully",
    }
    api._write_manifest_data(manifest_path, original_text, manifest)

    item = {
        "item_id": "scene10_cut1",
        "kind": "scene",
        "output": "assets/scenes/scene10_cut1.png",
        "video_prompt": "move carefully",
        "video_tool": "higgsfield",
        "video_duration_seconds": 8,
        "video_aspect_ratio": "16:9",
        "video_input_mode": "image_to_video",
        "video_native_audio_mode": "natural_sound",
        "video_first_reference": "assets/characters/hero.png",
        "video_last_reference": "assets/characters/hero.png",
        "video_references": [],
    }
    with (
        patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1", "HF_API_KEY": "test:secret"}),
        patch.object(api, "ROOT", tmp_path),
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/image-gen/video-prompts/create",
                json={"run_id": run.name, "items": [item]},
            )
        assert response.status_code == 200, response.text

        _, _, materialized = api._read_manifest_data(run)
        video_generation = materialized["scenes"][0]["cuts"][0]["video_generation"]
        execution_options = video_generation["api_prompt_payload"]["provider_request_binding"]["execution_options"]
        assert execution_options["model"] == KLING_IMAGE_MODEL
        assert execution_options["multi_shots"] is False
        assert "elements" not in execution_options
        assert video_generation["quality"] is None
        assert video_generation["api_prompt_payload"]["provider_request_binding"]["quality"] is None

        with pytest.raises(ValueError, match="does not support a resolution override"):
            api._compile_frontend_video_prompt_payload(
                data=materialized,
                item=api.FrontendReviewItem(**(item | {"video_quality": "720p"})),
                run_dir=run,
            )

        request = api._materialized_video_generate_item(
            run_dir=run,
            request=api.VideoGenerateItem(
                item_id=item["item_id"],
                prompt=item["video_prompt"],
                first_reference=item["video_first_reference"],
                last_reference=item["video_last_reference"],
                quality=None,
                aspect_ratio=item["video_aspect_ratio"],
                duration_seconds=item["video_duration_seconds"],
                tool="higgsfield",
                candidate_count=1,
            ),
        )

        sent = {}

        def fake_generate(_client, **kwargs):
            sent.update(kwargs)
            kwargs["out_path"].write_bytes(b"mock-video")
            return {"status": "completed", "request_id": "mock-request"}

        with (
            patch("toc.providers.higgsfield.HiggsfieldClient.generate_video", fake_generate),
            patch("toc.providers.video_validation.verify_generated_video", return_value={"duration": 8}),
        ):
            result = asyncio.run(api._generate_video_one(run, request, 1))

    assert result["status"] == "completed"
    assert sent["model"] == KLING_IMAGE_MODEL
    assert sent["multi_shots"] is False
    assert sent["elements"] is None
    assert sent["resolution"] is None
