# PLAN

## Goal

Make semantic repair converge into valid P400 and real P680 image generation.

## Current Strategy

Reproduce the stale-projection boundary with focused tests, add deterministic
reconciliation before P400 review refresh, then verify existing and fresh runs.

## Phases

- [x] Confirm user-approved goal and completion criteria.
- [x] Inspect reconciliation ownership and existing helper coverage.
- [x] Write failing focused tests.
- [x] Implement the smallest safe reconciliation fix.
- [ ] Run focused and regression verification. Focused tests are green; broader regression and review remain.
- [ ] Resume Cinderella to P680.
- [ ] Create a new story to P680.
- [ ] Final validation and report.

## Open Decisions

- Coverage package is not installed. Do not add a dependency without approval;
  rely on focused behavior tests unless an existing coverage route is found.
