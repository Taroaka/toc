---
name: toc-video-gen
description: Run the ToC video generation stage with canonical video docs, playbooks, and approval-gated grounding. Use when: preparing or executing `video_manifest.md` for clip generation.
---

# ToC Video Generation

1. Start with `python scripts/resolve-stage-grounding.py --stage video_generation --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Confirm `stage.video_generation.grounding.status=ready` before writing or generating.
3. Read `docs/video-generation.md`, `workflow/video-manifest-template.md`, and the relevant playbooks under `workflow/playbooks/video-generation/`.
4. Do not proceed unless image and narration approvals required by the grounding contract are already recorded.
