# Requirements

## Goal

Generate the initial `story.md` with configurable GPT-6 Codex authors instead
of deterministic prose scaffolding. The default role routing is Story
Architect/Scene Author=`gpt-6-astra` and bounded key-level Repair
Author=`gpt-6-luna`. `gpt-6-sol` is reserved for exceptional intermediate
tasks and is not part of the default story-production route.

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
- Model provenance records the exact GPT-6 role model; unavailable models fail
  explicitly instead of silently falling back to GPT-5.x.

## Non-goals

- Do not put camera, lens, provider prompt, or fixed cut count in `story.md`.
- Do not add title-specific production branches.
- Do not silently fall back to deterministic generic story prose.
