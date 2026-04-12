---
name: toc-narration
description: Run the ToC script / narration authoring stage with the canonical script docs and upstream grounding checks. Use when: drafting or revising narration-bearing script artifacts for a run.
---

# ToC Narration

1. Start with `python scripts/resolve-stage-grounding.py --stage script --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Confirm `stage.script.grounding.status=ready` before writing.
3. Read `docs/script-creation.md` and the relevant playbooks under `workflow/playbooks/script/`.
4. Keep narration aligned with approved `story.md` and the run's current script source of truth.
