# Drawable image prompt runtime task list

- [x] Audit current cut-to-send flow, artifacts, gates, app-server provenance, and parallel execution.
- [x] Define requirements and design for conditional drawable extraction and immutable execution snapshots.
- [x] Add failing unit/contract tests for conditional fragments, no filler, and internal-field exclusion.
- [x] Implement the shared `DrawablePromptIR` compiler and v2 payload.
- [x] Route frontend scaffold and manifest materializer through the shared compiler.
- [x] Remove production dependence on legacy `image_generation.prompt` while retaining read compatibility.
- [x] Add versioned request snapshot materialization and strict loading.
- [x] Fix named-fence prompt updates and snapshot regeneration/stale detection.
- [x] Add send-time prompt/reference hashing and exact app-server provenance.
- [x] Reuse outputs only when prompt/reference/output provenance matches; make resume partial.
- [x] Add per-run lease and cross-process image generation semaphore, including serial fallback lock.
- [x] Make prompt gates conditional and reject zero-entry/implicit-pass semantic review.
- [ ] Add per-scene image prompt semantic shards.
- [x] Align data contract, prompting docs, and workflow templates with the runtime contract.
- [ ] Run focused tests, broader verification, security/diff review, and frontless backend create.
