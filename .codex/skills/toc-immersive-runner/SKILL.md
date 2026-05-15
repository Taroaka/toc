---
name: toc-immersive-runner
description: Use when this repository needs to create a ToC immersive cinematic story run from a topic/source in one Codex skill invocation, progressing the regular p100-p650 workflow and producing real artifacts rather than placeholder scaffolds.
---

# ToC Immersive Runner

## Overview

This skill is the Codex-native replacement for the repo's Claude slash command
`/toc-immersive-ride` when a web/server caller needs one request to create a
production-ready ToC run.

Use it as a single orchestration skill. The caller provides:

- topic/title
- source text or story/source material
- run directory
- stop target, normally `p650`
- experience, normally `cinematic_story`

## Canonical References

Read these before changing stage behavior:

- `docs/root-pointer-guide.md`
- `docs/how-to-run.md`
- `docs/data-contracts.md`
- `docs/implementation/immersive-ride-entrypoint.md`
- `scripts/toc-immersive-ride.py`
- `.claude/commands/toc/toc-immersive-ride.md` as legacy reference only

## Required Outcome for `p650`

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
  request is on the Codex built-in no-reference lane
- `image_generation_requests.md`
- `p000_index.md`

Placeholder scaffolds are failures. Do not mark the task complete if any of the
required stage artifacts only contain TODO text, `placeholder`, `REPLACE_ME`,
or generic scaffold prose.

The app-server create flow validates every fixed slot through `p650`. Before
returning success, `state.txt` must contain a terminal status for each of:

- `p110`, `p120`, `p130`
- `p210`, `p220`, `p230`
- `p310`, `p320`, `p330`
- `p410`, `p420`, `p430`, `p440`, `p450`
- `p510`, `p520`, `p530`, `p540`, `p550`, `p560`, `p570`
- `p610`, `p620`, `p630`, `p640`, `p650`

Use `done` for completed slots and `skipped` for optional slots that
intentionally do not run under `review-policy drafts`. Use `awaiting_approval`
only for review/handoff slots where the artifact is complete and the normal
handoff is genuinely waiting for human review: `p130`, `p230`, `p320`, `p330`,
`p430`, `p540`, `p570`, `p630`, or `p640`. Do not use `awaiting_approval` for
work-product slots such as `p120`, `p220`, `p420`, `p450`, `p550`, `p620`, or
`p650`. Do not leave any p650-or-earlier slot as missing, `pending`,
`in_progress`, `blocked`, or `failed`.

## Stage Contract

Run stages in the normal ToC order inside one skill invocation:

1. `p100` リサーチ
   - Read `docs/root-pointer-guide.md`.
   - Use `docs/information-gathering.md` when available.
   - Produce `research.md` in the supplied run directory.
   - Mark the relevant p100/p120 state as done.
2. `p200` 物語
   - Use `research.md`.
   - Produce `story.md`.
   - Mark the relevant p200/p220 state as done.
3. `p300` 映像設計
   - Use `research.md` and `story.md`.
   - Produce `visual_value.md`.
   - Mark the relevant p300/p310 state as done.
4. `p400` 台本・マニフェスト
   - Use `story.md` and `visual_value.md`.
   - Produce `script.md` and `video_manifest.md`.
   - Mark the relevant p400/p420/p450 state as done.
5. `p550` 素材リクエスト作成
   - Produce `asset_generation_requests.md` and
     `asset_generation_manifest.md`.
   - Treat `asset_plan.md`, `story.md`, `script.md`, and `video_manifest.md`
     together as the source of truth. Do not merely copy short
     `fixed_prompts` into generation prompts.
   - Include reusable assets for every principal named visual subject needed by
     the story and scenes: protagonist variants, romantic/decision counterpart,
     antagonist/authority figures when visible, guide/helper figures, recurring
     props, setpieces, and recurring locations. For example, a Cinderella run
     must include the prince if a palace/dance/finding scene uses him.
   - Each asset prompt must be production-ready Japanese, not a one-line
     summary. Use stable sections such as `[全体 / 不変条件]`,
     `[作成するもの]`, `[人物固定]`, `[衣装]`, `[生成方針]`, and `[禁止]`
     as applicable.
6. `p560` 素材画像生成
   - For no-reference/bootstrap Codex built-in lane requests, generate the
     referenced reusable assets.
   - Prefer `$toc-p500-bootstrap-image-runner` or
     `$toc-no-reference-image-runner` for the image execution details.
7. `p650` シーン画像リクエスト作成
   - Produce `image_generation_requests.md`.
   - Scene prompts must be at least as detailed as p550 asset prompts. Do not
     emit terse scene summaries. Use stable sections such as
     `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`,
     `[連続性]`, and `[禁止]` as applicable.
   - Do not generate scene images unless the caller explicitly asks beyond
     `p650`.
   - Rebuild `p000_index.md`.

## Execution Rules

- Use the exact run directory supplied by the caller. Do not create a second run
  directory.
- Keep all user-facing generated artifacts in Japanese.
- Keep the experience `cinematic_story` unless the caller specifies otherwise.
- Use `--review-policy drafts` behavior for app-server create flows unless the
  caller explicitly overrides it.
- Stop at `p650` for app-server Image Gen create flows. Do not continue into
  narration, video generation, final render, or scene image generation.
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
- Keep shared planning files single-writer. If using subagents, they may draft
  stage content, but the main skill execution must integrate and write the final
  shared files.
- Do not call external image/video/TTS providers from this skill. For p560
  no-reference Codex built-in image work, delegate to the repo image skills
  named above.

## Validation Gate

Before reporting completion:

1. Verify every required artifact for the stop target exists.
2. Inspect each required text artifact for placeholder/scaffold/TODO content.
3. Verify `asset_generation_requests.md` and `image_generation_requests.md`
   contain concrete request sections with output paths.
   Confirm that prompts are structured, self-contained, and cinematic. Reject
   one-line prompts or prompts that omit required principal characters from
   reusable assets.
4. Verify `state.txt` does not leave p100, p200, p300, p400, p550, p560, or
   p650 as pending when the related artifact is complete.
5. Verify every fixed slot from `p110` through `p650` has a terminal status.
   Use `awaiting_approval` only for the review/handoff slots listed above.
6. Rebuild or update `p000_index.md`.
7. Summarize the run directory and current p stage.

If validation fails, fix the run rather than returning success.
