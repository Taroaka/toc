# CONTROL

## Status contract

status_file: `.steering/20260808-stage-evaluator-refactor/PLAN.md`
tasklist: `.steering/20260808-stage-evaluator-refactor/tasklist.md`
attempt_log: `.steering/20260808-stage-evaluator-refactor/ATTEMPTS.md`
durable_notes: `.steering/20260808-stage-evaluator-refactor/NOTES.md`
update_memory_after: every meaningful test/implementation attempt
check_control_before: phase change, strategic pivot, expensive step

## Human priorities

primary_priority: behavior preservation
secondary_priority: maintainability with auditable evidence

## Scope knobs

allowed_files:
- `toc/stage_evaluator.py`
- `toc/stage_evaluation/**`
- `toc/stage_review_cli.py`
- `scripts/verify-pipeline.py`
- `scripts/review-*-stage.py`
- `tests/test_stage_evaluator_parity.py`
- directly related clean evaluator tests only when necessary
- `.steering/20260808-stage-evaluator-refactor/**`

protected_files:
- root `SPEC.md`, `GOAL.md`, and `PLAN.md`
- `docs/**`, `workflow/**`, prompts, marketing, frontend, server routes, and `output/**`
- every unrelated pre-existing dirty hunk
- current `tests/test_verify_pipeline.py` assertions and dirty changes

max_blast_radius: stage evaluation package, compatibility adapters, and review CLI only

## Resource knobs

max_runtime_per_step: 15 minutes unless a named final regression is known to require longer
max_parallel_jobs: 3
network_allowed: false
external_api_allowed: false

## Decision gates

require_approval_for:
- strategic pivot
- destructive change
- dependency change
- public behavior or schema change
- test weakening, deletion, skip, or xfail
- scope expansion

## Sidecar inputs

sidecar_apply_cadence: between green phases only
review_queue_file: none

## Latest human nudge

Proceed with the approved evaluator refactor. The new uncommitted
`verify-pipeline.py` hunk does not block editing that file. Add no feature and do
not refactor prompts or non-code production content.
