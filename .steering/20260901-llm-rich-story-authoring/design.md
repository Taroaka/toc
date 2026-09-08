# Design

1. Normalize `research.md` into an ID-addressable, lossless registry.
2. Send the full registry to a Story Architect model to create scene ownership
   and global handoffs.
3. Send each frozen scene slice plus neighboring handoffs to a Scene Author.
4. Assemble a rich `story_scene_contract_v1` document.
5. Validate source IDs, coverage, order, lifecycle, and handoffs
   deterministically.
6. On failure, request a bounded patch for only the failing scene/key and
   revalidate.
7. Publish `story.md` atomically only after validation.

The Python layer packs, validates, repairs, assembles, and writes. It does not
author story prose.
