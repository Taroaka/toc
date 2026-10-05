# Video Integration（正本）

`script.md` から asset/image/narration/video request を作り、生成、合成、ordinary output checks
を一つの流れで定義する。production order は
`script → skeleton manifest → asset → scene image → narration/TTS → duration → video → render`。

## 1. Canonical boundaries

- `script.md` は story meaning、scene/cut intent、reveal、narration text の source of truth。
- `video_manifest.md` は materialized scene/cut execution、provider settings、asset references、
  compiled payloads、request snapshots、output paths の source of truth。
- `scene_conte.md` や request Markdown は bridge/projection であり、別の authoring root ではない。
- `tts_text` は TTS provider 専用。image/video prompt の主 source にしない。
- `manifest_phase: skeleton` は p450、`manifest_phase: production` は p600 以後の execution
  fields を表す。

## 2. 全体フロー

```text
script.md
  → video_manifest.md (skeleton)
  → asset_inventory.md / asset_plan.md / asset requests
  → reusable assets and file checks
  → production manifest / image requests / stills
  → narration text / TTS / measured audio
  → motion requests / clips
  → stream normalization / render
  → ordinary QA data
```

p400 では provider を呼ばない。各 request は payload、source digest、settings、reference bytes、
destination を保存してから provider に渡す。

## 3. Scene → asset/image contract

scene/cut input:

- `scene_id`、`cut_id`、`cut_contract`、source event IDs
- `first_frame_contract`、`motion_contract`、`narration_contract`
- character/object/location IDs と optional references
- duration intent、downstream handoff

output:

- reusable assets under `assets/`
- scene image under `assets/scenes/`
- manifest entries under `video_manifest.md.scenes[].cuts[]`

New stills are generated for continuity anchors or explicit image requests. Existing valid anchors may
be reused when their bytes and provenance match.

## 4. Audio Story authoring

cut is an editing unit; narration span may cover one or more cuts. Write a continuous full-run spoken
draft, then split it into ordered `narration_spans[]` anchored to cuts. A visual-only cut may use:

```yaml
audio:
  narration:
    tool: silent
    text: ""
    tts_text: ""
    silence_contract:
      intentional: true
      duration_seconds: 4
      reason: "視覚の余韻"
```

Do not add words only to fill target duration. Audio timeline is measured spoken audio plus explicit
silence. Video timeline is measured clip/render-unit duration; the two are parallel layers.

Narration projection:

```yaml
narration_authoring:
  schema_version: narration_authoring_v1
  status: missing|draft|human_locked|silent
  revision: 0
  text_hash: sha256:<hash>
  tts_hash: sha256:<hash>
  source: author|user
  updated_at: ISO8601
  updated_by: ""
```

`script.md` stores readable `narration`, ElevenLabs authoring fields, and final `tts_text`.
`video_manifest.md` receives a one-way projection. Pronunciation aliases and provider settings are
stored in the TTS request snapshot. Candidates may be generated, listened to, selected, or edited by
the user; a changed text/settings revision invalidates old audio and reruns ordinary checks.

### B-roll: audio and subtitles are independently optional

A B-roll cut may contain neither narration nor subtitles, either one, or both. Do not add speech or
captions merely because the cut exists. Preserve explicitly authored audio, BGM/effects, native clip
audio, and subtitle content; B-roll classification does not mute or delete those values.

Use the existing discriminator `a_roll_or_b_roll: b_roll`. Author it in
`cut_contract.a_roll_or_b_roll` in script/manifest; the runtime also reads existing
`image_generation.api_prompt_payload.shot_design_contract.a_roll_or_b_roll` projections. An explicit
cut-contract value takes precedence. Empty character lists, shot-role prose, and `sub` cuts alone do
not identify B-roll.

```yaml
cut_contract:
  a_roll_or_b_roll: b_roll
video_generation:
  duration_seconds: 4
# audio.narration and text_overlay may be omitted independently.
```

