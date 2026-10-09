# Requirements

- Add one shared BGM/SE process after generated video approval and before final concatenation.
- Show editable generation proposals, generate real audio candidates, audition and select them, and configure timing, level, fades and BGM looping in the frontend.
- Keep all sound work in p860; keep p850 retired and p900 render numbering unchanged.
- Bind video approval to the current ordered clips, bytes and timeline. Changed inputs require renewed approval.
- Persist requests, candidate provenance and selections. Failed generation must retain prior candidates.
- Freeze the selected soundtrack with render inputs and actually mix it with narration. Explicitly choosing no added sound is supported.
- Preserve unrelated working-tree changes. No paid generation is necessary to validate implementation.
