# Requirements: Urashima still budget optimization

## Background

- The run-level `still_image_plan` audit for `output/浦島太郎_20260208_1515_immersive` improved the previous "generate every cut" assumption, but `generate_still: 33` is still too high for the actual continuity needs.
- The user wants the still budget pushed down to the low 20s while preserving story clarity and continuity.
- This optimization must not regress the global design rule that stills are only for continuity anchors, hero-object reveals, or irreversible character-state changes.

## Goals

- Reduce the Urashima run's generated still targets from 33 to the low 20s.
- Keep dedicated still generation only where a cut introduces one of:
  - a new place anchor that will be reused,
  - a hero-item reveal that benefits from a locked reference frame,
  - a major character-state transition that later cuts depend on.
- Reclassify transition cuts into `reuse_anchor` or `no_dedicated_still` where motion chains, editorial holds, or adjacent anchors are sufficient.

## Non-Goals

- Rewriting the whole script or re-storyboarding the entire run.
- Changing image model/provider selection.
- Re-rendering the run in this task.

## Success Criteria

- `video_manifest.md` records a low-20s `generate_still` count with updated per-cut `still_image_plan`.
- The cuts demoted from dedicated still generation have explicit replacement strategies (`reuse_anchor` or `no_dedicated_still`) and sources where needed.
- `verify-pipeline` is rerun for the run so downstream reports reflect the updated manifest.
