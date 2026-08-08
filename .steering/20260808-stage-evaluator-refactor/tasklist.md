# Stage evaluator refactor task list

## Goal preparation

- [x] Inventory code hotspots, policy differences, tests, and dirty paths.
- [x] Obtain user approval for scope, non-goals, scorecard, and done_when.
- [x] Resolve the new `verify-pipeline.py` dirty-hunk handling decision.
- [x] Compile and self-audit `SPEC.md` and `GOAL.md`.
- [x] Check Codex `/goal` configuration readiness.

## Baseline and TDD

- [x] Record baseline HEAD, dirty paths, LOC/function metrics, import surfaces,
      and focused test timings in `NOTES.md`.
- [x] Add `tests/test_stage_evaluator_parity.py` behavior characterization.
- [x] Run behavior characterization green and structural assertions red before
      production refactoring.

## Implementation

- [x] Create `toc/stage_evaluation/` and extract shared primitives.
- [x] Extract canonical research/story policy and preserve facade exports.
- [x] Extract canonical script/scene/cut policy and preserve facade exports.
- [x] Extract canonical manifest policy and preserve facade exports.
- [x] Extract canonical video policy and preserve facade exports.
- [x] Extract evaluator runner/render/state coordination.
- [x] Extract pipeline-specific stage policies and convert
      `scripts/verify-pipeline.py` shared entrypoints to thin adapters.
- [x] Add the reusable review CLI runner and convert all five scripts.
- [x] Split remaining over-200-line target functions while green.

## Verification

- [x] Pass fast parity and representative tests after each extraction.
- [x] Pass the focused evaluator and pipeline suites.
- [x] Prove at least 80% changed-code line coverage without a new dependency.
- [x] Pass compile, import-cycle, AST scorecard, and diff checks.
- [ ] Pass the full Python test suite.
- [ ] Pass CI golden dry-runs and placeholder render/verifier checks.
- [x] Complete independent code review and address all actionable findings.
- [x] Confirm no protected path or unrelated dirty hunk changed.

## Completion

- [x] Update `ATTEMPTS.md`, `NOTES.md`, and this tasklist with final evidence.
- [ ] Verify every `GOAL.md` done_when item and scorecard threshold.
