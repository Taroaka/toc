---
name: codex-parallel-image-batch
description: Use when Codex should generate or edit one or more images with built-in image generation, using gpt-image-1.5, optionally delegating one image per subagent for explicit parallel batch requests. Supports scene-cut images, thumbnails, and other reusable image asset workflows.
---

# Codex Parallel Image Batch

## Overview

This skill standardizes how Codex handles image generation batches.

It is intentionally generic:

- prefer Codex built-in image generation
- assume the built-in image model is `gpt-image-1.5`
- generate multiple images in parallel only when the user explicitly asks for parallel or subagent-based work
- keep output handling and naming consistent
- let the caller decide the destination directory and asset-specific rules

This skill does not define story-specific prompt content, `p500` / `p600` stage logic, or repository-specific output contracts.

## When to Use

Use this skill when at least one of these is true:

- the user wants multiple images generated from a cut list, shot list, scene list, or prompt list
- the user explicitly asks to use subagents or parallel generation for image work
- the user wants Codex built-in image generation rather than a repo-native provider
- the task is batch image generation for scene images, thumbnails, promo images, concept frames, or placeholder art

Do not use this skill when:

- the task is a single one-off image with no reusable batch workflow
- the request is primarily about story planning or manifest authoring rather than image execution
- the repo has a stricter domain-specific skill that should first prepare the prompt set and output contract

## Required Operating Rules

1. Prefer Codex built-in image generation for this workflow.
2. Treat built-in image generation as `gpt-image-1.5`-backed.
3. When the user explicitly requests parallel generation, fan out the batch with subagents.
4. Default to one image item per subagent unless the caller gives a different grouping rule.
5. The main agent remains the single writer for shared manifests, indexes, and summaries.
6. Subagents may generate assets and return results, but they should not race on a shared planning file.
7. The caller must define or infer the destination directory. If none is provided, use a caller-chosen default rather than inventing one here.
8. If an existing reference image or continuity anchor is provided, attach or use it instead of regenerating style from scratch.

## Execution Pattern

1. Read the batch source supplied by the caller.
2. Normalize the work into image items:
   - `id`
   - `purpose`
   - `prompt`
   - `reference_image` if any
   - `output_path`
   - `size_or_aspect`
3. Check whether the user explicitly asked for subagents or parallel generation.
4. If yes, delegate one image item per subagent where practical.
5. If not, generate serially in the main thread.
6. Use natural-language image generation or explicit `$imagegen` invocation when that improves reliability.
7. Save or place each result at the item's `output_path`.
8. Report a compact batch summary:
   - generated
   - skipped
   - failed
   - paths

## Built-in Reference Image Rule

- In built-in image generation mode, reference images must be visible in the conversation context.
- For generation with local reference files, attach or otherwise surface the local images in chat before calling image generation.
- Label the role of each reference clearly in the prompt:
  - identity continuity
  - costume continuity
  - shell or prop continuity
  - style anchor
- Do not assume a repo file path alone is enough for the built-in tool to use that image as a reference.
- Do not assume conversation-visible reference images will produce exact identity lock.
- Treat built-in reference-guided generation as candidate generation for likeness and continuity, not as a guaranteed one-to-one reconstruction workflow.
- When exact likeness is critical, test the subject in isolation first before attempting a multi-subject or story-scene composition.

## Built-in Save Rule

- Built-in image generation may save its initial output outside the workspace.
- If the user or caller expects a workspace asset, move or copy the selected final image into the requested `output_path` before finishing.
- Do not treat the built-in default save location as the final project location.
- When a repo helper exists for this import step, prefer it over ad-hoc shell moves.

## Prompting Rules

- Preserve caller-provided visual constraints exactly when they are explicit.
- Keep prompts concrete about subject, framing, lighting, mood, camera distance, and continuity anchors.
- For thumbnails, emphasize readability, composition, aspect ratio, and contrast.
- For cut images, emphasize continuity with neighboring cuts and story intent.
- Do not silently swap to another image provider unless the user explicitly asks.

## Parallelization Rules

- Only use subagents when the user explicitly asked for parallel or subagent work.
- For small batches, a serial run is acceptable if the overhead would outweigh the gain.
- For medium or large batches, use a fan-out pattern:
  - prepare all items first
  - assign disjoint output paths
  - let subagents generate independently
  - consolidate results in the main thread
- If a subagent fails, retry once if the fix is obvious; otherwise surface the failed item clearly.

## Output Contract

Each generated item should have:

- a stable file name
- a deterministic destination path
- enough metadata in the final summary to map output back to the original item

Suggested file naming:

- scene images: `sceneXX-cutYY.png`
- thumbnails: `thumb-variant-01.png`
- generic batch: `<item-id>.png`

## What Belongs Outside This Skill

The caller or a repo-specific skill should define:

- which scenes or cuts need images
- the source-of-truth file to read from
- test vs production output roots
- review gates before generation
- story-specific continuity rules

## Example Uses

- "Use $codex-parallel-image-batch to generate 8 cut images in parallel from this prompt list and save them under `asset/scene/`."
- "Use $codex-parallel-image-batch for 3 thumbnail variants, 16:9, high contrast, save under `asset/thumb/`."
- "Use $codex-parallel-image-batch with the attached reference image and generate one image per scene in parallel."
