# Requirements: Run Variant Generic Authoring

- Frontend create runs must not enter a Cinderella-specific scaffold just because topic/source contains `シンデレラ` or `cinderella`.
- Same topic/source created in different run directories should produce a distinct authored variant, including scene titles, motifs, artifact framing, prompts, and manifest metadata.
- Legacy Cinderella fixture behavior may remain only behind an explicit opt-in test/development flag.
- Storyboard mode still keeps per-cut images, then uses one scene storyboard image as the scene-level video input after storyboard materialization.
