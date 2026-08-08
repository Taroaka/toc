# PLAN

## Goal

Refactor stage evaluation into explicit modules without changing behavior.

## Current strategy

Characterize both policies first, extract shared primitives, then move canonical
and pipeline policies behind compatibility adapters in small green steps.

## Phases

- [x] Inspect relevant code, tests, policy differences, and constraints.
- [x] Finish the goal contract and configuration check.
- [x] Add behavior characterization and red structural tests.
- [x] Extract the smallest shared primitive layer.
- [x] Extract canonical stage modules and facade.
- [x] Extract pipeline policy adapters and review CLI runner.
- [x] Meet structural and coverage thresholds.
- [x] Run scoped final verification and independent review.

## External worktree limitations

- Whole-repository pytest remains red in four out-of-scope tests from the
  ignored current worktree changes.
- Golden and placeholder commands stop before evaluator execution on existing
  grounding `missing_inputs` gates.

## Open decisions

- The installed Codex config does not match Goal Forge's autonomous long-context
  profile. Execute this contract in the active task without changing user config.
- Stop for approval only if compatibility requires a dependency change,
  public behavior change, destructive operation, or scope expansion.
