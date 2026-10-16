# Full-run narration in automatic production

User outcome: normal frontend production must author a complete narrative before TTS. Rebuild the requested existing run from a full draft, preserving all 74 images and authored silence. Earlier p730 integration skipped p710 authorship; do not consider TTS file creation sufficient.

Design:
- Reuse the existing full-run prompt projection, audio-story/span validator, scratch merge and narration revision/candidate lane.
- Two ordered read-only structured author turns via the existing Astra runtime: (1) narrative plan + continuous draft, (2) allocate that fixed text across canonical cuts and write TTS delivery. Allocation cannot delete/repeat/change spoken content; only whitespace boundaries may change.
- Persist prompt/input hashes, author response, plan and allocation separately. Resume validated checkpoints without repeating successful author/provider work.
- Validate full inventory, protected text/silence, span order/coverage and whole-draft equality before publishing through script -> narration-only manifest sync. No image/video/reference edits.
- Insert this before automatic TTS; resumed TTS also requires current valid full-run authorship. Support explicit narration rewrite for already completed runs.
- Retain old audio candidates; new text/context invalidates their current status. Never claim listening or approval not performed.

Checks: tests first for true draft-before-allocation ordering, missing plan blocks TTS, projection/mismatch errors, locked/silent preservation, source drift/cache replay, image metadata stability, create/resume routing. Review code; run related checks. Then use the same automatic path on the requested run, decode/probe outputs, compare image hashes, expose readable full draft and audio preview. Duration follows source-grounded authorship; record plan vs measured duration without adding filler to pass a quota.
