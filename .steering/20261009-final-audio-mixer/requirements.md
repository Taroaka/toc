# Final audio mixer

- Final composition exposes independent narration, SE, and BGM gain and mute controls.
- Gains support amplification as well as attenuation; existing sound files remain unchanged.
- A video audition uses the same FFmpeg mixing path as final export, including offsets, cue gains, fades, native sound and limiting.
- Unsaved mixer changes cannot silently reach final export. Save settings with revision and video identity checks.
- Preserve existing source/candidate approval, narration readiness, and immutable render snapshots.
- No external generation or billing is needed to preview an adjusted mix.
