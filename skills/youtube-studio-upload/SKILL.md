---
name: youtube-studio-upload
description: Use when Codex should upload a longform video to YouTube Studio for `にわかのAI` via browser/Chrome MCP without using the YouTube Data API. Supports draft-first upload, metadata entry, thumbnail upload, audience setting, visibility setting, and pinned comment after publish.
---

# YouTube Studio Upload

## Purpose

This skill lets Codex execute a semi-automatic YouTube Studio upload flow for `にわかのAI`.
It is based on the behavior shape of `@different-ai/youtube-studio`, but is repo-local and channel-specific.

This skill does not automate login, 2FA, CAPTCHA, or unattended mass posting.

## Channel Assumptions

- Channel name: `にわかのAI`
- Handle: `@niwakanoai`
- Single-channel operation only

If channel identity is ambiguous, stop and ask the human to resolve it.

## Required Inputs

- `video_path`
- `thumbnail_path`
- `title`
- `description`
- `pinned_comment`
- `visibility`
- optional `publish_datetime_jst`
- optional `CHANNEL_ID`

## Source Of Truth

Use existing publish-kit documents for copy.
Do not invent title, description, or pinned comment during upload.

Primary source:

- `marketing/SNS/YouTube/urashima-publish-kit.md`

## Required Environment

- Chrome MCP or equivalent browser MCP connected
- Logged-in YouTube/Google session in the controlled browser profile
- Thumbnail under 2MB

## Default Policy

- Audience: `Not made for kids`
- Comments: enabled with moderation
- Upload first as `Private`
- No final publish without explicit human confirmation, unless scheduling was requested
- No automatic external sharing

## Upload Sequence

1. Take a browser snapshot.
2. Navigate to the YouTube Studio upload URL.
3. Confirm the channel is `にわかのAI`.
4. Upload the video file.
5. Wait until editing is stable enough to proceed.
6. Fill the title.
7. Fill the description.
8. Upload the thumbnail.
9. Set audience to `Not made for kids`.
10. Set visibility.
11. Save immediately.
12. Re-open or otherwise verify saved state.

## Post-Publish Sequence

1. Open the published video page.
2. Post the prepared pinned comment.
3. Pin the comment.
4. Verify the comment exists.

## Stop Conditions

Stop and hand back to the human if any of these occur:

- auth prompt appears
- channel switcher ambiguity appears
- thumbnail is rejected
- required save button is disabled unexpectedly
- publish state is not clearly confirmed
- unexpected validation errors block progress

## Operator Notes

- Human is responsible for login, 2FA, CAPTCHA, and final publish approval by default.
- Draft-first is the normal mode.
- If the upload is meant to be scheduled, ensure `publish_datetime_jst` is provided explicitly.

## Validation Checklist

- Title persisted
- Description persisted
- Thumbnail persisted
- Audience persisted as `Not made for kids`
- Correct channel confirmed
- If published, pinned comment exists
