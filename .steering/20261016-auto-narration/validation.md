# Validation

- Related Python suite: 81 passed, 9 subtests passed (automatic narration, all-stage resume, create/resume duration, frontend runner boundary, p500 failure state, revision contracts).
- Frontend: 20 tests passed (resume request, create polling, run-status projection).
- Frontend production build passed.
- Pointer docs validation passed.
- Isolated code review: four findings fixed and re-reviewed with no blocking issues: flat script silence; semantic hash in candidate reuse; draft-journal target escalation; repeated TTS failure attribution.

Additional existing tests failed outside this patch's modified paths:
- test_narration_frontend_workflow.py::test_draft_preview_stays_current_when_same_text_is_locked_during_generation: undefined test variable explicit_offset at line 569.
- test_media_resume.py::test_bulk_video_limit_is_enforced_before_provider_work: missing-manifest fixture returns 409 before expected 400 bulk-video-limit check.

Production validation is recorded under the requested run's logs/media_generation and logs/media_operations. Image bytes are compared before and after narration. No publishing or video generation is included.

Production completed: 21/21 spoken cuts, 11 authored silent cuts retained; total raw narration 149.342037 seconds. Every spoken file decoded successfully. All 74 image files matched pre-run SHA-256 hashes. Full spoken-only preview uses the shared narration loudness processor; provider originals preserved. Listening was not performed.

Local stack reloaded successfully. Frontend http://127.0.0.1:5173 ; backend http://127.0.0.1:8000/api/image-gen/runs ; logs `.codex/run/toc-server/`. Live OpenAPI confirms normal creation defaults to p730 and resume accepts p730.
