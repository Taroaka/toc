# Frontend create: error-directed repair

Normal frontend creation keeps validation enabled and feeds recoverable authoring
errors back to the author that owns the input. p120 retains its publication-only
contract; it does not regain source/content checks.

## Execution

- p220 repairs architect plans, scene response shape, scene content, and repair-response
  shape. Local non-progress promotes correction to the frozen scene set. Frontend
  duration/time-of-day handoff errors re-enter the story author with the failed story.
- p330 repairs the visual-value document and B-roll with its previous output and errors.
- p420 repairs scene direction and the assembled document. Accepted scenes are cached
  against upstream/preceding-scene/resource bindings for interrupted-run reuse.
- Projection/preflight and typed image-compiler failures return to p330 or p420;
  request materialization can return the same typed diagnostic across a subprocess.
  The same run reuses its completed checkpoints and rematerializes dependent outputs.
- Missing or undecodable provider images retry only the current item. Generated images
  are decoded before canonical publication, and existing images must decode before
  provenance-based reuse. Terminal output validation can regenerate diagnosed items.
- Unclassified exceptions, transport, changed source bindings, unsafe paths, authentication
  and storage failures do not become LLM content-repair instructions. Provider provenance
  assertions and path restrictions remain enforced.

`toc/production_diagnostics.py` defines typed errors. A materializer emits the
`toc.authoring_error.v1` envelope with exit 38; arbitrary stderr is never treated as a
repair directive. `toc/production_repair.py` builds repair context, reserves attempts,
checks convergence, and maintains persistent history. Compiler errors preserve their
original message; owner routing is supplied by code, never by the LLM.

The correction prompt includes the previous candidate, exact validation messages,
source binding, target, attempt, and limit, alongside the original author prompt and
source documents. The LLM returns the original schema. It cannot edit validators or
silence checks. Corrected candidates must pass the same gates before downstream work.

## History, budgets and progress

`logs/repair/ledger.json` stores an append-preserving event list, pending correction
contexts, and frozen limits. A pinned `.locks/production_repair.lock` protects atomic
ledger replacement across subprocesses. This is an atomic ledger, not a separately
appended JSONL journal: reservation and its diagnostic/candidate commit together.

Defaults are 12 correction rounds per authoring stage and 40 across the run. Existing
p220 and p420 correction loops share that budget, as do later handoff corrections.
Media has a separate budget with two additional attempts per item; authoring cannot
consume it. Repeated unchanged candidate/error pairs trigger scope promotion where
supported, then a `repair_exhausted` stop if the broader correction does not converge.
The number of rounds is not a promise about the number of model calls inside a scene
set round.

A reservation is marked dispatched before the external correction call. After a crash,
a dispatched pending correction consumes a new reservation when resubmitted; resume
cannot expand the saved limits. Unconfirmed provider completion is not exactly-once
billing. Existing completed outputs remain reusable only under their original bindings.

`runtime.repair.phase/stage/target/attempt/limit/reason` are projected into `RunProgress.repair`.
The existing frontend progress panel displays the active correction. Candidate failures
remain running; exhausted or unrepairable failures use the existing terminal failure path.
The same create job and run lease continue; no second resume job is posted automatically.

## Boundaries

Successful p680 completion still requires the current request snapshots, references,
image files, decode checks and request-bound provenance. A successful LLM response or
accepted provider call alone is not completion. p650 stops and materialize-only mode
retain their boundaries; this feature does not generate narration/video or publish.

Interrupted jobs use the existing resume action and saved inputs. No independent
background scheduler is introduced. Restart/redeployment should wait for active jobs
to finish; running workers do not have their policy replaced in place.

## Verification

`tests/test_frontend_auto_repair.py` runs the frontend create-job entrypoint with fake
LLMs and an authoritative fake image provider. It injects an image-prompt error, then
an image-generation failure, and requires real materialization, real final p680 gates,
a completed job, preserved upstream call counts and item-only regeneration.
Other tests cover malformed plans, repair context, final direction validation, p420
resume caching, cancellation, persistent limits, no-progress and rooted-path handling.
No live LLM/image API call is required by these tests.
