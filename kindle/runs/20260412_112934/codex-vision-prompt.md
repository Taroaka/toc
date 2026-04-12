You are given Kindle page images as attached local images.

Rules:
- Read the attached images directly with vision.
- Do not call external OCR services or external APIs.
- Do not browse the web.
- Do not change any files except `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt` and `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md`.
- Preserve the existing page headers in `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt`.
- Rewrite the body under each page header with the best faithful transcription you can read from the corresponding attached image.
- Do not keep old OCR text if the attached image lets you produce a better transcription.
- If a page is readable only in part, start that block with `[[partial vision transcription]]`.
- If a page is not readable enough to trust, write `[[vision transcription failed]]`.
- Keep line breaks reasonably aligned to the visible text, but prioritize correctness over visual formatting.

Files:
- Transcript file: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt`
- Session summary: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md`

Attached image order:
1. `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/pages/0001.png`
2. `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/pages/0002.png`
3. `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/pages/0003.png`
4. `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/pages/0004.png`
5. `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/pages/0005.png`

Process:
1. Inspect the attached images in the order listed above.
2. Update `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt` with the page-by-page transcription.
3. Update `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md` to note:
   - status: `completed` or `partial`
   - transcription source: `codex vision from local images`
   - whether any page remained partial/failed
4. Return a short summary of what you updated.
