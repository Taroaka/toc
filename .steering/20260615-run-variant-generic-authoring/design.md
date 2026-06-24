# Design: Run Variant Generic Authoring

- `_story_profile()` defaults to a generic topic profile and receives a `variant_seed` from `run_dir.name`.
- The variant seed is derived with SHA-256 from topic, source, and run identity, then mapped to a small creative variant bank.
- Variant values are used in creative fields, not just metadata: scene titles, locations, motifs, artifact name, artifact role, summary, and event wording.
- `story.md`, `script.md`, `video_manifest.md`, and `state.txt` expose the selected `run_variant` for frontend/debug comparison.
- The old Cinderella scaffold is gated by `TOC_ENABLE_LEGACY_CINDERELLA_PROFILE=1` so existing fixture assertions can be isolated without affecting production create flow.
