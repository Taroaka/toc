# CONTROL

## Status Contract

status_file: .steering/20260826-semantic-repair-reconciliation/PLAN.md
attempt_log: .steering/20260826-semantic-repair-reconciliation/ATTEMPTS.md
durable_notes: .steering/20260826-semantic-repair-reconciliation/NOTES.md
update_memory_after: every_experiment
check_control_before: phase_change, strategic_pivot, expensive_provider_run

## Human Priorities

primary_priority: stability
secondary_priority: evidence_quality

## Scope Knobs

allowed_files:
- server/image_gen_app.py
- server/codex_app_server.py
- scripts/toc-immersive-frontend-run.py
- toc/**
- tests/**
- docs/** when the runtime contract changes
- .steering/20260826-semantic-repair-reconciliation/**

protected_files:
- marketing/**
- output/** except canonical Cinderella resume and the final fresh validation run
- unrelated root PLAN.md

max_blast_radius: semantic repair reconciliation through P680 only

## Resource Knobs

max_parallel_jobs: existing bounded defaults unless a focused test requires less
network_allowed: true
external_api_allowed: final_p680_verification_only_after_tests_green

## Decision Gates

require_approval_for:
- destructive_change
- dependency_change
- schema_or_migration_change
- public_api_change
- qa_weakening
- scope_expansion
- continuation_beyond_p680

## Sidecar Inputs

sidecar_apply_cadence: between_runs_only
nudge_file: .steering/20260826-semantic-repair-reconciliation/CONTROL.md
human_overlay_file: none
review_queue_file: none

## Latest Human Nudge

First fix the immediate repair reconciliation problem, then prove Cinderella and one fresh story reach image generation/P680.
