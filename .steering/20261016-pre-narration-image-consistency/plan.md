# Image-only correction before narration

## Requested behavior

Image-only inconsistencies (identity, costume, props, poses, spatial layout,
first/last-frame compatibility) must be found and corrected after image generation
and before narration authoring/TTS. Audio duration and placement checks remain
before video submission. Existing generated audio and active production workers
must be preserved; this change applies through the shared pipeline, not by title.

## Design

- Extend the existing scene preparation service with an `images` phase. It uses
  actual hash-bound images and the same bounded repair/publication workflow,
  without requiring an audio file or considering measured speech timing.
- Keep image and video readiness receipts separate. Image readiness binds visual
  inputs and image bytes, ignores later narration-only changes, and never grants
  video readiness. Keep full source-byte checks during publication.
- The automatic narration continuation performs image preparation first. Manual
  narration authoring/generation entrypoints use the same prerequisite; stale or
  unresolved images cannot reach TTS. The standalone media generator fails closed
  on missing image readiness for marked cinematic runs.
- Preserve source story, narration, parent timing, request identity, locks,
  immutable outputs, cumulative image/cost budgets and uncertain-submit handling.
- Add API/CLI phase selection and explain the order in canonical docs. No new
  fixed p-slot or score-based review stage is introduced.

## Validation tasks

- Reproduce missing-audio failure for image-only preparation and order violation
  at narration entrypoints with offline tests.
- Test visual receipt reuse after audio/text changes and invalidation on changed
  image bytes or visual contracts; image readiness cannot bypass video checks.
- Test repairs preserve existing narration and provider settings, and TTS is not
  called when image preparation is incomplete.
- Run affected existing service/API/narration tests and incremental review.
- Preserve the active production run; update the monitor with the new ordering.

## Implementation and validation

- Implemented separate image snapshots/receipts, shared bounded repairs, API/CLI
  phase selection, automatic/manual narration prerequisites and standalone TTS
  guard. Image-only failure preserves the completed p680 handoff.
- Initial scoped validation: 105 passed, two existing unrelated failures excluded
  (undefined `explicit_offset` in a frontend fixture; video bulk-limit fixture
  lacking a manifest). The affected video bulk handler and durable-operation
  wrapper are byte-for-byte unchanged from the task baseline.
- Read-only image snapshots for all five scenes in the current production run
  succeeded and included zero audio files. No narration or running worker changed.
- Reviewer findings on saved fixed-image/model settings and phase-specific
  cancellation were addressed with regression tests. Manual text save/silent
  choice remains available: it does not generate narration, and should not start
  image generation as a side effect.
- Pointer docs and whitespace checks passed. Automation remains active every
  30 minutes with the new ordering recorded. Fresh CLI processes load the change;
  the resident server needs a safe restart after active jobs finish, not during
  the current image-repair operation.
- Final review also fixed stale phase status when the shared lock belongs to the
  other phase. Reviewer confirmed all adopted fixes, with no further findings.
  Final focused validation includes 13 new image-consistency regression cases.
