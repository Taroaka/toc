---
name: toc-research
description: Run the ToC research stage with the repo's canonical docs, templates, and source context. Use when: creating or revising `research.md` for a run directory.
---

# ToC Research

1. Start with `python scripts/resolve-stage-grounding.py --stage research --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Read the prepared source/readset and confirm the required documents and inputs are present before writing.
3. Read `docs/information-gathering.md`, `workflow/research-template.yaml`, and `workflow/research-template.production.yaml`.
4. Produce `research.md` in the run directory and keep evidence traceable.
