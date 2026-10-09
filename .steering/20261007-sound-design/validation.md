# Validation

2026-10-07 (user timezone: Asia/Tokyo)

- Targeted backend suite: 80 tests + 38 subtests passed (sound contract/API/mixing, narration, freeze CLI, render, run index, slots, media resume, immersive scaffold, pipeline verification).
- After adding authentication, stale-during-render and journal-reuse regressions and the final CLI snapshot changes: 26 focused backend tests passed.
- Existing image-gen rendering/current-video-revision tests: 3 passed.
- Existing run-resume entrypoint routes both render and sound journals to their proper slots: 2 passed (sound resumes at p860).
- Frontend: all 6 Vitest files, 29 tests passed; `tsc -b && vite build` passed.
- `validate-pointer-docs.py`, `validate-slot-contract.py`, `git diff --check`, and shell syntax checks passed.
- Actual ffmpeg test: narration/BGM/SE mix, BGM looping, delayed SE frequency content and silence outside the cue, and full final-video duration verified.
- Isolated local browser smoke test with temporary data and a mocked provider: video approval, proposal display, BGM generation/adoption, SE generation/adoption, volume edit/save, unsaved draft preservation across another cue's generation, completion, state restoration after workspace switches, audio playback and release of the sound gate in the final workspace. The tiny fixture was not used to claim a full production-duration frontend render.
- Read-only review found a stale rendered-video path taking priority over the current candidate. Fixed to current candidate → canonical generation output → legacy render path. Added regression and reviewer confirmed it passes.
- Temporary browser and local smoke server were closed. Existing live ToC processes and real run media were not operated on.
- Paid ElevenLabs endpoints were not called. Payloads follow the linked official Music and Sound Effects specifications; account-specific availability/credits remain unverified.
- Build reports existing Node 18 vs Vite supported-version and bundle-size warnings; build succeeds. No dependency upgrades were made.
