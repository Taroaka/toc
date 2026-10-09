# Validation

- Final affected backend suite: **255 passed, 4 subtests passed**. Covers stage checkpoints, all authoring boundaries, missing/invalid p400, exact source/duration recovery, source drift, run-root locks, existing p500 plan/apply, image resume, narration, video candidate reuse and limits, render, malformed operation IDs, cancellation barriers, and publication/rollback conflicts.
- Frontend Vitest: **7 passed** (same-run resume, terminal failure handling, continued polling).
- TypeScript/Vite production build: passed. Existing runtime reports Node 18.20.7 below Vite's supported version and a bundle-size warning; neither prevented this build.
- Pointer docs validator: passed. Scoped git diff whitespace check: passed.
- Code review findings addressed: missing early route; malformed script/manifest routing; input overwrite/conflict handling; confirmed publication heads; missing-output success; operation lookup 404/409; bulk limits; world-walk source and copied-reference reuse; pinned saved-input reads.
- Concurrent research-contract changes were preserved. No removed research-output validator was restored by this work.
- No live generation, production restart, publication, or existing-run mutation was performed. The already-running backend has not been reloaded to deploy these route changes.
- Legacy media calls without an operation journal still need their original request resubmitted. Abrupt loss after remote acceptance but before durable result recording is at-least-once recovery, not exactly-once remote billing.
