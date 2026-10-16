# 2026-10-15: neutral asset period context

## Requirement and evidence
The p500 worker failed in _write_asset_request_files -> compile_asset_prompt -> _validate_neutral_asset_lighting at 17:44:39, before any images. Supporting-character adapter subjects embed exact canonical story_metadata.time in a clothing/hair/material/social-status consistency clause. That setting is narrative background and can contain time-of-day prose, so scanning every substring as a positive lighting instruction rejects valid neutral references.

## Design
Keep the current canonical p450 artifacts and exact setting bytes. Distinguish only the known adapter-authored period-consistency clause containing the exact passed story_time from render instructions during lighting validation. Do not remove arbitrary story_time matches or weaken generation_prompt checks; remaining scene light instructions still fail. Make neutral-anchor lighting explicit in compiled prompts for every asset kind, including explicit prompts. Era/context is preserved, identity and period constraints remain intact, no story-name-specific rules.

## Tasks
- Add red regressions for mixed era/chronology in the adapter period clause, separate illicit light text, and explicit-prompt refusal.
- Implement narrow source-bound context handling and common neutral lighting instruction.
- Check all actual asset-plan entries read-only, run affected compiler/profile/materialization/resume suites, review diff.
- Only after all active jobs are absent: restart supported stack, resume same run from frontend once, observe job.

## Verification and review

The two behavioral regression tests fail before the patch, and the new negative test confirms ordinary story_time occurrences cannot exempt lighting directives. After the source-bound change: asset compiler/profile/p500 resume/phase handoff/variant/request-snapshot suites 150 passed, 2 subtests passed. All 20 current asset-plan entries compile in memory with exact canonical story time and no failures; no run artifact bytes were rewritten for that check. Compiler version updated to v4 to preserve request/compiler provenance. Local review confirms the exception only covers the known character-adapter clause in descriptive fields, never explicit generation_prompt; markers outside that clause still reject, and neutral lighting now applies to all asset types. Pointer docs pass. Existing unrelated edits are preserved.

## Verified resume and external network interruption

After the supported restart, Computer Use resumed once as job 9bf1a44943c745358f4295540623dfc8. It passed the prior time-leak error, published 20 asset requests with the neutral lighting contract, and completed p510/p520/p530. It then failed at 17:58:21 with Codex network preflight DNS resolution, before any generated images. Direct socket DNS for chatgpt.com/auth.openai.com now succeeds, and the exact preflight_codex_backend_network function returns passed for both DNS and HTTPS (HTTP 405 reachable), so a single same-run frontend retry is justified by changed external evidence. No network check is disabled, no stale artifact promoted, and no extra server restart. If the unchanged external error repeats, stop retrying and report it.

## Subsequent materializer defect

The DNS/HTTPS preflight now passes. Retry 67a117c61ffb440380fda43b67dd877e failed during shot schedule validation: shots sum to 32 while parent video_generation.duration_seconds is 10. Inspection shows _persist_video_materializations resolves shot targets solely by source_cut_ids and returns the parent cut video_generation, so each child overwrites the parent; the final child wins. Add exact shot-id/selector persistence and fail closed for missing/mismatched shots, preserving the parent and sibling nodes. Regression must persist two children with different durations/paths and show parent unchanged. Restore only proven overwritten parent video fields from current canonical cinematic projection (or a verified source-matching checkpoint), validate before publication, retain backup and repair receipt. No shot timeline relaxation, lock deletion, state truncation or stale full-manifest replacement.

## Shot persistence verification

New two-child persistence regression fails on the old resolver and passes after exact shot-id/selector routing. Related request-preview/shot-direction/p500 resume/phase-handoff suites: 171 passed, 44 subtests passed. Additional narrow checks reject missing shot, changed selector, missing source cut and render-unit/shot confusion without mutating any parent or sibling. Local diff review confirmed existing scene/cut/render-unit targets keep their original paths. Read-only canonical reprojection identified 32 overwritten parent video containers, with no cinematic projection issues and all exact shot schedules valid after replacing only those containers. The repair accepts only the final-child overwrite signature, preserves shot plans/timelines, holds the existing run lock, and saves a full before-image plus source hashes and field receipt.

## Source-projected recovery and resumed job

32 parent video containers were restored using current cinematic_direction.json and story.md only after exact authored-cut/shot-plan checks, all cinematic projection checks and all shot schedules passed in memory. Full before-image and exact before/after field receipt are stored at logs/repairs/parent-video-projection/; state.txt received a new repair event without changing earlier history. Research/story/visual_value hashes still match their original values. No provider media was generated during repair. Supported restart health checks passed; Computer Use resumed once as job 305f6a95c9b1428c871b55e78ef31f83 at 18:47:07 JST, p500_subprocess toward saved p680. Observe this worker; do not launch another job while it runs.

## Actual generation confirmed

Job 305f6a95c9b1428c871b55e78ef31f83 passed rematerialization at 18:51 JST and started six parallel request-bound asset generations at 18:51:31–32. First two items completed at 18:52:59 and 18:53:03; their PNGs decode successfully. Later requests started as slots became available. No item-generation failures are recorded at this observation. There are 20 requested assets in the frontend; p550/freezing state is a delayed boundary label, so actual worker events establish current image-generation activity. p680 is not complete. Screenshot frontend-generating-assets.png. Keep this healthy worker running and continue the existing 30-minute monitoring; do not restart it due to old p420 repair flags.

Latest exit observation: 8 of 20 asset items have completed, 0 failed; all eight PNGs pass decode verification. Remaining worker activity continues normally.
