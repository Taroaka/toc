---
name: toc-p500-bootstrap-image-runner
description: Use when this repository needs to create initial p500 assets with no existing reference images, routing only bootstrap-eligible assets through the shared built-in image generation skill.
---

# ToC P500 Bootstrap Image Runner

## Overview

This skill is the repository-specific adapter for `p500` bootstrap asset generation.

It only applies to asset-stage entries that have no existing visual references.
It delegates actual built-in generation to `$codex-parallel-image-batch`.
For non-`p500` no-reference image work, prefer `$toc-no-reference-image-runner`.

## Scope

Use this skill only when all of the following are true:

- the work is in `p500` / asset stage
- the source of truth is `asset_plan.md` or `asset_generation_requests.md`
- `generation_plan.reference_inputs[]` is empty
- `generation_plan.bootstrap_allowed` is `true`
- `generation_plan.execution_lane` is `bootstrap_builtin`

Do not use this skill for:

- `p600` cut image generation
- any asset with existing reference inputs
- any derived asset with `derived_from_asset_id`

## Routing Rule

This skill is an adapter only.
When execution is needed, explicitly use `$codex-parallel-image-batch`.

## Required Repository Rules

1. `bootstrap_builtin` is valid only in `p500`.
2. Missing new metadata defaults to `standard`, not `bootstrap_builtin`.
3. Any asset with `reference_inputs[]` must stay on the standard lane.
4. Any asset with `derived_from_asset_id` must stay on the standard lane.
5. Bootstrap outputs are not canonical until `review.status=approved`.
6. After approval, the selected bootstrap output may remain as the canonical asset in the workspace.

## Execution Workflow

1. Read `asset_plan.md` or `asset_generation_requests.md`.
2. Select only items where:
   - `execution_lane=bootstrap_builtin`
   - `bootstrap_allowed=true`
   - `reference_inputs=[]`
3. Ignore all other asset entries.
4. Normalize each bootstrap item into:
   - `asset_id`
   - `asset_type`
   - `prompt`
   - `output_path`
   - `review_status`
5. Route execution through `$codex-parallel-image-batch`.
6. After built-in generation, import the selected output into the canonical asset path.
7. Treat the asset as canonical only after human review approval.
8. Record the saved path in `existing_outputs[]` and mark `creation_status` accordingly when updating planning artifacts.

## Review Expectations

- `character_reference`: face, hairstyle, costume, age impression
- `object_reference`: silhouette, material, decoration, scale impression
- `location_anchor`: spatial identity, major structures, lighting environment
- `reusable_still`: usable as a continuity anchor for later cuts

## Guardrails

- Do not use this lane for `p600`.
- Do not use this lane when a stronger reference-driven standard lane is available.
- Do not treat built-in generation as the repo-wide default image provider.
- Do not mix bootstrap and standard assets in a single ambiguous summary; label them clearly.

## Example Uses

- "Use $toc-p500-bootstrap-image-runner for p500 assets that have no reference images yet."
- "Use $toc-p500-bootstrap-image-runner to create initial character/object/location seeds, then stop for human review."
