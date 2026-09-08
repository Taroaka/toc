# Design

Use build_research_registry as the shared ID authority for story foundation diagnostics. The author assigns deterministic keys to legacy string records; the reviewer currently ignores those records. Keep the supported reference-section allowlist and fail closed on missing IDs. Verify the failed run in a temporary copy without rewriting its history or pretending downstream work completed.
