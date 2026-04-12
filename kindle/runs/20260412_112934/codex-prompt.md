Use shell tools in this repo to run the Kindle CDP extractor.

Rules:
- Wait for me to complete login manually and open the target book manually before starting extraction.
- Do not click, type, or submit anything in Kindle for Web yourself.
- Do not attempt CAPTCHA solving, credential entry, or bulk extraction.
- Stop after exactly 5 pages.
- Do not use Playwright `browser_take_screenshot` or `browser_run_code` for page capture.
- Use `python3 ./kindle/extract-kindle-web-cdp.py --run-dir "/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934" --pages 5 --port 59708 --ocr-mode none`.
- After image export succeeds, run `./kindle/transcribe-kindle-pages-with-codex.sh "/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934"`.
- If the extractor reports that the reader is not open yet, stop and tell me what it needs.
- Record the result in `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md`.

Outputs:
- Transcript file: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt`
- Session summary: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md`

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
- Note whether the reader tab was found successfully
- Note the starting Kindle page number if available
- Note which page-turn control worked
- Note any partial/failed pages
- Note any UI instability that would affect longer runs

Process:
1. Ask me to log in and open the target book manually if that has not happened yet.
2. Run the CDP extractor from the shell.
3. Run the Codex vision transcription script from the shell.
4. Read `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/transcript.txt` and `/Users/kantaro/Downloads/toc/kindle/runs/20260412_112934/session.md`.
5. Summarize the outcome briefly and stop.
