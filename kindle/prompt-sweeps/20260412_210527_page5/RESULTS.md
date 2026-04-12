# Prompt Sweep Findings

- image: `/Users/kantaro/Downloads/toc/kindle/runs/20260412_210527/vision_inputs/0005.retest2.png`
- target issue: vertical Japanese page with text close to the right edge

## Best so far

`vertical-columns`

Why:
- It removed the `[[partial vision transcription]]` marker.
- It improved mid-page factual accuracy versus `baseline`.
- It preserved more faithful wording than `edge-first`, which fixed the first character but introduced more paraphrase and factual drift.

## Variant notes

- `baseline`
  - Better than the old prompt after padding/upscale.
  - Still dropped the first character and introduced some factual drift like `二〇年前`.

- `vertical-columns`
  - Best overall tradeoff.
  - Still misses the very first character on this page, but the rest of the page is more faithful.

- `edge-first`
  - Recovered the first character (`ひどくなっていて`).
  - Introduced more aggressive rewrites such as changed counts/nouns, so it is not the default choice.

## Decision

Use the `vertical-columns` style prompt in the runner for now.
