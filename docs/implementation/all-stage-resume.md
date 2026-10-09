# Production resume

`POST /api/image-gen/runs/{run_id}/resume` resumes an existing run. The web toolbar's
「停止した処理を再開」 action calls it, then polls the existing create-job status API.
It never creates a replacement run or deletes state history.

## Boundaries

| Failure | Continuation |
| --- | --- |
| p100 research, p200 story, p300 visual planning, p400 cinematic/script projection | `authoring_subprocess`: reuse matching validated stage receipts, finish p450, then use the existing p500 plan/apply worker. |
| p500 assets / p600 images | Existing `p500_subprocess` or `image_only` classifier, request binding and provenance validation. |
| Narration drafts or TTS, video prompt materialization or video candidates, render input freeze or final render | `media_operation`: replay the last incomplete saved operation with its exact request; reuse matching completed audio items and video candidates. |

The default request remains `{"stop_target":"p680"}` for compatibility. If a saved
incomplete media operation exists, its requested stage is the effective stop target;
resumption does not authorize new downstream work. `operation_id` can identify a
specific saved media operation. New media generation responses include `operationId`.
No resume route publishes the video or adds new approval/selection actions.

After image completion, the toolbar can start the pending p710 narration preparation
with `{"stop_target":"p680","continue_waiting":true}`. The backend verifies strict
p680 completion and the pending p710 boundary under the run lease, records a durable
`narration_drafts` operation with `replace=false`, and uses the existing media worker.
It does not regenerate images or generate TTS. Without that explicit opt-in, completed
p680 remains a terminal boundary. Existing incomplete media operations still take priority.

## Authoring receipts

`logs/checkpoints/<stage>.json` records configuration, upstream hashes and output
hashes. A receipt is completed only after the canonical stage returns its output and its
applicable validators pass; resume does not add a research output-validation gate.
Changing an input or output invalidates reuse. A running, missing or damaged receipt
is not evidence of completion. Current validators still run for reused artifacts.
Legacy artifacts without receipts are not silently adopted as verified authoring;
legacy p400-complete runs remain eligible for the existing p500 checks.

The existing-run CLI is explicit and restricted to p450:

```bash
python scripts/toc-immersive-frontend-run.py \
  --topic '<saved topic>' --run-dir 'output/<existing run>' \
  --resume-authoring --stop-target p450
```

It loads the exact persisted `logs/orchestration/create_input.json` under a pinned
run-directory lock. It refuses changed world-walk source content. The normal new-run
CLI still rejects nonempty destinations. API continuation inherits the existing run
lease, then executes the p500 dry-run/apply contract; do not launch a second CLI while
an API worker is active.

## p450 to p500 handoff

A resumed `skeleton` manifest is recompiled, checked against the existing p400 structural
contract, and promoted to `production` under the retained run lease before request
materialization. Grounding is refreshed for the promoted bytes. An unknown phase or
failed prerequisite stops before request generation; promotion does not authorize skipping
reference, output, or provenance validation.

A failed resume publishes a terminal canonical run state as well as a failed job record.
Specific subprocess failure diagnostics take precedence over the server fallback, so the
frontend can show the stopped stage and enable retry without losing the original cause.

## Media journals

`logs/media_operations/<operation_id>.json` persists the request before execution,
input hashes, per-item results and output hashes. It binds requested references and
actual render inputs. The journal records a pending hash before each manifest/script publication, then
advances its confirmed head. An interrupted publication accepts only its preceding
head or pending output; older revisions require an explicit transaction rollback.
External edits are never silently adopted as the old operation's input.

Reused media must still exist, have matching bytes and be decodable by the media
probe. A failed candidate does not invalidate another candidate's completed output.
The bulk video UI sends one bulk request so its candidates share an operation and a
run lease; the existing server candidate-count/concurrency limits remain enforced.

An orderly request cancellation waits for the in-flight provider work to reach a
terminal result and records it before releasing the lease. Render subprocess timeout
cleanup kills/reaps the process group. After an abrupt machine/process loss, a provider
result that was not durably recorded cannot be claimed completed: retry is at-least-once,
not a guarantee of exactly-once remote billing. The implementation does not invent
provider idempotency or task-recovery APIs.

## Limits and rollout

- Authentication, disk-space and invalid-input failures still need their underlying
  cause resolved. Changed media inputs require submitting the current settings again.
- An operation is replayable only if its original request was saved. Pre-upgrade media
  calls without a journal must be submitted again from their stage UI.
- A stage resumes from its last completed artifact/item, not from an LLM's partial
  reasoning or an encoder's unfinished frame.
- Code changes require the normal backend reload to become live. Do not restart the
  production stack while another run is active just to deploy this change.

## Error-directed corrections

Normal create now repairs supported authoring and image-output validation failures within
the existing job. Resume retains correction budgets and pending context as described in
[production-auto-repair.md](production-auto-repair.md). It does not reset exhausted budgets.
