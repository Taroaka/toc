# LangGraph Topology（正本）

この文書は、ToC stage の状態、遷移、再実行、subgraph を定義する。implementation は
library に依存せず、下記 artifact/state contract を満たす。

## Top-level state

```text
INIT → RESEARCH → STORY → VISUAL_VALUE → SCRIPT → ASSET
     → SCENE_IMPLEMENTATION → NARRATION → VIDEO → RENDER → QA
     → PUBLISH → DONE
```

起点は Codex assistant command（Claude Code slash command 互換）。L1 Run Orchestrator が
bucket order を管理し、L2 P-Bucket Supervisor が canonical artifact と `state.txt` を更新する。

## Direct stage topology

```text
PrepareSourceContext
  → AuthorResearch
  → ValidateResearchStructure
  → AuthorStory
  → ValidateStoryStructure
  → AuthorVisualValue
  → ValidateVisualValueStructure
  → AuthorSceneIntentAndEvents(p410)
  → AuthorCutBlueprints(p420)
  → ValidateSceneCutStructure
  → MaterializeSkeletonManifest(p450)
  → AuthorAssetPlan
  → GenerateAssets
  → ValidateAssetFiles
  → AuthorImagePrompts
  → GenerateImages
  → ValidateImageRequestsAndFiles
  → AuthorNarration
  → GenerateTTS
  → MeasureAudioTimeline
  → AuthorMotionPrompts
  → GenerateClips
  → ValidateClips
  → NormalizeStreams
  → RenderVideo
  → ValidateFinalMedia
```

Each arrow requires the previous artifact's ordinary structural and provenance checks. The graph
does not launch a separate content verdict worker or wait for a quality score.

## Stage subgraphs

### RESEARCH

Read required sources, write `research.md` with passages, facts, variants, uncertainty, and
provenance. Check source IDs, file/path identity, and required sections.

### STORY

Story Architect writes scene ownership, causal order, event beats, reveal ledger, character/
relationship/place/world-rule coverage, and source/creative boundary. Scene Authors may write isolated
slices; L2 integrates one canonical `story.md`. Hybridizing contradictory source variants requires
an explicit user choice.

### SCRIPT

`p410` authors scene intent and `scene_event`; `p420` authors cut blueprints and source beat
assignments; `p440` applies optional user changes; `p450` materializes skeleton
`video_manifest.md`. Structural validation checks IDs, order, event coverage, first-frame and motion
boundaries, narration boundaries, and handoff references.

### ASSET / SCENE_IMPLEMENTATION

Asset Author writes inventory/plan and request snapshots. Image Prompt Author compiles
`scene_event → cut_contract → first_frame_visual_plan → drawable_prompt_ir → image_api_payload`.
Generators use the saved payload and request-bound provenance. Missing files, decode failures, or hash
drift stop only the affected request.

### NARRATION

Narration Writer projects current script text to TTS text. TTS candidates may be listened to and
selected by the user. Generation records measured duration, pronunciation settings, and audio
provenance. Duration/timeline checks run before video requests.

### VIDEO / RENDER / QA

Video Prompt Author compiles motion from the current cut contract and bound frames/references.
Clip generation verifies provider response identity, duration, decode, and hashes. Render normalizes
streams, builds ordered concat lists, and validates ffprobe output, audio sync, subtitles, and final
file identity.

## Retry and resume

Retry the smallest failed item. A stale source/request digest invalidates only its downstream
dependents. Resume appends new state deltas, quarantines stale outputs, and preserves valid files
whose complete provenance binding still matches. Runtime transport/setup failure remains a runtime
error and does not become an artifact result.

## State

State is `output/<topic>_<timestamp>/state.txt`, append-only key/value deltas. Derived current state,
run status, and navigation index are rebuilt from this log. The active fixed slots are defined in
`docs/data-contracts.md`; p410 and p420 are authoring slots.

## References

- `docs/system-architecture.md`
- `docs/data-contracts.md`
- `docs/orchestration-and-ops.md`
- `workflow/state-schema.txt`

