# Design

Date: 2026-10-07 (Asia/Tokyo)
Status: decisions resolved. Narration plus synchronized sound and optional dialogue; Higgsfield public API is included.

## Existing integration points

- `toc/p400_authoring.py` authors each scene with research/story/visual_value and prior scene context.
- `toc/p400_projection.py` carries `camera.light`/`focus` into the image plan; video motion currently receives camera movement but has no equivalent dedicated light/focus/performance projection.
- `toc/image_prompt_compiler.py` has a generic live-action style prefix and reference-scoping behavior.
- `toc/video_prompt_projection_registry.py` and `toc/video_prompt_compiler.py` define actual provider text and request identity.
- `server/image_gen_app.py` materializes/executes provider-bound requests and exposes frontend controls.
- `toc/sound_design.py`, `server/sound_design_api.py`, and `SoundDesignPanel.tsx` own p860 candidate selection and mixing.
- `scripts/freeze-approved-render-inputs.py`, `scripts/render-video.sh`, and `scripts/mix-sound-design.py` freeze/render media. The current standard mix replaces embedded clip audio.
- `toc/video_provider_capabilities.py` currently treats recognized Seedance 1.0 models as 2–12 seconds; current public Higgsfield Seedance 2.5 operations have different contracts.

## A. One authored film language

Use the existing `cinematic_direction.json` as the canonical owner. Add a versioned, top-level `film_language` object rather than maintaining a second independent visual bible.

Suggested fields: visual intent; palette; exposure/shadow treatment; material/texture rendering; optics/depth; camera behavior; composition; scope-specific avoidances; source-grounding notes. Keep short provider-ready fragments separate from author rationale and source references.

At the beginning of p410, one run-wide authoring operation reads research/story/visual_value and available user preferences. Its result is cached with source hashes and supplied unchanged to scene authoring. Reuse the existing author runtime and repair/cache mechanisms; this is part of p410, not a new pipeline bucket or reviewer. Do not repeat this author call on every scene or resume.

Inheritance is field based: film defaults → explicit scene overrides → explicit cut overrides. An empty override inherits; an explicit clear action removes an optional inherited aesthetic. Source facts and temporal/reveal constraints are always authoritative. Avoid concatenating contradictory strings and then asking the provider to resolve them.

One resolver computes the effective direction for both compilers. It records which scope supplied each value. Script/manifest contain projections with the owning revision/digest, not competing authoring roots.

The new-run frontend accepts optional filming preferences and the video panel displays each cut's effective settings. Existing-run changes use `cinematic_preferences.md` and the existing explicit p400 candidate/diff/apply workflow; there is no direct mutation of an approved film from the display panel. A scene/cut override is an authored exception and remains visible in the canonical direction.

## B. Cut execution detail

Extend the current cut cinematic/motion contracts with optional structured direction:

- Lighting: sources and position, color, illuminated subjects/regions, falloff, shadow treatment, and continuity constraints throughout motion.
- Focus: initial target/depth versus a time-ordered focus change. A focus action belongs in video; its initial state belongs in the still.
- Performance: playable action, observable reaction, pause/response timing, gaze, breath, and small involuntary detail. Purpose/interpretation stays authoring context unless converted to observable instructions.
- Physical behavior: contact, load/resistance, movement response, settling, and the source-grounded start/end boundary.

Avoid requiring every field in every shot. Unpeopled shots do not acquire actor fields; static shots can omit dynamic focus and resistance.

Projection separates: (a) first-frame facts and appearance, (b) time-dependent performance/camera/environment, (c) light/look constraints valid through the shot, (d) sound/dialogue. Each included fragment must come from a classified source. Fixed item limits must not silently drop an explicitly authored new field. Reject invalid structure or unsupported execution settings, not cinematic word choices.

Update the registry, compiler payload/IR versions, normalized source digest, request materialization, preview, resume, and validation together. Preserve a legacy route for existing contracts; new fields require an explicit contract marker. Existing outputs remain historical candidates and are not re-labelled as satisfying a new request.

## C. Synchronized audio and timeline

Keep narrative speech and generated clip audio separate in the authoring model. Add a cut/render-unit `native_audio` execution contract:

- `mode`: off, natural_sound, dialogue_and_sound (last value depends on Q1).
- `sound_events`: observable sound sources with temporal cues; no invented music unless explicitly intended.
- `dialogue`: speaker identity, exact source-authorized text, delivery, order/timing (when enabled).
- stable character voice description/reference binding where the chosen provider supports it; never claim a textual voice description guarantees identical speaker identity.

