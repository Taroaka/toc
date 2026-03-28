# Design: image prompt required blocks

## Detection

- Add a small utility in `review-image-prompt-story-consistency.py` to normalize prompt heading lines.
- Recognize both canonical Japanese labels and the English/runtime aliases already accepted elsewhere in the repo.
- Treat headings as present when a line is effectively a standalone block heading, including bracketed variants like `[シーン]`.

## Review integration

- Run required-block detection at the start of `review_entries`.
- Emit one finding per missing block using:
  - code: `missing_required_prompt_block`
  - message: `prompt is missing required block '[...]'.`
- Existing reason-key/message persistence will carry these findings into the prompt collection and clear them on successful re-review.

## Tests

- Add a unit test for heading detection via review results.
- Update CLI/re-review fixtures that should avoid block-noise to use fully structured prompts.