An absent/empty narration mapping (or only `tool: silent` and empty text) becomes intentional B-roll
silence. No TTS provider, audio file, or per-cut human confirmation is required. A positive declared
video duration is still required. Explicit provider, text, output, candidate, or revision data keeps
its ordinary validation. Non-B-roll missing narration remains an error. Script sync records a silence
contract with `kind: b_roll`; it does not fabricate `confirmed_by_human`.

Subtitles remain an independent opt-in at render time (`render-video.sh --srt`). Omitting subtitles
never forces narration, and omitting narration never creates or clears subtitles. In mixed spoken and
visual-only sequences, render preparation materializes local silence padding to preserve the B-roll
interval in audio concat lists; this is a render detail, not mandatory authored audio.

## 5. Request materialization

Image, audio, and video requests use immutable snapshots. Each binds:

```text
generation_job_id + item_id + turn_id + prompt_sha256 + reference_sha256s
  + saved_path + destination + source_digest
```

Materialization writes:

- exact provider prompt and negative prompt
- compiler/policy version and provider/model/mode
- duration, aspect ratio, quality, execution options
- first/last frame and ordered reference roles
- reference content hashes and destination
- request revision and source digest

Provider execution reads the saved payload, never reinterprets free text from a bridge file.

## 6. Video prompt compilation

```text
cut_contract + first/last frames + ordered references
  → video_prompt_projection_registry_v5
  → video_prompt_ir_v2
  → conditional_video_prompt_compiler_v5
  → video_api_prompt_v1
```

The compiled payload's `prompt` is exact provider-facing motion text. `sha256` hashes that text;
`source_digest` includes canonical design, duration, settings, frames, reference bytes, provider model,
and execution options. Internal IDs, paths, hashes, narration, and future event details stay in metadata.

Before calling the provider, recompile current design and compare prompt, hashes, binding, settings,
frames, ordered references, and source digest. Drift is a stale request error.

## 7. Ordinary output validation

After each provider call:

- verify provider response item identity and request binding
- verify expected output path, file type, existence, and decode
- verify duration, frames/streams, aspect ratio, audio/video compatibility
- verify content SHA-256, reference SHA-256, and destination lock
- record state and the smallest failing item

A failed item is repaired by editing its owning contract/request and rematerializing. Existing valid
files remain in place while the replacement is generated.

## 8. p700 duration and p900 render

Measure TTS audio with ffprobe and update the manifest. Set video duration from measured audio, intentional
silence, visual hold, and provider capability. If a clip or render unit exceeds provider capability,
split the render unit while preserving source cut IDs and one primary intent.

Before final concat:

- build clip and narration lists from active canonical selectors in order
- choose render-unit duration once; do not double-count source cuts
- normalize video size/fps/pixel format and audio codec/sample rate/channel layout
- check each input path and its provenance

After render, ffprobe and decode the final mp4; record measured duration, streams, aspect ratio, subtitles,
audio synchronization, output path, and content hash.

## 9. Optional user actions and publishing

Candidate selection, listening, image editing, narration editing, and explicit change requests are
optional. Store actor, timestamp, selectors, and selected revision under `human_choice.*`, then rerun
structural, request, file, and provenance checks.

Hybridizing contradictory source variants requires an explicit user choice and selected source IDs.
Publishing is a separate explicit user action and stores destination, actor, timestamp, and result.

## 10. Provider and output notes

- Image: Codex built-in image generation (`codex_builtin_image` / `gpt-image-2`)
- Video: Kling 3.0, Kling Omni, or Seedance according to request capabilities
- TTS: ElevenLabs
- provider-facing prompts are Japanese by default and contain visible content, not production metadata
- local placeholder or unrelated output is never copied to a canonical destination

## References

- `docs/data-contracts.md`
- `docs/script-creation.md`
- `docs/video-generation.md`
- `docs/implementation/video-prompting.md`
- `workflow/video-manifest-template.md`

