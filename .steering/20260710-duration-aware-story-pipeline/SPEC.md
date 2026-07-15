# Duration-aware story generation with semantic pre-cut gates

## Goal

Make frontend-created ToC stories honor a user-selected 5–20 minute target throughout planning and media-duration validation, while requiring auditable research and story semantic reviews before cut generation.

## Scope summary

- `target_duration_seconds`: 300–1200, default 300, with 5/10/15/20 minute presets.
- Target-derived minimum scene, cut, and narration budgets.
- Research/story review gates that fail closed before cut materialization.
- One lower-bound-only duration contract shared by CLI and frontend backend.
- Effective duration includes measured narration audio and declared intentional silence; render and final-video layers are measured independently.

## Approved thresholds

- scenes: `ceil(target / 40)`
- cuts: `ceil(target / 12)`
- narration: `ceil(target * 0.70)` seconds
- duration pass: `actual >= target * 0.80`
- maximum: none

## Non-goals

- Classic adaptation modes or source/rights/reference verification.
- Canonical fidelity guarantees.
- One-click p680-to-p900 continuation.
- Paid image, video, or TTS generation during verification.

## Scorecard

Pass threshold: every checklist item must pass.

1. Input and propagation: UI/API accept the range and every new artifact carries the same target.
2. Planning: 300/600/900/1200 fixtures produce the approved minimum budgets.
3. Review integrity: research/story fail and transport-error fixtures cannot reach cut materialization.
4. Duration parity: CLI and frontend call the same audit contract.
5. Boundary behavior: 79.9% fails; 80% and 150% pass.
6. Timeline correctness: measured audio and intentional silence are counted once; measurement layers are never summed together.
7. Readiness: p740 and video endpoints require the shared pass result.
8. Regression: focused tests, frontend build, headless backend create, and pointer-doc validation pass.

Scoring paths:

```bash
python -m pytest -q tests/test_story_duration_contract.py tests/test_audio_duration_gate.py
python -m pytest -q tests/test_image_gen_server.py -k 'duration or research_review or story_review or narration_ready'
python -m pytest -q tests/test_toc_immersive_frontend_run.py -k 'duration or review'
cd server/web && npm run build
python scripts/toc-create-run-headless.py --title "シンデレラ" --source "シンデレラ" --target-duration-seconds 300 --no-images --assert-profile cut_contract_v2
python scripts/validate-pointer-docs.py
```

Stop condition: all approved done_when criteria pass, no unconditional research/story pass remains on the frontend create route, and no CLI/frontend duration disagreement remains.

## Feedback loop

Fast check after each duration-contract edit, expected under 30 seconds:

```bash
python -m pytest -q tests/test_story_duration_contract.py tests/test_audio_duration_gate.py
```

Fast check after review-stage edits, expected under 60 seconds:

```bash
python -m pytest -q tests/test_toc_immersive_frontend_run.py -k 'research_review or story_review or cut'
```

Run backend focused tests at phase boundaries, then frontend build and a fresh headless create before completion.

## Done when

The nine criteria in `requirements.md` are the user-approved completion contract.

