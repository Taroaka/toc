# Requirements: image prompt collection first

## Background

- The intended workflow is to review image prompts before paid image generation, but the repo does not make that step explicit enough.
- Users should not have to dig through `video_manifest.md` to review only the actual still-generation prompts.

## Goals

- Make `prompt collection -> review -> image generation` an explicit default workflow.
- Provide a reusable script that extracts the image prompt collection from a manifest.
- Update canonical docs so this step is part of the normal runbook.

## Non-Goals

- Changing the manifest schema.
- Auto-generating images from the prompt collection itself.

## Success Criteria

- There is a script that exports a prompt collection from `video_manifest.md`.
- `docs/how-to-run.md` and `docs/implementation/image-prompting.md` describe prompt collection as the default pre-image-generation step.
