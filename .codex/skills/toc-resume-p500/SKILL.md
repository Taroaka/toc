---
name: toc-resume-p500
description: Use when an existing frontend-created ToC run must resume after a semantic, asset, reference, or image-generation failure. Start from the closest verified boundary with a canonical continuation—normally p650 for scene-image-only retry or p500 when asset/reference or upstream state is stale—while preserving valid work in the same run.
---

# ToC Adaptive Resume

## Overview

Resume the same frontend-created run from the closest verified boundary before
the failed operation. Do not default to p500 merely because a later operation
failed. Preserve every current upstream artifact and generated output that the
selected route can prove is still valid.

The skill name is retained for compatibility, but this skill is an adaptive
resume router. It chooses the canonical p650 scene-image-only route when that
boundary is current, and otherwise falls back to the canonical p500 checkpoint
route. It never invents an unsupported arbitrary slot resume.

## Canonical Contract

Before acting, read:

- `docs/data-contracts.md`, sections `p500 resume contract` and the p650
  image-only resume rule
- `docs/implementation/immersive-ride-entrypoint.md`
- `.codex/skills/toc-immersive-runner/SKILL.md`

Prefer `POST /api/image-gen/runs/{run_id}/resume` as the automatic routing
entrypoint. It validates the current run, chooses p650 image-only or p500
checkpoint resume, and repeats safety classification after acquiring the run
lease. Use `scripts/resume-from-p500.py` only when the selected route is the
canonical p500 checkpoint path or when explicitly performing p500 diagnostics.

Do not reimplement quarantine or deletion lists in chat. Do not invoke the
fresh-run frontend CLI for an existing run.

## Required Inputs

Resolve:

- the exact existing run directory under `output/`
- stop target: normally `p680`
- whether the request is reset-only, semantic/materialization diagnostics, or a
  full media retry
- the failed operation and its evidence: canonical state, app-server/job log,
  request snapshot, generation provenance, validator result, and regeneration
  plan when present

If several similarly named runs exist, use provenance and the user's named run.
Other runs may belong to concurrent Codex development; do not reset, move, or
delete them.

## Resume Boundary Selection

Start at the first verified prerequisite with a canonical continuation worker
when tracing upstream from the failed operation. Do not compare all later
checkpoints or select the largest numeric slot, `runtime.stage`, or a stale
progress label.

### Choose p650 scene-image-only resume

Choose p650 only when all of these are true:

- strict current p650 validation passes
- the failed or missing work is scene image provider/output work after p650
- every regeneration target is a safe current-request-bound scene output
- the regeneration plan does not require asset/reference repair
- no create, resume, or bulk image job is active for the run

This includes a scene image API timeout or provider failure when the frozen
requests, approved assets, semantic evidence, and provenance bindings remain
current. Preserve valid p500 assets and unaffected scene outputs. Use the Image
generation app resume API; its image-only worker performs hash-aware partial
regeneration and revalidates p650 under the retained lease.

### Choose canonical p500 checkpoint resume

Choose p500 when the verified p650 route does not apply and any of these are true:

- scene-image work is the target but strict p650 validation fails
- asset generation, asset/reference repair, or prompt materialization must run
- the asset plan, asset request snapshot, image prompt request, or their semantic
  evidence is stale or invalid
- a canonical artifact before p650 changed and invalidated downstream bindings

The p400 foundation must still pass fresh deterministic readiness. The p500
route preserves p100-p450, quarantines stale p500+ artifacts, and applies an
append-only invalidation event.

### Block instead of guessing

Stop without mutation when the plan is malformed, a target is unsafe or not
bound to the current request, state and artifacts contradict each other, an
active job owns the run, or p400 readiness is invalid. Repair or classify the
upstream defect first. Never promote `done` state text into proof that a boundary
is current.

## Workflow

### 1. Inspect under the canonical router

Invoke the Image generation app resume API and record its returned `resumeMode`:

- `image_only`: resume from verified p650 and retry only the bound scene outputs
- `p500_subprocess`: use canonical p500 dry-run/exact-token/apply

