# Validation

- Combined source-first, research author, frontend, scene/cut, adaptation, resume and grounding suite: 223 passed; 21 subtests passed.
- Regression tests were red before the corresponding implementation (preset removal, research boundary, malformed sources, wrong topic / URL-only source).
- Research author line coverage measured with Python stdlib trace: 92% before the final topic/URL regression addition. pytest-cov/coverage are not installed; no dependency was installed.
- Python compilation and git diff whitespace checks passed.
- AGENTS.md / CLAUDE.md pointer validator passed; Astra requires explicit user permission before subagent use. Agents were interrupted when requested; subsequent implementation and review were performed locally.
- Local Codex app-server JSON schema confirms completed webSearch/openPage URL records used by source verification.
- No live research author, image/TTS/video provider, or existing production run was executed or regenerated for this change.

# Review scope

Confirmed no RUN_VARIANTS, _run_variant, _build_research or default narrative scene-title fallback remains in the frontend production helper. Legacy compiler fixtures exist only under tests; production does not import them. The researcher receives exact input and canonical grounding, never a populated narrative profile. Failed retrieval/structural validation cannot publish a synthetic replacement or advance to Story Author. Runtime uses read-only authoring, safe file publication, source hashing and recorded retrieval provenance.
