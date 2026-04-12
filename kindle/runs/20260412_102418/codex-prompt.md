Use the Playwright MCP to open `https://read.amazon.com`.

Rules:
- Wait for me to complete login manually and open the target book manually before interacting with the Kindle reader.
- While the login screen, account chooser, landing page, or Kindle library page is visible, do not click, type, or submit anything.
- Passively observe the page and continue only after the Kindle book reader UI for a specific book is clearly available.
- Do not attempt CAPTCHA solving, credential entry, or bulk extraction.
- Stop after exactly 5 pages.
- Save one screenshot per page into `/Users/kantaro/Downloads/toc/kindle/runs/20260412_102418/pages` using filenames `0001.png` through `0005.png`.
- Use screenshot + vision as the primary transcription method.
- If a page cannot be reliably transcribed, write `[[transcription failed]]` for that page and continue when possible.
- Prefer a visible `Next page` control.
- If that is unavailable, use a safe fallback such as a single right-side click or one `ArrowRight` press.
- Record which page-turn method worked in `/Users/kantaro/Downloads/toc/kindle/runs/20260412_102418/session.md`.

Outputs:
- Transcript file: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_102418/transcript.txt`
- Session summary: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_102418/session.md`

Transcript format:
- Replace the `[[pending]]` marker for each page.
- Keep the page headers exactly as:
  - `=== Page 1 ===`
  - `=== Page 2 ===`
  - `=== Page 3 ===`
  - `=== Page 4 ===`
  - `=== Page 5 ===`

Session summary requirements:
- Mark overall status as `completed`, `partial`, or `failed`
- Note whether login succeeded
- Note whether login and book-open state were detected automatically from the page state
- Note whether the target book had to be opened manually by the user
- Note which page-turn control worked
- Note any partial/failed pages
- Note any UI instability that would affect longer runs

Process:
1. Open Kindle for Web and wait until manual login is completed and a specific book is opened to the reader UI.
2. Inspect the reader UI and identify the safest page-turn action.
3. For each of 5 pages:
   - save a screenshot
   - transcribe the visible reading content
   - update the transcript
   - move to the next page unless this is page 5
4. Update the session summary and stop.
