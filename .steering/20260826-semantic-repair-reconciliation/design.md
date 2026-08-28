# Design: Semantic Repair Reconciliation

## Current Defect

`_reconcile_after_semantic_repair()` refreshes P400 evidence while repaired
canonical sources still have stale downstream projections. The P400 critics
correctly reject the stale data, preventing later request synchronization and
provider submission.

## Proposed Design

Introduce or reuse one canonical reconciliation operation with this order:

1. Load repaired `story.md`, `script.md`, and `video_manifest.md`.
2. Resolve the changed scene set from repair fingerprints/report selectors.
3. Reproject story-to-script and script-to-manifest fields required by the
   changed contracts.
4. For each affected cut, rebind source event facts/action/reaction/evidence,
   event context, first-frame/motion/narration boundaries, and asset dependencies.
5. Reconcile image-generation character/object/location IDs and explicit
   references.
6. Reconcile character timeline bindings, removing stale variants rather than
   adding semantically invalid variants.
7. Run deterministic script/manifest checks.
8. Only after step 7 passes, refresh P400 review artifacts and require P400
   readiness.
9. Rebuild downstream requests/snapshots and run fresh semantic review.

## Invariants

- Idempotent on unchanged input.
- No provider submission before all current gates pass.
- No mutation of unrelated scenes except deterministic projections whose source
  digest changed.
- No review artifact is written as passed without its normal verifier/critic
  path.
- Transport and semantic failures remain separate.

## Test Design

- Stale action/evidence projection fixture modeled on scene10/scene60.
- Removed transformed-appearance fixture modeled on scene40.
- Idempotence test comparing canonical projections before/after a second pass.
- Ordering test that fails if P400 refresh is called before reconciliation.
- Regression tests around P500 resume and frontend P680 orchestration.

## Final Validation

- Existing Cinderella same-run resume to P680.
- New story through backend create route to P680.
- Assert real files, provenance, terminal slots, and no manual artifact edits.
