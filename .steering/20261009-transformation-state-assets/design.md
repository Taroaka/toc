# Design: Transformation State Asset Binding

## Existing Contracts

- Manifest asset bibles already support `reference_variants[]` and scenes already select
  `character_variant_ids`, `object_variant_ids`, or `location_variant_ids`.
- `generate-assets-from-manifest.py` merges selected variant image paths into scene image requests
  and validates variant IDs.
- Video materialization already supports a request-bound `video_generation.last_frame` and ordinary
  file/hash checks, but generated runs do not consistently materialize an authored result-state image
  or require a supported first/last-frame mode.
- Frontend create creates `asset_plan.md` and request files from the p420 manifest; Codex stage tools
  use the shared manifest materializer and p500 artifacts.

## Proposed Shape

Extend the existing asset variant contract rather than introducing a title-specific transformation
system. The p400 author reads the current source events and declares reusable visible state changes
in state_variants[], with stable variant and transition IDs, parent entity identity, creation-event
beat IDs, before/after state descriptions, and a drawable generation prompt. This applies to costume,
appearance, object condition, material, and structural changes that need recurring visual identity;
it does not create an asset for every transient pose. Consumers bind the existing parent plus variant
using state_variant_refs[] and name their own source event beat IDs. This permits later cuts and
scenes to reuse an earlier state anchor without tying all reuse to the creation beat.

p420 projects each declaration to an ordinary reference_variants[] entry, and p500 emits a derived
asset request from its parent reference. The generated output path is the variant's reference_images
entry. Existing generation grouping orders a derived request after its parent reference.

A transition cut can optionally author result_frame with after-state variant bindings and a
same-scene composition brief. Projection creates a nested video_generation.result_frame image
request. The shared p600 materializer exposes it as an auxiliary image-only target under the same cut,
not as extra footage, narration, or duration. Its image request depends on the actual primary scene
image as a layout anchor plus the after-state p500 assets; snapshot binding defers the primary-image
hash until that producer finishes and binds external asset bytes immediately. This scene-specific
image, never the neutral p500 asset sheet, becomes the provider last_frame. p800 binds and hashes
its current bytes, and checks that the provider mode supports first/last-frame input. Missing or
unsupported required frames fail before video execution.

No title-specific or keyword-triggered runtime inference is used. Author instructions and schema
guide the production author to read source events and declare visible state changes where continuity
needs a reusable p500 anchor. Existing manifests without state-transition declarations keep current
behavior.

## Tasks

1. Trace p420 asset-bible authoring, p500 plan/request generation, and shared scene/video request
   materialization for frontend and Codex conversational workflows.
2. Define the additive authored variant/result-frame fields and structural validation semantics in
   canonical docs/templates and authoring instructions.
3. Project required variants into p500 asset requests and publish their generated paths back to the
   manifest before dependent scene requests materialize.
4. Bind selected variant references into scene image requests and bind each required result selector's
   generated scene image into supported video last-frame requests, with fail-closed errors.
5. Add focused regression tests for the shared runtime and entrypoints.
6. Run targeted checks and inspect the final diff for title-specific logic and generated-output edits.
