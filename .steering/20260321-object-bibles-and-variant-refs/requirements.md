# Requirements

## Background

The repo already documents object/setpiece bibles, visual-value midroll cuts, and immersive manifests, but the current Urashima artifacts may not consistently carry those concepts into runnable manifests and reference selection. The user asked for three concrete checks and implementation where missing.

## Goals

1. Confirm and, if needed, implement a canonical instruction sheet for non-character hero items/setpieces such as `tamatebako` and `ryugu_palace`.
2. Confirm and, if needed, implement canonical scene-design and image-guidance support for a Ryugu exploratory spectacle block before Otohime appears, using 4-6 cuts of about 4 seconds each.
3. Confirm and, if needed, implement support for multiple reference variants per character/object across time/state variants so scenes can select different reference images instead of only one reference per entity.

## Non-Goals

- Re-rendering all existing runs.
- Changing unrelated flows outside the minimal contract/runtime/docs needed for these three capabilities.

## Requirements

### R1. Object/Setpiece Canonical Guidance

- There must be a canonical repo source describing how to define and use hero-item/setpiece generation guidance.
- The source must cover `assets.object_bible[]`, `reference_images`, `fixed_prompts`, and per-scene `object_ids`.
- If current design is insufficient, templates/docs/runtime must be updated so new immersive runs can use it directly.

### R2. Ryugu Exploratory Midroll

- There must be a canonical repo source describing a pre-Otohime Ryugu exploratory sequence.
- The sequence must support 4-6 cuts, about 4 seconds each, narration-free, and intended as visual payoff.
- If current design is insufficient, canonical templates/playbooks/docs must be updated so this sequence can be authored and rendered intentionally.

### R3. Variant Reference Support

- The contract/runtime must support multiple reference variants for a single character or object when time/state/phase differs.
- Scenes must be able to select among variants explicitly rather than relying on a single reference image path per entity.
- Backward compatibility with current `character_ids`, `object_ids`, and existing manifests must be preserved.

### R4. Verification

- Add or update targeted tests for any runtime/contract changes.
- Prefer minimal, spec-first updates in docs/workflow/templates, with runtime changes only where selector or parsing behavior is insufficient.
