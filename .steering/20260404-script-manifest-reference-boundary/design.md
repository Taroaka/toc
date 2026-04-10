# Design

## Core boundary

### `script.md`

`script.md` は以下の正本とする。

- scene の役割
- cut の `visual_beat`
- reveal / story progression
- narration / tts_text
- human review の image/video 指示

ここで扱うのは **意味設計** であり、provider 実装ではない。

### `video_manifest.md`

`video_manifest.md` は以下の正本とする。

- `scene_contract`
- `image_generation.prompt`
- `still_assets[]`
- `reference_usage[]`
- `video_generation.direction_notes`
- `video_generation.motion_prompt`
- asset / dependency / trace

ここで扱うのは **生成実装** である。

## Generator read order

### Image generation

1. `video_manifest.md`
   - `scene_contract`
   - `image_generation`
   - `still_assets[]`
   - `reference_usage[]`
   - `location_ids[]`
2. `script.md`
   - `visual_beat`
   - `human_review.approved_visual_beat`
   - `approved_image_notes`
   - `human_change_requests[]`
3. narration は補助参照
   - `narration`
   - `tts_text`

`tts_text` は image generation の主ソースにしない。

### Video generation

1. `video_manifest.md`
   - `video_generation`
   - `still_assets[]`
   - `reference_usage[]`
   - `implementation_trace`
2. `script.md`
   - `visual_beat`
   - `approved_video_notes`
   - `human_change_requests[]`
3. narration は補助参照

## Script authoring guidance

`script.md` は image/video を全く触れない文書にはしない。
ただし、次は持ち込まない。

- provider 固有 prompt syntax
- 実行パラメータ
- 参照依存を解決しきった asset wiring

`script.md` が持つべき映像情報は次に留める。

- 何を見せるか
- 何をまだ見せてはいけないか
- どの感情/状況で見せるか
- 人レビューで来た参照/背景/前景/ズーム/切替などの意図

## Contract implications

- `approved_image_notes[]` と `approved_video_notes[]` は generator の補助ソースとして扱う
- `human_change_requests[]` は image/video generation 前に manifest へ materialize 済みであること
- `audio.narration.tts_text` は `generate-assets-from-manifest.py` の TTS payload 専用字段とみなす
