# Requirements

2026-10-07. The user explicitly selected all four remaining improvements: spatial preview, character state variants, candidate improvement records, and post-generation editing. Paid generation remains excluded.

- Spatial preview: author/review metric camera and subject placement, inspect a top-down and camera view, and carry the same concrete geometry into image/video instructions. The local Blender executable is absent; the working preview must use the existing browser/runtime, without an installation prerequisite or claiming photometric accuracy.
- Character state variants: preserve an immutable base image, compose an existing edited candidate only in explicitly selected regions, record the state change and exact input/output hashes, and make the derived image available as a reference. Never silently overwrite the base or assign the variant to all scenes.
- Candidate records: store observed defects, the requested correction, the outcome, and a human disposition against candidate bytes and request revision. Show candidates and notes together for comparison. No aesthetic scoring or required selection gate.
- Editing: create a derived video candidate from a source time range plus explicit numerical color/fade settings; preserve synchronous original audio through the same trim; preview the result and adopt it explicitly. Adoption must preserve narration audio/text, reject insufficient video duration, and invalidate obsolete p860 approval/mix settings.
- Existing run files and unfinished work by others must remain intact. All writes are run-relative, serialized, revision/hash checked, and recoverable.

Success is usable UI→API→local processing→candidate/selection→final render integration with offline tests. No external AI call is necessary for any of these tools.
