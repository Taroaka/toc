<goal>
Refactor ToC stage evaluation into explicit, acyclic modules without changing
any evaluator, pipeline, state, report, artifact, or CLI behavior. Produce a
small `toc.stage_evaluator` compatibility facade, single-owner shared
primitives, separate canonical-review and p-slot pipeline-gate policies, thin
`verify-pipeline.py` adapters, one reusable review CLI runner, and auditable
characterization evidence.
</goal>

<context>
Read first:

- `.steering/20260808-stage-evaluator-refactor/requirements.md`
- `.steering/20260808-stage-evaluator-refactor/design.md`
- `.steering/20260808-stage-evaluator-refactor/CONTROL.md`
- `.steering/20260808-stage-evaluator-refactor/NOTES.md`
- `docs/root-pointer-guide.md`
- `toc/stage_evaluator.py`
- `scripts/verify-pipeline.py`
- `tests/test_stage_evaluator_scripts.py`
- `tests/test_verify_pipeline.py`
- all five `scripts/review-*-stage.py` entrypoints

Before editing, run:

```bash
git status --short
git diff -- scripts/verify-pipeline.py tests/test_verify_pipeline.py
rg "from toc\.stage_evaluator import|STAGE_EVALUATOR\._|VERIFY_MODULE\._|shared_check_manifest_single" scripts toc tests -n
rg "^def (check_|non_empty|as_list|nested_get|add_check|_probe_duration|append_grounding)" toc/stage_evaluator.py scripts/verify-pipeline.py -n
```

Baseline HEAD recorded during planning:
`fc439442b9d22acb07e33805103bb1a14b3229f8`. The worktree contains extensive
unrelated user changes. The user allowed the new `scripts/verify-pipeline.py`
p680 hunk to cease blocking this refactor, but unrelated semantics should remain
intact.
</context>

<constraints>
- Preserve behavior. Existing canonical and pipeline outputs are separate
  baselines; do not make the two policies equal.
- Preserve pass/fail results, ordered check IDs/messages, scores, detail keys,
  return schemas, state updates, report contents, stdout, exit codes, file write
  order, CLI arguments/defaults, slot fallback behavior, and compatibility
  imports.
- Keep pipeline orchestration and all report/state file writes in
  `scripts/verify-pipeline.py`.
- Keep `toc.stage_evaluator` as the explicit compatibility import path. Re-export
  current production/public names and externally used private helpers without a
  dynamic export-all loop.
- Keep pipeline function names/signatures and module monkeypatch seams,
  especially `target_slot`, `shared_check_manifest_single`, and
  `_probe_duration`.
- Use common primitives plus separate canonical-review and pipeline-gate policy
  modules. A direct canonical-to-pipeline alias is forbidden because it changes
  behavior.
- Do not add dependencies, evaluation rules, API features, schemas, CLI flags,
  or import cycles.
- Do not refactor or edit prompts, prompt literals, `docs/`, `workflow/`, UI,
  server routes, generation orchestration, marketing, or `output/` artifacts.
- Do not overwrite root `SPEC.md`, `GOAL.md`, or `PLAN.md`.
- Preserve unrelated dirty files/hunks. Do not stash, reset, clean, revert,
  broadly reformat, or delete user work.
- Do not weaken, delete, skip, or xfail tests to obtain a passing result.
- Do not edit `tests/test_verify_pipeline.py` merely to adapt expectations to
  the refactor; treat its current assertions as regression evidence.
- Use `apply_patch` for manual edits and keep every extraction small enough to
  verify independently.
</constraints>

<scorecard>
Primary checklist; passing threshold is 7/7 with no regression failure:

1. Single ownership: `non_empty`, `as_list`, `nested_get`, `add_check`,
   grounding-check append, and duration probing have one implementation under
   `toc/stage_evaluation/`.
2. Policy clarity: canonical stage review and pipeline p-slot gate are separate,
   named policies with characterization tests for their known differences.
