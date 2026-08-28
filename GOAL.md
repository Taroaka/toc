<goal>
Fix semantic producer repair reconciliation so repaired story/scene meaning is deterministically propagated into script cuts, manifest cuts, character timelines, asset references, image request inputs, and review evidence before P400 review is refreshed. Then prove the complete behavior by resuming the existing Cinderella run to P680 and creating one brand-new frontend story that generates real reusable assets and scene images through P680 without manual artifact edits.
</goal>

<context>
Read first:

- `SPEC.md`
- `.steering/20260826-semantic-repair-reconciliation/requirements.md`
- `.steering/20260826-semantic-repair-reconciliation/design.md`
- `.steering/20260826-semantic-repair-reconciliation/tasklist.md`
- `docs/root-pointer-guide.md`
- `docs/data-contracts.md`, especially P400 and P500 resume contracts
- `server/image_gen_app.py`, especially `_reconcile_after_semantic_repair`
- `scripts/toc-immersive-frontend-run.py`, especially P400 review refresh and readiness
- `toc/stage_evaluation/script.py`
- `toc/stage_evaluation/manifest.py`
- `tests/test_image_gen_server.py`
- `tests/test_toc_immersive_frontend_run.py`
- `tests/test_p500_resume.py`

Useful discovery:

```bash
rg "_reconcile_after_semantic_repair|_refresh_p400_review_artifacts|_require_fresh_p400_readiness|source_event_preservation|timeline_states_complete" server scripts toc tests -n
```
</context>

<constraints>
- Keep semantic QA, deterministic verifiers, provider gates, and human review fail-closed.
- Do not forge passed reviews, relax acceptance criteria, or infer pass from file existence.
- Preserve earliest-source-first propagation: story -> script -> manifest -> requests/snapshots.
- Reconciliation must be deterministic and idempotent.
- Remove stale appearance/reference dependencies when repair removes them; do not reintroduce semantically invalid characters merely to satisfy timeline validation.
- Preserve append-only state history and same-run P500 resume behavior.
- Do not manually patch production run artifacts as the final solution.
- Do not use local raster placeholders.
- Stop at P680; narration/video/render are out of scope.
- Preserve unrelated user changes and avoid marketing/LINE/unrelated modules.
</constraints>

<scorecard>
Pass threshold: all checklist items pass.

1. Repaired event action, reaction, facts, visual evidence, and event context are exactly projected into every affected cut contract.
2. Repaired participant/appearance changes are consistently reflected in timelines, cut asset dependencies, manifest image-generation IDs, and request references.
3. P400 reviews are materialized only after deterministic reconciliation passes.
4. A second reconciliation pass on unchanged input is idempotent.
5. Semantic and provider gates remain fail-closed and transport failures remain distinct.
6. Existing Cinderella reaches P680 with real assets and scene images.
7. One new frontend-created story reaches P680 without manual artifact edits.

Fast scoring command:

```bash
cd tests
PYTHONPATH=.. python -m unittest test_semantic_repair_reconciliation
```

Regression inspection paths include the focused P400/frontend tests, P500 resume tests, semantic review tests, and `verify-pipeline.py` for both final runs.

Stop only when every done_when item is satisfied. Do not stop merely because unit tests pass if real P680 verification has not completed.
</scorecard>

<done_when>
1. A focused failing-first test reproduces repaired scene events with stale cut contracts and passes only after production reconciliation projects exact action/evidence/event-context fields.
2. A focused failing-first test reproduces a removed appearance variant and proves stale cut/image references are removed while timeline integrity passes.
3. A focused test proves reconciliation idempotence.
4. A focused ordering test proves P400 review refresh never occurs before repair reconciliation has passed deterministic validation.
5. Relevant semantic review, P400, frontend runner, P500 resume, run-root binding, and image-generation regression tests pass.
6. `output/シンデレラ_20260812_2341` reaches `p560=done`, `p660=done`, and `p680=awaiting_approval` through canonical resume tooling, with nonzero real asset and scene-image files and request-bound Codex provenance.
7. A brand-new run created through the frontend-button-equivalent backend create route reaches the same P680 state without manual edits to canonical artifacts or review/request files.
8. Both final runs pass `python scripts/verify-pipeline.py --run-dir <run> --flow immersive --profile standard` or the canonical frontend P680 validator when it is stricter, with any provider transport retry recorded separately from semantic results.
</done_when>

