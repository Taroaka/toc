# Frontend create handoff requirements

## Goal

Keep frontend create and p500 resume mutations bound to the exact inspected run-directory inode from reservation/probe through lease acquisition, background execution, child processes, cancellation, and cleanup.

Keep the p500-to-p680 continuation bound to that same identity through semantic review, request publication, image-provider submission, output validation, and the final frontend handoff.

## Success criteria

- Fresh normal, storyboard, and world-walk endpoints retain the reserved directory descriptor until their background job reaches a terminal cleanup path.
- Lock metadata is created relative to the retained descriptor and never in a replacement public directory.
- Existing-run resume performs classification, preflight, lease acquisition, start logging, and task handoff under the probed inode binding.
- Server and frontend child share the run-directory ownership lock so an orphan child excludes a restarted server and p500 mutators.
- Cancellation or any `BaseException` before/after task creation releases leases, closes descriptors, removes in-memory running records, and safely quarantines only the reserved inode.
- Expected-identity CLI execution never recreates a missing run path.
- Overlong public candidates and reservation publication failures leave no private staging residue and never clobber a raced entry.
- Child exec helpers do not leak the pinned directory descriptor past `fchdir`.
- Semantic reviewers and producer repair operate in private workspaces; only validated reports and approved artifact diffs are imported through retained descriptors.
- Existing semantic, world-source, request-snapshot, state, and provenance artifacts are published without a reader-visible missing canonical name, including rollback after a failed write.
- p650/p680 validators hash and parse the same descriptor-read bytes and cannot accept a report, request, image, provenance record, or state snapshot from a same-name replacement.
- Blocked scene items are rechecked from descriptor-bound semantic state immediately before every irreversible provider submission.
- The p680 supervisor result and state handoff cannot reuse a p650 result or remain falsely published after terminal validation fails.
- Direct single and bulk image-generation providers execute under the retained run descriptor binding for their full foreground or background operation.

## Scope

- `server/image_gen_app.py`
- `toc/runtime_locks.py`
- `toc/p500_resume.py`
- `scripts/toc-immersive-frontend-run.py`
- `scripts/resume-from-p500.py`
- `scripts/run-from-directory-fd.py`
- Focused regression tests for those handoffs
- `toc/run_root_binding.py`, `toc/semantic_review.py`, `toc/image_request_snapshot.py`, `scripts/world_walk_source.py`
- p650/p680 semantic-provider, provenance, verifier, and supervisor handoff code in `server/image_gen_app.py`
- Focused regression tests for atomic publication, provider isolation, exact-snapshot validation, and p680 failure recovery
