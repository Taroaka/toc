---
name: toc-immersive-runner
description: Use when this repository needs to create a ToC immersive cinematic story run from a topic/source by following the canonical ToC p100-p900 run design, normally stopping at p680 for frontend image review.
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
- stop target, normally `p680` for frontend image review handoff flows
- experience, normally `cinematic_story`

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
`/toc-immersive-ride` constraints: `cinematic_story`, frontend image review
handoff, and a stop target that normally ends at `p680`.

## Frontend Create Policy

When `review_policy` is `frontend`, do not pause for CLI human review. Generate
the review artifacts, write gate/state records, and hand approval to the web UI.
This is not a review skip. It is a frontend handoff.

For app-server Image Gen create flows, the normal stop target is `p680`. The
skill strengthens image prompts, retries bootstrap asset generation up to 10
times when the visual gate fails, generates scene images, and creates the
frontend image-review handoff. Asset and scene image generation each use their
own reference-dependency DAG: no-reference requests run in the first parallel
group, requests whose references are already available run in later groups, and
each group is gated before the next group starts. If the bootstrap asset gate
still fails after those retries, the server still hands the generated images to
the frontend for review instead of leaving the user waiting forever.
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
`image_generation_requests.md`, with image review state handed off to the
frontend.

Placeholder scaffolds are failures. Do not mark the task complete if any of the
required stage artifacts only contain TODO text, `placeholder`, `REPLACE_ME`,
or generic scaffold prose.

The app-server create flow validates every fixed slot through its stop target.
For `p680`, before returning success, `state.txt` must contain a terminal status
for each of:

- `p110`, `p120`, `p130`
- `p210`, `p220`, `p230`
- `p310`, `p320`, `p330`
- `p410`, `p420`, `p430`, `p440`, `p450`
- `p510`, `p520`, `p530`, `p540`, `p550`, `p560`, `p570`
- `p610`, `p620`, `p630`, `p640`, `p650`, `p660`, `p670`, `p680`

Use `done` for completed slots and `skipped` for optional slots that
intentionally do not run under `review-policy drafts`. Use `awaiting_approval`
only for review/handoff slots where the artifact is complete and the normal
handoff is genuinely waiting for human review: `p130`, `p230`, `p320`, `p330`,
`p430`, `p540`, `p570`, `p630`, `p640`, or `p680`. Do not use `awaiting_approval` for
work-product slots such as `p120`, `p220`, `p420`, `p450`, `p550`, `p620`, or
`p650`. Do not leave any slot through the stop target as missing, `pending`,
`in_progress`, `blocked`, or `failed`.

Review artifacts must explain the essential cause of each finding, not only the
failed check. When the cause and fix are clear, include the target
artifact/section, concrete fix direction, downstream impact, and acceptance
condition for the next review round.

## ToC Run Contract

Follow the run-level p100-p900 architecture in `docs/system-architecture.md`.

- L1 Run Orchestrator owns bucket order, stop target, and bucket completion
  validation.
- L1 records each L2 supervisor invocation in
  `logs/orchestration/l2_supervisor_progress.md`. Do not record L3 task/review
  agent invocations in this progress memo.
- L2 P-Bucket Supervisors own the canonical artifacts, `state.txt`, and
  `p000_index.md` updates inside their assigned bucket.
- L3 Task / Review Agents run only under the owning L2 supervisor and write
  isolated scratch, logs, review artifacts, or explicitly requested generated
  media.
- Each completed bucket must leave
  `logs/orchestration/pXXX.supervisor_result.json` for the L1 validator.
- Do not make the skill itself a second copy of the stage contract. If a
  bucket-specific rule is missing or conflicting, update the canonical docs
  rather than adding a private rule here.

For this skill, the normal bucket range is:

- `stop_target=p680`: run `p100` through `p600` until scene images are generated
  and image review is handed off to the frontend.
- `stop_target=p650`: supported only as an explicit early-stop override before
  scene image generation, after reusable asset generation required by `p650`.

## Execution Rules

- Use the exact run directory supplied by the caller. Do not create a second run
  directory.
- Keep all user-facing generated artifacts in Japanese.
- Keep the experience `cinematic_story` unless the caller specifies otherwise.
- Use `review_policy=frontend` for app-server Image Gen create flows.
- Use the caller's exact `stop_target`. For app-server Image Gen create flows
  invoked by `server/image_gen_app.py`, this is normally `p680`; generate p660
  scene images inside the skill for the normal frontend handoff path.
- Do not continue into narration, video generation, or final render.
- Use repo scripts/helpers when they already encode the local contract:
  - `scripts/prepare-stage-context.py` as the standard manual/chat stage entry
  - `scripts/resolve-stage-grounding.py`
  - `scripts/audit-stage-grounding.py`
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
5. Verify every fixed slot from `p110` through the stop target has a terminal status.
   Use `awaiting_approval` only for the review/handoff slots listed above.
6. For `stop_target=p680`, verify generated asset and scene image outputs exist,
   verify generated assets/scene stills are photorealistic/live-action
   Codex app-server outputs with generation provenance, not local procedural
   raster fallbacks, and not vector-like / illustration-like / low-detail
   rasters. Verify `review.image.status=pending` plus
   `gate.image_review=required`.
7. Rebuild or update `p000_index.md`.
8. Summarize the run directory and current p stage.

If validation fails, fix the run rather than returning success.
