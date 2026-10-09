# Validation

- `python -m pytest tests/test_research_author.py tests/test_story_authoring.py tests/test_stage_grounding.py -q`: 54 passed, 6 subtests passed.
- Both research templates parse as YAML. Checked event source/version/passage references, version event membership, and the example material JSON Pointer.
- Both templates, with a fixture URL, pass the existing research structural validator. Added a temporary two-event causal-link fixture and confirmed all fields survive `build_research_registry` in raw_research and event records.
- Called the real `prepare_grounding` in a temporary run directory and `build_research_prompt`; verified the responsibility boundary and new evidence fields are in the actual prompt.
- `python scripts/validate-pointer-docs.py`: passed.
- Scoped `git diff --check`: passed. Existing unrelated edits in story-creation.md and the rest of the working tree were retained.
- No live LLM generation was run. The new fields are an authoring contract; semantic truth and all new references are not enforced by the existing runtime validator.
