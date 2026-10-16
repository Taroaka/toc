# Current shot view projection

## Requirements

A relative continuity phrase in a view description must not discard all explicit
current subject states, framing, and composition authored in that same view.
Do not invent missing prose, copy future/end state into a start image, or pass
internal production references into provider text. Missing current descriptions
must still fail when any visible subject lacks its own drawable current state.

## Design

Keep the scalar metadata filter unchanged. If it rejects a shot's description,
assemble the current moment from that view's explicit subject states and visible
parts, framing, and composition only when every visible subject is drawable.
Preserve the canonical authored plan and audio. Use this projected current moment
consistently in still and motion handoff. Do not change author contract/cache IDs.

## Tasks

- [x] Reproduce rejected mixed continuity/current-view input and missing-state cases.
- [x] Implement projection and run image/shot/repair regressions.
- [x] Review, verify saved scene, and request one resume without budget or candidate edits.

## Verification

The same-view regression failed before implementation; both missing-state cases
remain rejected. The relevant image/shot/repair suites pass 129 tests and 12
subtests; the one previously confirmed unrelated baseline failure is excluded.
Two legacy diagnostic assertions were aligned with the earlier ordinary-end-view
contract; premature parent variant tests remain present and passing.

Saved scene 5 passes both ordinary direction and actual image projection checks.
The assembled five-scene direction also passes validation with its research and
reconstructed resources. No saved scene or repair budget was edited.
Isolated read-only review found no actionable issue. Pointer-doc validation and
`git diff --check` pass. Other chats were idle and the run lease was unheld before
the resume request. Acceptance is not image/narration completion.
Baseline: `/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-current-view-wmr3jfzj`.
