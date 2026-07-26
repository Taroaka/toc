---
name: toc-resume-p500
description: Use when an existing frontend-created ToC run must be retried from p500 after Codex fixes, while preserving p100-p450 research, story, visual planning, script, and manifest work instead of creating a new run.
---

# ToC P500 Resume

## Overview

Resume the same frontend-created run at p500. Preserve the authored p100-p450
foundation, quarantine stale p500+ requests/reviews/media, append an
invalidation snapshot, and then run the normal semantic and image workflow again
through p650 or p680.

This is a pseudo rollback. Never rewrite `state.txt` history and never delete the
old downstream artifacts in place.

## Canonical Contract

Before acting, read:

- `docs/data-contracts.md`, section `p500 resume contract`
- `docs/implementation/immersive-ride-entrypoint.md`
- `.codex/skills/toc-immersive-runner/SKILL.md`

Use `scripts/resume-from-p500.py` as the only reset/resume entrypoint. Do not
reimplement the quarantine list in chat and do not invoke the fresh-run frontend
CLI for an existing run.

## Required Inputs

Resolve:

- the exact existing run directory under `output/`
- stop target: normally `p680`; use `p650` only when explicitly stopping before
  scene image generation
- whether the request is reset-only, semantic/materialization diagnostics, or a
  full media retry

If several similarly named runs exist, use provenance and the user's named run.
Other runs may belong to concurrent Codex development; do not reset, move, or
delete them.

## Workflow

### 1. Inspect and dry-run

Run:

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

### 2. Apply the intended mode

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

### 3. Handle a repeated QA failure

If semantic QA fails:

1. Keep the same run directory.
2. Diagnose and fix the canonical upstream artifact named by the QA report.
3. Make the p400 deterministic/review gate current if the fix changed
   `script.md` or `video_manifest.md`.
4. Invoke this skill again. The next checkpoint quarantines the failed retry's
   p500+ artifacts and starts from the corrected foundation.

Do not create a fresh frontend run merely to retry a downstream failure.

## Stage Routing

- p500 no-reference reusable assets follow
  `$toc-p500-bootstrap-image-runner`.
- p600 scene images follow `$toc-p600-image-runner`.
- Contextless semantic QA remains mandatory. Do not convert schema/count success
  into a semantic pass.
- `video_manifest.md` remains in place even when it says
  `manifest_phase: production`; frontend create materializes its execution
  skeleton at p450. Requests, frozen snapshots, reports, media bytes, and
  downstream state are what become stale.

## Completion Gate

Before reporting success:

- confirm the checkpoint contains `checkpoint.json` and the quarantined files
- confirm upstream SHA-256 values in the checkpoint match the dry-run plan
- confirm `runtime.resume.p500.status` is `completed` for a full retry or
  `semantic_materialized` for diagnostic materialization
- for p680, run the normal frontend-create validator and confirm the handoff is
  ready
- report the reused run directory and checkpoint path; do not report a new run
  id

## Guardrails

- Never use `rm`, recursive deletion, or manual blank files for this workflow.
- Never modify or truncate the append-only state history.
- Never move unknown artifacts automatically.
- Never bypass fresh p400 readiness.
- Never use this skill for a brand-new run; use `$toc-immersive-runner`.
- Never use this skill for a p600-only image recreation when p500 assets remain
  valid; use `$toc-p600-image-runner`.
