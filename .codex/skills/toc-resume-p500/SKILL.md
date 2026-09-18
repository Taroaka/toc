---
name: toc-resume-p500
description: Resume a failed frontend-created ToC run from verified p650 or p500 while preserving valid artifacts and images.
---

# ToC Adaptive Resume

Use the same run and the nearest supported, verified prerequisite before the failure. The retained skill name is for compatibility; a scene-image failure does not automatically require p500.

Resolve the exact existing run, failure evidence, and requested mode: inspection, reset, materialization diagnostics, or media retry. Use state, request snapshots, provenance, logs, and current validators. Read the p500/p650 resume sections of `docs/data-contracts.md` and the relevant resume section of `docs/implementation/immersive-ride-entrypoint.md`.

## Boundary selection

| Evidence | Route |
| --- | --- |
| Strict current p650 passes; failed/missing targets are safe scene outputs bound to current requests; no asset/reference repair is needed | `image_only`: preserve p500 assets and unaffected scene outputs; regenerate only validated targets. |
| p650 is invalid or assets/references/requests need repair; fresh p400 structural readiness passes | `p500_subprocess`: preserve p100–p450, quarantine stale downstream files, append the invalidation event, and rematerialize. |
| Active job, malformed/unsafe plan, contradictory state, or invalid p400 foundation | Resolve that prerequisite before mutation; a numeric stage or `done` label is not evidence. |

Only p650 and p500 have supported continuation routes here. Do not invent a p550 or arbitrary-slot restart.

## Execute once

For an authorized normal retry to p680, prefer `POST /api/image-gen/runs/{run_id}/resume` with `{"stop_target":"p680"}`. This is a **mutation that starts a job**, not an inspection or dry run. The API classifies again under the run lease and starts the selected worker. Observe that job and record its `resumeMode`; do not also launch the p500 CLI for the same job.

For a read-only inspection, use existing state/logs and validator results without calling the resume POST. For manual p500 execution, reset-only, or materialization diagnostics, read [p500 CLI procedure](references/p500-cli.md). Its dry-run checkpoint ID and plan token must be used unchanged for apply.

Preserve the same `create_resume.lock`; do not remove locks or interfere with another active create/resume/bulk job. Never reset another run, manually delete downstream files, truncate `state.txt`, or promote stale artifacts into valid state. `video_manifest.md` remains canonical even when its phase is `production`.

After a failed check, fix the evidenced canonical prerequisite and reclassify the run. If the same unchanged external failure persists, report that blocker instead of starting duplicate retries. Do not create a fresh run to work around a downstream failure.

## Completion

- Confirm the selected worker actually completed; an accepted job is not completion.
- For image-only retry, confirm p650 was revalidated under the lease and regenerated images match current requests/provenance.
- For p500, confirm the checkpoint, preserved upstream hashes, and `runtime.resume.p500.status` match the intended mode. Materialization-only success is not p680 image completion.
- For p680, require the normal frontend-create output validator, including files, decode, references, duration, and provenance checks.
- Report the reused run, selected boundary, validation outcome, and checkpoint path when applicable. Candidate selection is only required if the user requested it.
