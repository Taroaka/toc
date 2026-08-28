# Semantic Repair Reconciliation and Image-Generation Completion

## Goal

Fix the systemic frontend-create failure where semantic producer repair updates
`story.md`, `script.md`, or `video_manifest.md`, but stale cut, character,
timeline, reference, and request projections cause P400 review to fail before
image generation. After fixing the pipeline, prove it first on the existing
Cinderella run and then on a brand-new frontend-created story through the real
P680 image-review handoff.

## User-Approved Outcome

1. Repair reconciliation is fixed in production code.
2. The existing Cinderella run resumes in the same run directory and reaches
   P680 without manual artifact edits after the code fix.
3. A new story is created from the frontend-button-equivalent backend route.
4. The new run generates reusable assets at P560 and scene images at P660.
5. The new run reaches P680 with real Codex image-generation provenance and no
   manual repair of `story.md`, `script.md`, `video_manifest.md`, review files,
   or request snapshots.

## Current Failure

`server/image_gen_app.py::_reconcile_after_semantic_repair()` refreshes P400
review artifacts before all repaired semantic sources have been projected into
their dependent contracts. Concrete failures observed in the Cinderella run:

- repaired `scene_event.visible_action` differs from stale
  `cut_contract.source_event_contract.source_visible_action`;
- repaired `required_visual_evidence` is absent from cut contracts;
- character appearance variants removed by semantic repair remain in
  `asset_dependency.character_ids_required` and
  `image_generation.character_ids`;
- manifest character timelines no longer bind every remaining cut asset ID;
- P400 critics see these deterministic failures and materialize
  `changes_requested`, so provider submission is never reached.

## Scope

- Repair dependency reconciliation and ordering in `server/image_gen_app.py`.
- Add or reuse deterministic projection helpers in the smallest appropriate
  module, likely `scripts/toc-immersive-frontend-run.py` or a focused `toc/`
  module.
- Reconcile changed scene events into cut contracts, event context, asset
  dependencies, image-generation character references, and character timelines.
- Ensure P400 review materialization happens only after deterministic
  reconciliation passes.
- Add focused unit/integration tests covering the observed failures.
- Run existing-run and fresh-run P680 verification through canonical scripts and
  backend routes.

## Non-Goals

- Do not weaken, skip, or fabricate semantic QA results.
- Do not mark reviews passed from file existence or schema/count success.
- Do not manually patch run artifacts as the final solution.
- Do not create local raster placeholder images.
- Do not proceed past P680 into narration, video generation, or final render.
- Do not modify marketing, LINE, unrelated media, or unrelated user changes.
- Do not redesign the entire story/cut schema unless the focused fix proves
  impossible and the user approves a strategic pivot.

## Architecture Constraints

- Preserve earliest-source-first semantics: `story.md -> script.md ->
  video_manifest.md -> requests/snapshots`.
- Preserve append-only `state.txt` history and same-run P500 resume semantics.
- Provider submission remains fail-closed until deterministic and semantic gates
  are current.
- Correct stale downstream references; do not reintroduce semantically invalid
  variants merely to satisfy a timeline count check.
- Reconciliation must be deterministic and idempotent.
- A second reconciliation pass on unchanged input must produce no semantic or
  byte-level contract drift, except allowed timestamp/state evidence.
- Transport failures remain distinct from semantic failures.

## Scorecard

Pass threshold: every item passes.

- Unit projection: repaired event action/evidence is exactly projected into all
  affected cut contracts.
- Reference projection: removed/changed appearance variants are reflected in
  cut asset dependencies, image request references, and timelines.
- Ordering: P400 reviews are refreshed only after deterministic reconciliation.
- Idempotence: a second reconciliation pass does not change canonical contracts.
- Gate integrity: semantic QA and provider gates remain fail-closed.
- Existing-run proof: Cinderella reaches P680 with real generated files.
- Fresh-run proof: one new frontend-created story reaches P680 without manual
  artifact edits.

Primary scoring inspection paths:

```bash
cd tests
PYTHONPATH=.. python -m unittest test_semantic_repair_reconciliation
PYTHONPATH=.. python -m unittest \
  test_image_gen_server.ImageGenApiTests.test_non_image_semantic_repair_reconciles_dependencies_in_safe_order
python scripts/verify-pipeline.py \
  --run-dir output/<run> --flow immersive --profile standard
```

Stop condition: all focused tests pass, the relevant regression suites pass,
the existing Cinderella run reaches P680, and a fresh frontend-created run also
reaches P680 with real asset and scene-image provenance.

## Feedback Loop

Fast check after each projection/reconciliation edit, expected under one minute:

```bash
cd tests
PYTHONPATH=.. python -m unittest test_semantic_repair_reconciliation
```

This check is representative because it reproduces the exact repair-to-P400
boundary without external image generation. Run the broader P400/frontend tests
after each coherent implementation step. Reserve real provider-backed P680 runs
for the final existing-run and fresh-run verification.

## Done When

1. A focused test mutates scene event action/evidence like the Cinderella
   repair, starts with stale cuts, runs production reconciliation, and proves
   exact cut-contract projection plus an approved deterministic P400 result.
2. A focused test removes an appearance variant from a repaired scene and proves
   stale asset/image references are removed rather than reintroduced into the
   timeline.
3. Reconciliation is idempotent and tested.
4. P400 review refresh cannot run against unreconciled repaired sources.
5. Existing semantic review, repair, P500 resume, run-root binding, and image
   generation tests touched by the change pass.
6. The same Cinderella run reaches `p560=done`, `p660=done`, and
   `p680=awaiting_approval`, with nonzero real asset and scene-image files.
7. A new story created through the frontend-button-equivalent backend route
   reaches the same P680 state without manual artifact edits.
8. Both P680 runs pass the normal standard pipeline validator and contain
   request-bound Codex image provenance.

## Risks

- Existing helper functions may rebuild prompts without rebuilding every cut
  contract field, requiring a focused canonical projection helper.
- Repair can change scene participants, event IDs, location routes, dayparts, or
  appearance variants; reconciliation must handle all without inventing story
  content.
- Real image generation is slow and may hit external transport limits. Such
  failures must be diagnosed separately and must not be reported as a successful
  reconciliation.
- The current Cinderella `state.txt` is very large; this is a performance risk
  but not part of the initial functional fix unless it blocks verification.
