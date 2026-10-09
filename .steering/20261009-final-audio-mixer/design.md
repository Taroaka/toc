# Design

Add optional `mix` to sound_design_v1 and sound_render_v1. Each of narration/se/bgm has volume_db (-60..36) and muted, defaulting to 0 dB and false. Cue gains are additive with category gain. Native video audio follows SE gain; existing dialogue ducking remains supported. Frozen sound hashes include mixer values.

The final tab has three accessible sliders, numeric inputs, mute switches, reset, save and audition buttons. Audition is an explicit local render, not an approximate browser audio graph. Changing a slider marks the previous audition stale and disables final export until settings are saved. Existing per-cue controls remain available for individual effects.

POST mix validates the existing video hash and sound-plan revision. It preserves a completed sound selection while invalidating downstream render state. POST mix-preview creates isolated temporary render inputs under a UUID, without writing the manifest or completing production stages. It validates the selected inputs before and after render and rejects concurrent changes. Authenticated existing media routes serve the resulting preview.
