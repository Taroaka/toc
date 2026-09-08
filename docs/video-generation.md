# Video Generation System

ToC の video stage は、source-grounded scene/cut design と image/audio outputs を provider に渡せる
motion requests へ変換し、clips を生成して render へ渡す。production は authoring → structural
validation → generation の順で進む。

## 概要

### 関連ドキュメント

- `docs/data-contracts.md`
- `docs/script-creation.md`
- `docs/implementation/video-prompting.md`
- `docs/implementation/video-integration.md`
- `workflow/video-manifest-template.md`
- `workflow/playbooks/video-generation/kling.md`

### 入力

- `video_manifest.md`（scene/cut、first/last frame、asset references、motion contract）
- `script.md`（story event、reveal、narration、human change requests）
- request-bound image/audio outputs
- provider/model settings と target duration

### 出力

- `video_generation_requests.md`
- provider clips と provenance record
- `video_clips.txt`、render units、final `video.mp4`

## 1. 原則

- AI provider は設計された shot を実行する。story meaning、event order、reveal は
  `script.md` / `video_manifest.md` が所有する。
- `1 clip = 1 primary intent`。複数の独立した reveal、location change、感情反転を一つの clip に
  詰め込まない。
- first frame は開始時の visible state、last frame は到達状態である。静止画に future action を
  描かず、連続 motion で到達する。
- provider prompt は compiled payload の exact text。内部 ID、path、hash、request metadata を
  provider prose に連結しない。
- 生成済み画像/動画は request-bound provenance が current の場合だけ canonical output にする。
- candidate の選択、listening、編集、change request は任意の user action であり、選択後に
  request revision と普通の構造/provenance validation を更新する。
- hybridization と publication は explicit user authorization を必要とする別操作である。

## 2. Scene → clip 接続

### 2.1 Canonical cut contract

各 cut は次を持つ。

- `source_event_contract.primary_event_beat_id` と ordered `source_event_beat_ids[]`
- `cut_function`、`intent_budget.primary_intent`、`viewer_contract`
- `first_frame_contract`（current visible state、not-yet list、imageable evidence）
- `motion_contract`（start state、motion brief、end state、must-not-add）
- `narration_contract`（allowed/forbidden information、event boundary、voice function）
- `asset_dependency`、`downstream_handoff`

Structural validator は event beat IDs の exact coverage、unique selectors、source references、
first-frame imageability、motion ceiling、reveal constraints、narration boundary、asset IDs、
scene handoff を確認する。

### 2.2 Locations and transitions

複数場所の scene は `location.sequence[]` と `location.segments[]` を source of truth とする。
各 segment の location、responsibility、primary subject、visible action、required evidence、
roles、motion end state を保持する。cut は一つの departure segment に束縛する。別 location は
scene sequence と current obligation の allowlist に登録された arrival boundary のときだけ許可する。

`allowed_new_reveal_elements[]` と `allowed_reveal_info_ids[]` は exact obligation にだけ
設定できる。未登録の人物、物、建築、情報、場所、actor inversion、抽象 placeholder、未解決の
alternative は materialization 前に停止する。

### 2.3 Image-to-video

```text
scene_event + cut_contract + first-frame image
  → motion contract
  → video_prompt_projection_registry_v5
  → video_prompt_ir_v2
  → conditional_video_prompt_compiler_v5
  → video_api_prompt_v1
```

first-frame image の path と bytes SHA-256、last-frame image がある場合はその値、ordered
references、provider settings、duration、source digest を payload に保存する。payload は provider
call 前に immutable request snapshot へ保存し、current canonical design の再 compile 結果と
照合する。

## 3. Provider prompt contract

```yaml
video_generation:
  api_prompt_payload:
    policy_version: video_api_prompt_v1
    compiler_version: conditional_video_prompt_compiler_v5
    projection_registry_version: video_prompt_projection_registry_v5
    provider: kling_3_0
    mode: image_to_video
    provider_policy:
      one_clip_one_intent: true
      max_camera_instructions: 2
      single_continuous_shot: true
      first_last_frame_boundary: false
      negative_prompt_mode: separate
    provider_request_binding:
      duration_seconds: 8
      quality: 1080p
      aspect_ratio: "16:9"
      first_frame: assets/scenes/scene01_cut01.png
      last_frame: ""
      references: []
      reference_roles: []
      reference_content_sha256: {}
      execution_options: {}
    prompt: "exact provider-facing motion text"
    negative_prompt: "compiled constraints"
    source_digest: "sha256:<normalized source>"
    sha256: "sha256:<prompt hash>"
    included_fragments: []
    omitted_groups: []
```

