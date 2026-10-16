# P650 effective shot output set

## Evidence and requirement
P500 completed all 20 asset images at 18:58 JST with no generation failures. P650 then rejected a legacy parent result-frame selector missing from the 54-shot snapshot. The parent is a nonexecuted audio/direction container; its result visual plan supplies state-variant metadata to projected children. The generator already executes only shot starts and explicit child end frames, and the parent result frame still references the nonexecuted legacy parent still. The server's image target enumeration and cut-output gate incorrectly include this parent-only auxiliary image.

## Design and tasks
- Match server target enumeration and cut output requirements to the existing effective shot execution model. Preserve the canonical parent result visual plan; do not request an unused parent image or relax validation of any executed shot/end frame.
- Add red regressions for parent result metadata excluded, actual child result image included, correct required output set, and missing required child end frame rejected. Keep standalone cut auxiliary requests unchanged.
- Run affected shot-runtime, p650/resume, request snapshot/provider and state-variant suites, then verify current run with ordinary readiness checks.
- Preserve all 20 valid generated assets and their provenance. Re-freeze/revalidate existing requests via the normal supported handoff path if necessary; use image_only resume when strict p650 is valid. Do not run a p500 reset that needlessly quarantines/regenerates valid images.

## Verification and review

The parent/child auxiliary target regression fails before the patch and passes after matching effective shot execution. It verifies the exact child-start/end output set and still rejects a missing required child result frame. Related shot-runtime/direction/snapshot/asset-state/p500-failure/resume/video-preparation checks: 121 passed (two existing FastAPI deprecation warnings). Current run passes the ordinary materialized-p650 validator. Strict p650 now reaches only the expected pending freeze slot; the false missing parent-image error is gone. Local review confirms standalone cuts retain their auxiliary end images, every executed child schedule/output remains validated, and the canonical parent visual plan is untouched. Finish the existing normal request-freeze handoff under the retained run lease, then require strict p650 before frontend image_only resume.

## Strict p650 recovered without regeneration

The ordinary materialized-p650 validator passed, then the normal _mark_image_prompt_request_freeze_done handoff bound the current reference bytes and froze the existing request revision under the retained run lease. The strict _validate_p650_run now passes. All 20 asset PNG hashes are unchanged; preserved-assets-p650.json records them. No scene/media provider was invoked by this repair, no request or check was bypassed, and no slot status was assigned manually. Next action is a supported server restart and one frontend resume expected to classify as image_only.

## Frontend image-only worker confirmed

Supported restart health checks passed. Computer Use resumed the same run as ea40e589ed394354adaf3dd5df03f39d (image_only) at 19:33:45 JST. Actual scene request batch started at 19:34:51 and the first six shot items were submitted by 19:34:56. Canonical state now has p650=done, p660=in_progress, runtime.stage=scene_images_generating; all 20 asset hashes remain unchanged. API job-status reconciliation still surfaces an old terminal failure from the prior attempt while actual item generation is active; do not restart this healthy worker on that stale view. Screenshot frontend-resumed-image-only.png. Continue using fresh item activity, state and actual workers; p680 completion remains unverified.
