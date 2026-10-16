# Ordinary shot end frames

## Requirements

An authored end view may show the result of ordinary motion without requiring a
reusable appearance transformation. Preserve the starting-frame prohibition on
future result state and every source-bound transformation/reference check.
Do not change source prose, media, pending author candidates, or repair budgets.

## Design

Allow `end_view.state_source=result` without changed entities only when the parent
has no result image or result-state reference. It uses the existing base identity
references plus the authored end-view composition and pose. An initial view still
cannot request a future result. Any parent result-variant contract still requires
its transform event before either view can select it. Document this distinction.

## Tasks

- [x] Reproduce ordinary end-view failure and protect premature variant use.
- [x] Implement the narrow end-view rule; validate and review.
- [x] Validate the saved candidate with existing limits, then request one resume.

## Verification

The ordinary end-view test failed before the change; both premature-parent-result
cases already failed closed. After implementation, all 59 shot-direction,
shot-runtime, and asset-state tests pass. `git diff --check` and pointer-doc
validation pass. Isolated read-only review found no state/provenance regression.

The saved pending scene passes both `validate_scene_direction` and actual
`projection_diagnostics`, including reconstructed prior-scene resources and
variants, without any candidate edit or budget change. Automatic repair remains
at its original cap; valid output may proceed through the normal worker.

Baseline:
`/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-ordinary-result-zw2p6i45`.

## Guidance placement correction

The added `SHOT_PLAN_FORMAT.end_view` description changed the serialized field
contract and thus invalidated accepted/pending author cache bindings despite no
structural field change. The subsequent resume regenerated an earlier scene and
stopped at the unchanged repair cap. Restore the exact prior description and
place the clarification in `SHOT_AUTHOR_GUIDANCE`, which is the prose instruction
layer. No cache checks or recorded bindings are modified.

The recomputed current source binding now exactly matches all three accepted
scene caches and the pending fourth scene. A regression test confirms that a
guidance-only update preserves accepted-scene reuse after interruption.
Incremental snapshot:
`/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-shot-guidance-resume-fsyss9xf`.
