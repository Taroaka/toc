# Requirements: Urashima V3/O3 video design

## Background

- The current Urashima immersive manifest contains narration and still planning, but only two test `video_generation` entries, leaving the total at 9 seconds.
- The user clarified that the intended provider path is EvoLink-backed Kling V3 / O3, not O1.
- We need a concrete video design now, before paid generation, so later execution has a coherent clip plan.

## Goals

- Expand the Urashima run from a 9-second test residue into a full provisional clip design.
- Reuse the existing still-image audit so only selected anchor cuts and transition beats are promoted to video clips.
- Use V3 for standard clips and O3 only for visually difficult threshold / transformation clips.

## Non-Goals

- Running paid video generation in this task.
- Locking final durations before narration audio is generated.
- Rewriting the script or story structure.

## Success Criteria

- `video_manifest.md` contains a coherent set of provisional `video_generation` entries across the story arc.
- `video_generation_plan.md` summarizes clip count and duration totals.
- The design stays consistent with the still-image plan rather than promoting every cut to a video clip.
