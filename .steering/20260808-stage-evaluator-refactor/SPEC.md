# Behavior-preserving stage evaluator refactor

## Goal

Turn the monolithic stage evaluation code into explicit, testable modules while
preserving every existing evaluator, pipeline, state, report, and CLI behavior.

## Scope summary

- `toc/stage_evaluator.py` becomes a compatibility facade.
- New `toc/stage_evaluation/` modules own shared primitives, canonical stage
  policy, pipeline p-slot policy, and review coordination.
- `scripts/verify-pipeline.py` keeps pipeline orchestration and exposes thin
  compatibility adapters for shared stage evaluation.
- Five `scripts/review-*-stage.py` files keep their command paths and delegate to
  one reusable runner.
- A new parity test captures behavioral and structural contracts before code is
  moved.

## User-visible behavior

No intentional behavior changes. Pass/fail results, score/check schemas, check
ordering and text, state updates, report artifacts, stdout, exit codes, CLI
arguments, slot gates, and compatibility import paths remain unchanged.

## Important policy decision

Canonical stage review and pipeline verification are not aliases:

- canonical review has richer rubrics, warning semantics, currentness checks,
  and stage review updates;
- pipeline verification has its own score schema, target-slot semantics,
  localized-partial handling, duration gates, and pipeline report lifecycle.

The implementation extracts common primitives but keeps these policies separate.
Collapsing them into one result policy would be an out-of-scope feature change.

## Scope and non-goals

Allowed production paths are the evaluator facade/package, pipeline adapters,
and review CLI entrypoints. Tests and goal-local steering files may be added.

Do not refactor prompts, docs, workflow contracts, frontend, backend routes,
generation logic, marketing, or output artifacts. Do not change evaluation
criteria or p-slot semantics. Do not add dependencies or broadly format files.
Keep unrelated dirty work intact. The user allowed the new
`scripts/verify-pipeline.py` hunk to cease blocking this work, but unrelated
behavior in that hunk should still be preserved.

## Architecture

- `common.py`: shared parsing/check/grounding/duration primitives.
- stage modules: canonical research/story, script, manifest, and video policy.
- `pipeline.py`: pipeline-only policy with dependencies passed explicitly.
- `runner.py`: canonical evaluate/render/append coordination.
- `toc/stage_evaluator.py`: explicit compatibility re-exports only.
- `toc/stage_review_cli.py`: common implementation for the five review commands.

Use an acyclic dependency order and retain current monkeypatch seams through
explicit dependency parameters where necessary.

## Risks and boundaries

- The similarly named canonical and pipeline checks currently produce different
  result schemas and pass/fail decisions. Parity means preserving each against
  its own baseline, not making the two equal.
- Tests import private evaluator helpers and dynamically load pipeline functions.
  Keep an explicit compatibility layer until all current callers pass.
- Full evaluator tests are slow; use selected subtests and the new parity suite
  during iteration, with broad suites at phase and completion gates.
- Existing dirty changes make broad formatting and destructive git operations
  unacceptable.

## Scorecard

Pass threshold: 7/7 and no regression failure.

1. Shared primitives have one definition under `toc/stage_evaluation/`.
2. Canonical and pipeline policies are explicit and independently characterized.
3. `toc/stage_evaluator.py` is at most 300 lines; pipeline shared entrypoints are
   thin compatibility adapters.
4. No target-package function exceeds 200 lines; internal import cycles remain
   zero.
5. Five review commands delegate to one runner without CLI/output changes.
6. Changed-code line coverage is at least 80%; focused, full, golden, and
   placeholder checks pass.
7. No protected or non-code scope is intentionally modified.

Scoring paths:

```bash
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_parity.py
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_scripts.py tests/test_verify_pipeline.py
python -m compileall -q toc server scripts
python -m pytest -q
git diff --check
```

Stop condition: all nine requirements in `requirements.md` Done when are
evidenced and the final diff review finds no behavior or scope change.

## Feedback loop

After every coherent edit, run parity tests and three representative existing
tests. Expected runtime is under 10 seconds once the parity suite is in place.
At phase boundaries run the relevant evaluator/pipeline clusters. Run the full
suite, golden dry-runs, placeholder render/verifier path, and standard-library
coverage only before completion.

## Working memory

Maintain goal-local `PLAN.md`, `ATTEMPTS.md`, `NOTES.md`, `CONTROL.md`, and
`tasklist.md`. Update them after each meaningful experiment and before phase
changes so the run does not rely on conversation context.

## Done when

The nine concrete Done when items in `requirements.md` are the user-approved
termination contract.
