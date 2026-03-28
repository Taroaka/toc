# Requirements: image prompt required blocks

## Background

- Prompt story review currently checks narrative consistency, but it does not enforce the structured prompt skeleton expected by the runtime.
- Prompts that omit core sections like continuity or avoid lists are more likely to drift even if they mention the right story entities.

## Goals

- Add a runtime review criterion that marks prompts invalid when any required structured block is missing.
- Required blocks:
  - `[全体 / 不変条件]`
  - `[登場人物]`
  - `[小道具 / 舞台装置]`
  - `[シーン]`
  - `[連続性]`
  - `[禁止]`
- Write explicit agent reason key/message into the prompt collection for missing blocks.
- Add targeted tests for both detection and pass cases.

## Non-Goals

- Editing docs.
- Auto-rewriting prompts to add missing sections.

## Success Criteria

- Review emits explicit findings when any required block is absent.
- Prompt collection updates `agent_review_ok` / reason fields accordingly.
- Tests cover missing-block detection and a fully structured prompt that passes the block check.
