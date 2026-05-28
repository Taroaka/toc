# Codex App-Server Consistency Requirements

## Goal

Frontend story creation must not lose asset or scene images because a nested
Codex app-server runtime is started from inside another app-server turn.

## Success Criteria

- Frontend create with `generate_images=true` runs the normal p680 helper in
  the backend process, not through the `toc-immersive-runner` app-server skill.
- Every server/CLI app-server caller uses `server/codex_app_server.py` runtime
  contract and diagnostics.
- Runtime setup or transport failures, including unwritable `CODEX_HOME`, are
  recorded as app-server transport/runtime blocks and are not treated as
  semantic QA findings.
- Semantic producer repair starts only after a real semantic report requests
  changes. Transport failure during repair records a blocked transport state
  and stops the loop.
- Root design docs explain why nested app-server create paths are prohibited.

## Non-Goals

- Do not redesign the semantic QA rubric.
- Do not change user-owned frontend styling or unrelated semantic pack edits.
- Do not allow silent fallback to a temporary Codex home in production server
  paths.

## Verification

- `python3 -m py_compile server/codex_app_server.py server/image_gen_app.py scripts/toc-immersive-frontend-run.py scripts/run-semantic-review.py scripts/generate-assets-from-manifest.py`
- `python -m unittest discover -s tests -p 'test_image_gen_server.py'`
- `python -m unittest discover -s tests -p 'test_toc_immersive_frontend_run.py'`
- `python scripts/validate-pointer-docs.py`
- Restart with `/Users/kantaro/.codex/skills/toc-server-restart/scripts/restart-toc-server.sh`.
- Create a new Cinderella run through the frontend create API and confirm
  asset/scene images exist and required semantic gates pass, or report the
  remaining runtime blocker with state/log evidence.
