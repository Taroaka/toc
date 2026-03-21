# Design

## Principle
- The right workflow is not "write a good one-liner and send it".
- The right workflow is: structure the prompt, choose the anchor, fix the reference, review the collection, then generate.

## Prompt shape
- Keep prompts in a stable block order.
- Make camera language describe the frame's intent instead of only listing a lens number.
- Prefer combinations such as:
  - `wide` + what is in the foreground / mid-ground / background
  - `mid-range` + which subject should dominate
  - `close` + what detail must be readable

## Synchronization
- Update the reviewable prompt collection first.
- If the run manifest is a source of truth for `image_generation.prompt`, sync the same wording there.
- Preserve story meaning and do not revert unrelated edits.
