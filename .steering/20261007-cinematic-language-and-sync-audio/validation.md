# Validation and delivery

Date: 2026-10-07 (Asia/Tokyo)

## Delivered

- Higgsfield public VIDEO API, scoped to Seedance 2.5 image-to-video and reference-to-video, in ToC's video workspace.
- Input mode, first/last or ordered references, duration, resolution, and native audio settings bound through compiled payload and immutable request.
- Durable request identity, resume after accepted submission, refusal to duplicate an indeterminate submission, credential/URL boundaries, and atomic verified candidate publication.
- Film-wide p410 direction, optional user filming preferences, scene/cut inheritance and clear semantics, source-aware caching, effective shot display, and p400 rebuild freshness checks.
- Lighting/focus/performance/physics projection into appropriate image/video requests. Exact source-bound optional character dialogue; normal narration remains separate.
- p860 native source audio selection, gain/fade, full-timeline mixing, and optional explicit narration ducking during dialogue. Native mixed tracks are not represented as separated stems.

## Automated evidence

- Pre-change baseline: 170 passed, 202 subtests passed across p400/image/video/sound/provider checks.
- Higgsfield public adapter: 12 focused tests passed, covering upload/credential separation, request identity, malformed inputs, uncertain submission, accepted-request resume and completed-download recovery.
- Higgsfield server integration: 6 tests passed, including request materialization, first/end versus reference mode, native audio, actual local ffmpeg verification, candidate publication and resume without another POST (external transport mocked).
- Combined affected suite: 221 passed, 189 subtests passed. Additional scoped checks after the last changes cover execution repair, source preferences and rebuild freshness.
- p400 rebuild/preferences: 20 passed.
- Related server create/registry/Higgsfield subset: 46 passed, 68 subtests passed.
- Sound mix: 5 passed after the final dialogue fix. Real ffmpeg tests verify source-relative timing, one/two dialogue sidechains, narration recovery and full output duration.
- Frontend focused tests: 12 passed. TypeScript/Vite build passed; existing bundle-size warning remains.
- Final delta suite after quote/speaker binding and dialogue-mix fixes: 20 passed. Quote tests reject descriptive-only text and mismatched speakers and accept exact `beat.dialogue[].text`.
- Python syntax checks and pointer-doc validation passed. Task-scoped whitespace/diff checks passed.

## Known pre-existing failure

`tests/test_downstream_layered_repair.py::test_semantic_cut_rewrite_keeps_healthy_cut_and_uses_original_validator`
expects a lighting phrase containing an alternative to trigger the old semantic image gate. Current repository policy/implementation no longer uses that heuristic, so the test's fake repair runner receives a normal author prompt and fails JSON parsing.

Reproduced the same failure using pre-change copies of the image compiler, p400 author, and p400 projection loaded in an isolated Python process. No working-tree files were reverted. Evidence: `/private/tmp/toc-baseline-known-failure.log`; current scoped suite: 65 passed and this one failure in `/private/tmp/toc-cinematic-repair-tests.log`.

## Runtime and limits

- Backend and frontend were restarted and their health checks passed. Codex app-server initialize/thread/no-op transport check also passed.
- Live local OpenAPI confirms Higgsfield video tool, new-run cinematic preferences, and native source-audio API are loaded.
- Frontend: http://127.0.0.1:5173/image_gen/
- Backend: http://127.0.0.1:8000/api/image-gen/runs
- Logs: `.codex/run/toc-server/`.
- The first restart helper stopped at Docker daemon availability. Existing DB listeners were present; rerunning the helper with DB startup skipped restored the local stack. DB contents were not changed.
- HF_API_KEY presence and format checked without exposing its value.
- The user explicitly declined paid generation. No actual Higgsfield generation/upload was performed. Real account/model access, final provider acceptance, and aesthetic quality are unverified.
- A prepared 4s/480p synthetic smoke request remains in `/private/tmp/toc-higgsfield-smoke/request.json` but was not executed.
- Existing production media and accepted narrator audio were not regenerated or migrated.
- Existing-run filming changes use the explicit p400 candidate/diff/apply workflow. The effective-direction display itself is read-only.