3. Thin compatibility: `toc/stage_evaluator.py` is at most 300 physical lines,
   and shared stage entrypoints in `scripts/verify-pipeline.py` are thin adapters
   rather than full duplicate implementations.
4. Hotspot reduction: no function under `toc/stage_evaluation/` exceeds 200
   physical lines and the target package has zero internal import cycles.
5. CLI consolidation: all five review scripts retain their filenames/contracts
   while delegating to one reusable runner.
6. Evidence: changed/extracted code has at least 80% line coverage, focused and
   full regressions pass, and golden/placeholder flows remain green.
7. Scope integrity: diff inspection finds no intentional prompt/non-code or
   protected user-work change.

Scoring commands and inspection paths:

```bash
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_parity.py
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_scripts.py tests/test_verify_pipeline.py
python -m compileall -q toc server scripts
python -m pytest -q
git diff --check
git diff --stat
```

`tests/test_stage_evaluator_parity.py` must contain the AST/import-cycle/facade
size assertions used to audit structural thresholds. Stop only when every
checklist item and every done_when item passes and final diff review finds no
behavioral or scope drift.
</scorecard>

<done_when>
1. `tests/test_stage_evaluator_parity.py` proves unchanged canonical/pipeline
   outputs, result schemas, public signatures, compatibility imports,
   monkeypatch seams, and all five review CLI contracts; the file passes with
   `python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_parity.py`.
2. `toc/stage_evaluator.py` is an explicit compatibility facade of at most 300
   physical lines, and existing import/call sites pass focused evaluator tests.
3. Shared primitives are defined once under `toc/stage_evaluation/`; canonical
   and pipeline-specific policy code is separate and its intentional behavior
   differences are asserted rather than erased.
4. Shared evaluator entrypoints in `scripts/verify-pipeline.py` are thin adapters
   preserving the old signatures, schemas, `target_slot` rules, module
   monkeypatch seams, and report/state ownership; `tests/test_verify_pipeline.py`
   passes unchanged relative to its starting worktree state.
5. Each `scripts/review-*-stage.py --help` command and parity subprocess tests
   prove unchanged flags/defaults, stdout, exit status, output resolution, write
   order, exception behavior, and state artifact key through one reusable
   runner.
6. AST assertions in `tests/test_stage_evaluator_parity.py` prove the facade is
   at most 300 lines, no target-package function exceeds 200 lines, duplicate
   primitive definitions are absent, and the target package has no internal
   import cycle.
7. A standard-library `trace` report or already-installed equivalent shows at
   least 80% line coverage for newly added or materially extracted
   `toc/stage_evaluation/` and `toc/stage_review_cli.py` code, without adding a
   dependency.
8. Focused tests, `python -m pytest -q`, compile checks, CI golden dry-runs,
   placeholder render/verifier checks, pointer validation, and
   `git diff --check` pass without test weakening.
9. Final `git diff` inspection shows only allowed evaluator/test and goal-local
   steering changes, with unrelated pre-existing dirty work preserved.
</done_when>

<feedback_loop>
On every red/green/refactor step, run the new parity test plus these three
representative evaluator tests:

```bash
python -m pytest -q -p no:cacheprovider \
  tests/test_stage_evaluator_parity.py \
  tests/test_stage_evaluator_scripts.py::TestStageEvaluatorScripts::test_adjacent_distinct_cuts_reusing_canonical_motion_and_end_state_are_redundant \
  tests/test_stage_evaluator_scripts.py::TestStageEvaluatorScripts::test_script_evaluator_fails_without_scene_set_approval \
  tests/test_stage_evaluator_scripts.py::TestStageEvaluatorScripts::test_image_api_prompt_v2_gate_allows_omitted_optional_fragments
```

Expected runtime: under 10 seconds after the parity fixtures exist. Run after
every coherent extraction. This check represents compatibility wiring, script
policy, and manifest/prompt policy, but does not cover every slow subprocess or
pipeline slot.

