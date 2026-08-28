---
name: marketing-skills-router
description: Use when the task is explicitly scoped to ToC marketing, including the public site, persona-specific LPs, digital acquisition, lead conversion, or SNS distribution under `marketing/`.
---

# Marketing Skills Router

## Purpose

This skill is the scoped gateway for marketing guidance in this repository. It keeps visitor acquisition and conversion rules available without leaking them into normal ToC production.

Primary source:

- `marketing/README.md`
- `marketing/first-offer.md` for the first sellable offer and delivery boundary

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
   - ToC has exactly two production modes: `image_batch` for generating the necessary images together, and `video` for completing structure, images, motion, voice, and editing
   - reuse across the same idea or assets is a shared strength, not a third production mode
   - primary personas are side-business individuals and small-business operators; personal brand is a small-business use case
   - the first focused persona is a side-business individual who wants to turn their knowledge or experience into a faceless video; this persona does not redefine the entire side-business segment
   - the first production mode for this persona is `video`; small-business operators remain the next market
   - the first offer delivers an accepted first video together with the customer-owned production setup and reusable materials; it is not a video-only agency delivery
   - mythology / folklore are proof examples, not the product category
4. Apply changes only to marketing-scoped files and required repo pointers.

## Guardrails

- Use plain Japanese for user-facing copy and explanations. Do not insert internal English terms mid-sentence. When a specialist concept is unavoidable, explain its meaning in Japanese before using it.
- Never let marketing promises rewrite production quality gates.
- Never use unmeasured speed claims, revenue guarantees, or fake scarcity.
- Treat `large-volume image generation` as evidence-backed only; default to `necessary images in a managed batch` until requested/generated/accepted counts, time, cost, and review evidence are bound.
- Keep side-business and small-business-operator personas separate in ads, LPs, CTA, and analytics.
- Treat campaign-specific files as subordinate to `marketing/README.md`.
- Do not use Notion or Google Forms as the canonical public site / intake route.
