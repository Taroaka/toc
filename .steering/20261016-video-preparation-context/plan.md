# Bounded video-preparation author input

## Problem and requirements

Video preparation currently embeds the entire materialized script and the target
manifest scene, including repeated compiled prompts, traces, child contracts and
candidate history. A real request reached 3,099,758 characters and exceeded the
app-server limit of 1,048,576 before any video was submitted.

Preserve full story source, the selected script scene, global narration and user
instructions, parent cut meaning/timing/audio, complete authored shot plans,
resource identities, neighboring boundaries and the hash-bound actual images.
Do not truncate creative text or alter canonical artifacts, snapshots or validation.

## Design and tasks

- Project a read-only scene view for authoring/review: retain parent contracts and
  authored shot plans; expose generated shot media paths/settings without copying
  compiled payloads or derived child contracts. Exclude inactive audio history.
- Supply the current script scene plus global script fields, rather than all other
  materialized scenes. Full story and neighboring boundary inputs remain available.
- Check assembled prompt size before an external call; never silently truncate.
- Add regression tests for large irrelevant execution data, source preservation,
  immutable inputs, review projection, and oversized authoring input.
- Run preparation/API tests, review the patch, and resume the same run using the
  sanctioned CLI so unrelated active server jobs need no restart.

## Verification and execution

- Three new regressions reproduced excess execution-data copies and missing local
  prompt-size checks before the fix, then passed with the projection.
- Preparation/API/cut-direction suite: 51 passed. After retaining the complete
  scene-level cinematic direction, the three focused checks passed again.
- Bounded review found no actionable issues. Canonical artifacts and snapshot
  hashes remain untouched by prompt projection.
- The same run resumed through `scripts/prepare-scene-video.py --execute`, using
  a process-local video price upper estimate of USD 0.126/second, USD 80 cumulative
  cap, and zero additional image submissions in the initial preparation pass.
  Execution log and generation plan live in the run under
  `logs/media_generation/video_monitor/`. Video provider submission has not yet
  been claimed; preparation must finish first. The 30-minute monitor is active.
- Final review-source projection supplies the complete revised scene once, with
  full story, global narration/user changes, resource and boundary context beside
  it. It does not repeat the old manifest and script scene. The final suite again
  passed all 51 tests and follow-up review found no actionable issues.
- Real-run scene/source portions measured 515,864–826,647 characters for authoring
  and 306,919–462,812 for review. Complete prompt size is checked at runtime before
  attachments/author invocation. Measurements are in
  `logs/media_generation/video_monitor/context_sizes.json`.
