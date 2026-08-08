# Frontend create handoff design

Use an owned reservation/retained-run object containing the public name, parent directory descriptor, run directory descriptor, and `(st_dev, st_ino)` identity. Ownership moves exactly once from endpoint code to the tracked background task.

Runtime lock acquisition accepts a pinned run descriptor plus expected identity. For run-scoped `.locks` paths it creates and validates metadata with `*at` operations below that descriptor, and derives kernel lock offsets from the lexical name plus the pinned inode without resolving the public path.

The server execution lease combines the runtime lock with a nonblocking exclusive `flock` on the pinned run-directory descriptor. Fresh frontend children inherit the same open file description, retaining ownership if the server dies. Existing p500 mutation acquires the same run-inode lock before any write.

Endpoint setup is transactional: reserve/probe, bind, acquire, classify/log, create and register the task, then transfer ownership. Every earlier `BaseException` rolls back the job record and exact held resources. Task shutdown cancellation is awaited before maps and leases are cleared.

Cleanup uses only retained descriptors and conditionally quarantines the named entry after identity verification. It never deletes or writes through a public replacement.

All active-run reads use run-relative, no-follow descriptor traversal. A validator captures each artifact once and uses those exact bytes for parsing and hashing. Shared artifact writers publish a new inode with a native atomic name exchange when a canonical leaf already exists; rollback uses the reverse exchange. If the reverse exchange cannot be proven, the writer leaves one complete canonical version visible, retains the other version in its protected cleanup namespace, and reports an indeterminate failure.

External semantic turns receive private immutable workspaces. Producer repair receives a private writable staging copy limited to an explicit artifact allowlist; the runtime validates the review input digest, reported changed-artifact set, canonical baselines, UTF-8 output, and computed diff before descriptor-relative import. Image turns likewise receive private reference copies and a private output destination before verified import.

The p650/p680 gates consume descriptor-read request, state, report, image, and provenance snapshots. Localized semantic blocking is re-derived from bound state immediately before provider submission. The terminal p680 supervisor artifact must name p680 as its completed terminal slot and agree with the state handoff; failed validation demotes or invalidates both representations.
