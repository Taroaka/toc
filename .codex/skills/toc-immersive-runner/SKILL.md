---
name: toc-immersive-runner
description: Create a new ToC immersive run from a topic/source through scene images and p680 output checks; use for frontend-equivalent production execution.
---

# ToC Immersive Runner

Create the requested run through the canonical frontend production path. Resolve the topic/source, exact run directory, and stop target from the request. Default to `cinematic_story` and `p680`; use `p650` only for an explicit stop before scene images. Keep generated user-facing text in Japanese.

## Choose the task

- **New run:** Read `docs/implementation/immersive-ride-entrypoint.md` for the execution contract, then use the command below and [completion requirements](references/completion.md).
- **Existing run retry:** Use `.codex/skills/toc-resume-p500/SKILL.md`; preserve the existing run and valid outputs.
- **Status or implementation diagnosis:** Inspect the named run's state, logs, or affected implementation. Reading this skill does not authorize starting generation.
- **Stage behavior or ownership change:** Read the relevant sections of `docs/system-architecture.md`, `docs/implementation/agent-roles-and-prompts.md`, and `docs/data-contracts.md`. Other operating details are in `docs/how-to-run.md` and `docs/orchestration-and-ops.md`.

## Execute a new frontend-equivalent run

```bash
python scripts/toc-immersive-frontend-run.py \
  --topic "<topic>" \
  --source "<source>" \
  --run-dir "<run_dir>" \
  --stop-target "<p650|p680>"
```

Use the exact caller-supplied run directory and stop target. The backend create API runs this helper directly; do not wrap it in an app-server turn that starts another app-server generation flow. `scripts/toc-immersive-ride.py` is a scaffold helper and cannot establish frontend p650/p680 completion.

For `world_walk`, require the source run and follow the experience-specific canonical entrypoint, preserving `video_metadata.source_run` and `video_metadata.source_assets`. Do not silently run it as `cinematic_story`.

The runner owns stage sequencing, prepared source context, structural validation, materialized requests, image execution, and output/provenance checks. Keep canonical artifacts/state/index single-writer and follow the active agent policy. Manual/chat authoring uses `scripts/prepare-stage-context.py` for the selected stage.

Use the repository's image execution lanes and their reference-dependency order. Preserve request identity and generation provenance; procedural placeholder images cannot satisfy generation. `--materialize-only` is for explicit diagnostics/tests and does not establish media completion.

Continue through the requested stop target and its checks. Diagnose and repair a failed prerequisite before retrying the affected item; use the resume route for an existing run. Report a concrete blocker if progress needs missing input or an external change. This image workflow ends before TTS, video generation, or final render.