At each policy/module phase boundary run the relevant `-k` cluster from
`tests/test_stage_evaluator_scripts.py` and `tests/test_verify_pipeline.py`.
The complete focused pair is a slower escalation check. A baseline evaluator
run exceeded 4 minutes before interruption, so do not run the complete pair on
every edit.
</feedback_loop>

<workflow>
1. Reread `CONTROL.md`; inspect live dirty hunks and compatibility call sites;
   update `NOTES.md` if the baseline changed.
2. Add behavior characterization to `tests/test_stage_evaluator_parity.py`.
   Existing behavior assertions must start green. Add structural assertions that
   fail against the monolith to establish the TDD red state.
3. Extract the common primitives into `toc/stage_evaluation/common.py`; keep old
   names as explicit imports/adapters and return to green.
4. Extract canonical research/story policy, then script/scene/cut policy, then
   manifest policy, then video policy. After each coherent move, update explicit
   facade exports and run the fast loop.
5. Extract `evaluate_stage`, report rendering, and state append coordination into
   the runner module while preserving file/state contracts.
6. Extract pipeline-specific policy into `toc/stage_evaluation/pipeline.py` and
   convert shared `verify-pipeline.py` entrypoints into thin wrappers. Pass
   monkeypatchable dependencies explicitly and preserve the separate pipeline
   schema and orchestration.
7. Add `toc/stage_review_cli.py` and convert all five review scripts to thin
   stage-specific entrypoints. Run CLI parity tests.
8. Split any remaining target-package function over 200 lines along existing
   ordered check groups; do not change messages, order, or conditions.
9. Run changed-code coverage, structural checks, focused suites, and independent
   code review. Fix actionable findings through new red/green cycles.
10. Run the full suite, golden dry-runs, placeholder render/verifier path,
    pointer validation, compile, and final diff review. Update working memory and
    close tasklist items only with exact evidence.
</workflow>

<working_memory>
Maintain only goal-local working-memory files:

- `.steering/20260808-stage-evaluator-refactor/PLAN.md`: update at each phase or
  strategy change.
- `.steering/20260808-stage-evaluator-refactor/ATTEMPTS.md`: append every
  meaningful test/implementation attempt with the exact command, result, and
  next adjustment.
- `.steering/20260808-stage-evaluator-refactor/NOTES.md`: append durable
  compatibility discoveries, baseline changes, and blockers.
- `.steering/20260808-stage-evaluator-refactor/tasklist.md`: check items only
  after their evidence exists.

Update memory after every meaningful experiment and before context compaction.
Never replace unrelated root planning files.
</working_memory>

<human_control_surface>
Reread `.steering/20260808-stage-evaluator-refactor/CONTROL.md` before each phase
change, strategic pivot, expensive check, or sidecar review. It may narrow or
pause work but cannot weaken the approved scorecard or done_when contract.

Relevant knobs are behavior preservation, allowed/protected paths, no network or
external API use, a 15-minute normal step budget, and approval gates for
dependencies, public behavior/schema changes, destructive operations, test
weakening, and scope expansion.
</human_control_surface>

<verification_loop>
Focused verification first:

```bash
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_parity.py
python -m pytest -q -p no:cacheprovider tests/test_stage_evaluator_scripts.py tests/test_verify_pipeline.py
python -m compileall -q toc server scripts
python scripts/validate-pointer-docs.py
git diff --check
```

Changed-code coverage without a new dependency:

```bash
stage_eval_cover_dir="$(mktemp -d)"
PYTHONDONTWRITEBYTECODE=1 python -m trace --count --missing --summary \
  --coverdir "$stage_eval_cover_dir" --module pytest -q -p no:cacheprovider \
  tests/test_stage_evaluator_parity.py tests/test_stage_evaluator_scripts.py
```

