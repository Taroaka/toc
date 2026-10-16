# Source-bound state variant entry

## Requirements

Preserve source-authored ellipses that begin with an already changed appearance.
Keep rejecting premature state use without evidence, future-beat references, and
malformed bindings. Recoverable findings must enter bounded p420 repair without
replacing scenes, source material, narration, valid media, or repair budgets.

## Design

An optional `source_entry` on a cut state-variant reference binds a source beat,
its unique cut-transition ID, and its exact first-frame brief. The author uses
this only when that source first frame establishes the selected variant already.
For a scene entry or explained ellipsis, it can justify same-beat initial use;
it cannot justify a future transition or an unbroken continuous state change.
Ordinary structural validation checks the reference and exact source text, while
the author retains responsibility for its meaning. No prose keyword inference.

Map known premature-use/source-entry findings to the affected cut's reference
list in the existing repair loop. This permits removal/rebinding and preserves
all other cut fields. Unknown findings still fail closed. Canonical direction
retains the evidence; downstream projection uses the validated selected variant.

## Tasks

- [x] Add failing tests for source-bound entry, invalid evidence, and scoped repair.
- [x] Implement and document the optional binding and diagnostic adapter.
- [x] Run affected tests and review the incremental change.
- [x] Start the same run once, preserving verified upstream checkpoints.
- [ ] Monitor through all narration output validation.

## Verification

- The initial focused run reproduced three failures and nine passing rejection cases.
- After implementation and scene-entry coverage, all 13 focused cases pass.
- The broader p400/downstream/state-variant/shot suites passed 137 cases. One existing
  `test_semantic_cut_rewrite_keeps_healthy_cut_and_uses_original_validator` failure
  also occurs with both production modules restored in-memory from the pre-change
  snapshot. It is outside this state-entry change and was not modified.
- `git diff --check` and `python scripts/validate-pointer-docs.py` pass.
- Isolated read-only review found no actionable correctness/security issue.
- The saved failure now maps to `/cuts/1/state_variant_refs`. Verified research,
  story, and visual-value checkpoint hashes match their files.
- Existing API accepted one `authoring_subprocess` resume with job
  `27f29f134d274d5b8710361248cc0c1a`. Authoring runs in a fresh subprocess, so no
  shared-server restart was needed. Acceptance is not production completion.
- Incremental baseline snapshot:
  `/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-state-variant-entry-8_ttnbe7`.
