# Cut Loop (p420)

This document is the canonical operating guide for turning an approved scene contract into viewer-facing cut contracts.

p420 does not split a scene into short summaries. It designs the beats the audience will actually see, hear, and follow, then makes those beats usable by p500 assets, p600 image prompts, p700 narration, and p800 video motion.

## Outcome

p420 is complete only when every production scene has:

- a `coverage_plan` that assigns the scene's dramatic question, visible value shift, causal turn, reveal constraints, and handoff to concrete cuts;
- enough cuts for the scene importance and duration;
- one viewer-facing intent per cut;
- a startable first-frame still for p600;
- a motion contract for p800 that starts from that still without adding new story;
- a narration contract or explicit silent reason for p700;
- a downstream handoff for p500/p600/p700/p800.

## Cut Count

Use the larger of the importance floor and the duration floor.

```text
min_by_importance:
  low: 2
  medium: 3
  high: 5
  critical: 7

min_by_duration = ceil(target_duration_seconds / 8)
min_cut_count = max(min_by_importance, min_by_duration)
```

Reference stills, title cards, and pure transitions may use fewer cuts only with an explicit exception reason. A cut longer than 12 seconds needs a `duration_exception.reason`.

Transformation, spectacle, proof reveal, confrontation, and emotional reversal should usually be split into approach, pressure or threshold, turn or payoff, reaction, and handoff.

## p420 Steps

### p420a Coverage Planning

Create `coverage_plan` before writing cuts.

```yaml
coverage_plan:
  coverage_strategy: "3_cut|5_cut|7_cut|spectacle_ladder|custom"
  min_cut_count:
    by_importance: 3
    by_duration: 3
    selected: 3
    exception_reason: ""
  function_sequence:
    - setup
    - pressure
    - threshold
    - turn
    - reaction
    - handoff
  scene_obligations:
    audience_information_to_cover: []
    withheld_information_to_preserve: []
    visual_evidence_to_show: []
    causal_turn_cut_selector: ""
    handoff_cut_selector: ""
```

### p420b Cut Contract Drafting

Each cut should materialize a `cut_contract`. `scene_contract` may remain as a compatibility alias for older readers, but `cut_contract` is the semantic source of truth.

Required areas:

- `viewer_contract`: target beat, screen question, dramatic job, visual proof, must-show, must-avoid, done-when.
- `cinematic_contract`: camera purpose, shot size, subject priority, foreground/midground/background, screen direction.
- `continuity_contract`: start state, end state, carry-forward items, continuity risks.
- `first_frame_contract`: p600-only still requirement and action completion state.
- `motion_contract`: p800-only movement, end state, and things motion must not add.
- `narration_contract`: p700 role or silent reason.
- `downstream_handoff`: what each downstream stage receives.

### p420c Review

The review is a gate, not advice. The aggregate report must include:

```text
## Cut Blueprint Gate
cut_intent_isolation
beat_ladder_coverage
first_frame_motion_readiness
multimodal_contract_coverage
duration_density_and_handoff
coverage_plan_complete
continuity_contract_complete
narration_contract_complete
downstream_handoff_complete
triangulation_review_ready
```

Do not pass p420 while any of these are unresolved.

### p420d Handoff Matrix

Build a handoff matrix that checks what each cut receives from the previous cut, what it delivers to the next cut, and what p500/p600/p700/p800 need.

### p420e Manifest Materialization

Materialize the approved cut contracts into `video_manifest.md.scenes[].cuts[]`.

New manifests should write `cut_contract`. During migration, also copy the core fields into `scene_contract` for compatibility.

## Blocking Reason Keys

```yaml
- cut_overloaded_multiple_beats
- cut_missing_screen_question
- cut_missing_visual_proof
- cut_not_imageable
- cut_not_movable
- cut_missing_narration_contract
- cut_narration_is_caption
- cut_silent_without_reason
- cut_missing_threshold_before_turn
- cut_missing_reaction_after_turn
- cut_missing_handoff
- cut_breaks_reveal_constraint
- cut_continuity_unclear
- cut_asset_dependency_missing
- cut_duration_unjustified
- cut_role_duplicate
- cut_downstream_handoff_missing
- cut_triangulation_unready
```