Inspect the trace summary for each new/materially extracted target module and
require at least 80% line coverage. If `trace` cannot correctly report a target
module, record the exact limitation and use an already-installed equivalent;
do not add a dependency without approval.

Final Python regression:

```bash
python -m pytest -q
```

CI golden topic dry-runs:

```bash
stage_eval_golden_dir="$(mktemp -d)"
python scripts/toc-run.py "桃太郎" --dry-run --timestamp 20990101_0000 --base "$stage_eval_golden_dir" --force
python scripts/toc-scene-series.py "竹取物語" --dry-run --timestamp 20990101_0001 --base "$stage_eval_golden_dir" --force
python scripts/toc-immersive-ride.py --topic "浦島太郎" --timestamp 20990101_0002 --base "$stage_eval_golden_dir" --force
```

CI placeholder smoke verification:

```bash
stage_eval_render_dir="$(mktemp -d)"
python scripts/toc-scene-series.py "桃太郎" --timestamp 20990101_0003 --base "$stage_eval_render_dir" --placeholder-e2e --force
python scripts/toc-immersive-ride.py --topic "竹取物語" --timestamp 20990101_0004 --base "$stage_eval_render_dir" --force
stage_eval_run_dir="$stage_eval_render_dir/竹取物語_20990101_0004"
python scripts/generate-placeholder-assets.py --manifest "$stage_eval_run_dir/video_manifest.md" --force
python scripts/build-clip-lists.py --manifest "$stage_eval_run_dir/video_manifest.md" --out-dir "$stage_eval_run_dir"
scripts/render-video.sh --clip-list "$stage_eval_run_dir/video_clips.txt" --narration-list "$stage_eval_run_dir/video_narration_list.txt" --out "$stage_eval_run_dir/video.mp4"
python scripts/toc-state.py append --run-dir "$stage_eval_run_dir" --set "runtime.render.status=success" --set "artifact.video=$stage_eval_run_dir/video.mp4" --set "review.video.status=pending"
python scripts/verify-pipeline.py --run-dir "$stage_eval_run_dir" --flow immersive --profile fast
```

If a broad pre-existing failure occurs, record the exact command/output and
compare it with baseline evidence. A changed-path failure is never classified as
pre-existing without proof. Do not complete while any required changed-path or
scorecard check fails.
</verification_loop>

<execution_rules>
- Check git status before edits and preserve unrelated user changes.
- Prefer `rg` over `grep` for discovery.
- Use `apply_patch` for manual edits.
- Read context and live dirty hunks before implementation.
- Batch independent reads and bounded sidecar reviews when safe.
- Follow TDD: write behavior characterization and failing structural tests
  first, run red, implement the smallest extraction, run green, then refactor.
- Keep the scorecard current and maintain goal-local working memory.
- Update `ATTEMPTS.md` after every meaningful approach so failed experiments are
  not repeated without new evidence.
- Use fast representative checks repeatedly and reserve slow checks for phase
  boundaries and completion.
- Run focused tests before broad tests.
- Do not paper over failures, weaken tests, add dependencies, or widen scope.
- Do not perform destructive git operations or network/external API calls.
- Keep final communication concise and evidence-based.
</execution_rules>

<output_contract>
Required final artifacts:

- modular evaluator implementation and explicit compatibility adapters;
- `tests/test_stage_evaluator_parity.py` with behavior and structural evidence;
- updated goal-local plan, tasklist, attempts, notes, and control files;
- changed-code coverage evidence at or above 80%;
- exact focused/full/golden/placeholder verification results;
- independent code-review findings and their resolution;
- a final diff audit proving unrelated user work was preserved.

The final response must lead with whether behavior-preserving modularization is
complete, link the main changed files, summarize scorecard/test evidence, and
name any remaining limitation. Completion signal: all nine done_when items are
evidenced, scorecard is 7/7, and no required work remains.
</output_contract>
