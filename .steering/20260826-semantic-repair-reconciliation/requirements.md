# Requirements: Semantic Repair Reconciliation

## Problem

Frontend-created ToC runs repeatedly stop before image generation because
semantic producer repair changes canonical scene meaning without consistently
regenerating dependent cut, timeline, asset-reference, request, and P400 review
contracts.

## Requirements

- Reconcile repaired semantic sources before refreshing P400 reviews.
- Project repaired scene event action, reaction, facts, evidence, and context to
  affected cuts.
- Reconcile participant and appearance variants across timelines, asset
  dependencies, image generation IDs, and request references.
- Keep reconciliation deterministic and idempotent.
- Preserve all semantic, deterministic, provider, provenance, and human gates.
- Verify the fix on the existing Cinderella run and one brand-new frontend run
  through P680 with real images.

## Acceptance Criteria

- Focused tests reproduce and eliminate stale cut/reference failures.
- P400 review cannot observe unreconciled repaired sources.
- Existing Cinderella reaches P680 without manual artifact edits after the code
  fix.
- A fresh backend frontend-create run reaches P680 without manual artifact edits.
- Both runs contain real generated asset/scene files with request-bound Codex
  provenance.

## Non-Goals

- No QA bypass, local raster placeholder, or fabricated review pass.
- No work beyond P680.
- No unrelated marketing, LINE, narration, video, or render changes.
