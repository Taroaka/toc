# Cut planning from narration (tasklist)

- [ ] Add cut duration support: `video_generation.duration_seconds` override in `scripts/generate-assets-from-manifest.py`
- [ ] Extend placeholders: support `cuts[]` and duration override in `scripts/generate-placeholder-assets.py`
- [ ] Update `/toc-scene-series` scaffold to emit `cuts[]` with per-cut narration placeholders
- [ ] Update `scripts/toc-immersive-ride-generate.sh` to prefer `--narration-list` when present
- [ ] Update templates/docs/agents to reflect:
  - 1 cut = 1 narration
  - main 5–15s; sub 3–15s
  - split decision after scene+narration are drafted
  - exclusion: `cloud_island_walk`
- [ ] Run unit tests relevant to manifest parsing and scaffolds
