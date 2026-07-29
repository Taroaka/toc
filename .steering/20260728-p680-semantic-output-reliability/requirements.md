# Requirements

## User goal

Frontend-created ToC runs must not stop before p680 because a completed semantic
review was returned as JSON instead of the legacy line-oriented report format.
The pipeline must also fail safely for missing or malformed reviewer output and
must not invoke a producer repair unless a substantive semantic verdict exists.

## Success criteria

- A complete JSON semantic verdict from an app-server `final_answer` is
  materialized as the canonical semantic report and validated normally.
- Commentary and analysis messages are never accepted as the terminal verdict.
- Legacy line-oriented verdicts remain supported.
- A completed turn with no valid verdict is classified as a reviewer output
  contract/transport failure, not as a semantic `changes_requested` verdict.
- Output-contract failures never invoke the producer repair path.
- The same behavior applies to monolithic, scene-detail shard, and image-prompt
  shard reviews through p680.
- A semantic repair that changes an upstream artifact must re-enter every
  affected deterministic and semantic gate before provider execution.
- A failure that can be completely localized to scene/cut image items blocks
  only those items; unaffected image items continue to provider execution and
  p680 exposes synthetic failed candidates for the blocked items.
- p650 and p680 completion are accepted only from fresh, request-bound,
  immutable asset/image provenance and a successful terminal verifier report.
- A frontend resume preserves the exact original create input. New runs record
  it in a hash-bound canonical artifact; legacy runs require an explicit source.
- `scene_storyboard` render units are a p800 execution overlay. Adding them at
  p680 must not stale the approved pre-p800 review projection, while changes to
  reviewed scene/cut design still do.
- An image-only resume is permitted only for a strictly validated scene-only
  repair plan. Any asset/reference repair is routed through canonical p500.
- A resumed `world_walk` preserves its source-reference asset contract.
- Resume locks, plan tokens, deletion, provider destinations, and subprocess
  cancellation fail closed against races, links, and partial mutation.
- Existing run content is not manually rewritten; recovery uses the canonical
  p500 resume path.

## Scope

- `server/image_gen_app.py` semantic review orchestration
- `scripts/toc-immersive-frontend-run.py` create-input and p680 finalization
- `scripts/resume-from-p500.py` canonical p500 continuation
- `toc/p500_resume.py`, `toc/runtime_locks.py`, and review projection helpers
- focused server tests and p680 regression coverage
- canonical resume verification for
  `output/シンデレラ_20260728_2211`

## Out of scope

- Manually repairing or replacing the Cinderella story/script/manifest
- Narration, video generation, and final render stages after p680
