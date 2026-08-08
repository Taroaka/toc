# Frontend create handoff task list

- [x] Add failing FD-relative runtime-lock and p500 replacement regressions.
- [x] Add failing fresh-create swap, failure, cancellation, and task-tracking regressions for all create modes.
- [x] Add failing missing expected-run, long-name residue, and inherited-FD regressions.
- [x] Implement pinned runtime-lock metadata API and composite run execution lease.
- [x] Retain and transfer fresh reservations transactionally through tracked tasks and cleanup.
- [x] Bind existing-run resume setup and task execution to a retained descriptor.
- [x] Transfer the run-directory ownership FD to frontend children and close it before nested exec.
- [x] Bind direct foreground and background image-generation providers to the retained run descriptor.
- [x] Isolate semantic review and producer repair in private workspaces and import only validated outputs.
- [x] Make semantic, world-source, and request-snapshot overwrite/rollback publication reader-visible and atomic.
- [ ] Make state/debug/provenance append, write, read, and conditional deletion safe under leaf and ancestor replacement.
- [ ] Bind p650/p680 report, regeneration, image, provenance, and blocked-item decisions to exact retained-descriptor snapshots.
- [ ] Make p680 supervisor artifact/state publication and failure demotion a fail-closed terminal contract.
- [x] Run focused tests, `py_compile`, and a scoped diff check.
- [ ] Run the complete affected Python suites, web tests/build, pointer/slot validators, and final independent reviews.
- [ ] Restart the ToC server, verify health, and resume the canonical Cinderella run through p680.
