# Kindle session

- run_dir: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_102418`
- target: `https://read.amazon.com`
- page_target: `5`
- login_mode: manual
- transcription_source: screenshot + vision, then direct CDP page-image export + OCR fallback
- status: completed

## Notes

- Initial `codex exec` + Playwright MCP run captured pages 1-3, then stalled on page 4 when `browser_take_screenshot` and `browser_run_code` both hit the 120s MCP timeout.
- The reader browser had to be reopened manually after stopping the stuck `codex exec` session, because that session owned the Playwright Chrome process.
- Pages 4 and 5 were recovered by reconnecting to the reopened Chrome over the Chrome DevTools Protocol on port `59708` and exporting the current Kindle page images directly from the DOM.
- `pages/0004.png` corresponds to the `Introduction` title page. `pages/0005.png` corresponds to the following introduction page.
- OCR quality for the final page is partial because Kindle for Web is rendering image pages and Japanese OCR remained noisy even after switching to a direct page-image export path.
