<goal>
Implement safe high-concurrency Codex app-server image generation for ToC frontend story creation. Set the effective image generation parallelism to 100, run asset and scene image generation in dependency-safe parallel groups, and make generated-image fallback safe enough that concurrent requests cannot claim each other's images.
</goal>

<context>
Read these first:

- `SPEC.md`
- `server/image_gen_app.py`
- `server/codex_app_server.py`
- `tests/test_image_gen_server.py`
- `docs/root-pointer-guide.md`
- `docs/system-architecture.md`
- `docs/orchestration-and-ops.md`

Useful discovery commands:

```bash
rg "IMAGE_GENERATION_PARALLELISM|_generate_request_outputs|_generate_request_item_output|wait_for_unclaimed_generated_image_after|claim_latest_generated_image_after|generated_images" server tests -n
rg "request_generation_batch|request_generation_group|request_item_generation_retry" server tests -n
rg "semantic_review|producer_repair|check_semantic_review|verify-pipeline" server scripts tests -n
```
</context>

<constraints>
- `IMAGE_GENERATION_PARALLELISM` must be 100 in production code.
- Asset generation must preserve dependency-safe generation groups and run items inside a group concurrently.
- Scene generation must use the same safe concurrency model where dependencies allow it.
- Do not use shared timestamp-only fallback from `CODEX_HOME/generated_images` in a way that can assign one item's image to another item.
- A generated image may be copied to an item output only when identity is proven for that item. If identity is ambiguous, fail or retry the item.
- Do not introduce local raster placeholders or any non-Codex image fallback.
- Do not bypass semantic QA, producer repair, verifier, or human review gates.
- Preserve app-server transport failure state separately from semantic QA failure state.
- Preserve unrelated user changes and do not clean or delete output run directories as part of this goal.
</constraints>

<scorecard>
Primary checklist with pass threshold: all items must pass.

- Parallelism: production code sets `IMAGE_GENERATION_PARALLELISM = 100`.
- Asset logs: batch logs expose `parallelism: 100`, and dependency-safe asset groups still gate downstream groups.
- Scene logs: batch logs expose `parallelism: 100`, and scene items run concurrently without output misassignment.
- Fallback safety: tests prove concurrent fallback cannot claim another item's generated image.
- Timeout isolation: tests prove a timed-out item is retried or failed without corrupting siblings or adopting their images.
- Regression checks: existing image generation, semantic QA, producer repair, app-server transport, and verifier-related tests touched by the change still pass.

Scoring command/inspection paths:

```bash
rg "IMAGE_GENERATION_PARALLELISM = 100" server/image_gen_app.py
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenParserTests.test_generate_image_keeps_fallback_watcher_for_item_timeout
python -m unittest discover -s tests -p 'test_semantic_review.py'
```

Stop condition: the done_when list is satisfied, focused tests pass, and code inspection shows no remaining shared time-order fallback path that can misassign generated images under concurrency.
</scorecard>

<done_when>
1. `server/image_gen_app.py` has effective `IMAGE_GENERATION_PARALLELISM = 100`.
2. Asset batch logs are produced with `parallelism: 100` and asset generation runs by dependency-safe parallel groups.
3. Scene batch logs are produced with `parallelism: 100` and scene generation runs by dependency-safe parallel groups.
4. Fallback image recovery is safely tied to the requesting item, so parallel generation cannot adopt another item's generated image.
5. TimeoutError handling records retry/failure for the affected item without assigning sibling images or blocking unrelated successful items.
6. Existing semantic QA, producer repair loop, and verifier gates are not bypassed or weakened.
7. Tests cover parallel fallback misassignment prevention, asset/scene parallel scheduling, and timeout isolation.
</done_when>

<feedback_loop>
Fast iterative check:

```bash
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests.test_request_generation_group_cancels_sibling_items_after_failure test_image_gen_server.ImageGenApiTests.test_request_generation_group_does_not_start_queued_items_after_failure
```

Expected runtime: under one minute. Run after each scheduling or failure-handling edit. This is representative for group cancellation and sibling isolation, but not sufficient for fallback identity.

Add and run new focused tests as soon as the fallback design is implemented:

```bash
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests -k fallback
```

