# Shot state projection repair

## Requirements

Keep validating the authored shot timeline and state references. A recoverable
`state_source` mismatch must reach the existing bounded p420 repair loop, with
the exact cut, shot, and view, rather than terminating as an unclassified runtime
error. Preserve other shots, narration, upstream checkpoints, and repair budgets.
Use no title-specific branches or fixtures.

## Design

Emit the existing typed shot-image projection diagnostic for premature result
state, resetting a transformed visible entity to start state, and a missing
previous-shot reference. The p400 projection already adds the parent cut index.
Map these known codes to the affected view's `state_source` field with valid
inheritance choices. Unknown runtime, path, and provenance errors still fail
closed. The author selects the correction and the normal validators rerun.

## Tasks

- [x] Add failing regression tests for typed diagnostics and bounded repair.
- [x] Implement state-source diagnostics without weakening state checks.
- [x] Run affected tests and review the incremental changes.
- [x] Verify saved failure is classified and resume the same run once.
- [x] Continue scheduled monitoring through narration completion.

## Validation

- Four initial regressions failed with the unclassified state errors before the fix.
- The final affected suite passed 113 tests (layered repair, shot direction,
  cinematic authoring, and shot runtime). One unrelated test,
  `test_semantic_cut_rewrite_keeps_healthy_cut_and_uses_original_validator`, failed
  identically with the pre-task module snapshots and was excluded from the final
  run. Its failure is a JSON decode expectation in its fake author; it is not
  evidence that this state-source repair failed.
- Review identified an invalid `previous_end` option for end views. Restricted it
  to later initial views and covered both cases; follow-up review found no
  actionable incremental findings.
- The saved failed candidate now yields an exact
  `/cuts/2/shot_plan/shots/1/end_view/state_source` diagnostic, without changing the
  run artifacts or weakening projection validation.
- Resume request and upstream hashes are in `resume.json`. The existing API
  accepted job `092f29a8141d4581b999dd547c68e5d7` with mode
  `authoring_subprocess`; acceptance is not completion. No stack restart was
  needed because the resumed authoring subprocess imports the changed modules.

## Monitoring endpoint

All 19 narration candidates passed revision, request/provenance, hash, decode,
stream, non-silent output, and measured-duration checks on 2026-10-16. The 11
intentional silent cuts remain unchanged. Detailed results are stored in the
run's `logs/media_generation/narration_monitor/validation.json`. Candidate
generation is complete; human listening/selection and downstream video work
are not claimed complete. The requested monitoring endpoint has been reached.
