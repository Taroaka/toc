# Design

Introduce a research author boundary using the existing read-only structured Codex app-server transport and stage readset. Persist exact request, authored output and transport provenance; validate structure/source references before publishing research.md. Topic-only requests require retrieved sources; provided original source text may be evidence, but is never represented as a fetched tradition.

Keep initialization content-free. Build the runtime profile from authored research only after research completes, and project scene-specific data after Story Author. Stable IDs and duration settings remain deterministic technical metadata. No fixed narrative selection or research fallback remains in production.

Use dependency-injected author runners for offline tests. Move any legacy narrative scaffolds required by downstream unit tests into clearly test-only fixtures; production must not import them. Preserve unrelated in-progress changes.
