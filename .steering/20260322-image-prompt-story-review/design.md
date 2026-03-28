# Design: image prompt story review

## Review entrypoint

- Add `scripts/review-image-prompt-story-consistency.py`.
- Primary input is `image_prompt_collection.md`.
- By default, infer sibling paths:
  - `video_manifest.md`
  - `story.md`
  - `script.md`
  - output report: `image_prompt_story_review.md`

## Review heuristics

- Parse `image_prompt_collection.md` into `sceneXX_cutYY` entries.
- Join each entry back to the matching manifest cut.
- Build local source context from:
  - cut narration
  - matching `story.md` structured scene content when `scene_id` matches
  - matching structured `script.md` scene content when available
- Extract entity-like anchor terms from Japanese/English tokens plus optional `review_aliases` declared in `assets.character_bible[]` and `assets.object_bible[]`.
- Emit `WARN` findings for:
  - source anchor term present in narration/story/script but missing from prompt
  - prompt anchor term present in prompt but absent from the local source context and undeclared in the cut asset ids
  - alias-implied `character_ids` / `object_ids` missing from the cut

## Output

- Write `image_prompt_story_review.md` with:
  - review summary
  - pass/warn status
  - scene/cut findings with context
- Exit `0` by default.
- Support an opt-in `--fail-on-findings` mode for automation.

## Docs

- Update `docs/implementation/image-prompting.md` to make story-consistency review part of the default image workflow.
- Update `docs/how-to-run.md` and `workflow/playbooks/image-generation/reference-consistent-batch.md` with the new command.
- Document optional `review_aliases` in `docs/data-contracts.md` so manifests can improve name matching when needed.
