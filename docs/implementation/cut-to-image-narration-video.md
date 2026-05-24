# Cut to Image, Narration, and Video

This document defines how a p420 `cut_contract` is translated into p600 image, p700 narration, and p800 video work.

The three downstream stages must interpret the same `target_beat`. They are different media translations of one cut, not three independent prompts.

## p600 Image

p600 reads the first-frame side of the cut contract.

Input priority:

1. `cut_contract.first_frame_contract.first_frame_brief`
2. `cut_contract.viewer_contract.visual_proof`
3. `cut_contract.cinematic_contract`
4. `cut_contract.continuity_contract`
5. asset, character, object, and location bibles
6. narration text as secondary context only

`motion_contract.motion_brief` is p800-only. p600 must not read it, summarize it, or leak future motion into the still prompt.

The still should show the beat's entrance, not complete the action unless the cut function is explicitly reaction, aftermath, or hold.

In request materialization, `scripts/generate-assets-from-manifest.py` prepends visible requirements from `cut_contract` to the image request prompt. It may use `viewer_contract`, `cinematic_contract`, `continuity_contract`, and `first_frame_contract`, but it must not include `motion_contract.motion_brief` in the image prompt.

## p700 Narration

Narration is not a caption for the image. It should do one of these jobs:

- set up information that the image cannot efficiently carry;
- add a factual constraint required for comprehension;
- shape emotion without repeating visible content;
- create contrast between what is seen and what is understood;
- leave aftertaste after a turn or payoff;
- remain silent when silence is stronger.

```yaml
narration_contract:
  role: "setup|fact|emotion|contrast|aftertaste|silent"
  target_function: ""
  must_cover: []
  must_avoid: []
  timing:
    start: "early|mid|late|none"
    end: "before_turn|on_cut_end|after_visual|none"
  text: ""
  tts_text: ""
  silence_reason: ""
```

If `role: silent`, `silence_reason` is required.

## p800 Video

p800 reads the motion side of the cut contract.

The motion prompt should start from the approved still, execute the cut function, and end in the declared `end_state`.

```yaml
motion_contract:
  movable: true
  motion_brief: ""
  camera_motion: "static|slow_push|slow_pull|pan|tilt|tracking|handheld_subtle"
  subject_motion: ""
  environment_motion: ""
  emotional_change: ""
  end_state: ""
  must_not_add: []
```

p800 must not introduce a new character, key object, reveal, or story event that was not present in the cut contract.

In request materialization, `scripts/generate-assets-from-manifest.py` prepends motion requirements from `cut_contract.motion_contract` to the video request prompt. This is the downstream point where `motion_brief` becomes active.

## Triangulation Review

After p600/p700/p800 are drafted, review them against the same cut contract.

```yaml
triangulation_review:
  same_target_beat: false
  image_supports_motion_start: false
  motion_reaches_declared_end_state: false
  narration_not_captioning_image: false
  reveal_constraints_preserved: false
  continuity_preserved: false
  handoff_visible_or_audible: false
```

Blocking reason keys:

```yaml
- handoff_image_motion_mismatch
- handoff_narration_captioning
- handoff_motion_adds_new_story
- handoff_still_finishes_action
- handoff_reveal_early
- handoff_end_state_missing
- handoff_audio_visual_conflict
```
