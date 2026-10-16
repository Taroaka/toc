# Verification

- 136 related Python tests passed, 3 subtests passed. One pre-existing unrelated bulk-video-limit test was excluded (fixture lacks manifest and receives 409 before expected 400).
- Frontend TypeScript/Vite production build passed; progress labels now describe draft authorship and allocation in Japanese.
- Pointer docs and changed-file whitespace validation passed.
- Code review findings addressed: protected target text, forced rewrite identity and checkpoint replay, rewrite-flag propagation, non-destructive delivery invalidation, all obsolete narration journals retired on a full rewrite, source drift, plan shape checks, exact span/text coverage, and publication cancellation barrier.
- First draft receives story/scene semantic obligations without the old per-cut timing; allocation receives the canonical cut inventory afterward.
- Plan serialization compatibility is lossless: one authored permission string may become a one-element list. Open-loop cut anchors are copied only from an unambiguous single-cut span declaration; ambiguous mappings require an explicit author anchor and remain blocked otherwise. The ordinary canonical validator rejects unordered or same-cut opening/payoff pairs.

Live stack reloaded: frontend http://127.0.0.1:5173 ; backend http://127.0.0.1:8000/api/image-gen/runs ; logs `.codex/run/toc-server/`.

Production author output: 1,119 characters in the original paragraph layout, 1,113 in canonical cut-boundary layout; only newline boundaries differ. 21 voiced cuts and 11 authored silent cuts. All 74 image hashes matched after publication. Original short-draft audio is retained. TTS and final decoded-output verification completed successfully. All 21 spoken cuts are current; 11 silent cuts remain silent. Raw narration totals 199.157551 seconds (3m19s). The full-run plan/span/cut contract passed, every audio file decoded, all 74 images and all 21 previous raw narration files retained matching SHA-256 hashes, and all non-narration manifest fields were unchanged. Listening was not performed. The original 600-second video target is not a claim that 600 seconds of narration was produced.


Final artifacts:
- `output/笠地蔵_20261015_0827/narration_full_draft.md`
- `output/笠地蔵_20261015_0827/assets/audio/preview/narration_full_run_preview.wav` (spoken-only preview, shared loudness processing; originals preserved)
- `output/笠地蔵_20261015_0827/logs/media_generation/415e8dd0d8f7443b892b383a51a452dc/verification.json`
- Live narration-items API: P730, terminal failure false, 32 cuts / 21 voiced candidates.
