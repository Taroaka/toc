---
name: toc-immersive-runner
description: Use when this repository needs to create a ToC immersive cinematic story run from a topic/source in one Codex skill invocation, progressing the regular p100-p680 frontend-review workflow and producing real artifacts rather than placeholder scaffolds.
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
- stop target, normally `p650` for app-server Image Gen create flows and
  `p680` for direct one-shot frontend handoff flows
- experience, normally `cinematic_story`

## Canonical References

Read these before changing stage behavior:

- `docs/root-pointer-guide.md`
- `docs/how-to-run.md`
- `docs/data-contracts.md`
- `docs/implementation/immersive-ride-entrypoint.md`
- `scripts/toc-immersive-ride.py`
- `.claude/commands/toc/toc-immersive-ride.md` as legacy reference only

## Frontend Create Policy

When `review_policy` is `frontend`, do not pause for CLI human review. Generate
the review artifacts, write gate/state records, and hand approval to the web UI.
This is not a review skip. It is a frontend handoff.

For app-server Image Gen create flows, the server asks this skill to stop at
`p650`, then the server strengthens image prompts, retries bootstrap asset
generation up to 10 times when the visual gate fails, generates scene images,
and creates the `p680` frontend image-review handoff. Asset and scene image
generation each use their own reference-dependency DAG: no-reference requests
run in the first parallel group, requests whose references are already available
run in later groups, and each group is gated before the next group starts. If
the bootstrap asset gate still fails after those retries, the server still hands
the generated images to the frontend for review instead of leaving the user
waiting forever.
Direct one-shot frontend handoff flows may still use `p680` with
`handoff=frontend_image_review`.

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
  request is on the Codex built-in no-reference lane
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
   - Every production scene must be split into at least two cuts from the first
     create pass. Do not collapse a scene into scene-level `image_generation`.
     Use `scenes[].cuts[]` with distinct `image_generation.output` paths such as
     `assets/scenes/scene10_cut1.png` and `assets/scenes/scene10_cut2.png`.
   - Mark the relevant p400/p420/p450 state as done.
5. `p520` reusable asset inventory
   - Inventory the story's characters, story-specific items, used locations,
     setpieces, and reusable stills in `asset_inventory.md` before authoring requests.
   - The goal is coverage: every principal visual subject that can cause
     downstream identity drift must have an asset-plan candidate.
   - Do not turn one-off cut composition, acting beats, or camera movement into
     asset entries; leave those for p600.
6. `p530` / `p540` 素材設計と review/fix loop
   - Produce or update `asset_plan.md`.
   - Character references must be designed as full-body front / side / back
     three-view references. Character variants must derive from the main
     character reference, not from a new unrelated design.
   - Run the p540 evaluator-improvement loop when asset coverage is not already
     approved: review agents check for missing characters, story-specific
     items, locations, setpieces, reference misuse, lane mistakes, and weak
     visual specificity. Main applies fixes, then another review round checks
     again until passed or explicitly overridden.
7. `p550` 素材リクエスト作成
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
   - Do not write API-unhelpful production metadata in the prompt body.
     NG: `物語「シンデレラ」の scene10`, `scene30_cut01`,
     `この画像は物語「シンデレラ」の一場面`, `後続 scene で使う王子`.
     OK: `灰の台所。石床、大きな暖炉、薄い灰、朝の青灰色の光、奥へ続く暗い廊下が見える、人物なしの実写映画風 location anchor。`
8. `p560` 素材画像生成
   - For no-reference/bootstrap Codex built-in lane requests, generate the
     referenced reusable assets.
   - Prefer `$toc-p500-bootstrap-image-runner` or
     `$toc-no-reference-image-runner` for the image execution details.
9. `p650` シーン画像リクエスト作成
   - Produce `image_generation_requests.md`.
   - Reject any production scene with fewer than two cuts. Short scenes still need
     at least an establishing/transition cut and a character/action/result cut.
   - `image_generation_requests.md` must include every
     `scenes[].cuts[].image_generation.output`; scene-level request entries are
     not sufficient.
   - Scene prompts must be at least as detailed as p550 asset prompts. Do not
     emit terse scene summaries. Use stable sections such as
     `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`,
     `[連続性]`, and `[禁止]` as applicable.
   - Rebuild `p000_index.md`.
10. `p660` シーン画像生成
   - For `stop_target=p680`, generate scene still images from
     `image_generation_requests.md` using the same image execution lane as the
     request file declares.
   - The repo image provider is `tool: codex_builtin_image` (gpt-image-2 via the
     Codex app-server). Do not route p500/p600 images to Nano Banana, Gemini
     image, or SeaDream.
   - After generation, run the image gate. It must inspect the actual raster
     image content, not only the extension. If a p600 scene image is
     vector-like/low-detail and its reference images are clean raster assets,
     regenerate the p600 scene. If any referenced p500 asset is also
     vector-like/low-detail, return to p500/p560 and regenerate that reference
     before retrying p600.
   - Do not replace this with a server-side postprocess prompt rewrite.
11. `p670` 画像QA
   - Create or update review artifacts/state for image QA. Under
     `review_policy=frontend`, set `slot.p670.status=skipped` when the frontend
     image review gate is created instead of running CLI QA.
12. `p680` 画像レビュー引き渡し
   - Set `slot.p680.status=awaiting_approval`.
   - Set `review.image.status=pending` and `gate.image_review=required`.
   - The frontend is responsible for approval/rejection.

## Execution Rules

- Use the exact run directory supplied by the caller. Do not create a second run
  directory.
- Keep all user-facing generated artifacts in Japanese.
- Keep the experience `cinematic_story` unless the caller specifies otherwise.
- Use `review_policy=frontend` for app-server Image Gen create flows.
- Use the caller's exact `stop_target`. For app-server Image Gen create flows
  invoked by `server/image_gen_app.py`, this is normally `p650`; do not generate
  p660 scene images inside the skill unless the caller explicitly requests
  `stop_target=p680`.
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
- Keep shared planning files single-writer. If using subagents, they may draft
  stage content, but the main skill execution must integrate and write the final
  shared files.
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
   verify generated assets/scene stills are not vector-like or low-detail
   rasters, and verify `review.image.status=pending` plus
   `gate.image_review=required`.
7. Rebuild or update `p000_index.md`.
8. Summarize the run directory and current p stage.

If validation fails, fix the run rather than returning success.
