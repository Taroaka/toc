---
name: marketing-skills-router
description: Use when the task is explicitly scoped to ToC marketing, including the public site, persona-specific LPs, digital acquisition, lead conversion, or SNS distribution under `marketing/`.
---

# Marketing Skills Router

## Purpose

This skill is the scoped gateway for marketing guidance in this repository. It keeps visitor acquisition and conversion rules available without leaking them into normal ToC production.

Primary source:

- `marketing/README.md`

Routed sources:

- public site / LP / native form: `marketing/LP/`
- SNS / channel distribution: `marketing/SNS/`
- YouTube strategy: `marketing/SNS/YouTube/strategy.md`

## Scope gate

Use this skill when at least one is true:

- the task creates, edits, reviews, or organizes files under `marketing/`
- the task concerns the ToC public marketing site or persona-specific LPs
- the task concerns digital acquisition, lead conversion, Meta / SNS routing, or marketing analytics for ToC

Do not use this skill for normal:

- research or story production
- script or narration production
- image or video generation
- output run orchestration
- production frontend behavior under `server/web/`

## How to work

1. Read `marketing/README.md` first.
2. Select only the relevant slice:
   - site / LP / form -> `marketing/LP/`
   - channel / campaign / analytics -> `marketing/SNS/`
3. Preserve the positioning boundary:
   - ToC is a system for making individual video production faster and simpler
   - primary personas are side-business and personal-brand individuals
   - mythology / folklore are proof examples, not the product category
4. Apply changes only to marketing-scoped files and required repo pointers.

## Guardrails

- Never let marketing promises rewrite production quality gates.
- Never use unmeasured speed claims, revenue guarantees, or fake scarcity.
- Keep the two primary personas separate in ads, LPs, CTA, and analytics.
- Treat campaign-specific files as subordinate to `marketing/README.md`.
- Do not use Notion or Google Forms as the canonical public site / intake route.
