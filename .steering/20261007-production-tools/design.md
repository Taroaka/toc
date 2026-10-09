# Design

Use a new `server/production_tools_api.py` router installed alongside sound_design_api; reuse run path validation, locks, manifest selectors, media checks, and state append helpers from the existing app. Keep large request handlers out of main.tsx/image_gen_app.py where practical.

## Spatial preview

Optional `execution.geometry` is a versioned metric contract: camera position/target/vertical field of view, subject asset IDs with center positions and dimensions, and light positions/ranges. The p400 author receives its schema. Validation covers finite coordinates, nondegenerate camera, unique referenced subject IDs and positive sizes; it does not judge staging quality.

One projection computes screen rectangles and relative depth for a schematic browser SVG, plus a top-down view. Do not treat this preview as a generated asset or substitute it for a first-frame image. Render the same geometry as concrete shot instructions without exposing internal IDs. A saved per-target preview plan is optional; applying it to production must be an explicit source edit/rebuild, not a hidden prompt override.

## State variants

Take an immutable base and an existing edited image of equal dimensions. The user marks normalized rectangular editable regions on the base. Copy only those regions from the edited image and preserve the original RGB/RGBA pixels everywhere else. Store the result as a new referenced variant with a receipt binding base/candidate bytes, regions, state description, time, and selector. This provides deterministic pixel preservation around a face while reusing the existing image-generation workflow to create the proposed state change. No fresh image generation occurs in this tool.

## Candidate notes and comparison

`candidate_notes.json` owns a revision and append-only observations. Each note includes selector, image/video kind, candidate path/hash, optional request revision, human disposition, observed problem, change to try, and result. The current lookup must detect replaced candidate bytes rather than attaching an old note to new content. Notes are advisory and never trigger generation or automatic adoption.

## Editing and selection

`toc/video_editing.py` accepts bounded numerical settings, trims video and native audio together, re-encodes to a derived candidate, verifies streams/duration/decode, and writes an immutable receipt. The API records source hash/request revision and output hash. Originals stay unchanged.

Explicit video selection is stored independently from the generator's request identity. It must take precedence over the existing default candidate-1 lookup. Derived edits are selectable only if their receipt binds to a current source request and unchanged source bytes. For the first delivery the selected edit must cover the current cut/render-unit duration and narration; a shorter exported candidate may be inspected/downloaded, but changing an approved narrative timeline remains the existing explicit timing workflow. This avoids masquerading an edited duration as the duration of the original generation request.

The final renderer consumes the selected edited media; p860 fingerprints its new bytes and requires the existing approval/settings step again. Since the edited file includes trimmed native audio, the existing source-audio mixer uses that file without a second trim or offset.

## UI

Add compact optional production-tool panels to the current image/video workspace. Candidate comparison pairs the actual media with their notes. Character tools show base/edited/output images and editable-region selection. Video tools expose time range, brightness/contrast/saturation/gamma and fades, plus source/result preview and explicit adoption. Spatial preview displays camera/subject/light placement and supports local plan editing without requiring Blender.

## Verification

Test path containment, stale input hashes, optimistic revision conflict, immutable source behavior, exact pixel preservation, camera projection/degenerate geometry, note byte binding, real ffmpeg range/color/audio behavior, selected-candidate precedence, stale selection rejection, and final sound/render invalidation. Use synthetic local fixtures, not production media or paid providers.
