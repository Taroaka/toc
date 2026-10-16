# Verification

- RED: 10 selected character-key tests failed before implementation because the schema and binding lacked the key/contract.
- GREEN: tests/test_story_author_pipeline.py: 19 passed, covering two distinct research settings and arbitrary ID vocabularies, published YAML, late arrivals and state-only references, explicit empty participants, invalid state identity, unknown ID, missing/malformed/mismatched index, and rebinding after changed lifecycle references.
- Related story validation, bounded field repair, CLI, runtime, resume/cache, selection, duration, causal prompts, audience meaning, downstream lifecycle/profile projection, and story-neutral code checks: 145 passed, 13 subtests passed.
- After adding participants to the generation schema and final review: author pipeline, runtime and field-repair pipeline: 49 passed.
- python scripts/validate-pointer-docs.py: passed.
- git diff --check: passed.
- Read-only collection from the existing failed story: scene_01 [CH1, CH2]; scene_02 [CH1, CH4]; scene_03/04 [CH1, CH2, CH3]. Existing run files were not changed or resumed.

## Review

Checked the patch for title-specific branching, prose/name inference, publication before validation, malformed/unknown ID hiding, arrivals after start state, stale derived values after field patch, and preservation of explicit empty participants. The new index is derived only from typed source/lifecycle references, malformed references remain visible to validation, and field patches now retain the rebound scene. Existing artifacts without the new contract retain compatibility. Unrelated working-tree edits were preserved. No external generation or server restart was performed.

## Remaining scope

Protagonist identification, p400 cut/shot ID synchronization, and unknown-shot diagnostic repair remain the three separately deferred fixes. This change fixes future scene-key publication, not the entire failed p400 job.
