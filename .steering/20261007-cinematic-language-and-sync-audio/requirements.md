# Requirements

Date: 2026-10-07 (Asia/Tokyo)
Status: decisions resolved; implementation authorized.

## Request

Implement the three priorities agreed from the public AI-film production comparison:

1. Carry lighting, focus, acting, and physical behavior through to the actual image/video requests.
2. Author and consistently apply a film-wide visual and camera language.
3. Support synchronized generated audio and current model capabilities.

The user requested a design first, questions where needed, and implementation after resolving uncertainty.

## Outcomes

- A new production authors a film-wide direction once, then makes scene/cut decisions in that context.
- Visible appearance, dynamic performance, lighting continuity, and audio instructions reach the appropriate provider inputs without depending on another generation remembering a previous shot.
- Shot-specific facts and source constraints take precedence over aesthetic defaults. A night scene is not required to become bright, and a calm shot is not required to shake.
- Authored performance describes observable behavior and mechanics without inventing new source events or treating inferred inner motives as source facts.
- Narration, the generated clip audio, and independently authored BGM/SE can be mixed deliberately with a shared timeline.
- Provider/model/operation capabilities govern input combinations, durations, audio support, and references. Unsupported combinations are reported before generation.
- Existing completed runs and accepted media remain readable and usable. Enrichment/regeneration is explicit and scoped to selected targets.

## Pending decisions

- Q1 resolved: narration plus synchronized natural sound and optional dialogue. Preserve the existing narrator; use source-authorized character speech only where needed.
- Q2 resolved: implement the Higgsfield public-API adapter in this chat, including shared contracts and integration points.

Other defaults: derive the film language from the source and existing creative direction; keep it editable; apply automatically to newly authored productions; do not regenerate the existing production as part of a code migration.

## Boundaries

- Extend existing p400/p600/p800/p860/p910/p920 responsibilities. Do not add a critic, score, or new mandatory aesthetic approval stage.
- No story-specific code, fixed scene mapping, or global imitation of the reference film's dark/handheld look.
- Blender automation, general timeline editing, color-grading software, and face-mask asset editing are separate follow-up work.
- Do not assume mixed clip audio can be separated into dialogue, breath, and effects without a separate source-separation implementation.
- Keep narration identity, text, pronunciation rules, measured duration, and lead-in behavior intact unless the user edits those inputs.
- Tests use temporary fixtures and mocked provider transport. A live generation is a separate evidence step with a concrete payload and cost estimate.

## Acceptance

1. A fixture's explicit light restriction, focus transition, performance timing, and contact/resistance behavior survive authoring → projection → compiler → request snapshot.
2. Dynamic actions do not leak into a first-frame still prompt. Internal IDs and research/version discussion do not appear as newly introduced provider prose.
3. Film/scene/cut inheritance is deterministic, provenance includes the effective inputs, and changes invalidate only their dependent new requests.
4. Absence of the new contract preserves legacy execution semantics; no mass migration, re-authoring, or generation occurs on opening an old run.
5. Audio-off, natural-sound, and (if selected) dialogue modes are distinct. Unsupported providers cannot silently discard an audio request.
6. A real ffmpeg fixture preserves a deliberately positioned clip sound, narration lead-in, mix levels, and final duration across multiple cuts without duplicating render-unit audio.
7. Changed source audio/video bytes or selected candidates invalidate the frozen mix; failed operations preserve prior usable media.
8. Model-specific tests preserve reference roles and boundaries, reject unsupported combinations, and cover duration/audio limits.
9. If Q2 includes the adapter: submit identity is saved, polling resumes an existing request, uncertain POST outcomes are not automatically resubmitted, secrets remain server-side, and public media transfers do not receive provider credentials.
10. Focused backend tests, relevant frontend tests/build, pointer validation, and scoped review pass. Visual/acting quality and real provider access are reported separately from automated structural verification.
