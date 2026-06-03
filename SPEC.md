# Parallel Image Generation With Safe Fallback

## Goal

Make Codex app-server image generation fast enough for frontend one-shot story creation by setting the effective image generation parallelism to 100 and allowing both asset and scene image requests to run in parallel, while preventing generated image fallback from assigning an image to the wrong request.

## Scope

- `IMAGE_GENERATION_PARALLELISM` must be 100 in production code.
- Asset generation must run by dependency-safe generation groups, with items inside each group eligible for parallel execution.
- Scene generation must also run in parallel where request dependencies allow it.
- The generated image fallback path must be safe under parallel execution.
- Timeout handling must isolate the failing item and must not corrupt sibling item outputs.
- Existing semantic QA, producer repair loops, verifier gates, and p650/p680 state semantics must remain active.

## Non-Goals

- Do not change story, script, asset planning, or semantic review quality criteria.
- Do not bypass human review gates.
- Do not replace Codex app-server image generation with a local raster placeholder.
- Do not accept an image for an item unless the implementation can prove the image belongs to that item.
- Do not rely on manual cleanup or operator judgment to prevent fallback misassignment.

## Architecture Constraints

- Inspect and preserve the existing group dependency logic in `server/image_gen_app.py`.
- The current unsafe condition is that fallback can claim from the shared `CODEX_HOME/generated_images` directory by time order. With parallel requests, time order alone is not sufficient identity.
- A safe solution may use isolated app-server runtime state per item, a per-item generated image root, explicit turn/item correlation, or a stricter no-fallback mode when identity cannot be proven.
- If fallback safety cannot be guaranteed for an item, fail or retry that item rather than accepting an ambiguous generated image.
- App-server transport failures and semantic QA failures must remain separate states.
- Existing output provenance logs must become strong enough to audit item-to-image assignment under parallel generation.

## Likely Files

- `server/image_gen_app.py`
- `server/codex_app_server.py`
- `tests/test_image_gen_server.py`
- `docs/root-pointer-guide.md`
- `docs/system-architecture.md`
- `docs/orchestration-and-ops.md`

## Scorecard

Primary checklist, pass threshold: all items must pass.

- Parallelism: production `IMAGE_GENERATION_PARALLELISM` is 100 and logs expose `parallelism: 100`.
- Asset grouping: asset generation preserves dependency-safe group ordering and runs items inside a group concurrently.
- Scene grouping: scene generation uses the same safe concurrency model.
- Fallback identity: tests prove one item cannot claim another item's fallback image under concurrent generation.
- Timeout isolation: tests prove one timeout is logged and retried or failed for that item without corrupting siblings.
- Regression safety: existing semantic QA, repair loop, verifier, app-server transport, and image generation tests still pass.

Stop condition: focused unit tests plus py_compile pass, and code inspection shows no remaining shared time-order fallback claim that can misassign images under concurrency.

## Feedback Loop

Fast check during iteration:

```bash
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests.test_request_generation_group_cancels_sibling_items_after_failure test_image_gen_server.ImageGenApiTests.test_request_generation_group_does_not_start_queued_items_after_failure
```

Expected runtime: under one minute. Run after touching request generation scheduling or failure behavior.

Focused final checks:

```bash
python3 -m py_compile server/image_gen_app.py server/codex_app_server.py tests/test_image_gen_server.py
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenParserTests.test_generate_image_keeps_fallback_watcher_for_item_timeout
PYTHONPATH=. python -m unittest test_image_gen_server.ImageGenApiTests
python -m unittest discover -s tests -p 'test_semantic_review.py'
python scripts/validate-pointer-docs.py
```

If full `ImageGenApiTests` is too slow locally, run the newly added fallback/concurrency tests plus all existing tests touched by the implementation, then record the skipped slow command and reason.

## Done When

1. `server/image_gen_app.py` has effective `IMAGE_GENERATION_PARALLELISM = 100`.
2. Asset batch logs are produced with `parallelism: 100` and asset generation runs by dependency-safe parallel groups.
3. Scene batch logs are produced with `parallelism: 100` and scene generation runs by dependency-safe parallel groups.
4. Fallback image recovery is safely tied to the requesting item, so parallel generation cannot adopt another item's generated image.
5. TimeoutError handling records retry/failure for the affected item without assigning sibling images or blocking unrelated successful items.
6. Existing semantic QA, producer repair loop, and verifier gates are not bypassed or weakened.
7. Tests cover parallel fallback misassignment prevention, asset/scene parallel scheduling, and timeout isolation.

## Risks

- Codex app-server may not support a clean per-turn image identity in its notifications, requiring runtime isolation or fallback restriction.
- Creating many app-server processes concurrently may stress local resources or backend transport. If so, keep the configured parallelism at 100 but implement an internal resource gate only when necessary and document it.
- Existing tests may have assumed serialized behavior. Update only tests whose assumptions are intentionally changed; preserve behavioral guarantees around failure cancellation and provenance.
