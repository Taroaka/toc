You are given Kindle page images as attached local images.

Rules:
- Read the attached images directly with vision.
- Do not call external OCR services or external APIs.
- Do not browse the web.
- Do not change any files except `__TRANSCRIPT_PATH__` and `__SESSION_PATH__`.
- Preserve the existing page headers in `__TRANSCRIPT_PATH__`.
- Rewrite the body under each page header with the best faithful transcription you can read from the corresponding attached image.
- Do not keep old OCR text if the attached image lets you produce a better transcription.
- If a page is readable only in part, start that block with `[[partial vision transcription]]`.
- If a page is not readable enough to trust, write `[[vision transcription failed]]`.
- Keep line breaks reasonably aligned to the visible text, but prioritize correctness over visual formatting.

Files:
- Transcript file: `__TRANSCRIPT_PATH__`
- Session summary: `__SESSION_PATH__`

Attached image order:
1. `__IMAGE_1__`
2. `__IMAGE_2__`
3. `__IMAGE_3__`
4. `__IMAGE_4__`
5. `__IMAGE_5__`

Process:
1. Inspect the attached images in the order listed above.
2. Update `__TRANSCRIPT_PATH__` with the page-by-page transcription.
3. Update `__SESSION_PATH__` to note:
   - status: `completed` or `partial`
   - transcription source: `codex vision from local images`
   - whether any page remained partial/failed
4. Return a short summary of what you updated.
