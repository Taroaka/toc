# Tasks

Status: implemented and locally verified. Paid generation explicitly excluded by the user; known pre-existing test failure recorded in validation.md.

## 0. Decisions and baseline

- [x] Inspect current working tree, production contracts, p400 authoring/projection, provider limits, and sound/render boundaries.
- [x] Check current public model documentation and identify undocumented combinations.
- [x] Record requirements, design, and bounded tasks.
- [x] Resolve Q1 audio default and Q2 adapter ownership; update this plan with the answers.
- [x] Capture focused pre-change baselines and preserve unrelated working-tree edits.

## 1. Preserve cinematic execution detail

- [x] 1.1 Add optional lighting/focus/performance/physics contracts and structural validation.
- [x] 1.2 Extend author instructions with observable acting and material behavior, preserving source boundaries.
- [x] 1.3 Project initial appearance to stills and temporal behavior to video; prevent dynamic focus/action in still prompts.
- [x] 1.4 Add classified provider fragments and avoid silent truncation of explicit direction.
- [x] 1.5 Bind new fields to request digests, previews, rematerialization, and resume; preserve legacy behavior.
- [x] 1.6 Verify dim-light persistence, focus changes, reaction timing, contact/resistance, and no internal-ID leakage.

## 2. Film-wide direction

- [x] 2.1 Define film/scene/cut fields, override/clear semantics, and a deterministic effective-direction resolver.
- [x] 2.2 Author film language once inside p410 and cache it against current sources.
- [x] 2.3 Supply the fixed film language to every scene author and both media compilers.
- [x] 2.4 Add new-run filming preferences and effective cut-direction display; use existing explicit p400 candidate/diff/apply for saved-run changes.
- [x] 2.5 Cover resume/cache invalidation, source-first precedence, explicit shot exceptions, and old-run loading.

## 3. Synchronized sound and model support

- [x] 3.1 Implement per-cut/render-unit native-audio mode and sound-event contract; dialogue/voice fields according to Q1.
- [x] 3.2 Add generation-audio/reference-audio and model-operation capability checks.
- [x] 3.3 If Q2 includes it: implement Higgsfield upload/submit/persist/poll/download with uncertain-submission recovery.
- [x] 3.4 Connect provider/model/input/audio controls to exact request previews and immutable snapshots.
- [x] 3.5 Validate expected audio streams and preserve selected clip-audio provenance.
- [x] 3.6 Extend p860 with source-audio selection, gain, preview, and appropriate narration overlap handling.
- [x] 3.7 Freeze and mix native audio once per final target, preserving narrator offsets and clip synchronization.
- [x] 3.8 Test missing audio, stale candidates/bytes, unsupported settings, request resumption, and real ffmpeg timing/mixing.

## 4. Finish

- [x] Update canonical docs and templates for the implemented contracts and supported provider operations.
- [x] Run affected backend/frontend tests and frontend build when UI changes are complete.
- [x] Run `python scripts/validate-pointer-docs.py` and scoped diff/review checks.
- [x] Report implementation results separately from live provider access and aesthetic validation; prepare a concrete small-generation comparison if needed.
