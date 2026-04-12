# Kindle review queue

## Page 1

- kindle_page_number: `3`
- severity: `warn`
- reason: short_transcription
- evidence: normalized_length=50
- suggested_action: Check whether this is an intentionally sparse page or a weak transcription.
- artifact_links:
  - `pages/0001.png`
  - `vision/0001.txt`
  - `vision/0001.log`

## Page 2

- kindle_page_number: `4`
- severity: `warn`
- reason: short_transcription
- evidence: normalized_length=106
- suggested_action: Check whether this is an intentionally sparse page or a weak transcription.
- artifact_links:
  - `pages/0002.png`
  - `vision/0002.txt`
  - `vision/0002.log`

## Page 5

- kindle_page_number: `7`
- severity: `warn`
- reason: vision_partial
- evidence: vision_status=partial
- suggested_action: Inspect the screenshot and the matching vision log before trusting this page.
- artifact_links:
  - `pages/0005.png`
  - `vision/0005.txt`
  - `vision/0005.log`
