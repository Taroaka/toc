# Requirements: image prompt review reasons

## Background

- `image_prompt_collection.md` already stores `agent_review_ok` and `human_review_ok`, but it does not preserve why an agent review failed.
- That makes iterative prompt fixing clumsy because the re-review loop cannot show which findings are still active versus resolved.

## Goals

- Extend prompt collection entries with explicit agent review reason keys and messages.
- Preserve existing reason state on export when the prompt collection is regenerated.
- When story review finds issues, write reason keys/messages into the prompt collection.
- When a later re-review resolves the issues, clear the stored reasons and set `agent_review_ok` back to true.
- Keep generation blocking narrow: only block when both `agent_review_ok` and `human_review_ok` are false.

## Non-Goals

- Adding new docs or changing prompt authoring guidance.
- Blocking generation when either agent or human review alone is false.

## Success Criteria

- `export-image-prompt-collection.py` preserves agent review reasons across re-export.
- `review-image-prompt-story-consistency.py` writes and clears reason keys/messages correctly through re-review.
- Targeted tests cover reason persistence, reason clearing after fixes, and the block/allow behavior.
