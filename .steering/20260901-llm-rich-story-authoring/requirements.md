# Requirements

## Goal

Generate the initial `story.md` with a configurable Codex Story Author
(`gpt-5.6-sol` by default) instead of deterministic prose scaffolding.

## Success criteria

- Story Architect assigns every research event to exactly one semantic scene.
- Scene Author writes start state, complete event sequence, turning event, end
  state, reveal/preservation contract, and adjacent-scene handoff.
- Characters, relationships, places, world rules, symbols, facts, conflicts,
  passages, and confidence remain available without text truncation.
- Scene count follows semantic events, not target duration alone.
- Deterministic validation rejects unknown IDs, event gaps/duplicates/order
  drift, missing lifecycle fields, reveal rollback, and handoff mismatch.
- Repair sends only failing scene/key diagnostics back to the same author.
- `preapproved` skips reviewers, not Story Architect or Scene Author.
- At least two unrelated story fixtures use the same production path.

## Non-goals

- Do not put camera, lens, provider prompt, or fixed cut count in `story.md`.
- Do not add title-specific production branches.
- Do not silently fall back to deterministic generic story prose.
