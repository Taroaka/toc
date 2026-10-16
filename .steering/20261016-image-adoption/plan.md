# Explicit generated-image adoption

## Requirements

Allow an explicitly chosen, already-generated image from the same run to fill
another scene's missing output. Preserve the source and distinguish its original
provider provenance from the target's user-approved association. Never fabricate
a target generation receipt, retry a rejected generation, or loosen native
provenance checks. Keep current request, reference, decode, path and run-lock
checks. The latest user permits this non-overlapping work to proceed while the
unrelated publishing chat continues.

## Design

Provide a local adoption command guarded by the existing create/resume lock and
pinned run directory. Require current target revision/digest, source hash, and
explicit authorization/reason. Accept only a source with current native
request-bound provenance. Fill a missing destination; never overwrite different
existing bytes. Record a distinct user-approved reuse receipt binding source
receipt/hash and current source/target requests. Revalidation accepts this receipt
as an alternative provenance class, without relabeling it as native generation.
Subsequent candidate insertion invalidation, source/request/reference drift, or
byte changes invalidate adoption. Both server and standalone verification use
the shared adoption validator. Valid repeat calls are idempotent.

## Tasks

- [x] Add meaningful provenance, stale input, invalidation, and overwrite tests.
- [x] Implement adoption command and integrate the shared verifier.
- [x] Run relevant tests and code/security review; apply the selected image.
  - 111 relevant tests and 5 subtests passed across scoped suites. Reviewer findings on outer repair reservations and interrupted state publication fixed and re-reviewed.
  - Adoption receipt: logs/app_server/image_gen/20261016_092943_1792110583972242000_adoption.json.
  - Resume job 88caad92e3b84884ad1347227b25bd8c preserved 50 outputs, completed three remaining declared result frames, and passed normal frontend strict p680.
- [x] Validate p680, prepare saved narration, generate and verify all audio.
  - 19 audio outputs decoded/measured and matched to current revisions, hashes, provider settings; 4 intentional silent cuts preserved. Raw audio total186.723266 seconds.
  - p730 standard pipeline report passes all stages after shared validation compatibility fixes.
- [x] automation-3 PAUSED after completion.
