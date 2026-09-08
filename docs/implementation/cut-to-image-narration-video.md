# Cut to Image, Narration, and Video

A p420 cut contract is translated into p600 image, p700 narration, and p800 video. The three media
layers use the same target beat and IDs but each owns a separate prompt projection.

## p600 Image

p600 reads the first-frame side:

1. cut_contract.first_frame_contract
2. cut_contract.viewer_contract.visual_evidence
3. cut_contract.cinematic_contract
4. cut_contract.continuity_contract
5. asset/character/object/location bibles
6. narration as secondary context

motion_contract.motion_brief is p800-only. The still shows the current visible entrance state and does
not complete a future action or reveal.

## p700 Narration

Narration adds information, causality, inner state, time, viewpoint, world rules, contrast, meaning, or
aftertaste that the image cannot carry. It does not repeat visible action as a caption. Silence is valid
when the visual beat carries the moment.

```yaml
audio:
  narration:
    text: ""
    tts_text: ""
    contract:
      schema_version: narration_contract_v2
      story_role:
        narrative_position: opening|middle|ending
        cut_function: custom
        voice_function: information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence
        audience_state_before: ""
        audience_state_after: ""
        must_cover: []
        must_not_reveal: []
      visual_distance:
        distance_policy: stay_close|contextual|meaning_first|silent
        visible_facts_in_frame: []
        narration_should_add: []
        must_not_caption_visible_action: true
      rhythm_and_timing:
        target_speech_seconds: 0
        start_timing: immediate|after_visual_read|mid_cut|late_cut|none
        end_timing: before_cut_end|on_cut_end|after_visual_resolution|none
        pause_intent: []
      tts_readiness:
        normalization_policy: kanji_public_hiragana_tts|mixed|dictionary_first
        pronunciation_targets: []
        max_sentence_chars: 42
    silence_contract:
      intentional: false
      kind: visual_value_hold|transition_hold|reaction_hold|tension_hold|breathing_room|ending_aftertaste|none|other
      duration_seconds: 0
      reason: ""
```

When a cut is silent, set intentional silence, duration, and reason. The validator checks that the
audio timeline includes the declared silence.

## p800 Video

p800 reads only the motion side:

```yaml
motion_contract:
  movable: true
  source_event_beat_id: scene_01_beat_01
  starts_from_first_frame: true
  motion_brief: ""
  camera_motion: ""
  subject_motion: ""
  environment_motion: ""
  emotional_change: ""
  end_state: ""
  must_not_add: []
```

Motion starts from the saved first-frame bytes, performs one primary action, and reaches the declared
end state. It cannot introduce an unlisted character, object, location, story event, or reveal.

## Shared structural checks

After each translation, compare the media projection to the same cut contract:

```yaml
cut_media_checks:
  same_target_beat: true
  image_supports_motion_start: true
  motion_reaches_declared_end_state: true
  narration_not_captioning_image: true
  reveal_constraints_preserved: true
  continuity_preserved: true
  handoff_visible_or_audible: true
```

A false check names the owning cut field and blocks the affected request until the source contract or
projection is repaired. This is ordinary cross-field validation; no separate content verdict is created.

## References

- docs/data-contracts.md
- docs/implementation/image-prompting.md
- docs/implementation/video-prompting.md
- docs/implementation/video-integration.md

