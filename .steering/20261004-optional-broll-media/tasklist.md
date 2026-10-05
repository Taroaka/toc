# Tasks

- [x] Add failing B-roll omission, explicit audio, non-B-roll and malformed-input tests
- [x] Implement shared resolution and wire runtime boundaries
- [x] Document authoring and subtitle contract
- [x] Run focused regressions, applicable validation and inspect diff
- [x] Produce a patch with baseline and limits for later Mac application
- [x] Apply on an independent Mac checkout of origin/main (baseline unchanged)
- [x] Verify on Python 3.12.2: 145 focused tests + 13 subtests, 317 API/provenance tests + 60 subtests, 13 scaffold/pointer/state tests + 21 subtests
- [x] Verify real ffmpeg audio/subtitle combinations and mixed silent/spoken timing; compileall, TOML, pointer/slot validators, and diff whitespace checks pass

Existing CI limitation: main contains a Python 3.12 f-string in server/image_gen_app.py while CI uses Python 3.11. Baseline CI, lint, and security runs already fail; unrelated CI cleanup is outside this patch. No production/provider generation or existing run data was changed.
