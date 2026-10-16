# Scene character key contract

## Request and scope

The user asks why scene.character_ids was absent and wants future stories to publish the correct key reliably, regardless of story or character ID vocabulary. Implement this upstream key contract before the separately discussed protagonist adapter, p400 ID repair, and shot-error repair changes. Do not resume or overwrite the failed production run.

## Evidence

Scene Author schema and story template describe source_basis.character_ids and lifecycle participants, but do not require scene.character_ids. The story validator accepts the omission. A downstream reader nevertheless expects the direct field. Existing failed output demonstrates that mismatch; no title-specific code is permitted.

## Success criteria

- Every newly authored scene has a deterministic, duplicate-free scene.character_ids list derived from its source_basis and explicit lifecycle references; no character is guessed from names or prose.
- The key is required by the author schema and documented in the canonical template.
- Newly published stories declare the character-binding contract and validation rejects missing, malformed, inconsistent, or unregistered references before publication.
- Explicit empty participant lists and scenes without characters remain possible.
- Existing unmarked artifacts retain their previous compatibility rules.
- Tests cover different ID vocabularies, late arrivals, state-only characters, empty scenes, invalid references, publication, and post-repair rebinding.

## Deferred

The three previously identified adapter and p400 repair changes remain separate work. This contract does not claim to fix or resume the current failed job by itself.
