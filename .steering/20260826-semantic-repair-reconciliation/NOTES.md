# NOTES

## Chronological Notes

- 2026-08-26 Current production failure is before provider submission; generated asset count is zero.
- 2026-08-26 Concrete stale examples include `scene10_cut04` action mismatch, `scene60_cut01..06` action/evidence mismatch, and scene40 transformed-appearance references remaining after repair removed that variant.
- 2026-08-26 Correct fix is deterministic projection before P400 review, not adding invalid variants or weakening reviewers.
- 2026-08-26 Existing root `PLAN.md` is unrelated and must not be overwritten.
- 2026-08-26 Existing `test_non_image_semantic_repair_reconciles_dependencies_in_safe_order` encoded the old order with P400 review before authoring projection; expectation updated to require authoring projection first.
- 2026-08-26 Character variant replacement must be scene-local. The same transformed variant can be stale in a pre-transformation scene and required in later scenes.
- 2026-08-26 Asset variant ancestry is read from `asset_plan.assets[].reuse_contract.derived_from_asset_id`; unresolved missing references fail closed.
