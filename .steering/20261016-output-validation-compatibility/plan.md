# Preserve authored contracts in ordinary output validation

## Requirements and evidence
The frontend's strict image check succeeds but the independent pipeline verifier
rejects source-linked event/meaning/moment records, state variants with canonical
single-view plans, and a p500 supervisor result left pending after asset handoff.
The docs require source IDs on authored preservation requirements. Preserve the
richer authored records and all generated artifacts; do not flatten away sources
or add title-specific exceptions. Missing text/source lists still fail.

## Design
Allow legacy strings and explicit source-linked records (requirement/meaning/moment
plus nonempty source_event_refs) in the three adaptation preservation lists. Validate
optional passage refs when present. Keep all other strict adaptation checks.
Character state variants identified by reuse_contract.mode=state_variant require a
single view and declared parent; base identities retain front/side/back checks.
Finalize the p500 supervisor result after validated asset handoff using the existing
helper and active slot inventory. Keep exact state comparison. Resolve the run root
in the verifier entry point so its documented relative path invocation works.

## Tasks
- Add regression tests for valid and malformed typed records, variant/base views,
  p500 result completion, and relative run paths.
- Implement minimal generic fixes and review.
- Reconcile the validated run's p500 summary under its lock and rerun verification.

## Verification
43 scoped tests and2subtests pass; read-only reviewer clean after requiring distinct declared base and canonical manifest variant lookup. The existing untouched manifest-template YAML parse test remains a baseline failure and was excluded from this scope. Relative CLI invocation and p730 standard verification now pass for the run. The current p500 summary was reconciled only after normal asset validation.

Audio output verification decoded19files, measured186.723266seconds, and checked current text/TTS revisions, hashes, delivery settings and provenance. Four intentional silent cuts are preserved. Later video-timeline readiness is separate: the old duration utility does not recognize cinematic_direction_v1 silence records and its80%target gate has not been marked passed. No video/render work or listening approval was performed.
