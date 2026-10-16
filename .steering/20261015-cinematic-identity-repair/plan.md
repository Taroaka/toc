# Generic identity handoff and p400 repair

## Authorized request
Fix remaining identity adapter and shot repair faults for arbitrary stories; then resume the existing failed run via the supported resume API to its saved p680 target. Preserve validated upstream artifacts, append-only state, and unrelated workspace edits.

## Design
- Treat registered research character IDs as identity; gather actual scene references from canonical/lifecycle keys for both new and historical stories. Do not expose nameless phantom protagonists or infer a first character from prose. Use only explicit primary-role declarations for the legacy protagonist alias and avoid duplicate identity entries.
- Attach exact source-entity bindings to base character resources so short names/aliases cannot force an unrelated identity choice. Validate reuse by explicit source identity, not substring names.
- Diagnose shot entity/actor/target/event IDs against the cut's registered references, with precise paths and reference candidates. When the cut list itself needs correction, include its allowed replacement candidates in the same bounded patch. Revalidate cut and shot bindings together.
- Route other shot-plan structural findings to the affected shot plan only instead of treating them as unscoped terminal errors. Never rewrite unrelated cuts or infer mappings between distinct people.
- Reuse valid existing authoring receipts and execute one resume job under the existing run lease. Preserve research/story/visual-value byte hashes when valid.

## Verification
Regression tests for arbitrary research IDs, unnamed/multiple/no protagonist cases, legacy nested scenes, aliases with exact source binding, cut+shot ID repair, unknown shot IDs, and scoped structural diagnostics. Run affected frontend/story/p400 suites and review the focused diff locally (repository policy prohibits subagents for this Astra session). Observe resumed worker through actual p680 output validation.