<feedback_loop>
Use TDD. Add the focused reproduction tests before implementation and confirm they fail for the observed reason.

Fast check, expected under one minute, after every projection/reconciliation edit:

```bash
PYTHONPATH=. python -m unittest tests.test_image_gen_server.SemanticRepairReconciliationTests
```

Run the focused frontend/P400 integration tests after each coherent step. Run real provider-backed Cinderella and fresh-story P680 flows only after focused and regression tests are green because they are slow and consume external resources.
</feedback_loop>

<workflow>
1. Inspect current reconciliation and existing helpers; record the exact stale fields and ordering defect.
2. Add failing tests for event projection, appearance/reference removal, idempotence, and review ordering.
3. Implement the smallest canonical reconciliation helper and invoke it before P400 review refresh.
4. Run focused tests, refactor while green, and update working memory.
5. Run broader semantic/P400/P500/frontend regression tests.
6. Resume the existing Cinderella run via canonical resume tooling and verify P680 plus real image provenance.
7. Use the frontend-button-equivalent backend create route to create a new story from scratch and verify P680 plus real image provenance.
8. Run final verification, inspect the diff, and report only after the scorecard reaches 100%.
</workflow>

<working_memory>
Maintain goal-local working memory under `.steering/20260826-semantic-repair-reconciliation/`:

- `PLAN.md`: current phase, strategy, next action, blockers.
- `ATTEMPTS.md`: every meaningful implementation or runtime attempt with commands and evidence.
- `NOTES.md`: durable discoveries and contract details.

Update `ATTEMPTS.md` after each meaningful attempt and `PLAN.md` whenever the phase or strategy changes. Do not overwrite the unrelated root `PLAN.md`.
</working_memory>

<human_control_surface>
Maintain `.steering/20260826-semantic-repair-reconciliation/CONTROL.md`. Reread it before phase changes, strategic pivots, and real provider-backed P680 runs.

The user may narrow scope, pause expensive provider work, or add a nudge. Explicit approval is required for destructive changes, dependency/schema/public API changes, weakening QA, or expanding past P680. The control surface cannot weaken done_when.
</human_control_surface>

<verification_loop>
Focused verification first:

```bash
python3 -m py_compile server/image_gen_app.py scripts/toc-immersive-frontend-run.py toc/semantic_repair_reconciliation.py toc/stage_evaluation/script.py toc/stage_evaluation/manifest.py tests/test_image_gen_server.py tests/test_toc_immersive_frontend_run.py tests/test_semantic_repair_reconciliation.py
cd tests
PYTHONPATH=.. python -m unittest test_semantic_repair_reconciliation
```

Then run relevant P400, semantic repair, P500 resume, run-root, and frontend runner tests. Run pointer-doc validation if pointer docs change. Final verification includes canonical P680 validation for Cinderella and one new frontend-created run.
</verification_loop>

<execution_rules>
- Check git status before edits and preserve unrelated user changes.
- Prefer `rg` for discovery.
- Use the patch tool for manual edits.
- Follow tests-first TDD and keep focused feedback fast.
- Maintain the goal scorecard and working-memory files.
- Do not paper over failures or weaken gates.
- Do not widen scope.
- Run focused tests before broad tests and broad tests before expensive provider-backed verification.
- Keep final communication concise and evidence-based.
</execution_rules>

<output_contract>
Required outputs:

- production reconciliation fix and regression tests;
- updated steering and working-memory evidence;
- existing Cinderella P680 evidence with real generated assets/scenes;
- one fresh frontend-created P680 run with real generated assets/scenes;
- verification commands and results;
- concise final report naming any remaining external transport caveats.

Completion signal: all done_when items and scorecard checks pass. Unit tests without both real P680 proofs are not completion.
</output_contract>
