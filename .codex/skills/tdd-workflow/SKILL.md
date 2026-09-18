---
name: tdd-workflow
description: Use test-first development for requested behavior changes, regression fixes, or refactors whose behavior needs protection.
---

# Test-Driven Development

Translate the requested behavior into a failing regression or acceptance test at the smallest useful boundary. Use existing tests when they already expose the defect. Confirm the failure tests the intended behavior, implement the change, and rerun affected checks.

Choose verification by risk:

- Unit tests for isolated decisions and transformations.
- Integration tests for storage, service, serialization, or pipeline boundaries.
- End-to-end tests when correctness depends on the complete user interaction.

Use only the levels that can detect the relevant failure. Preserve repository-required coverage thresholds; do not invent a universal percentage, a timing budget, or a requirement to add all three test levels. Documentation, formatting, and reversible low-impact edits need appropriate validation rather than artificial tests.

[Test examples](references/test-examples.md) are available when a Jest/Vitest, API, Playwright, or mocked-service example helps. Adapt them to the actual project; they are not required dependencies or a test plan.

For ToC production code that maps research into story/script/manifest, also use [story invariants](references/toc-story-invariants.md). This check is scoped to that pipeline and does not add a separate production evaluator stage.

Complete the requested implementation and applicable checks. Repeat or broaden testing when a change, failure, or unresolved risk warrants it; passing checks alone are not a reason to keep rerunning them.
