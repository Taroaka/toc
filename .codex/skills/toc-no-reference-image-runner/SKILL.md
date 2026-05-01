---
name: toc-no-reference-image-runner
description: Use when this repository needs to generate images with no existing references, routing no-reference asset or scene requests through the shared built-in image generation skill instead of the standard reference-driven providers.
---

# ToC No-Reference Image Runner

## Overview

This skill is the repository adapter for no-reference image generation.

Use it when an image request has no resolved reference images and should move to
Codex built-in image generation instead of the repo's standard providers.

It delegates actual built-in generation to `$codex-parallel-image-batch`.

## Scope

Use this skill when all of the following are true:

- the source of truth is `asset_generation_requests.md` or `image_generation_requests.md`
- the request has `reference_count: 0` or an empty `references` list
- the request is on `execution_lane=bootstrap_builtin`
- the task is image generation, not video generation

Do not use this skill when:

- any resolved reference image is available
- the request should stay on `google_nanobanana_2`, `gemini_3_1_flash_image`, or `seadream`
- the task is only manifest authoring with no image execution

## Compatibility Note

The execution lane name stays `bootstrap_builtin` for backward compatibility.
In current repo policy, that lane means "no-reference built-in image lane" for
both asset and cut image work.

## Routing Rule

This skill is an adapter only.

When execution is needed, explicitly use `$codex-parallel-image-batch`.

## Output Size Rule

For repo scene stills, generate for YouTube horizontal delivery.

- Default target aspect ratio is `16:9`.
- Match the existing scene still convention used in this repo, which is currently
  `1376x768` for generated scene images under `output/.../assets/scenes/`.
- Require the built-in prompt to explicitly ask for a native horizontal `16:9`
  image suitable for YouTube landscape delivery.
- Do not rely on crop-to-fit as the default way to make scene stills horizontal.
- Do not leave no-reference scene still tests in portrait orientation unless the
  user explicitly asks for a different format.

## Execution Workflow

1. Read `asset_generation_requests.md` or `image_generation_requests.md`.
2. Select only items where:
   - `reference_count=0`, or
   - `references=[]`, or
   - `execution_lane=bootstrap_builtin`
3. Ignore any item that already has resolved references.
4. Normalize each selected item into:
   - `id`
   - `prompt`
   - `output_path`
   - `aspect_ratio` if present
   - `review_status` if present
5. If the request is a repo scene still and no explicit aspect ratio overrides it,
   add an explicit native-horizontal instruction to the generation prompt:
   - YouTube horizontal frame
   - landscape orientation
   - native `16:9`
   - do not compose as portrait
   - do not rely on later cropping
6. Route execution through `$codex-parallel-image-batch`.
7. Save the chosen built-in output into the requested workspace path.
8. If the model still returns portrait, treat that result as a failed fit for the
   scene-still contract and retry or report it clearly instead of silently cropping.
9. Summarize generated, skipped, and failed items.

## Guardrails

- Do not send no-reference work back to `google_nanobanana_2`, `gemini_3_1_flash_image`, or `seadream`.
- Do not use this skill when even one required continuity reference is already available.
- Keep shared planning files single-writer; use this skill for execution, not parallel manifest edits.
- For scene stills, do not fix portrait outputs by default with center-crop. The
  preferred behavior is to regenerate until the native composition is horizontal.
- If the request is a `p500` asset seed, `$toc-p500-bootstrap-image-runner` is still a valid narrower wrapper.

## Example Uses

- "Use $toc-no-reference-image-runner for scene stills that have no references yet."
- "Use $toc-no-reference-image-runner to generate the first visual seed for this location."
