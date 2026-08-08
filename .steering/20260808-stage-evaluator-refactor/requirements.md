# Stage evaluator refactor requirements

## Goal

Refactor the code-only stage evaluation layer so that shared primitives have one
implementation, canonical stage-review policy and p-slot pipeline-gate policy
have explicit boundaries, and the existing command/API behavior does not change.

## User-approved scope

- Refactor `toc/stage_evaluator.py` into a small compatibility facade over a
  stage-evaluation package.
- Refactor the shared research, story, script, manifest, and video evaluator
  portions of `scripts/verify-pipeline.py` into explicit pipeline-policy
  adapters.
- Replace the duplicated implementation in the five
  `scripts/review-*-stage.py` entrypoints with one reusable CLI runner while
  retaining every existing script path.
- Add characterization and parity tests before moving implementation.
- The user approved editing `scripts/verify-pipeline.py` despite the new
  uncommitted p680 supervisor-validation hunk. Preserve that hunk unless the
  refactor directly requires adapting it.

## User-visible behavior

There must be no intentional user-visible or artifact-visible behavior change.
In particular, preserve:

- evaluator pass/fail results, check IDs, messages, scores, detail fields, and
  state updates;
- the intentional policy differences between canonical stage reviews and
  p-slot pipeline gates;
- `target_slot` behavior and localized-partial rules in pipeline script/video
  evaluation;
- report filenames, state artifact keys, stdout, exit status, write order, and
  exception behavior of every `review-*-stage.py` command;
- the `eval_report.json`, `run_report.md`, `run_status.json`, and append-only
  `state.txt` contracts owned by `verify-pipeline.py`.

## Architecture constraints

- Use a common-primitives layer plus separate canonical-review and
  pipeline-gate policies. Do not alias one policy to the other.
- Keep `toc.stage_evaluator` as the stable import path for current public
  functions and externally used private compatibility helpers.
- Keep `scripts/verify-pipeline.py` function names, signatures, return schemas,
  and monkeypatch seams used by tests.
- Keep pipeline orchestration and file-writing side effects in
  `scripts/verify-pipeline.py`; the evaluator package remains read-oriented.
- Do not add a dependency or introduce an import cycle.
- Prefer explicit dependencies over module-global mutation. Where compatibility
  requires a module-level monkeypatch seam such as `_probe_duration`, pass it
  explicitly into the extracted implementation.

## Allowed code paths

- `toc/stage_evaluator.py`
- new modules under `toc/stage_evaluation/`
- an optional reusable CLI module under `toc/`
- `scripts/verify-pipeline.py`
- `scripts/review-research-stage.py`
- `scripts/review-story-stage.py`
- `scripts/review-script-stage.py`
- `scripts/review-manifest-stage.py`
- `scripts/review-video-stage.py`
- new `tests/test_stage_evaluator_parity.py`
- clean, directly related evaluator tests only when a new characterization
  cannot live in the new parity test
- this goal's `.steering/20260808-stage-evaluator-refactor/` files

## Protected paths and non-goals

- Do not refactor prompts, prompt literals, `docs/`, `workflow/`, marketing,
  frontend UI, server routes, generation orchestration, or `output/` artifacts.
- Do not change evaluation criteria, thresholds, schemas, p-slot semantics,
  semantic QA gates, or state lifecycle.
- Do not modify the unrelated root `SPEC.md`, `GOAL.md`, or `PLAN.md`.
- Preserve every unrelated dirty file and hunk. Do not stash, reset, clean,
  revert, broadly format, or delete user work.
- Do not modify `tests/test_verify_pipeline.py` merely to make the refactor pass;
  its current dirty assertions are regression evidence.
- Do not add lint, typing, or coverage dependencies.

## Edge cases to preserve

- Canonical warning checks are excluded from scoring; pipeline checks are not.
- Pipeline invalid slot strings keep their existing default fallback behavior.
- `check_manifest_single(..., require_review_artifacts=False)` remains valid.
- `shared_check_manifest_single` remains available in `verify-pipeline.py`.
- Replacing `VERIFY_MODULE._probe_duration` in a test still affects pipeline
  video evaluation.
