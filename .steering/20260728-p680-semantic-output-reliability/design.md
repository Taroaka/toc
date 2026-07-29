# Design

## Verdict materialization

Treat the app-server final message as an alternate transport envelope for the
canonical semantic report:

1. Prefer a terminal canonical report already written by the turn.
2. Otherwise inspect completed final agent messages from newest to oldest.
3. Accept either the legacy line-oriented report or one strict JSON object.
4. Normalize JSON into the existing canonical line-oriented report contract.
5. Run the existing digest, scope coverage, and semantic validators after
   materialization.

The normalizer preserves the exact input digest and ordered entry arrays. It
does not infer missing fields or turn an incomplete response into a verdict.

## Failure classification

A successfully completed app-server turn without a materializable terminal
verdict is an output-contract failure. It is operational failure, not evidence
that the reviewed artifacts are semantically wrong. The orchestration therefore
raises a Codex app-server transport error, records the distinct
`output_contract` kind, and skips producer repair.

Shard paths return their existing transport-failure result shape so their
bounded shard transport retry remains active.

## p680 coverage

The shared materializer covers scene_set, cut_blueprint, and asset_plan. The two
sharded call sites additionally fail closed as transport errors when no verdict
can be materialized, covering scene_detail and image_prompt.

## Review projection and storyboard finalization

Pre-p800 review and semantic-currentness hashes use a shared canonical YAML
projection. For `video_manifest.md`, the projection excludes only direct
`scenes[].render_units`, because those units are derived at p680 for p800
execution. All other known and unknown manifest fields remain review-bound.

The shared storyboard p680 finalizer validates the approved manifest,
materializes render units transactionally, proves that the review projection
did not change, and validates the specialized storyboard contract. It never
rewrites authored cut IDs or durations.

## Resume identity and route selection

New frontend runs write `logs/orchestration/create_input.json` with the exact
source bytes, source hash, topic, experience, source-run identity, and target
duration. The optional artifact is included in the p500 resume fingerprint.
When present it is the canonical resume input and a conflicting CLI value is
rejected. A legacy run without it requires an explicit non-empty source.

The API and the image-only worker share one strict p680 regeneration-plan
classifier. Pure scene repair may use the image-only path. Asset/reference
repair must use the canonical p500 dry-run/exact-token/apply path. Unknown,
malformed, unsafe, or request-unbound actions fail before deletion or provider
execution, and the image-only decision is checked again while holding the run
lease.

`world_walk` applies one shared asset-generation contract in both fresh and
resumed runs: restored source references are verified against the manifest,
bounded to four, and projected into provider requests with the standard lane,
bootstrap disabled, and the world-walk observer prompt contract.

## Localized semantic failures

For `scene_detail`, `cut_blueprint`, and `image_prompt`, a terminal semantic or
transport failure may continue only when every failed selector maps to current
scene/cut image-request items. Those items are carried forward as blocked
synthetic failed candidates; all other items continue. Any unaccounted
selector, stale request binding, or failure in a non-localizable stage remains
a run-level blocker.

## Terminal and mutation safety

p650/p680 validation is request-bound and always requires immutable generation
snapshots and provenance. Terminal p680 additionally requires a fresh verifier
report targeting p680, overall success, and success for every emitted stage.

Resume fingerprints cover downstream artifact bytes and filesystem type.
Locking and destructive operations use no-follow, same-run leases, canonical
path allowlists, preflight-before-mutation, rollback where applicable, and a
cancellation barrier that keeps the lease until blocking mutation or child
process cleanup has completed.
