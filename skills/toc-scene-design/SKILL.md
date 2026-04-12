---
name: toc-scene-design
description: Run the ToC story / scene design stage with the canonical story docs and grounding preflight. Use when: turning `research.md` into `story.md` for a run directory.
---

# ToC Scene Design

1. Start with `python scripts/resolve-stage-grounding.py --stage story --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Confirm `stage.story.grounding.status=ready` before writing.
3. Read `docs/story-creation.md`, `docs/affect-design.md`, and `workflow/story-template.yaml`.
4. Write `story.md` so later script / manifest stages can trace back to `research.md`.
