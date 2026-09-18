---
name: verification-loop
description: Verify an implementation or PR using the repository checks relevant to its changed behavior.
---

# Verification Loop

Determine the changed behavior and the checks required by the repository or request. Use existing verification scripts and project commands. Select applicable checks instead of imposing a fixed build/types/lint/test/security sequence on every change.

- Run the narrowest meaningful check first. Add integration or broader regression checks for affected boundaries or unresolved risk.
- Use a build/type check when compiled code or public types changed, lint/format checks for touched code, and security checks for an implicated trust boundary.
- Fix failures caused by the requested change and rerun affected checks. Record unrelated existing failures separately without expanding scope.
- Inspect the final diff for unintended edits and preservation of unrelated working-tree changes.

Finish when the requested result and required checks are complete. Do not rerun unchanged checks on a timer. Report what was verified, actual results, checks that could not run, and any material remaining risk; do not imply unexecuted checks passed.
