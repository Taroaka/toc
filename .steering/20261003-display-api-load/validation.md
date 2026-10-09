# Validation

- Existing server/status/media regression: 347 passed, 60 subtests passed.
- Cache/offload/snapshot/progress regressions: 9 passed.
- Frontend: 23 passed; TypeScript and Vite build succeeded.
- Read-only production fixture measurement while old server was busy: 8MB manifest parse alone took 10.37s. The old narration list repeatedly read it for candidate provenance per cut.
- Fixed display helper, same 58-cut run: first narration list 2.768s, repeated list 0.782s, image gallery 0.187s.
- Generation validation and mutation reads retain original strict paths. Display cache only stores parsed data; it invalidates on file/directory identity and metadata changes and returns independent copies.

## Live verification after restart

Concurrent HTTP reads for the existing 58-cut run returned successfully: image gallery 0.725s (58/58 images available), narration list 4.313s cold / 0.296s warm, progress 0.194s. Status remains P720, audio files 0; no generation or artifact changes were initiated. Backend/frontend health and Codex runtime no-op passed.
