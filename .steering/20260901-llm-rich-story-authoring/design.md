# Design

1. Normalize `research.md` into an ID-addressable, lossless registry.
2. Send the full registry to `gpt-6-astra` as Story Architect to create scene
   ownership and global handoffs.
3. Send each frozen scene slice plus neighboring handoffs to `gpt-6-astra` as
   Scene Author.
4. Assemble a rich `story_scene_contract_v1` document.
5. Validate source IDs, coverage, order, lifecycle, and handoffs
   deterministically.
6. On failure, ask `gpt-6-luna` for a bounded patch to only the failing
   scene/key and revalidate.
7. Publish `story.md` atomically only after validation.

`gpt-6-sol` is not a default story author. Use it only for an explicitly
selected intermediate task that is too broad for a Luna branch but does not
own the Astra-level canonical story decision.

The Python layer packs, validates, repairs, assembles, and writes. It does not
author story prose.
