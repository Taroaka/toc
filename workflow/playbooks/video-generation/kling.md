# Kling 3.0 Video Prompt Policy

kling_3_0 / kling_3_0_omni 用の provider 固有 policy。prompt projection の正本は
docs/implementation/video-prompting.md、全体 flow は docs/video-generation.md。

## 適用範囲

- video_generation.tool: kling_3_0|kling_3_0_omni
- cut_contract.first_frame_contract
- cut_contract.motion_contract
- cut_contract.continuity_contract
- video_generation.api_prompt_payload.prompt
- first/last frame、Kling continuity、constraints

現在の adapter は first/last frame を画像入力として送る。未実装の auxiliary references[] は
黙って捨てず、入力 error とする。ordered multi-image input が必要ならその mode に対応する
provider を選ぶ。Kling payload の mode は text_to_video|image_to_video|first_last_frame。

## Canonical flow

```text
cut_contract + first/last frame + continuity + settings
  → video_prompt_projection_registry_v5
  → compile_video_api_prompt_v1
  → video_api_prompt_v1
  → immutable request snapshot
  → Kling API
```

cut_function、event/reveal ID、path、hash、image prompt、narration、internal design labels は
provider prompt に入れない。free-text fallback は canonical field がない場合だけ使い、
event boundary、end state、identity を変更しない。

## Required policy

### One clip, one intent

- 中心動作は一つの感情変化または空間 action にする。
- 「振り向く、走る、爆発する」のような独立 event 列は cut/render unit へ分ける。
- duration を伸ばすために intent や filler motion を追加しない。

### Camera

camera 指示は一つ、必要でも互換性のある二つまで。主動作が感情変化なら camera を安定させ、
空間 action なら人物演技を詰め込みすぎない。急旋回、複数方向 pan/tilt、視点 jump を避ける。

### Single continuous shot

fade、暗転、dissolve、montage、別 shot 切替をしない。複数 shot が必要なら canonical
cut/render unit を分ける。

### First/last boundary

first frame は人物、構図、物の位置、光の departure state。last frame は一つの連続運動で
到達する arrival state。last frame を別 shot として挿入しない。

## Motion fields

```yaml
motion_contract:
  source_event_beat_id: scene1_event_01
  starts_from_first_frame: true
  motion_brief: "一つの観察可能な動作"
  camera_motion: "胸の高さを保って緩やかに寄る"
  subject_motion: ""
  environment_motion: ""
  emotional_change: ""
  end_state: "物理的な終了状態"
  must_not_add: ["新しい人物", "別の場所"]
```

allowed_new_reveal_elements[]、allowed_reveal_info_ids[]、next-frame binding は exact obligation
entry だけに置く。allowlist は source event と motion/end state に接地し、must_not_add と交差
しない。cross-location arrival は scene sequence、allowlist、current end/next start state が
exact match する場合だけ許可する。

## Prompt and binding

The compiler emits fragments in this order:

```text
start_state → primary_motion → camera_motion → environment_motion
→ emotional_change → end_state → continuity → constraints
```

Empty optional groups are omitted. payload stores exact prompt/negative prompt, prompt hash,
source digest, provider/model/mode/settings, first/last frame, ordered references/roles, reference
content hashes, and destination. Request snapshot is saved before provider call and current design is
recompiled before execution.

Kling does not accept auxiliary references in this adapter. provider_request_binding.references must be
empty; first/last frame paths and bytes hashes must match.

## Structural and output checks

Before execution:

- required fields, source/event/selector IDs, first/last frame, motion boundary
- provider mode, duration, camera count, settings, exact prompt/source/provider hashes
- request snapshot, frame/reference paths and bytes hashes, destination

After execution:

- response item identity, saved path, destination, file type, decode, duration, frames/stream
- content hash and complete request-bound provenance

Any mismatch is a request error. Repair canonical motion/request data and rematerialize. Do not patch
compiled prompt text to hide the source error.

## Candidate selection

The same request may produce multiple candidates. A user may select a candidate after listening/viewing;
store actor, timestamp, selector, and request revision under human_choice.*. Recompile/revalidate the
selected revision before downstream use. Candidate selection is optional and does not change source event
ownership.

## References

- docs/implementation/video-prompting.md
- docs/video-generation.md
- workflow/video-manifest-template.md

