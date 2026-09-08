---
name: toc-immersive-runner
description: Use when this repository needs to create a ToC immersive cinematic story run from a topic/source by following the canonical ToC p100-p900 run design, normally stopping at p680 after image generation and ordinary output checks.
---

# ToC Immersive Runner

## Overview

This skill is the Codex-native entrypoint for `/toc-immersive-ride` when a
web/server caller needs one request to create a production-ready immersive ToC
run. It does not own the overall ToC stage design; it reads and follows the
canonical run-level design.

Use it as a thin ToC run entrypoint. The caller provides:

- topic/title
- source text or story/source material
- run directory
- stop target, normally `p680` after scene image generation
- experience, normally `cinematic_story`
- source run, required when experience is `world_walk`

## Canonical References

Read these before changing stage behavior or deciding agent ownership:

- `docs/root-pointer-guide.md`
- `docs/system-architecture.md`
- `docs/implementation/agent-roles-and-prompts.md`
- `docs/orchestration-and-ops.md`
- `docs/how-to-run.md`
- `docs/data-contracts.md`
- `docs/implementation/immersive-ride-entrypoint.md`
- `scripts/toc-immersive-ride.py`
- `.claude/commands/toc/toc-immersive-ride.md` as legacy reference only

This skill must not duplicate the full p100-p900 operating design. The
canonical design lives in the docs above. This skill only adds the
`/toc-immersive-ride` constraints: `cinematic_story`, frontend image handoff,
and a stop target that normally ends at `p680`.

## Frontend Create Policy

Frontend create uses the same source context, authoring, structural validators,
request materialization, provider execution, and output/provenance checks as the
CLI path. The frontend may display generated candidates or offer optional image
selection/editing, but it does not add a production quality gate.

For app-server Image Gen create flows, the normal stop target is `p680`. The
skill authors image prompts, generates scene images, and creates the frontend
image handoff. Asset and scene image generation each use their
own reference-dependency DAG: no-reference requests run in the first parallel
group, requests whose references are already available run in later groups, and
each group is checked before the next group starts. If an item fails, the owner
records the processing error and retries that item after rematerialization.
Use `p650` only when the caller explicitly asks to stop before scene image
generation.

## Required Outcome for `p650` / `p680`

When the stop target is `p650`, the run directory must contain real Japanese
content for:

- `state.txt`
- `research.md`
- `story.md`
- `visual_value.md`
- `script.md`
- `video_manifest.md`
- `asset_generation_requests.md`
- `asset_generation_manifest.md`
- generated reusable asset image files referenced by asset requests when the
  request is on the Codex built-in no-reference lane. These must be
  photorealistic/live-action Codex app-server image generation outputs with
  generation provenance, not local procedural raster fallbacks.
- `image_generation_requests.md`
- `p000_index.md`

When the stop target is `p680`, all `p650` artifacts are still required, and the
run directory must additionally contain generated scene image files referenced by
`image_generation_requests.md`, with optional candidate/selection data handed off
to the frontend.

Placeholder scaffolds are failures. Do not mark the task complete if any of the
required stage artifacts only contain TODO text, `placeholder`, `REPLACE_ME`,
or generic scaffold prose.

The app-server create flow validates every active slot through its stop target.
For `p680`, before returning success, `state.txt` must contain terminal status
for the active slots `p110`, `p120`, `p210`, `p220`, `p310`, `p330`, `p410`, `p420`,
`p440`, `p450`, `p510`, `p520`, `p530`, `p550`, `p560`, `p570`, `p610`, `p620`,
`p650`, `p660`, `p670`, and `p680`. Use `done` for completed work and `skipped`
only for an intentionally inapplicable optional slot. Use `awaiting_user_choice`
only when the caller explicitly requests a candidate selection/editing action.
Do not leave an active slot through the stop target as missing, pending,
in_progress, blocked, or failed.

## ToC Run Contract

Follow the run-level p100-p900 architecture in `docs/system-architecture.md`.

- L1 Run Orchestrator owns bucket order, stop target, and bucket completion
  validation.
- L1 records each L2 supervisor invocation in
  `logs/orchestration/l2_supervisor_progress.md`.
- L2 P-Bucket Supervisors own the canonical artifacts, `state.txt`, and
  `p000_index.md` updates inside their assigned bucket.
