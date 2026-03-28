# Requirements: image prompt story review

## Background

- The repo already exports `image_prompt_collection.md`, but there is no canonical step that reviews whether each prompt still matches the story/script intent before paid image generation.
- We need a lightweight review artifact that can catch obvious mismatches such as "the story beat requires a turtle, but the prompt no longer mentions it".

## Goals

- Add a post-export review step that takes `image_prompt_collection.md` as input.
- Compare prompt text against nearby `video_manifest.md`, `story.md`, and `script.md` to surface likely story-consistency issues.
- Catch at least these classes of issues:
  - source-side anchor terms missing from the prompt
  - prompt-only story entities that do not belong to the local scene/cut
  - source-implied `character_ids` / `object_ids` that are missing from the manifest cut
- Write a human-readable review report that can be checked before image generation.

## Non-Goals

- Perfect semantic validation.
- Auto-editing prompts or manifests.
- Blocking all image generation by default.

## Success Criteria

- There is a script that reads `image_prompt_collection.md` and writes a story-consistency review report.
- Canonical docs describe the default order as `prompt collection -> story consistency review -> human review -> image generation`.
- Tests cover missing source anchor detection and prompt-only local mismatch detection.