Generation-time audio instructions determine what to request. Provider capabilities determine whether that request is executable. Off explicitly disables generation or use; natural_sound requests breath/environment/contact sound without unscripted speech or score. Provider-native audio stays a mixed track unless the provider actually returns stems.

Store selected clip audio as a source track tied to the video's bytes hash, stream identity, request revision, and measured duration. If expected audio is absent, report the missing stream; do not silently synthesize a replacement.

Extend p860 to expose per-target source audio on/off, gain, and placement/fades. Reuse BGM/SE settings and preview. Native dialogue, when enabled, gets an explicit narration-overlap policy; do not automatically duck or remove intelligible dialogue as ordinary background noise.

Freeze the chosen native tracks in the same sound render snapshot. Compute positions from the final canonical cut/render-unit timeline, not from independently concatenated audio. Narration retains its existing offset; native audio begins at its video-relative time. Include one track per render unit, never once per underlying cut. Missing optional audio is silence; required selected audio must exist and decode.

Final mix includes narration + selected native tracks + selected BGM/SE. Preserve approved video duration, guard headroom, and test clip boundaries and trailing silence using real ffmpeg fixtures. Approval invalidation continues to use the existing p860 rules; do not add another approval gate.

## D. Model and provider boundary

Resolve capability by provider + model + operation + input mode. Record explicit input roles, allowed combinations, reference limits, duration step/range, aspect/resolution, native-audio and reference-audio support, and single/multi-shot support. Generation audio support and audio-reference support are separate capabilities.

Follow the existing public-API choice in `higgsfield_todo.md` if Q2 includes that work. Reuse shared HTTP/media/path handling and add a server-side Higgsfield adapter. Keep provider credentials out of UI, snapshots, errors, and uploads to external object storage.

Lifecycle: materialize exact local input hashes/settings → upload needed assets → save submission intent → submit once → immediately persist request ID → poll/resume → download and verify → publish a candidate. A timeout without a request ID becomes an uncertain-submission state; automatic retry must not charge twice. Failed and stale results do not replace selected media.

Initial target is the documented Seedance 2.5 public API; add only operations whose request schema and input combinations are verified. The official reference-to-video page documents image/video/audio URL arrays, 4–30 seconds, and generated audio. It does not establish arbitrary combined first/last frames plus references or array limits. Verify these separately before advertising support. The current official Kling Pro page lists start/end and elements, but elements are not generic image URLs.

If Q2 excludes the adapter, publish the same capability/audio/request contracts and mocked integration fixtures for its owner; no duplicate provider implementation.

## Compatibility and delivery

- New productions opt into the new direction contract. Old artifacts load through their current version. A selected existing run can be explicitly enriched later with a reviewable candidate diff.
- Do not reinterpret an approved narrator track as dialogue or change its text, voice, timing, or hash.
- Source changes invalidate cached film language and its dependent scene authoring. Film override changes invalidate effective direction and requests, not unrelated narration.
- Candidate state updates, request snapshots, and final sound freeze preserve existing locks and provenance behavior.
- Do not install a global imitation style or use a reference-film/story name as an executable branch.

## Delivery order and validation

1. Define contracts, resolver, and regression fixtures.
2. Implement film authoring/cache and cut execution projection; connect image/video materialization and previews.
3. Implement audio authoring/request policy and provider capabilities; adapter according to Q2.
4. Implement source-track selection, p860 preview/freeze, and final mix.
5. Finish frontend controls, docs, migration guidance, focused regressions, and scoped review.

Use focused tests around p400 author/projection, both prompt compilers/registries, frontend materialization, provider capabilities/adapters, sound API/mix/freeze, and renderer. Add meaningful acceptance cases for a dim room, restrained face performance, and a weighted physical action. These are generic test data, not story-specific runtime rules.

## References checked 2026-10-07

Implementation verification uses mocks for provider transport and real local ffmpeg fixtures. The user explicitly declined paid generation on 2026-10-07; no Higgsfield paid submission was made. The local server credential's presence/shape was checked without printing its value. Real account/model access is unverified.

- https://docs.higgsfield.ai/docs/llms.txt
- https://open.higgsfield.ai/models/bytedance/seedance-2.5/reference-to-video/api-reference
- https://open.higgsfield.ai/models/kling-video/v3.0/pro/image-to-video/api-reference
- `higgsfield_todo.md`
- `docs/implementation/p400-cinematic-authoring.md`
- `docs/implementation/image-prompting.md`
- `docs/implementation/video-prompting.md`
- `docs/implementation/sound-design.md`
