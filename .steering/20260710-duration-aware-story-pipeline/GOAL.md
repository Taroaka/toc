<goal>
Implement duration-aware ToC story creation for frontend-selected targets from 300 to 1200 seconds. Propagate one target through authoring artifacts, scale scene/cut/narration planning from that target, require auditable research and story semantic reviews before cut materialization, and make CLI/frontend media-duration gates share the rule `actual >= 0.8 * target` with no upper limit.
</goal>

<context>
Read first:

- `.steering/20260710-duration-aware-story-pipeline/requirements.md`
- `.steering/20260710-duration-aware-story-pipeline/design.md`
- `.steering/20260710-duration-aware-story-pipeline/CONTROL.md`
- `docs/root-pointer-guide.md`
- `server/web/src/main.tsx`
- `server/image_gen_app.py`
- `scripts/toc-immersive-frontend-run.py`
- `scripts/toc-create-run-headless.py`
- `scripts/check-audio-duration-gate.py`
- `scripts/sync-manifest-durations-from-audio.py`
- `toc/stage_evaluator.py`

Useful discovery commands:

```bash
rg "target_duration|minimum_duration|estimated_duration|300|600" server scripts toc workflow tests -n
rg "research.*review|story.*review|authoring_review|auto.*pass|materialize.*review" server scripts toc tests -n
rg "p740|narration_ready|duration_fit|ffprobe|silent|render_units" server scripts toc tests -n
```
</context>

<constraints>
- Preserve every unrelated uncommitted change; do not revert, clean, or broadly reformat dirty files.
- Do not overwrite root `SPEC.md`, `GOAL.md`, or `PLAN.md`; they belong to another goal.
- Keep existing create endpoints and default old clients to 300 seconds.
- Accept only integer targets from 300 through 1200 seconds.
- Use `ceil(target/40)` scenes, `ceil(target/12)` cuts, and `ceil(target*0.70)` narration seconds as approved minimum planning budgets.
- Duration passes at 80% or more; never reject an over-target result solely for length.
- Do not add audio, render-unit, and final-video layers together. Audit each non-overlapping timeline independently.
- Do not mark research/story passed with deterministic unconditional artifacts or on review transport failure.
- Do not implement classic adaptation modes, title/version disambiguation, source/rights/reference validation, canonical-fidelity guarantees, or p680-to-p900 one-click continuation.
- Do not invoke paid image, video, or TTS providers during verification.
- Preserve all existing cut/image/video semantic, provenance, and human-review gates.
</constraints>

<scorecard>
Primary checklist; pass threshold is 8/8 with no regression failure:

1. Input/propagation: UI and API accept/default/validate target and artifacts carry one value.
2. Planning: 300/600/900/1200 produce the approved minimum budgets.
3. Review integrity: failed or unavailable research/story review cannot reach cut materialization.
4. Audit parity: CLI and frontend use the same duration contract implementation.
5. Boundary behavior: 79.9% fails; 80% and 150% pass.
6. Timeline correctness: narration audio and intentional silence count once; audit layers are not summed.
7. Readiness: p740 and video endpoints require the shared lower-bound pass.
8. Regression: focused tests, frontend build, backend-route headless create, and pointer validation pass.

Scoring commands/paths:

```bash
python -m pytest -q tests/test_story_duration_contract.py tests/test_audio_duration_gate.py
python -m pytest -q tests/test_image_gen_server.py -k 'duration or research_review or story_review or narration_ready'
python -m pytest -q tests/test_toc_immersive_frontend_run.py -k 'duration or research_review or story_review'
cd server/web && npm run build
python scripts/toc-create-run-headless.py --title "シンデレラ" --source "シンデレラ" --target-duration-seconds 300 --no-images --assert-profile cut_contract_v2
python scripts/validate-pointer-docs.py
```

Stop only when every done_when item is evidenced, the backend create route has produced a fresh passing run, and inspection finds no unconditional research/story pass or divergent frontend/CLI duration formula.
</scorecard>

<done_when>
1. `server/web/src/main.tsx` exposes 5/10/15/20 minute choices plus a 300–1200 second custom value, both normal and storyboard create requests carry `target_duration_seconds`, backend request tests prove default 300 and range rejection, and `cd server/web && npm run build` passes.
2. `tests/test_story_duration_contract.py` proves these exact budgets: 300→8 scenes/25 cuts/210 narration seconds/240 minimum seconds; 600→15/50/420/480; 900→23/75/630/720; 1200→30/100/840/960. It also proves targets 299 and 1201 are rejected.
3. A new frontend-backend create integration test proves the same target is written to state, research, story, script, and manifest; the 1200-second fixture exposes at least 30 scenes, 100 cuts, and an 840-second narration budget.
4. Focused tests prove research or story semantic failure and review transport failure stop before cut materialization, while passed review artifacts contain auditable criterion results. No unconditional production auto-pass remains.
5. `tests/test_audio_duration_gate.py` and shared-contract tests prove 79.9% fails, exactly 80% passes, 150% passes, measured narration audio plus declared intentional silence is counted exactly once, and render/final layers are independent.
6. Backend tests prove p740 completes only when every narration-required cut is ready and the shared audio timeline passes; video generation endpoints reject runs without that pass.
7. A focused final-media test proves ffprobe duration uses the same 80%-minimum/no-maximum contract when a final video exists.
8. A fresh `scripts/toc-create-run-headless.py` run through `/api/image-gen/runs/create` with `--target-duration-seconds 300 --no-images --assert-profile cut_contract_v2` completes and its regression report/artifacts satisfy the new contract.
9. Relevant focused and regression tests, frontend build, Python compile checks, and `python scripts/validate-pointer-docs.py` pass without deleting or overwriting unrelated user work.
</done_when>

