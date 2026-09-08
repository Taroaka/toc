# Tasks

- [x] Add prompt regression coverage and observe failure.
- [x] Update shared prompts, story guide, and template.
- [x] Run focused tests and independent code review.

Validation: focused authoring/pipeline/runtime/integration tests: 21 passed. Scoped diff whitespace check passed. Broader downstream projection tests blocked by existing missing _append_grounding_checks import from toc.stage_evaluation.common (4 failures); no files in that failure path changed for this task. No live generation performed.

Independent code review: no critical/warning findings. Template YAML parses successfully.
