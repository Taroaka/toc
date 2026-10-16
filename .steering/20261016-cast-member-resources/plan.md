# Bind declared cast members into visual resource projection

## Evidence and requirement
Image preparation rejected a declared ensemble member because the direction loader
returned resources without the validated cast-design member rows. The immutable
manifest and cast design both declare those IDs. Preserve source files, parent
references, and unknown-member rejection; do not add run-specific identifiers.

## Design
After normal direction-byte binding validation, validate the optional cast design
against its resource/source bindings. Enrich a deep-copied runtime character
registry with its canonical subject contract and named member appearance records.
Keep existing per-member reference fields when the same member is present. No
canonical file or saved image request is rewritten by the loader.

## Tasks
- Reproduce ensemble lookup failure and verify no mutation of source bytes/data.
- Preserve stale binding, invalid cast, and unknown-member rejection with tests.
- Review the bounded change; replay the failed scene through the existing route
  after the current unrelated scenes finish, without resetting snapshots/budgets.

## Verification
24 targeted tests passed. Reviewer found internal cast binding also needed validation; canonical binding comparison and regression added, re-review clean. Fresh read-only projection of all4 saved scene50 cut plans now passes. Current source files and images were not changed. Apply through a fresh existing CLI process after the current image-preparation lease is released; do not restart active production.
