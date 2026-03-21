# Design

## Summary

Treat the three asks as one cohesive immersive-manifest contract refinement:

- object/setpiece guidance is canonicalized in docs/templates and reflected in runnable manifests,
- Ryugu spectacle midroll is formalized as a visual-value pattern,
- variant reference selection is added as an explicit optional layer on top of existing IDs.

## Design Choices

### 1. Keep object/setpiece design manifest-first

- Use `assets.object_bible[]` as the canonical definition layer.
- Keep per-scene activation via `image_generation.object_ids`.
- If current templates do not expose concrete examples strongly enough, add them there rather than inventing a second contract.

### 2. Treat Ryugu spectacle as visual-value design, not ad hoc prompt text

- The canonical home is `visual_value.md` plus the existing visual-value playbook and scene-conte guidance.
- Strengthen templates/examples if needed so the pre-Otohime Ryugu sequence is visible as a first-class pattern.
- Do not hardcode a single folktale-specific sequence into generic runtime logic unless selection/render behavior requires it.

### 3. Add explicit variant reference selection while preserving IDs

- Preserve `character_ids` and `object_ids` as base identity selectors.
- Introduce optional per-scene selectors for variants if runtime lacks them today.
- Candidate shape:
  - `image_generation.character_variant_ids: []`
  - `image_generation.object_variant_ids: []`
- Add optional variant metadata to bible entries rather than replacing existing `reference_images`.
- Runtime merges base refs plus variant-specific refs when requested.

## Compatibility

- Existing manifests with only `character_ids` / `object_ids` continue to work.
- Variant selectors are additive and optional.
- Existing docs remain valid; new docs clarify when to use variants.

## Verification

- Add parsing/guide-merge tests for variant selectors if runtime changes.
- Update scaffold/template tests if canonical examples change.
