# Design

- Extend `CharacterBibleEntry` with `physical_scale` and `relative_scale_rules`.
- Parse these fields from `assets.character_bible[]` and preserve them through character-bible expansion helpers.
- During asset-guide prompt injection, add physical-scale lines for every active character and relative-scale rules when two or more characters are active.
- Keep the existing reference/refstrip behavior unchanged; scale locking is additive.
- Update manifest templates and the Urashima manifest to include the new contract.