- Isolated task workers run only under the owning L2 supervisor and write
  isolated scratch, validation diagnostics, or explicitly requested generated
  media.
- Each completed bucket must leave
  `logs/orchestration/pXXX.supervisor_result.json` for the L1 validator.
- Do not make the skill itself a second copy of the stage contract. If a
  bucket-specific rule is missing or conflicting, update the canonical docs
  rather than adding a private rule here.

For this skill, the normal bucket range is:

- `stop_target=p680`: run `p100` through `p600` until scene images are generated
  and ordinary image/output checks are complete.
- `stop_target=p650`: supported only as an explicit early-stop override before
  scene image generation, after reusable asset generation required by `p650`.

Server frontend create does not invoke this skill as its main orchestration
path. `/api/image-gen/runs/create` must run
`scripts/toc-immersive-frontend-run.py` directly from the backend process so the
effective `CODEX_HOME`, generated image root, network preflight, and app-server
diagnostics are all resolved by one runtime contract. Do not call this skill
from an app-server turn and then start another app-server-backed semantic/image
generation flow inside it.

## Execution Rules

- For app-server create flows, use the repo CLI as the canonical Codex
  entrypoint instead of hand-authoring the run in chat:

  ```bash
  python scripts/toc-immersive-frontend-run.py \
    --topic "<topic>" \
    --source "<source>" \
    --run-dir "<run_dir>" \
    --stop-target "<p650|p680>"
  ```

  This helper creates p100-p650 artifacts, prepares source context, runs ordinary
  structural checks, uses the existing Codex app-server image lane
  for p560/p660 unless `--materialize-only` is explicitly passed for tests,
  rebuilds `p000_index.md`, and validates the requested stop target. Do not use
  `scripts/toc-immersive-ride.py` as the completion path for this frontend
  create flow; it is a scaffold helper and is not sufficient for p650/p680
  success.
- Use the exact run directory supplied by the caller. Do not create a second run
  directory.
- Keep all user-facing generated artifacts in Japanese.
- Keep the experience `cinematic_story` unless the caller specifies otherwise.
- For `world_walk`, require an existing source run and preserve its `story.md` /
  `assets/` as references through `video_metadata.source_run` and
  `video_metadata.source_assets`.
- Use the caller's exact `stop_target`. For app-server Image Gen create flows
  invoked by `server/image_gen_app.py`, this is normally `p680`; generate p660
  scene images inside the skill for the normal frontend path.
- Do not continue into narration, video generation, or final render.
- Use repo scripts/helpers when they already encode the local contract:
  - `scripts/prepare-stage-context.py` as the standard manual/chat stage entry
  - `scripts/resolve-stage-grounding.py`
  - `scripts/build-run-index.py`
  - `scripts/generate-assets-from-manifest.py` for request materialization when
    it matches the current manifest contract
  - `scripts/toc-state.py` for state updates when practical
- Do not rely on the Claude `.claude/commands/` command being executable by
  Codex. Treat those files as reference material only.
- Keep shared planning files bucket-single-writer. L2 P-Bucket Supervisors
  integrate their bucket's L3 outputs and write the final shared files for that
  bucket. L1 must not re-integrate bucket content after the supervisor returns.
- Do not call external video/TTS providers from this skill. For p560 and p660
  image work, use the repo's image execution lanes and delegate to the repo image
  skills named above when appropriate.

## Validation Gate

Before reporting completion:

1. Verify every required artifact for the stop target exists.
2. Inspect each required text artifact for placeholder/scaffold/TODO content.
3. Verify `asset_generation_requests.md` and `image_generation_requests.md`
   contain concrete request sections with output paths.
   Confirm that prompts are structured, self-contained, and cinematic. Reject
   one-line prompts or prompts that omit required principal characters from
   reusable assets.
4. Verify `state.txt` does not leave p100, p200, p300, p400, p550, p560, p650,
   p660, p670, or p680 as pending when the related artifact is complete.
5. Verify every active slot through the stop target has a terminal status.
   Use `awaiting_user_choice` only when the caller explicitly requested a user choice.
6. For `stop_target=p680`, verify generated asset and scene image outputs exist,
   verify generated assets/scene stills have request-bound generation provenance,
   and verify they are decodable image files rather than local placeholder rasters.
7. Rebuild or update `p000_index.md`.
8. Summarize the run directory and current p stage.

If validation fails, fix the run rather than returning success.
