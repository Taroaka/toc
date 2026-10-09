# Source-first visual planning

New production runs use `visual_value_metadata.visual_planning_contract: source_first_v2`.
`visual_value.md` supplements the authored story; it does not replace the story with an abstract interpretation.

## Authoring

Prepare the `visual_value` readset and read research and story in full. Write only decisions needed for this work.
Keep facts, a character's beliefs, audience knowledge and intended affect distinct. A character can sincerely
misunderstand their own motives; external success may reinforce a harmful belief. Do not require those patterns
in every scene or add them to an adaptation without source support.

Every source scene appears exactly once, in source order, with its exact `scene_id` as `scene_selector`.
New author output also includes `boundary_b_roll` per scene, following
[unpeopled B-roll design](b-roll-design.md). The runtime binds `b_roll_policy: boundary_b_roll_v1`;
p400 projects the authored environmental holds into sub cuts. Missing decisions fail closed.
`notes` is an array of concrete decisions and may be empty. A missing scene or failed author response is an error;
the runtime never supplies empty notes or generic prose to disguise incomplete authoring.

Optional `global_visual_identity.notes` describes work-specific or user-requested visual choices.
Optional `continuity_notes` records existing subjects/states that must remain recognizable across scenes.
Each continuity item has `source_refs` (`source: research|story`, JSON `pointer`), `scene_selectors`, and `note`.
Do not invent asset IDs, cut IDs, time pressure, symbolic props, future events, or provider requests at p300.
Metaphorical nouns are not automatically physical objects. Narration person does not determine camera viewpoint.

The runtime supplies `source_bindings` for `research.md` and `story.md` with raw-byte SHA-256 digests.
The author does not invent hashes. The shared author is `scripts/author-visual-value-with-codex.py`;
frontend create invokes the same path. It uses the existing read-only author runtime and the caller's run lock.

## p400 handoff

Read story and visual planning together. Project authored event/beat identity, facts, participants, state,
reveal and handoff directly. `scene_intent.visual_notes` preserves the received scene notes.
`source_story_scene_id` links a runtime scene ID to the source without numbering heuristics.
Script and manifest metadata carry the same `visual_planning_contract` and `source_visual_value: {path, sha256}`.
Each cut also carries `visual_planning_contract: source_first_v2`, including composed video render units.
Rebuild reads the saved planning and verifies its source digests before projecting it again.
Existing visual planning is an optional, digest-tracked input to script, asset, narration,
scene implementation and video generation readsets; legacy runs without the file remain readable.

Additional dramatic questions, conflicts and transformations are optional author decisions. Equal start/end states
are valid when the authored scene maintains them. Do not synthesize an irreversible turn, emotional contradiction,
iconic moment, generic pressure or reaction merely to fill a field. Existing state/reference checks still apply.

The v2 path does not emit `adaptation_intent`, `scene_value_amplification` or cut `expressive_contract`.
Actual story facts and adaptation source contracts remain upstream; scene/event and request/provenance checks remain active.
Required image state and motion contracts must still be complete before generation. Empty creative notes are not permission
to omit required source or provider inputs.

## Validation and compatibility

Validate source bindings, types, ordered scene coverage, source pointers, file safety and downstream note/source identity.
Unknown versions, mixed legacy/v2 planning blocks and stale source files fail closed. A new v2 author failure never falls back
to a deterministic plot. Existing v1 artifacts keep their v1 validation/reader path; do not silently migrate stored runs.

p310 completes after valid authored planning is saved. p330 completes with source-bound handoff; no automatic approval wait.
p450 stop writes a skeleton manifest and no asset/image requests. p650/p680 continue the normal materialization flow.
No critic, score or new quality certificate is required.

For v2, a first frame with no authored motion can remain still. The video compiler does not
add breathing or weight shifts to an unpeopled image. Missing both usable frame content and
motion is an input error. The v1 fallback remains available only to existing unmarked contracts.

Tests establish input preservation and deterministic projection, not whether an actual model
follows every freeform direction or whether a generated film succeeds artistically. New p400 runs now use [cinematic authoring](p400-cinematic-authoring.md): an LLM reads the complete story and
visual planning to author the cut sequence. Stored runs without the cinematic contract retain their previous projection.

See `workflow/visual-value-template.yaml`, `toc/visual_planning_contract.py` and `toc/source_scene_projection.py`.
