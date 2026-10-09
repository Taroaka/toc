# Validation and delivery

Date: 2026-10-07 (Asia/Tokyo)

## Delivered

- Optional production tools panel in image and video cards, loaded only when expanded.
- Byte-bound, revision-checked human candidate notes with side-by-side media comparison.
- Immutable state variants using a base image and existing edited image; only selected rectangular areas change. Palette transparency, EXIF orientation and unchanged pixels outside the region are covered by tests. Adding a variant as a reference is explicit.
- Metric subject/camera/light geometry validation, top and camera schematic SVG previews, and p400 `execution.geometry` projection into still/video instructions without asset IDs in prose. UI preview saves are planning-only; applying them to production requires explicit canonical direction editing/rebuild. No Blender installation or photometric renderer is claimed.
- Local ffmpeg time-range/color/fade editing, immutable output/receipt, source-chain verification and stale detection.
- Explicit video selection takes precedence over the default first candidate, preserves original generation identity during final freeze, and invalidates sound approval when the selected bytes change. Current cut duration and narration remain protected; shorter edits can be inspected/exported but are not silently adopted into a shorter timeline.
- Relative A/V starts are preserved through video editing and p860 native-track mixing, including delayed and pre-video audio and silent non-overlap ranges.

## Evidence

- Final affected backend suite: **229 passed, 189 subtests passed**. Log: `/private/tmp/toc-production-tools-final-suite.log`.
- Final API regression subset after obsolete edit-request flag fix: **4 passed**.
- Frontend targeted suite: 10 passed before the final manual-region validation addition; final production-tool subset: 5 passed, including that addition. TypeScript/Vite build passed.
- Existing Vite bundle-size warning and FastAPI lifespan deprecation warnings remain; no new compilation error.
- Real local ffmpeg fixtures test range/color edits, native audio delay, nonzero container timestamps, no-audio-overlap silence, recursive derived edits, and API edit → selection → p860 reapproval → freeze → mixed output.
- Pixel fixtures verify source immutability and protected-region equality including transparent palette PNGs.
- Review fixes include image-content coordinate mapping, stale async UI response protection, obsolete geometry/edit revision labels, strict receipt/source lineage, and bounded local media subprocesses.
- Task-scoped `git diff --check` and `python scripts/validate-pointer-docs.py` passed.

## Runtime

- Checked that the local backend had no child generation processes and no queued/running media operation records before reload.
- Reloaded via the existing server helper with DB startup skipped; existing DB contents were unchanged.
- Backend, frontend, and Codex app-server no-op transport checks passed.
- Frontend: http://127.0.0.1:5173/image_gen/
- Backend: http://127.0.0.1:8000/api/image-gen/runs
- Logs: `.codex/run/toc-server/` and `/private/tmp/toc-production-tools-restart.log`.
- Read-only checks against an existing run confirmed its image/video context can be assembled. No production media were changed by these checks.
- No paid generation, no external uploads, and no production-run media regeneration were performed.

## Limits

- The spatial panel is a geometric planning diagram, not a lighting/physics render. Saved previews do not silently override canonical prompts.
- Rectangular state variants require an already-edited image with equal oriented display dimensions. This tool does not generate the desired new appearance itself.
- Video finishing supports bounded color parameters and fades, not an arbitrary NLE timeline or automatic color matching.
- Final selection requires the current planned duration/narration; shortening the narrative timeline remains an explicit timing/authoring operation.
