# Validation

The regression reproduced authored actions being replaced by generic pressure
and exit gestures despite correct primary beat IDs. Another regression reproduced
two research IDs with identical event prose collapsing to one ID.

Source-first cut planning now uses authored beat order, research IDs, explicit
subdivision IDs, and their start/motion/end prose. The production integration
tests assert those identities and first-frame text in both script and manifest.
Custom beat functions also retain future-beat boundaries. Offscreen beats remain
in inventory without receiving a visible cut.

Checks: authored beat mapping, source-first scene projection, story author
integration, story authoring, B-roll pipeline, story author runtime. Pointer
validation, Python compilation and whitespace checks also pass.

Scope: current source_first_v2 production, with legacy artifact compatibility
retained. No image/video generation or existing output artifact edits were performed.
Correct source interpretation still belongs to the author; structural projection
cannot prove arbitrary prose semantically correct or guarantee image compliance.
Long scenes need meaningful authored cut_transitions; they no longer receive
synthetic filler gestures from the source-first planner. Provider duration checks
remain in effect and fail if authored cut capacity is insufficient.

During final validation another workspace task added cinematic_direction authoring
to the P450 entrypoint. Its fixture subsequently injected the new director test
double. The combined final suite, including the P450 entrypoint and cinematic
author tests, passed: 80 tests. That direction path uses its own authored cut IDs;
the new fallback planner applies to source-first scenes without a cinematic plan.
Research ledger and coverage matrix improvements apply to both routes. Production
author/provider generation has not been exercised by this test suite.
