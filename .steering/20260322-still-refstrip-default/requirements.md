# Requirements

- When a still image scene includes a character via `image_generation.character_ids`, any existing `assets/characters/*_refstrip.png` for that character should also be used as a reference by default.
- This should strengthen character consistency for still generation without requiring extra CLI flags beyond the existing asset-guide flow.
- B-roll scenes with `character_ids: []` must remain unaffected.
