# CONTROL

## Status contract

status_file: `.steering/20260710-duration-aware-story-pipeline/tasklist.md`
attempt_log: `.steering/20260710-duration-aware-story-pipeline/ATTEMPTS.md`
durable_notes: `.steering/20260710-duration-aware-story-pipeline/NOTES.md`
update_memory_after: every meaningful test/implementation attempt
check_control_before: phase change, strategic pivot, expensive step

## Human priorities

primary_priority: behavior preservation
secondary_priority: auditable duration and review evidence

## Scope knobs

allowed_files:
- `server/web/src/main.tsx`
- `server/image_gen_app.py`
- `scripts/toc-immersive-frontend-run.py`
- `scripts/toc-create-run-headless.py`
- duration/audio scripts under `scripts/`
- duration/review modules under `toc/`
- related tests, workflow contracts, and durable docs

protected_files:
- root `SPEC.md`, `GOAL.md`, and `PLAN.md`
- existing `output/` runs
- unrelated user changes in every dirty file

max_blast_radius: frontend create and duration/review pipeline only

## Resource knobs

max_runtime_per_step: 15 minutes unless a known broader regression requires longer
max_parallel_jobs: 3
network_allowed: existing Codex app-server path only; no new source-retrieval feature
external_api_allowed: no paid image, video, or TTS provider calls

## Decision gates

require_approval_for:
- strategic pivot
- destructive change
- dependency change
- database/schema migration
- public endpoint replacement
- paid external generation
- scope expansion into classic/source/rights validation

## Latest human nudge

Implement the approved duration and semantic-gate scope. Duration passes at 80% or more with no upper bound. Do not implement the earlier classic/source/rights requirements or one-click p680-to-p900 continuation.

