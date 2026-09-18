---
name: coding-standards
description: Apply TypeScript/JavaScript/React/Node.js conventions when reviewing code style or resolving a concrete maintainability problem.
---

# Coding Standards

Use nearby code, formatter, linter, and type-checker settings as the source of local conventions. Do not introduce a second naming scheme, directory layout, API response format, or dependency merely to match this skill.

For the code under review, focus on decisions that affect maintenance:

- Represent meaningful domain states with types; validate untrusted values at their boundary instead of asserting a type.
- Keep shared state and React state updates explicit. Local mutation is acceptable when ownership is clear and existing conventions allow it.
- Handle errors where recovery or useful context is possible. Preserve the original cause and avoid logging secrets.
- Run independent asynchronous work together only when ordering and shared state allow it.
- Extract duplication when it represents one shared rule. Keep coincidentally similar behavior separate.
- Explain non-obvious constraints and tradeoffs in comments; use names and structure for the rest.

Limit cleanup to the requested files or changes needed for the task. Use the existing formatter, linter, types, and relevant behavior checks; arbitrary function-length limits or project-wide cleanup are not completion criteria.
