---
name: improve-workflow
description: |
  Run a structured development loop for this repo: restate scope, plan, make the smallest safe change, verify, and summarize.
  Use when: the user asks for a coding workflow, implementation plan, TDD loop, verification pass, code review cleanup, or help running the repo's multi-agent tmux workflow.
---

# Improve Workflow

This skill is shared across Claude Code and Codex. Prefer the current agent's planning and verification primitives when they exist.

## Default loop (plan → implement → verify)

1) Restate requirements and constraints (what is in/out)
2) If the change is non-trivial, create/update a plan using the current agent's planning primitive
3) Implement smallest safe change set (avoid unrelated refactors)
4) Validate (prefer fast, local checks before full test suite)
5) Summarize what changed + how to run/verify

## Common sub-modes

- `plan`: Restate requirements + risks + step plan; WAIT if user wants approval gates
- `tdd`: Write/adjust tests first (if repo has tests), then implement, then re-run
- `verify`: Run the most relevant checks; if none exist, run minimal sanity checks
- `build-fix`: Build/test first, then fix errors iteratively (smallest diff each loop)
- `code-review`: Review changed areas for correctness, security, perf, readability; propose follow-ups
- `refactor-clean`: Do mechanical cleanup only when it reduces risk or enables the requested change
- `update-docs`: Update the smallest canonical doc files (avoid random new docs)

## Validation quick picks (choose what exists)

- Python: `python -m compileall .` then (if present) `pytest`
- Node: `npm test` / `pnpm test` / `yarn test`
- Go: `go test ./...`

Prefer repo-local scripts (`scripts/*`) if they exist.

## Multi-agent tmux (this repo)

If the repo contains `scripts/ai/multiagent.sh`, use it to launch:

- Claude Code: `scripts/ai/multiagent.sh --engine claude`
- Codex CLI: `scripts/ai/multiagent.sh --engine codex`

If `tmux` is missing on macOS: `brew install tmux`.
