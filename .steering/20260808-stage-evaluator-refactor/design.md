# Stage evaluator refactor design

## Design summary

Split the monolithic evaluator into a dependency-ordered package, preserve
`toc.stage_evaluator` as a compatibility facade, and move pipeline-only gate
policy behind thin adapters. A reusable review CLI runner removes five copies of
the same command implementation.

The refactor separates reuse from policy. Canonical review and pipeline gating
currently differ in scoring, schemas, semantic-review requirements, duration
gates, and slot behavior. Those differences are contracts, not duplication to
erase.

## Proposed module boundaries

```text
toc/
├── stage_evaluator.py              # compatibility facade only
├── stage_review_cli.py             # reusable review command runner
└── stage_evaluation/
    ├── __init__.py
    ├── common.py                   # parsing/check/score/grounding primitives
    ├── research_story.py           # canonical research/story policy
    ├── script.py                   # canonical script and scene/cut policy
    ├── manifest.py                 # canonical manifest policy
    ├── video.py                    # canonical video policy
    ├── pipeline.py                 # p-slot pipeline policy adapters
    └── runner.py                   # evaluate/render/append coordination
```

The exact split may be tightened during extraction, but changing the dependency
direction or introducing an import cycle requires a recorded design adjustment.

Expected dependency direction:

```text
common
  ├── research_story
  ├── script (may depend on research_story read helpers)
  ├── manifest (may depend on script/read helpers)
  └── video

runner -> stage policies
pipeline -> common + narrowly shared read helpers
stage_evaluator facade -> all compatibility exports
stage_review_cli -> stage_evaluator public runner API
```

## Compatibility architecture

### Canonical stage review

Canonical functions keep their current richer rubrics, warning handling,
semantic/currentness gates, review artifacts, and `eval.*` state updates.

### Pipeline p-slot gate

Pipeline functions keep their current lightweight or slot-aware behavior:

- pipeline scoring continues to include all checks;
- script adapters retain `target_slot`, localized-partial behavior, and
  generation-receipt requirements;
- video adapters retain duration-fit and `video_motion` slot gates;
- pipeline return dictionaries keep their current schema and empty/non-empty
  update behavior;
- report and state writes stay in `scripts/verify-pipeline.py`.

### Existing import paths

The facade explicitly re-exports all production imports plus externally used
private helpers discovered by `rg`. Do not use a dynamic export-all loop; the
compatibility surface should be inspectable.

`scripts/verify-pipeline.py` retains these module attributes when tests or
callers rely on them:

- `check_research`, `check_story`, `check_script_single`,
  `check_script_scene_series`, `check_manifest_single`,
  `check_manifest_scene_series`, `check_video_single`, and
  `check_video_scene_series`;
- `shared_check_manifest_single`;
- `_probe_duration` and other explicit monkeypatch seams.

### Review CLI

`toc.stage_review_cli.run_stage_review_cli(stage, description, default_name)`
owns argument parsing and execution. Each existing script remains a tiny
entrypoint that provides stage-specific constants.

The reusable runner preserves:

- flags and defaults;
- path resolution behavior;
- UTF-8 report write followed by state append;
- one-line stdout path;
- `--fail-on-findings` exit behavior;
- uncaught exceptions.

## TDD migration sequence

1. Add `tests/test_stage_evaluator_parity.py` before production changes.
2. Characterize public signatures, return schemas, known policy differences,
   facade compatibility names, `_probe_duration` monkeypatch behavior, and CLI
   contracts. Run red only for the new structural requirements; existing
   behavior assertions must start green.
3. Extract shared primitives and rerun parity/focused tests.
4. Extract canonical modules in dependency order, updating the facade after
   each move.
5. Extract pipeline policy functions and replace script bodies with thin
   wrappers. Keep orchestration in place.
6. Extract the review CLI runner and replace the five script bodies.
7. Split the remaining over-200-line functions without changing ordered checks
   or messages.
8. Run focused, phase, and final verification; review the complete diff.

## Characterization strategy

- Prefer representative temporary run directories and exact result comparison.
- Test known intentional differences explicitly instead of forcing canonical and
  pipeline results to equal each other.
- Assert ordered check IDs/messages where ordering is part of report output.
- Inspect function signatures with `inspect.signature`.
- Load `verify-pipeline.py` the same way its current tests do so module-level
  seams are exercised.
- Exercise every review script as a subprocess for CLI compatibility.
- Add AST checks only for structural scorecard requirements; behavioral tests
  remain the primary safety net.

## Coverage strategy

The repository has no coverage dependency. Do not add one. Use Python's
standard-library `trace` module against the focused parity/evaluator tests and
calculate line coverage only for newly added or materially extracted
`toc/stage_evaluation/` and `toc/stage_review_cli.py` code. The passing threshold
is 80% for that changed-code allowlist.

## Risk controls

- Preserve exact check construction order while moving code.
- Move one coherent region at a time; avoid simultaneous policy cleanup.
- Keep compatibility aliases during the whole migration.
- Read the live dirty hunk before every edit to `scripts/verify-pipeline.py`.
- Do not auto-format unrelated sections of large files.
- If current behavior is ambiguous, write a characterization test and preserve
  it; do not choose a new behavior during this goal.
- If a required compatibility behavior can only be preserved by widening scope,
  stop at the current green state and request approval.

## Rollback approach

No destructive git rollback is permitted. Each extraction must be small enough
to reverse with a targeted `apply_patch`. Record failed approaches and their
evidence in `ATTEMPTS.md` before attempting a different design.
