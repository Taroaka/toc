# Design

Existing p700 manages narration revisions/listening; p800 resolves cut/render-unit video targets; p910 freezes narration and clips before p920 rendering. Extend this boundary with p860 sound design.

`sound_design.json` owns a versioned video approval, editable cue proposals, immutable generated candidates, selected candidate IDs and mix settings. Video hashes include canonical selectors, actual file hashes, ordered durations and narration timeline. BGM and SE both live in this artifact and slot. Proposals derive from canonical scene/motion context and remain editable; generation is an explicit user action using ElevenLabs Music / Sound Effects with existing API-key configuration.

API exposes read, approve-video (also prepares proposals), generate, save-cue and complete. Mutations use the existing run-artifact lock. Generation saves a request before the provider call, releases the lock while generating, then verifies the approval and cue request identity before publication. A stale result is retained but never selected automatically. Errors remain visible and retryable.

The frontend adds a BGM・SE workspace between video and final render. It shows the ordered videos for approval, proposals and candidates with audio controls, cue settings and a completion action. Canonical render freeze requires current approval and a complete p860 decision. Freezing copies selected cue metadata and verifies output hashes. The renderer mixes narration and delayed/trimmed/faded sound tracks before video muxing, preserving the full approved duration.

Verification covers approval-before-generation, changed video/timeline, candidate failure/retry, invalid paths/settings, selected-byte drift, render handoff and real ffmpeg duration/mixing. Provider calls are mocked in tests.
