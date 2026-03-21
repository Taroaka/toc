# Requirements

## Problem
- Image prompt collections still contain weak camera shorthand such as `30mm` alone or lens values without framing intent.
- This makes review and downstream generation harder because the prompt does not say what the frame should let the viewer read.

## Goals
- Treat prompt construction as structured work: select anchors, fix references, review before generation.
- Replace weak camera shorthand with framing language that explains:
  - wide / mid / close intent
  - foreground / mid-ground / background roles
  - what the shot should help the viewer read
- Keep existing meaning intact.

## Non-goals
- Do not change story beats.
- Do not alter run semantics or generation order.
- Do not rewrite unrelated prompts outside the target run unless required for synchronization.
