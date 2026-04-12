---
name: marketing-skills-router
description: Use when the task is explicitly scoped to files under `marketing/` in this repo, especially `marketing/SNS/`. This skill routes Codex to the repo's SNS marketing docs. Never use for normal ToC story creation, script creation, image generation, or video generation tasks.
---

# Marketing Skills Router

## Purpose

This skill is the scoped gateway for the marketing/SNS docs bundled in this repository.
It exists to keep marketing-specific guidance available without leaking it into the default ToC production workflow.

Primary sources:

- `marketing/README.md`
- `marketing/SNS/`

## Scope Gate

Use this skill only when at least one of these is true:

- The user explicitly asks about files under `marketing/`
- The task is to create, edit, review, or organize `marketing/SNS/` content
- The task is clearly a marketing or SNS workflow for this repository

Do not use this skill when the task is about:

- `docs/story-creation.md`
- `docs/script-creation.md`
- `docs/video-generation.md`
- `output/`
- Standard ToC research, story, script, image, narration, or video generation work

If the task is outside `marketing/`, stop and use the normal ToC workflow instead.

## How to Work

1. Read `marketing/README.md` first.
2. Read the relevant files under `marketing/SNS/`.
3. Apply the result back to this repository's `marketing/` files.

## Selection Rules

- Treat `marketing/SNS/` as the source of truth for marketing work in this repo.
- If a request mixes ToC production and marketing, use this skill only for the marketing slice.

## Guardrails

- Never invoke this skill for ordinary story production tasks.
- Never let marketing-oriented prompts or heuristics rewrite story/script/video rules.
- Do not treat marketing guidance as globally available defaults for the whole repository.
- If scope is ambiguous, do not use this skill.
