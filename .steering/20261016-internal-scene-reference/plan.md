# Consistent internal scene-reference handling

## Requirements and design

Image projection must reject internal scene/cut identifiers with numeric,
underscore, or hyphen spellings just as the video compiler does. Preserve
self-contained current-view sentences when separate sentences only refer to
production continuity. Keep the scalar filter strict; only shot view projection
may select complete drawable sentences from that same authored field. Never
salvage forward-cut/scene context, use future views, or invent missing content.
Pure metadata and missing subject states remain errors. Canonical direction and
author cache IDs remain unchanged; derived artifacts use ordinary reprojection.

## Tasks

- [x] Add image/video boundary and mixed-view regression tests.
- [x] Implement strict ID recognition and current-view sentence projection.
- [x] Run affected tests and verify canonical scene projection.
- [x] Complete review after forward-reference corrections.
- [x] Reload the idle stack and request one resume through the existing API.

## Verification

Initial regressions reproduced six internal-ID leaks and the mixed-field failure.
Review found forward-reference variants that could be salvaged; the guard now
runs before scalar normalization and at the image boundary, covers Japanese
particle/kana forms, English wording, and numbered/hyphenated labels, and never
reinjects raw subject text. Ten explicit forward-reference cases are tested.

All 28 shots projected from canonical direction pass the video first-frame state
boundary. Canonical artifacts and author schema fingerprints remain unchanged.
The affected image/video/shot/downstream suites pass 207 tests and 135 subtests;
one previously reproduced unrelated baseline failure is excluded.
The final read-only review found no remaining actionable issue. The idle stack
restart initially failed because Docker was stopped; Docker was started and its
daemon confirmed available before retrying the existing stack helper. No run
worker or other active chat was interrupted.
The helper confirmed DB readiness, backend/frontend HTTP health, and Codex
app-server initialization plus a no-op turn. API resume job
`a636a38eaff0453090e14ec7d92ff745` uses `authoring_subprocess` so stale derived
projections are regenerated from verified upstream artifacts before p500.
Baseline: `/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-internal-ref-gl5ufsqa`.
