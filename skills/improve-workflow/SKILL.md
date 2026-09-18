---
name: improve-workflow
description: "Use when: the user asks for a repository implementation plan, a development/fix loop, or a coordinated verification pass."
---

# Improve Workflow

Use the requested outcome and the repository's existing workflow to decide what work remains. A plan-only request ends with a usable plan; an implementation request continues through the change and relevant verification.

- Reuse clear requirements from the conversation. Ask only about unresolved choices that affect the result; do not require another confirmation of an already authorized action.
- For a non-trivial change, keep a compact plan in the repository's preferred location.
- Fix the cause, run affected checks, and continue until the requested behavior works or a concrete external blocker remains.
- Use focused repo commands. Broaden testing when dependencies or new failures justify it; avoid whole-repo compile/test commands for a small unrelated edit.
- Report the outcome, evidence, and remaining limitations.

For an explicitly requested TDD or code-review workflow, use the corresponding available skill if it adds useful guidance. Do not load every development skill by default.

## Requested multi-agent tmux work

Use `scripts/ai/multiagent.sh --engine claude|codex` only when that workflow is requested and current agent policy permits it. Preserve the user's chosen engine. If tmux or the helper is unavailable, report the missing dependency and continue independent work; do not install tooling or launch agents merely because this skill was loaded.
