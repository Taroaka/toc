# Requirements

## Goal

Remove production-code reinforcement for Cinderella or any other single story.
Story-specific facts must enter through research and run artifacts, not title
checks, fixed scene tables, fixed character aliases, or prompt exceptions.

## Success criteria

- Production Python contains no Cinderella-specific branches, constants,
  profiles, events, roles, assets, prompts, examples, or aliases.
- The immersive frontend runner uses one generic path for every story.
- A deterministic test rejects reintroduction of known story-specific tokens
  in production code.
- The root agent guide prohibits story-specific production reinforcement.
- Both shared TDD workflow copies require a story-neutrality review.
- Pointer docs, targeted tests, and diff checks pass.

## Scope

- `scripts/toc-immersive-frontend-run.py`
- `scripts/build-semantic-review-pack.py`
- `scripts/review-image-prompt-story-consistency.py`
- `toc/scene_acceptance_contract.py`
- `docs/root-pointer-guide.md`
- `.codex/skills/tdd-workflow/SKILL.md`
- `.agents/skills/tdd-workflow/SKILL.md`
- related tests

## Non-goals

- Do not replace Cinderella with another hardcoded story.
- Do not edit existing run artifacts under `output/`.
- Do not weaken generic schema, grounding, provenance, or output validation.
