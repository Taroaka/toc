# Design: EvoLink Kling v3/O3 Provider

## Overview

Add an EvoLink client (`toc/providers/evolink.py`) that supports:

- Base64 file upload (local images -> hosted URL)
- Video generation task submission
- Task polling
- Result download

Then wire `scripts/generate-assets-from-manifest.py` so that when `EVOLINK_API_KEY` is present (or a switch is enabled), `kling_3_0` / `kling_3_0_omni` routes to EvoLink instead of the official Kling API.

## API Mapping (EvoLink)

- Upload: `POST https://files-api.evolink.ai/api/v1/files/upload/base64` -> `file_url`
- Submit: `POST https://api.evolink.ai/v1/videos/generations` -> `task_id`
- Poll: `GET https://api.evolink.ai/v1/tasks/{task_id}` -> `status` + `results[]` URLs

## Model Mapping

- `kling_3_0`:
  - I2V: `kling-v3-image-to-video`
  - T2V: `kling-v3-text-to-video`
- `kling_3_0_omni`:
  - T2V: `kling-o3-text-to-video`
  - I2V: default to `kling-v3-image-to-video` (override via env/flags)

All model names must remain overrideable because providers can change naming.

## Configuration

Environment variables (and equivalent CLI flags):

- `EVOLINK_API_KEY`
- `EVOLINK_API_BASE` (default `https://api.evolink.ai`)
- `EVOLINK_FILES_API_BASE` (default `https://files-api.evolink.ai`)
- Model overrides:
  - `EVOLINK_KLING_V3_I2V_MODEL`
  - `EVOLINK_KLING_V3_T2V_MODEL`
  - `EVOLINK_KLING_O3_I2V_MODEL`
  - `EVOLINK_KLING_O3_T2V_MODEL`

## Payload

For image-to-video, build payload like:

- `model`
- `prompt`
- `negative_prompt` (optional)
- `duration` (int)
- `aspect_ratio` (string)
- `quality` (`720p`/`1080p`)
- `sound` (false by default)
- `image_start` (uploaded file URL)
- `image_end` (optional uploaded file URL)

Additionally, merge `extra_payload` on top so users can pass `model_params` (e.g., `element_list`, `multi_shot`) without code changes.

## Fallback

If EvoLink is not configured, keep current behavior (official/gateway Kling client).

