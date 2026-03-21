# Design: default video resolution 1080p and sound off

## Runtime

- Change `--video-resolution` default from `720p` to `1080p` in the main manifest-driven generation script.
- Leave EvoLink payload default `sound: False` unchanged.

## Documentation

- Add a short note to `docs/how-to-run.md` that the normal default is now `1080p / sound off`.
- Avoid expanding the change into multiple docs because this is a narrow runtime-default adjustment.