- Relative `--out` remains relative to the current working directory.
- `--fail-on-findings` alone controls whether findings produce exit code 1.
- A missing `state.txt` does not prevent report creation by review scripts.
- Review-script exceptions remain uncaught and non-zero.

## Scorecard

Pass threshold: every item must pass.

1. Single ownership: identical shared primitives (`non_empty`, `as_list`,
   `nested_get`, `add_check`, grounding-check append, and duration probing) have
   one implementation under `toc/stage_evaluation/`.
2. Explicit policies: canonical stage review and pipeline p-slot gate remain
   separate, named policies with characterization coverage for their known
   differences.
3. Thin adapters: `toc/stage_evaluator.py` is at most 300 lines, and the shared
   evaluator entrypoints left in `scripts/verify-pipeline.py` are compatibility
   adapters rather than full duplicate implementations.
4. Hotspot reduction: no function added or moved under
   `toc/stage_evaluation/` exceeds 200 physical lines; the target area retains
   zero internal import cycles.
5. CLI consolidation: the five review scripts keep their filenames and CLI
   behavior while delegating to one reusable runner.
6. Regression: focused parity tests, existing evaluator/pipeline tests, the full
   Python suite, CI golden dry-runs, and placeholder verification pass.
7. Scope integrity: no prompt/non-code or protected user change is altered.

Scoring inspection:

```bash
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_parity.py
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_scripts.py tests/test_verify_pipeline.py
python -m compileall -q toc server scripts
git diff --check
```

## Fast feedback loop

After each small extraction, run the new parity test plus three representative
existing tests. Expected runtime after the parity fixtures are established:
under 10 seconds.

The full evaluator/pipeline suites are deliberately final or phase-boundary
checks. A baseline run of the evaluator suite exceeded 4 minutes before it was
interrupted; it is not suitable for every edit.

## Done when

1. `tests/test_stage_evaluator_parity.py` proves unchanged canonical/pipeline
   outputs, schemas, public signatures, compatibility imports, monkeypatch
   seams, and all five review CLI contracts.
2. `toc/stage_evaluator.py` is a compatibility facade of at most 300 lines and
   existing imports continue to work under the focused tests.
3. Shared primitives are defined once in `toc/stage_evaluation/`, while
   canonical and pipeline-specific policy code remains separate and auditable.
4. Every shared evaluator entrypoint in `scripts/verify-pipeline.py` is a thin
   adapter that preserves its old signature, schema, and `target_slot` rules;
   pipeline report/state writing stays in that script.
5. The five `scripts/review-*-stage.py --help` commands and parity tests prove
   unchanged flags, defaults, stdout, exit status, output path, write order, and
   state artifact keys through one reusable runner.
6. An AST-based assertion in `tests/test_stage_evaluator_parity.py` proves no
   function under `toc/stage_evaluation/` exceeds 200 lines, the facade is at
   most 300 lines, and the duplicate primitive definitions are absent.
7. New/extracted modules reach at least 80% line coverage using the standard
   library `trace` tool or an already-installed equivalent; no dependency is
   added to obtain the metric.
8. Focused tests, `python -m pytest -q`, compile checks, CI golden dry-runs, the
   placeholder verifier path, and `git diff --check` pass without weakening,
   deleting, skipping, or xfail-marking existing tests.
9. `git diff` shows no intentional changes outside the allowed code/test and
   goal-local steering paths, and preserves unrelated pre-existing hunks.

## Approval record

- 2026-08-08: user approved the proposed scope, non-goals, dirty-worktree
  protection, scorecard, and done-when criteria.
- 2026-08-08: user explicitly allowed the newly observed
  `scripts/verify-pipeline.py` change to be ignored as a blocker. The
  implementation may edit that file but should preserve unrelated semantics.
