# 2026-10-15 11:50: recover completed cast response

All four scenes have accepted p400 receipts. Cast authoring completed a response whose inner JSON has one adjacent closing-pair transposition: ]} instead of }]. Swapping those exact two characters at the parser offset makes the full document valid. Primitive tokens, strings, keys, values, commas and container counts are unchanged. The existing decoder only handles one redundant final brace; the syntax-only LLM path deliberately rejects unbalanced container input.

Add a second bounded deterministic rule only when the prefix stack proves the two closers are reversed, the rest parses strictly as one complete object, and duplicate keys/non-JSON constants remain rejected. No quote/value repair, truncation completion, arbitrary bracket insertion or recursive multi-edit recovery.

To avoid another long cast generation, reuse logged completed turns only when prompt, output schema, model, run directory, full transcript, final response text and payload hashes all agree with the provenance. Then run normal decoding and cast validators again. Keep scene receipts, source hashes and correction budgets unchanged. Do not edit the saved model response to hide the typo.

## Verification

New closing-pair regressions failed on the original decoder and now pass. The rule proves the prefix container stack and only swaps one adjacent closing pair if the entire result passes strict parsing, including duplicate-key and non-JSON-constant rejection. New response-replay tests cover changed prompt/model/schema, tampered transcript/payload hash, and different run directory. Related decoder/runtime/cache/repair/p400/cast/resume suites: 130 passed, 1 known baseline test deselected. Focused latest runtime/cache checks: 37 passed. Pointer docs and whitespace checks passed.

Read-only recovery of the actual cast turn verifies all recorded request/response hashes; original thread 01a13d6e-9152-7c73-80eb-f437a74ff33d, correction offset 13455, rule one_transposed_closing_pair. The recovered cast has 4 character entries (including the six-member statue ensemble) and validate_cast_design returns no issues against current source/resource/reference bindings. No original model-response bytes, canonical source artifacts or repair counters were edited.

## p450 completed; p500 boundary checks

The resumed worker replayed the exact recorded cast turn, applied the deterministic syntax receipt, passed cast validation, and wrote the p450 artifacts. P500 then reported manifest.node_types and manifest.cinematic_direction. Read-only diagnostics show two boundary inconsistencies: provider limits are checked on parent audio containers (while ignoring their executed children), and normal prompt recompilation adds the nonexecuting debug_prompt_source trace that a full-dict shot comparison treats as artistic drift.

Fixes validate parent logical interval plus actual child provider/model/duration capabilities, and compare all authoritative image plan/payload fields while excluding only that known nonexecuting trace. Result-frame image packs receive the same treatment. Executable prompt/model/reference edits remain rejected. New regression tests reproduce both issues and pass after the change. No canonical manifest bytes were edited for the read-only checks; normal resume will revalidate/rematerialize under its retained lease.

## Boundary verification

New provider-child and image-trace regressions reproduce the boundary failures. The fixed current manifest now passes check_manifest_single with no failed checks. Related shot/projection/stage-evaluator/video-preparation/resume/request-snapshot suites: 130 passed. Runtime/cache/decoder/cast/repair/resume suite also passed 130 tests with 1 known unrelated baseline test deselected. Pointer and whitespace checks pass. Review confirmed executed child models/durations remain checked and changing provider prompt bytes still fails cinematic projection validation. p450 is complete; p500 has not generated images yet.

## Frontend resume after boundary fixes

2026-10-15 17:41 JST: restart helper completed backend/frontend/Codex health checks. Computer Use clicked the existing run resume once. Job e97b1f9b04514ee9a039927a0210c3d4 is recorded running with resumeMode=p500_subprocess, fromProcess=p450, stopTarget=p680, and message p500再開計画を検証中. Frontend shows p450からp680へ再開中; screenshot frontend-resumed-p500.png. The backend is using CPU during synchronous readiness validation; a 20-second read-only status request timed out, so no later stage or image-generation progress is claimed. No second resume, lock mutation, source rewrite, or budget reset. Continue monitoring this job rather than restarting it while validation is active.
