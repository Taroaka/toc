# Requirements: EvoLink Kling v3/O3 Provider

## Goal

Enable generating videos via **EvoLink** (gateway) so we can use **Kling V3** and **Kling O3** model offerings even when the official Kling API does not expose those model IDs to our account.

## User Story

- As a video-generation pipeline user, I want to generate a short clip using `kling_3_0` / `kling_3_0_omni` tool names but backed by EvoLink so that V3/O3 models and reference features are available via API.

## Non-Goals

- Replacing image generation or TTS providers.
- Implementing a full “elements” authoring workflow UI; we only need to pass through payload fields once available.
- Removing official Kling support entirely (keep it as fallback when EvoLink key is absent).

## Constraints / Safety

- Do not read or print secrets.
- Keep changes minimal and reversible; prefer env/CLI switches.
- Default to **no audio** unless explicitly enabled.

## Acceptance Criteria

- With `EVOLINK_API_KEY` configured, a `kling_3_0` / `kling_3_0_omni` scene can generate a video via EvoLink.
- Local first-frame images are automatically uploaded to EvoLink File API and used as `image_start` for image-to-video.
- A completed run writes the `.mp4` output to the manifest `video_generation.output` path.
- If EvoLink is not configured, behavior falls back to existing Kling client behavior.