Do not override the selected mode merely to save time. The route is evaluated
again after lease acquisition so a concurrent state change cannot make the
earlier choice unsafe.

### 2. Run canonical p500 dry-run only when selected

For explicit p500 diagnostics or when the router selects `p500_subprocess`, run:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<unique-checkpoint-id>"
```

The command must pass the fresh deterministic p400 content/readiness gate before
it produces a plan. The continuation path rematerializes p400 review artifacts
and passes the full review-integrity gate before any p500 request/provider work.
Inspect the JSON and confirm:

- `preserved_files` includes `research.md`, `story.md`, `visual_value.md`,
  `script.md`, and `video_manifest.md`
- `downstream_files` contains only p500+ requests, reports, generated media, and
  derived outputs
- `checkpoint_dir` is inside the same run under `logs/resume/p500/`
- record the returned `checkpoint_id` and `plan_token`; apply must use both
  exact values

Stop on any upstream canonical file in `downstream_files`. Fix the classifier
before applying; never work around it with manual deletion.

### 3. Apply the intended p500 mode

Reset only:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply
```

Run semantic/materialization diagnostics without media generation:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply \
  --continue-to p650 \
  --materialize-only
```

Normal frontend image-review retry:

```bash
python scripts/resume-from-p500.py \
  --run-dir "output/<topic>_<timestamp>" \
  --checkpoint-id "<dry-run checkpoint_id>" \
  --plan-token "<dry-run plan_token>" \
  --apply \
  --continue-to p680
```

The CLI holds the same `create_resume.lock` used by frontend create/resume and
single/bulk image generation. It also rejects persisted bulk jobs that are
still `queued` or `running`. If another process owns the run, report the
conflict and wait; do not remove lock files.

### 4. Handle a repeated QA failure

If semantic QA fails:

1. Keep the same run directory.
2. Diagnose and fix the canonical upstream artifact named by the QA report.
3. Make the p400 deterministic/review gate current if the fix changed
   `script.md` or `video_manifest.md`.
4. Invoke this skill again. Reclassify from current evidence; do not assume the
   next attempt must use the same boundary.

Do not create a fresh frontend run merely to retry a downstream failure.

## Stage Routing

- p500 no-reference reusable assets follow
  `$toc-p500-bootstrap-image-runner`.
- p600 scene images follow `$toc-p600-image-runner`.
- A p650 image-only retry must preserve current p500 assets and unaffected scene
  outputs; it may regenerate only scene paths named by the validated current
  regeneration plan.
- Contextless semantic QA remains mandatory. Do not convert schema/count success
  into a semantic pass.
- `video_manifest.md` remains in place even when it says
  `manifest_phase: production`; frontend create materializes its execution
  skeleton at p450. Requests, frozen snapshots, reports, media bytes, and
  downstream state are what become stale.

## Completion Gate

Before reporting success:

- report the selected boundary and the evidence that made it repairable
- for p650 image-only, confirm strict p650 was revalidated under the lease,
  regenerated outputs are request/provenance-bound, and strict p680 passes
- for p500, confirm the checkpoint contains `checkpoint.json` and quarantined
  files, upstream SHA-256 values match the dry-run plan, and
  `runtime.resume.p500.status` is `completed` or `semantic_materialized`
- for p680, run the normal frontend-create validator and confirm the handoff is
  ready
- report the reused run directory and checkpoint path; do not report a new run
  id. For p650 resume, report that no p500 checkpoint was created.

## Guardrails

- Never use `rm`, recursive deletion, or manual blank files for this workflow.
- Never modify or truncate the append-only state history.
- Never move unknown artifacts automatically.
- Never choose a resume boundary from slot status alone.
- Never bypass fresh p400 readiness for canonical p500 resume or strict current
  p650 validation for image-only resume.
- Never use this skill for a brand-new run; use `$toc-immersive-runner`.
- Never send a scene-image-only API failure back to p500 when strict p650 and the
  current scene-only regeneration plan are valid.