<feedback_loop>
After each duration-contract edit, run:

```bash
python -m pytest -q tests/test_story_duration_contract.py tests/test_audio_duration_gate.py
```

Expected runtime: under 30 seconds. Run on every red/green/refactor cycle. It is representative for calculations and boundaries, but not request propagation or authoring order.

After review-stage edits, run:

```bash
python -m pytest -q tests/test_toc_immersive_frontend_run.py -k 'research_review or story_review or cut'
```

Expected runtime: under 60 seconds. At phase boundaries run focused backend tests. Before completion run the slower frontend build, broader regressions, and one fresh headless backend create.
</feedback_loop>

<workflow>
1. Reread `CONTROL.md`, inspect dirty diffs around every target symbol, and record discoveries in `NOTES.md`.
2. Write failing pure duration-contract tests for target validation, planning budgets, lower-bound-only comparisons, and timeline accounting.
3. Implement the smallest shared duration contract/audit code to pass those tests; refactor only while green.
4. Write failing API/frontend-runner tests for default/range/propagation, then implement backend and runner propagation.
5. Add the frontend selector and request fields, then build the frontend.
6. Write failing tests for target-derived scene/cut/narration planning, then replace fixed-duration authoring behavior.
7. Write failing tests for research/story fail-closed semantic stages, then replace unconditional review artifacts with the existing semantic-review transport/rubric conventions.
8. Write failing p740/video/final-media tests, then route CLI and frontend through the shared audit.
9. Update state/workflow/durable docs for the final contract without overwriting unrelated edits.
10. Run focused regressions, inspect the diff, execute frontless_review without images, and resolve failures until the scorecard passes.
</workflow>

<working_memory>
Maintain goal-local files only:

- `.steering/20260710-duration-aware-story-pipeline/tasklist.md`: update checkboxes at phase completion.
- `.steering/20260710-duration-aware-story-pipeline/ATTEMPTS.md`: append each meaningful red/green attempt, command evidence, result, and next adjustment.
- `.steering/20260710-duration-aware-story-pipeline/NOTES.md`: append durable discoveries, compatibility decisions, and blockers.

Update memory after each meaningful experiment and before context compaction. Never replace the unrelated root `PLAN.md`.
</working_memory>

<human_control_surface>
Reread `.steering/20260710-duration-aware-story-pipeline/CONTROL.md` before each phase change, strategic pivot, or expensive step. It may narrow work but may not weaken approved thresholds.

The user-visible knobs are: protected dirty files, external-generation prohibition, 15-minute step budget, no classic/source/rights scope, and approval requirements for dependencies, schema changes, endpoint replacement, destructive changes, paid calls, or scope expansion.
</human_control_surface>

<verification_loop>
Focused checks first:

```bash
python -m pytest -q tests/test_story_duration_contract.py tests/test_audio_duration_gate.py
python -m pytest -q tests/test_image_gen_server.py -k 'duration or research_review or story_review or narration_ready'
python -m pytest -q tests/test_toc_immersive_frontend_run.py -k 'duration or research_review or story_review'
python3 -m py_compile server/image_gen_app.py scripts/toc-immersive-frontend-run.py scripts/check-audio-duration-gate.py
```

Phase/final checks:

```bash
cd server/web && npm run build
python -m pytest -q tests/test_stage_evaluator_scripts.py tests/test_manifest_parsing.py
python scripts/toc-create-run-headless.py --title "シンデレラ" --source "シンデレラ" --target-duration-seconds 300 --no-images --assert-profile cut_contract_v2
python scripts/validate-pointer-docs.py
```

If a broad pre-existing failure is unrelated, record its exact command/output and prove changed paths with narrower passing checks. Do not classify a changed-path failure as pre-existing without baseline evidence.
</verification_loop>

<execution_rules>
- Check git status before edits and preserve unrelated user changes.
- Prefer `rg` for discovery and `apply_patch` for manual edits.
- Read the current dirty hunk before editing any overlapping file.
- Batch independent reads and bounded sidecar reviews when safe.
- Follow TDD: add a failing behavioral test, run it red, implement minimally, run green, then refactor.
- Keep the scorecard current and update goal-local working memory after meaningful attempts.
- Use fast representative checks repeatedly and reserve broad checks for phase boundaries/final verification.
- Run focused tests before broad tests.
- Do not paper over failures, widen scope, or weaken a threshold to obtain green tests.
- Do not perform destructive git operations or paid external generation.
- Keep final communication concise and evidence-based.
</execution_rules>

<output_contract>
Required artifacts:

- implementation and tests satisfying the nine done_when items;
- updated goal-local tasklist, attempts, and notes;
- a fresh frontless regression report and run path;
- verification results with exact commands and any justified limitation;
- preserved unrelated working-tree changes.

Final response: lead with whether duration propagation, semantic pre-cut gates, and shared 80% duration auditing are complete; link the main changed files and frontless report; summarize tests and any remaining caveat. Completion signal is all done_when evidence present and no required work remaining.
</output_contract>
