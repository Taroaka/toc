# Design

Use research/run-artifact data as the only source of story-specific facts.
Delete title detection and story-key branching, dedicated scene/beat/role tables,
and story-derived generic fallbacks. Preserve generic `RUN_VARIANTS`, generic
profile construction, generic scene/cut contracts, and strict validators.

Add a source-neutrality regression test over the affected production modules.
Document the rule in the canonical root pointer guide and in both synchronized
TDD workflow skill copies.
