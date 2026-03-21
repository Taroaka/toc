# Requirements: default video resolution 1080p and sound off

## Background

- The current asset generation runtime defaults video resolution to `720p`.
- The user wants the default operating assumption to be `1080p` and `sound off` every time.
- EvoLink video generation already defaults `sound` to off in the current runtime, but that policy is not clearly captured as the normal default.

## Goals

- Make the main asset generation CLI default to `1080p`.
- Keep `sound off` as the runtime default and document it clearly.
- Update user-facing run instructions so execution no longer requires an explicit `--video-resolution 1080p` for the normal path.

## Non-Goals

- Changing image defaults.
- Changing provider routing.
- Enabling audio-on video generation.

## Success Criteria

- `scripts/generate-assets-from-manifest.py` defaults video resolution to `1080p`.
- Canonical docs state that normal video generation defaults to `1080p / sound off`.
