# Frontend Image Completion

Read when executing or verifying p650/p680 completion. The runner’s current validators and canonical slot contract are authoritative.

## Required Outcome for `p650` / `p680`

When the stop target is `p650`, the run directory must contain real Japanese
content for:

- `state.txt`
- `research.md`
- `story.md`
- `visual_value.md`
- `script.md`
- `video_manifest.md`
- `asset_generation_requests.md`
- `asset_generation_manifest.md`
- generated reusable asset image files referenced by asset requests when the
  request is on the Codex built-in no-reference lane. These must be
  photorealistic/live-action Codex app-server image generation outputs with
  generation provenance, not local procedural raster fallbacks.
- `image_generation_requests.md`
- `p000_index.md`

When the stop target is `p680`, all `p650` artifacts are still required, and the
run directory must additionally contain generated scene image files referenced by
`image_generation_requests.md`, with optional candidate/selection data handed off
to the frontend.

Placeholder scaffolds are failures. Do not mark the task complete if any of the
required stage artifacts only contain TODO text, `placeholder`, `REPLACE_ME`,
or generic scaffold prose.

The app-server create flow validates every active slot through its stop target.
For `p680`, before returning success, `state.txt` must contain terminal status
for the active slots `p110`, `p120`, `p210`, `p220`, `p310`, `p330`, `p410`, `p420`,
`p440`, `p450`, `p510`, `p520`, `p530`, `p550`, `p560`, `p570`, `p610`, `p620`,
`p650`, `p660`, `p670`, and `p680`. Use `done` for completed work and `skipped`
only for an intentionally inapplicable optional slot. Use `awaiting_user_choice`
only when the caller explicitly requests a candidate selection/editing action.
Do not leave an active slot through the stop target as missing, pending,
in_progress, blocked, or failed.

Confirm request output paths, decodable image files, request-bound generation provenance, and the completed run index. Report the run directory, stop target, and actual validation outcome. Optional candidate selection is a user action, not an automatic production gate.
