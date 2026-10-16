# 2026-10-15 10:20 heartbeat: child image diagnostics

The resumed job stopped at 09:57. The previous identity error did not recur. Reproduction of the saved candidate and bounded first-frame patch identifies the sixth projected child still: character_state_gate.pose concatenates BOTH character and object subject views. One object's view contains an internal previous-cut reference; drawable normalization discards the entire combined pose, making valid visible characters appear to lack state. The child compiler exception also lacks cut/shot/view context, so normal scoped repair cannot handle it.

Fix the generic projection to keep character pose independent of object prose, retain compiler checks, attach cut/shot/view diagnostics to child compiler failures, and route evidenced invalid view text to a bounded author patch. Preserve current candidate, upstream artifacts, and repair budgets. Regression tests must reproduce object-to-character contamination and repair the precise object view without changing another shot/cut.

## Verification

- Added two regression tests; both failed before the change and passed afterward.
- Shot, layered repair, p400/p420, authoring resume, frontend repair and image-compiler tests: 160 passed, 1 known pre-existing test deselected, 12 subtests passed.
- Replayed the actual saved candidate plus its durable bounded patch in memory: current diagnostic is exactly /cuts/2/shot_plan/shots/0/initial_view/subjects/2/view (object state), rather than an unscoped character-state exception. No run artifacts were rewritten for this reproduction.
- Pointer docs and whitespace checks passed. Review was local, with unrelated changes preserved.

## Resume

2026-10-15 10:23 JST: bundled server restart completed HTTP and Codex no-op checks. Computer Use selected the same run and clicked resume once. New job ec7272df76a6430787e7acdd7b23afa2 is running in authoring_subprocess mode; canonical runtime.stage=cinematic_authoring and last_error is empty. The research/story/visual_value hashes remain unchanged and all three stages were reused. Frontend proof: frontend-resumed-1023.png. p680 is not complete; the 30-minute heartbeat remains active.
