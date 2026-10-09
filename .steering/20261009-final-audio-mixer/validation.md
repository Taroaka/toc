# Validation

- Backend: 38 sound-design, API, real FFmpeg mixing and preview tests passed.
- Frontend: 6 mixer/settings tests passed. TypeScript + Vite production build passed.
- Browser: isolated real FastAPI backend and built frontend; set SE +12dB, mute BGM, generate/playable 4s preview; change gain marks preview stale; save +18dB and confirm gain/mute survive full page reload.
- Preview uses same final mixer. Real tones verify independent bus mute, +6dB SE gain and no leakage.
- Original source audio/video hashes and manifest preserved by audition test. Concurrent video changes reject result.
- Code reviewer: no blocking findings; suggestion to remove intermediate preview files implemented and tested.
- Pointer docs validator passed.
- Existing localhost:8000 OpenAPI includes new routes; existing production listeners were not restarted.
- Vite warned about the shell Node 18 version and pre-existing bundle size; build nevertheless completed.
