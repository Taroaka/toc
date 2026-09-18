---
name: toc-image-prompt
description: >
  Run the ToC image prompt / manifest authoring stage against the canonical prompt docs and current upstream artifacts. Use when: revising `video_manifest.md` prompts before image generation.
---

# ToC Image Prompt

1. Start with `python scripts/resolve-stage-grounding.py --stage image_prompt --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Read the prepared source/readset and confirm required inputs are present before writing.
3. Read `docs/implementation/image-prompting.md`, `docs/implementation/asset-bibles.md`, and `workflow/video-manifest-template.md`.
4. Keep manifest prompts grounded in the current `story.md`, cut contracts, and run manifest.
