---
name: toc-video-gen
description: >
  Run the ToC video generation stage with canonical video docs, playbooks, and source context. Use when: preparing or executing `video_manifest.md` for clip generation.
---

# ToC Video Generation

1. Start with `python scripts/resolve-stage-grounding.py --stage video_generation --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Read the prepared source/readset and confirm the required manifest, image, and narration inputs are present before writing or generating.
3. Read `docs/video-generation.md`, `workflow/video-manifest-template.md`, and the relevant playbooks under `workflow/playbooks/video-generation/`.
4. Materialize current prompt/request payloads and run ordinary structural, file, and provenance checks before provider execution.
