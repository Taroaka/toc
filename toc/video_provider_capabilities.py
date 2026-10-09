from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class VideoProviderCapabilities:
    duration_min_seconds: int
    duration_max_seconds: int
    reference_images_min: int
    reference_images_max: int
    supported: bool = True
    unsupported_reason: str = ""
    native_audio: bool = False
    reference_audio: bool = False
    reference_limit_verified: bool = True


def _canonical_video_tool(tool: str) -> str:
    normalized = re.sub(r"[\s-]+", "_", str(tool or "").strip().lower())
    if normalized in {
        "seedance",
        "byteplus_seedance",
        "bytedance_seedance",
        "ark_seedance",
        "seadream_video",
        "seedream_video",
        "see_dream",
    }:
        return "seedance"
    if normalized in {"kling", "kling_3.0", "kling_3_0"}:
        return "kling_3_0"
    if normalized in {
        "kling_omni",
        "kling_3.0_omni",
        "kling_3_0_omni",
    }:
        return "kling_3_0_omni"
    return normalized


def resolve_video_provider_capabilities(
    *,
    tool: str,
    model: str = "",
    input_mode: str = "",
) -> VideoProviderCapabilities:
    """Return the reviewed request limits for a provider/model/input mode.

    Model is part of the lookup contract even when the current provider family
    has one shared limit. This keeps future model-specific changes out of the
    server, CLI, and prompt compiler call sites.
    """

    normalized_tool = _canonical_video_tool(tool)
    normalized_model = str(model or "").strip().lower()
    normalized_mode = str(input_mode or "").strip().lower()
    reference_mode = normalized_mode in {
        "reference_images",
        "reference_to_video",
    }

    if normalized_tool == 'higgsfield':
        image_model = 'bytedance/seedance-2.5/image-to-video'
        reference_model = 'bytedance/seedance-2.5/reference-to-video'
        expected = reference_model if reference_mode else image_model
        valid_mode = reference_mode or normalized_mode in {'image_to_video', 'first_last_frame'}
        supported = valid_mode and normalized_model == expected
        return VideoProviderCapabilities(4, 30, 1 if reference_mode else 0, 32 if reference_mode else 0,
            supported=supported, unsupported_reason='' if supported else 'Higgsfield model/input operation is not supported',
            native_audio=True, reference_audio=False, reference_limit_verified=not reference_mode)

    if normalized_tool == "seedance":
        # Current Seedance 1.0 endpoints share the 2–12 second task window.
        # An unspecified model resolves to the repository's Seedance 1.0
        # defaults and therefore must use the same fail-closed limits.
        known_model = not normalized_model or normalized_model.startswith(
            "seedance-1-0-"
        )
        if known_model:
            return VideoProviderCapabilities(
                duration_min_seconds=2,
                duration_max_seconds=12,
                reference_images_min=1 if reference_mode else 0,
                reference_images_max=4 if reference_mode else 0,
            )
        return VideoProviderCapabilities(
            duration_min_seconds=2,
            duration_max_seconds=12,
            reference_images_min=1 if reference_mode else 0,
            reference_images_max=4 if reference_mode else 0,
            supported=False,
            unsupported_reason=(
                f"Seedance model {model!r} has no reviewed capability contract"
            ),
        )

    if normalized_tool in {"kling_3_0", "kling_3_0_omni"}:
        return VideoProviderCapabilities(
            duration_min_seconds=1,
            duration_max_seconds=60,
            reference_images_min=0,
            reference_images_max=0,
        )

    return VideoProviderCapabilities(
        duration_min_seconds=1,
        duration_max_seconds=60,
        reference_images_min=0,
        reference_images_max=32,
    )
