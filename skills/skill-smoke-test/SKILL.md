---
name: skill-smoke-test
description: |
  Validate shared skill loading by reading a repo fixture and emitting a deterministic sentinel response.
  Use when: the user asks to verify shared skill loading, confirm the repo's skill routing works, smoke test skill activation, or check that a shared skill can read a local fixture.
---

# Skill Smoke Test

This skill should activate from intent, not only from the literal skill name.

## Contract

When this skill is invoked, do all of the following:

1. Read `skills/_shared/skill-smoke-test/token.txt`
2. Output `SKILL_SMOKE_TEST_ACTIVE`
3. Output the token exactly as `token=<value>`
4. End with `skill-smoke-test:ok`

## Rules

- Do not paraphrase the sentinel lines
- Do not omit the token
- Keep the response short unless the user explicitly asks for more detail