If `-k` is unsupported in the local unittest runner, run the explicit new test method names from the `tests` directory with `PYTHONPATH=.`.

Slower final check:

```bash
python3 -m py_compile server/image_gen_app.py server/codex_app_server.py tests/test_image_gen_server.py
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenParserTests.test_generate_image_keeps_fallback_watcher_for_item_timeout
python -m unittest discover -s tests -p 'test_semantic_review.py'
python scripts/validate-pointer-docs.py
```
</feedback_loop>

<workflow>
1. Inspect current generation scheduling, group construction, generated image fallback, and provenance logging.
2. Decide the fallback identity strategy. Prefer a provable per-item isolation or explicit item/turn correlation. If impossible, disable ambiguous fallback for parallel contexts and rely on explicit app-server image result paths.
3. Implement `IMAGE_GENERATION_PARALLELISM = 100` and preserve dependency-safe group sequencing.
4. Update image generation fallback and provenance logging so each generated image is tied to exactly one item.
5. Update TimeoutError handling so retry/failure is item-local and cannot copy sibling output.
6. Add focused tests for asset parallel scheduling, scene parallel scheduling, fallback misassignment prevention, and timeout isolation.
7. Run focused feedback checks, then final verification commands.
8. Update architecture/ops docs only if the implementation changes the app-server runtime boundary or fallback contract.
</workflow>

<working_memory>
This goal can run for hours and touches concurrency, fallback behavior, and app-server transport. Maintain these files during execution:

- `ATTEMPTS.md`: record each fallback identity design tried, why it passed or failed, and exact test results.
- `NOTES.md`: record discoveries about app-server image notifications, generated image paths, transport timeouts, and group scheduling.

Do not overwrite the existing root `PLAN.md`; it appears unrelated to this ToC task. If a plan file is needed, create a short goal-local section in `ATTEMPTS.md` instead.
</working_memory>

<human_control_surface>
Report before making a strategic fallback tradeoff. The user should be able to see:

- whether fallback is proven safe by identity, isolated by runtime, or disabled for ambiguous parallel cases;
- whether the implementation keeps full configured parallelism at 100 or introduces an internal resource guard;
- whether any final verification command could not run.

Require explicit user approval before reducing the configured `IMAGE_GENERATION_PARALLELISM` below 100.
</human_control_surface>

<verification_loop>
Run focused checks first:

```bash
python3 -m py_compile server/image_gen_app.py server/codex_app_server.py tests/test_image_gen_server.py
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests.test_request_generation_group_cancels_sibling_items_after_failure test_image_gen_server.ImageGenApiTests.test_request_generation_group_does_not_start_queued_items_after_failure
```

Then run the new fallback/concurrency tests by explicit method name.

Final verification:

```bash
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenParserTests.test_generate_image_keeps_fallback_watcher_for_item_timeout
python -m unittest discover -s tests -p 'test_semantic_review.py'
python scripts/validate-pointer-docs.py
```

If FastAPI or environment dependencies prevent a broad test from running, record the exact error and run the narrow tests that cover the changed code paths.
</verification_loop>

<execution_rules>
- Check git status before edits.
- Preserve unrelated user changes.
- Prefer `rg` over `grep` when available.
- Use the runtime's patch/edit tool for manual edits when available.
- Read context files before implementation.
- Batch independent file reads in parallel when the runtime supports it.
- Keep the goal scorecard current: know the primary metric, passing threshold, regression checks, scoring method, and stop condition.
- Use the fastest representative feedback check while iterating; reserve slower checks for escalation points and final verification.
- Maintain `ATTEMPTS.md` and `NOTES.md` for this long-running goal.
- Update `ATTEMPTS.md` after each meaningful approach so future iterations do not repeat work without new evidence.
- Run focused tests before broad tests.
- Do not paper over failures.
- Do not widen scope.
- Keep the final answer concise.
</execution_rules>

<output_contract>
Final output must summarize:

- the fallback identity strategy implemented;
- the effective asset and scene parallel behavior;
- the tests added or updated;
- the verification commands run and their results;
- any remaining operational caveats around Codex app-server transport.

Completion signal: all seven done_when items are satisfied and final verification has passed or any skipped check is explicitly justified with narrower passing evidence.
</output_contract>
