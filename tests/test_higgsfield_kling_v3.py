from pathlib import Path
from unittest import mock

import pytest

from toc.providers.higgsfield import HiggsfieldClient, HiggsfieldConfig, KLING_IMAGE_MODEL
from toc.video_provider_capabilities import resolve_video_provider_capabilities


MODEL = KLING_IMAGE_MODEL


def _build_payload(client: HiggsfieldClient, **kwargs):
    with mock.patch.object(client, "_image_ratio_matches", return_value=True):
        return client._build_payload(**kwargs)


def test_kling_v3_higgsfield_capability_is_model_and_mode_specific():
    capability = resolve_video_provider_capabilities(
        tool="higgsfield", model=MODEL, input_mode="first_last_frame"
    )

    assert capability.supported
    assert (capability.duration_min_seconds, capability.duration_max_seconds) == (3, 15)
    assert capability.first_last_frame_supported
    assert capability.native_audio
    assert not capability.multi_shots_supported
    assert not capability.elements_supported
    assert capability.reference_images_min == capability.reference_images_max == 0
    assert not resolve_video_provider_capabilities(
        tool="higgsfield", model=MODEL, input_mode="reference_images"
    ).supported
    assert not resolve_video_provider_capabilities(
        tool="higgsfield", model="kling-video/v3.0/omni/image-to-video", input_mode="first_last_frame"
    ).supported


def test_kling_v3_payload_maps_last_image_and_sound_and_disables_multishots(tmp_path: Path):
    first = tmp_path / "first.png"
    last = tmp_path / "last.png"
    first.write_bytes(b"first")
    last.write_bytes(b"last")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with mock.patch.object(
        client, "_upload_file", side_effect=["https://cdn.example/first.png", "https://cdn.example/last.png"]
    ):
        payload = _build_payload(client,
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=first,
            last_frame_image=last,
            reference_images=None,
            generate_audio=True,
        )

    assert payload == {
        "prompt": "move",
        "duration": 5,
        "sound": "on",
        "image_url": "https://cdn.example/first.png",
        "last_image_url": "https://cdn.example/last.png",
        "multi_shots": False,
    }


@pytest.mark.parametrize("duration", [2, 16, True, 5.0])
def test_kling_v3_rejects_duration_outside_integer_three_to_fifteen(tmp_path: Path, duration):
    image = tmp_path / "first.png"
    image.write_bytes(b"first")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with pytest.raises(ValueError, match="3 to 15"):
        _build_payload(client,
            model=MODEL,
            prompt="move",
            duration_seconds=duration,
            aspect_ratio="16:9",
            resolution=None,
            input_image=image,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
        )


def test_kling_v3_requires_first_image_and_rejects_reference_images(tmp_path: Path):
    ref = tmp_path / "reference.png"
    ref.write_bytes(b"ref")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with pytest.raises(ValueError, match="requires one first image"):
        _build_payload(client,
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=None,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
        )
    with pytest.raises(ValueError, match="cannot combine references"):
        _build_payload(client,
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=ref,
            last_frame_image=None,
            reference_images=[ref],
            generate_audio=False,
        )


def test_kling_v3_rejects_explicit_resolution_override(tmp_path: Path):
    image = tmp_path / "first.png"
    image.write_bytes(b"first")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with pytest.raises(ValueError, match="does not support a resolution override"):
        _build_payload(
            client,
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution="1080p",
            input_image=image,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
        )


@pytest.mark.parametrize(
    ("unsupported"),
    [
        {"multi_shots": True},
        {"elements": ["person-1"]},
    ],
)
def test_kling_v3_does_not_silently_drop_unsupported_native_options(tmp_path: Path, unsupported):
    image = tmp_path / "first.png"
    image.write_bytes(b"first")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with pytest.raises(ValueError, match="not implemented"):
        _build_payload(client,
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=image,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
            **unsupported,
        )


def test_kling_v3_submission_uses_model_endpoint_and_schema_payload(tmp_path: Path):
    image = tmp_path / "first.png"
    image.write_bytes(b"first")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with (
        mock.patch.object(client, "_upload_file", return_value="https://cdn.example/first.png"),
        mock.patch.object(client, "_image_ratio_matches", return_value=True),
        mock.patch.object(
            client,
            "_api_request_json",
            return_value={
                "status": "queued",
                "request_id": "req-1",
                "status_url": "https://api.higgsfield.ai/requests/req-1/status",
            },
        ) as request,
    ):
        client.generate_video(
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=image,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
            out_path=tmp_path / "out.mp4",
            journal_path=tmp_path / "journal.json",
            request_digest="request-1",
            poll=False,
        )

    submitted = request.call_args.kwargs
    assert submitted["url"] == f"https://api.higgsfield.ai/{MODEL}"
    assert submitted["json_payload"] == {
        "prompt": "move",
        "duration": 5,
        "sound": "off",
        "image_url": "https://cdn.example/first.png",
        "multi_shots": False,
    }


@pytest.mark.parametrize("unsupported", [{"multi_shots": True}, {"elements": ["person-1"]}])
def test_kling_v3_rejects_unsupported_native_options_before_upload_or_submission(tmp_path: Path, unsupported):
    image = tmp_path / "first.png"
    image.write_bytes(b"first")
    client = HiggsfieldClient(HiggsfieldConfig(api_key="id:secret"))

    with (
        mock.patch.object(client, "_upload_file") as upload,
        mock.patch.object(client, "_api_request_json") as request,
        pytest.raises(ValueError, match="not implemented"),
    ):
        client.generate_video(
            model=MODEL,
            prompt="move",
            duration_seconds=5,
            aspect_ratio="16:9",
            resolution=None,
            input_image=image,
            last_frame_image=None,
            reference_images=None,
            generate_audio=False,
            out_path=tmp_path / "out.mp4",
            journal_path=tmp_path / "journal.json",
            request_digest="request-1",
            poll=False,
            **unsupported,
        )

    upload.assert_not_called()
    request.assert_not_called()
