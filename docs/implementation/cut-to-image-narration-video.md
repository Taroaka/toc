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
audio:
  narration:
    text: ""
    tts_text: ""
    contract:
      schema_version: "narration_contract_v2"
      story_role:
        narrative_position: "opening|middle|ending"
        cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
        voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
        audience_state_before: ""
        audience_state_after: ""
        must_cover: []
        must_not_reveal: []
        done_when: []
      visual_distance:
        distance_policy: "stay_close|contextual|meaning_first|silent"
        visible_facts_in_frame: []
        narration_should_add: []
        must_not_caption_visible_action: true
        visual_overlap_allowed: false
        visual_overlap_reason: ""
      rhythm_and_timing:
        target_speech_seconds: 0
        start_timing: "immediate|after_visual_read|mid_cut|late_cut|none"
        end_timing: "before_cut_end|on_cut_end|after_visual_resolution|none"
        pause_intent: []
        audio_visual_sync_point: ""
      tts_readiness:
        normalization_policy: "kanji_public_hiragana_tts|mixed|dictionary_first"
        pronunciation_targets: []
        max_sentence_chars: 42
      # compatibility aliases
      role: "setup"
      target_function: "derive_from_story_role_voice_function"
      must_cover:
        - "derive_from_story_role_must_cover"
      must_avoid:
        - "映像のキャプション化"
      done_when:
        - "derive_from_story_role_done_when"
      silence_reason: ""
    silence_contract:
      intentional: false
      kind: "visual_value_hold|transition_hold|reaction_hold|tension_hold|breathing_room|ending_aftertaste|none|other"
      confirmed_by_human: false
      reason: ""
```

If `role: silent`, `silence_reason` is required.
If `story_role.voice_function: silence` or `visual_distance.distance_policy: silent`, `silence_contract` is required on the runtime `audio.narration` node.

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