`video_prompt_ir` と projection trace は compilation diagnostics であり provider prose に出さない。
Optional empty groups are omitted. `source_digest` includes canonical design, compiler/provider policy,
duration, first/last/reference bytes, execution options, and exact prompt inputs, so a changed design
cannot reuse an old payload.

Kling I2V and first/last-frame requests use a single continuous shot. Seedance reference-image requests
use provider capability limits and ordered reference roles. Duration and reference counts always come from
the selected provider/model/input mode.

## 4. Materialization and execution

frontend, server, CLI, and scene storyboard all save the same compiled payload and request snapshot.
`video_generation_requests.md` is a human-readable projection containing exact positive and negative
prompts, settings, source digest, prompt hash, request revision, and reference hashes. It is not parsed to
rebuild a provider request.

Before provider execution, validate:

- target and materialized payload exist
- current policy/compiler/registry versions match
- payload prompt and hashes match
- current canonical design recompiles to the same prompt, negative prompt, source digest, and binding
- duration, quality, aspect ratio, frames, ordered references, reference bytes, model, and execution options match
- output destination and request revision match

Missing payload, malformed data, unknown reference, hash drift, settings drift, or stale request is a
processing error. Repair the owning design/request and materialize again.

## 5. Human change requests

The canonical user change shape is:

```yaml
human_change_requests:
  - request_id: change_001
    created_at: ISO8601
    raw_request: "scene/cut/image/video change"
    original_selectors: [scene01_cut01]
    current_selectors: [scene01_cut01]
    normalized_actions: []
    status: pending|normalized|applied|deferred
    resolution_notes: ""
```

Apply a request transactionally to its owning artifact, update source/request revision, rematerialize
payloads, and rerun ordinary validation. A user choice may delete a scene/cut or select a candidate; it
does not permit unbound output or hidden source changes.

## 6. Image, asset, audio, and video flow

```text
p400 script.md + skeleton manifest
  → p500 asset inventory/plan and reusable assets
  → p600 scene image requests and stills
  → p700 narration/TTS and measured audio
  → p800 motion requests and clips
  → p900 stream normalization and final render
```

Images are generated only for cuts whose `still_image_plan.mode` calls for a still or whose request
requires an anchor. Reusable assets are defined once and referenced by stable IDs. Audio uses the
current script narration and pronunciation dictionary. The final render uses measured media durations,
not self-reported metadata.

## 7. Render units and continuity

A scene may define `render_units[]` when several ordered cuts share one provider clip. Each unit lists
source cut IDs exactly once, keeps the first source start state and last source end state, and declares a
single primary motion. A unit duration must satisfy provider capability; source cuts are not double-counted
during concat.

first/last-frame chaining updates the next request snapshot with the actual previous output path and bytes
hash. If a chained frame changes, only stale dependent requests and clips are regenerated.

## 8. Ordinary output checks

After each provider call:

- verify provider response item identity and request binding
- verify output exists at the expected run-relative destination
- verify file type, decode, frames/stream, duration, and audio/video compatibility
- verify content hash and reference hashes
- record processing errors and target selectors in state

A generated clip may be absent or stale for operational reasons. The owner retries or repairs the
smallest failing request; no quality score or external pass field is needed.

## 9. Final render

Before render:

- build clip and narration concat lists from active selectors in canonical order
- normalize all clips to target size, frame rate, pixel format, audio codec, sample rate, and channels
- choose render unit duration once when render units exist
- check every referenced media file and its provenance

After render, use ffprobe and media decode to verify file existence, streams, duration, aspect ratio,
subtitle files, and audio synchronization. Store measured values under ordinary QA state.

## 10. Existing-story adaptation

For an existing story, `adaptation_value_contract: required_v1` preserves source value IDs, non-negotiable
facts, iconic moments, and forbidden value distortions. The lineage is:

```text
adaptation_source_contract.core_values[].value_id
  → adaptation_intent.source_value_ids[]
  → scene_value_amplification.source_value_refs[]
  → cut_contract.expressive_contract.source_value_refs[]
```

The source/value contract is separate from provider prompt text. The authoring and structural checks ensure
every selected value is traceable to the source.

## 11. Reference material

- `docs/implementation/video-prompting.md`
- `docs/implementation/video-integration.md`
- `docs/data-contracts.md`
- `workflow/video-manifest-template.md`

