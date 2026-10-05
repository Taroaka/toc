---
name: toc-narration
description: >
  Run the ToC script / narration authoring stage with the canonical script docs and current upstream source. Use when: drafting or revising narration-bearing script artifacts for a run.
---

# ToC Narration

1. Start with `python scripts/resolve-stage-grounding.py --stage script --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Read the prepared source/readset and confirm required inputs are present before writing.
3. Read `docs/script-creation.md` and the relevant playbooks under `workflow/playbooks/script/`.
4. Keep narration aligned with the current `story.md` and the run's script source of truth.

5. B-roll audio and subtitles are independently optional. Read the B-roll contract in `docs/implementation/video-integration.md`; preserve supplied media and do not fill visual-only cuts with speech or captions.
