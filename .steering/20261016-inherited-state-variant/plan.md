# Inherited state variants in projection preflight

## Requirement and cause

The p420 scene validator recognizes variants defined by preceding accepted scenes,
but its projection preflight omits that registry when calling `project_scene`.
A later result frame that validly reuses one of those variants therefore stops
with `cinematic_result_frame_variant_unbound`.

## Change and checks

Pass the same preceding-scene variant inventory through `projection_diagnostics`
to the existing projector. Keep current-scene variants owned by the current row,
and preserve missing-binding and source-order checks. Do not regenerate or change
valid story content to compensate for a missing runtime argument.

- [x] Reproduce with object and character variants reused in a later result frame.
- [x] Pass the existing validated inventory and verify cached resume reuse.
- [x] Run affected tests, review incremental changes, and check the saved candidate.
- [x] Resume the same production run with unchanged upstream hashes and budgets.

## Evidence

- Both regression variants failed before the change with the same unbound-reference
  exception as production.
- Asset variants, asset requests, cinematic authoring, and layered repair tests:
  109 passed. One previously confirmed unrelated failure in the semantic-cut fake
  author test remains excluded (see the preceding shot-state repair record).
- Incremental review found no actionable issues; missing source bindings still
  fail closed and cached scenes are not regenerated.
- The saved failed scene now passes scene validation and proceeds through result
  variant resolution. It exposes a separate state-source content diagnostic that
  the previously fixed bounded repair path handles. No artifact was hand-edited.
- The single resume request and upstream hashes are preserved in `resume.json`.
  Completion will be verified from the running worker; job acceptance alone is
  not completion.
