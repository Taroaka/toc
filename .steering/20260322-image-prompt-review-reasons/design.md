# Design: image prompt review reasons

## Data model

- Extend prompt collection entries with:
  - `agent_review_reason_keys`
  - `agent_review_reason_messages`
- Keep these fields agent-only for now. Human review remains a boolean override.

## Export

- Parse existing prompt collection entries and preserve:
  - `agent_review_ok`
  - `human_review_ok`
  - `agent_review_reason_keys`
  - `agent_review_reason_messages`
- New exports default to empty reason lists.

## Review loop

- Parse stored reason fields from the prompt collection.
- After review:
  - if findings exist, set `agent_review_ok = false` and write reason keys/messages from findings
  - if findings do not exist, set `agent_review_ok = true` and clear both reason lists
- Human review updates should only flip `human_review_ok` and should not erase agent reason state.

## Generate gate

- Keep generate-time review invocation unchanged in shape, but rely on the stricter unresolved rule:
  - block only when findings still exist and both booleans are false

## Tests

- Extend story review tests to cover:
  - prompt collection parsing/rendering with reason fields
  - re-review clearing stale reasons after prompt fixes
  - `--fail-on-findings` allowing human-approved entries through
