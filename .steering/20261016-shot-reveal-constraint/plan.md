# Typed shot identity reveals and narrative constraints

## Requirements

A typed shot's reveal list names existing participants moving into view. A prose
constraint mentioning a participant can restrict a cause, action, or outcome
without forbidding that participant. Retain all such constraints in provider
instructions. Continue rejecting an entity listed directly in both allowed and
forbidden lists. Preserve the existing legacy new-story-element conflict checks.

## Design

For each `shot_direction_v1` identity reveal bound to a typed camera/entry event,
registered participant absent from the initial view, present in the end view,
and ID/name/path references of the actual last-frame image, compare direct
forbidden labels rather than searching for the identity as a substring of
every narrative constraint. A schema tag alone does not enable this behavior.
Do not infer natural-language prohibitions, discard
constraints, alter source content, or add title-specific logic. Existing source,
participant, reveal-event, and end-state validation remains in place.

## Tasks

- [x] Reproduce causal-constraint false conflict and protect real conflicts.
- [x] Implement typed identity comparison and run compiler regressions.
- [x] Review the incremental change.
- [x] Verify all saved materialization targets; reload idle stack and resume once.

## Verification

Both provider cases reproduced the false conflict before implementation. Related
video compiler, shot, runtime, projection-registry, and frontend materialization
tests pass: 152 tests and 189 subtests. Legacy conflict tests remain unchanged.
All 28 current saved manifest video-request targets compile without errors in
read-only verification. No video generation API was called.
Review caught the initial schema-tag-only switch. It was replaced with actual
typed event, participant, visibility, and last-frame reference evidence. Negative
tests protect tag-only, unknown participant, already-visible participant, missing
event, and unused end-frame metadata for both providers.
Final read-only review found no remaining actionable issue. `git diff --check`
and pointer-doc validation pass. Only this chat was active and no production
workers were running before using the normal stack restart helper.
The helper confirmed DB, HTTP, and Codex transport health. Resume job
`eed1facc909f48c48cc7f787c2c37d89` uses the existing `p500_subprocess` route,
preserving all verified authoring. Production completion remains under monitoring.
Baseline: `/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-shot-reveal-nxqsl4s7`.
