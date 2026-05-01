---
name: toc-p600-image-runner
description: Use when this repository needs to execute the p600 image stage for story cuts, turning approved cut image requests into generated files by routing through $codex-parallel-image-batch. Defaults test runs to `asset/scene/` and keeps story-specific planning in p600 documents rather than inside the skill.
---

# ToC P600 Image Runner

## Overview

This skill is the repository-specific adapter for cut image generation.

It does not own the generic batch-generation logic. Instead, it prepares this repo's `p600` image work and routes execution through `$codex-parallel-image-batch`.

Use this skill to connect:

- this repository's scene and cut image requests
- the `p600` image-stage contract
- the current output mode
- Codex built-in image generation with optional subagent fan-out

## Scope

This skill is for this repository's scene and cut image generation only.

Primary sources:

- `video_manifest.md`
- `image_generation_requests.md`
- `workflow/p600-scene-image-batch-spec-template.md`
- `docs/how-to-run.md`

Optional supporting sources:

- `script.md`
- scene-local manifests under `output/<topic>_<timestamp>/scenes/`

## Routing Rule

When generation execution is needed, explicitly use `$codex-parallel-image-batch`.

This skill is the planner and adapter.
`$codex-parallel-image-batch` is the execution engine.

## Required Repository Rules

1. Respect the repo's stage contract:
   - `p500` is asset
   - `p600` is image
2. Keep story-specific prompt design and cut semantics in `p600` documents, not in this skill.
3. Treat `video_manifest.md` and `image_generation_requests.md` as the source of truth for what to generate.
4. Use a single-writer pattern for shared manifest or request-file edits.
5. Only batch-generate images that are ready for execution.

## Output Mode Rules

There are two output modes:

- test mode:
  - write generated images to `asset/scene/`
- production mode:
  - write generated images to `output/<topic>_<timestamp>/asset/scene/`

Default behavior for this skill:

- if the request says this is a test or does not provide a production run directory, use `asset/scene/`
- if a concrete run directory is given, use the production path under that run

Do not silently mix test and production paths in the same batch.

## Execution Workflow

1. Read the request source:
   - `image_generation_requests.md`
   - or a caller-provided p600 batch spec
2. Determine mode:
   - test
   - production
3. Build normalized image items with:
   - scene id
   - cut id
   - prompt
   - reference image if any
   - target path
4. Verify that each item has a unique output path.
5. When using built-in image generation with local reference images, make those images visible in the conversation before generation and label their continuity role.
6. Treat built-in reference-guided generation as candidate generation. Do not assume exact reproduction of face, costume, or prop identity from conversation-visible images alone.
7. When likeness matters, validate the main subject in an isolated continuity test before moving to full scene cuts.
8. If the user explicitly wants parallel generation, invoke `$codex-parallel-image-batch` in parallel mode.
9. If the user did not ask for parallel generation, you may still prepare the batch here, but do not force subagent fan-out.
10. After built-in generation, move or copy selected outputs into the repo `target path` when the built-in tool initially saved elsewhere.
11. After generation, produce a compact summary of:
   - completed items
   - failed items
   - saved paths

For this repo, prefer the workspace helper script when available:

- `python scripts/import-codex-generated-image.py --dest <target-path>`

## Guardrails

- Do not replace repo-native planning docs with this skill's own schema.
- Do not hardcode story-specific visual lore here.
- Do not write to `output/.../asset/scene/` during test-mode runs.
- Do not treat thumbnail generation as identical to scene-cut generation; it may reuse the shared batch skill, but should use its own spec.

## Recommended Pattern

- Keep the batch execution rules in `$codex-parallel-image-batch`
- Keep p600 story/cut requirements in `image_generation_requests.md` or a p600 batch spec
- Use this skill only to bridge the two

## Example Uses

- "Use $toc-p600-image-runner to generate the approved cut images for this story in test mode under `asset/scene/`."
- "Use $toc-p600-image-runner with parallel generation for all ready items in `image_generation_requests.md`."
- "Use $toc-p600-image-runner for this run dir and write production outputs under `output/<topic>_<timestamp>/asset/scene/`."
