# Bounded saved-patch replay

## Requirements and evidence

Saved correction replay must never bypass convergence or the durable repair
budget. A running author was alternating the same two candidate hashes and
saved responses, producing over 28,000 replay records while its reserved
attempt stayed at 10. Its verified author child was terminated; the normal
parent failure path retains checkpoints, source files, and repair history.

## Design

Track candidate hashes visited during the current repair invocation. Apply a
source-bound saved patch only if its result is new. If it returns
to a visited candidate, preserve the current candidate, report cycle feedback
to the author, and enter the existing budgeted correction path. Successful
saved corrections still finish without another provider call, even at the cap.
No-op patches remain invalid under the existing patch contract. No budget resets,
validator relaxation, title-specific choices, or log deletion.

## Tasks

- [x] Reproduce two- and three-candidate replay loops with bounded tests.
- [x] Add replay convergence checks and test cap preservation.
- [x] Review the incremental change and request one resume of the same run.

## Verification

All four new cycle/cap cases failed before the change and pass afterward.
The downstream suite passes 45 tests, excluding the single baseline failure
already documented in the state-variant-entry work. All 11 production-repair
tests pass, including budget/no-progress handling; downstream tests also preserve
successful saved correction at cap. `git diff --check` passes. Isolated read-only
review found no actionable issue. The runtime has retained its original limits.

The original worker PID 6115 was verified against command, parent PID, and run
directory inode before SIGTERM. Its parent reported failure and released the
run lease. No shared server or other run was stopped. Other chats were idle
before the resume request.

Incremental baseline:
`/var/folders/fc/8s9bkp2x4g51wgm9brtmjn_h0000gn/T/toc-replay-cycle-eaclz47h`.
