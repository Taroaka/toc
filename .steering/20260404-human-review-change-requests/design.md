# Design

## Source Of Truth

- `script.md`
  - human review の正本
  - `human_change_requests[]` を top-level に持つ
  - scene / cut の `human_review` は approved 値と request 紐付けを持つ
- `video_manifest.md`
  - 実行用 contract
  - `location_bible[]`, `still_assets[]`, `reference_usage[]`, `implementation_trace` を持つ

## Human Change Request Contract

`script.md.human_change_requests[]`:

- `request_id`
- `source`
- `created_at`
- `raw_request`
- `original_selectors[]`
- `current_selectors[]`
- `normalized_actions[]`
- `status`
- `resolution_notes`
- `applied_manifest_targets[]`

`normalized_actions[].action` canonical set:

- `add_scene`, `delete_scene`, `add_cut`, `delete_cut`, `renumber_scene`, `renumber_cut`
- `update_scene_summary`, `update_story_visual`
- `update_narration`, `clear_narration`, `set_silent_cut`
- `update_visual_beat`
- `update_scene_contract`
- `add_location_asset`, `add_object_asset`, `add_character_variant`
- `create_still_asset`, `derive_still_asset`, `reference_asset`
- `set_image_direction`, `set_video_direction`

## Selector / ID Policy

- `scene_id` / `cut_id` は dotted numeric string を許可する
  - 例: `3`, `3.1`, `2.1`
- canonical selector は `scene<scene_id>_cut<cut_id>`
- sort は numeric token sort
- 出力ファイル名は `.` を `_` に slug 化する
- renumber trace は `original_selectors[]`, `current_selectors[]`, `implementation_trace.source_request_ids[]` で担保する

## Manifest Execution Contract

### assets.location_bible[]

- `location_id`
- `reference_images`
- `reference_variants[]`
- `fixed_prompts`
- `review_aliases[]`
- `continuity_notes[]`
- `notes`

### still_assets[]

各 cut は canonical に `still_assets[]` を持てる。

- `asset_id`
- `role`
- `output`
- `image_generation`
- `derived_from_asset_ids[]`
- `reference_asset_ids[]`
- `reference_usage[]`
- `direction_notes[]`
- `applied_request_ids[]`

`reference_usage[]`:

- `asset_id`
- `mode`
- `placement`
- `keep[]`
- `change[]`
- `notes`

### video_generation extension

- `input_asset_id`
- `first_frame_asset_id`
- `last_frame_asset_id`
- `reference_asset_ids[]`
- `direction_notes[]`
- `continuity_notes[]`
- `applied_request_ids[]`

### trace

scene / cut / still / video / audio node は `implementation_trace` を持てる。

- `source_request_ids[]`
- `status`
- `notes`

## Flow

1. 人レビュー後、raw request を `human_change_requests[]` に残す
2. request を `normalized_actions[]` に落とす
3. `script.md` の approved field を更新する
4. sync が `script.md -> video_manifest.md` へ一方向 materialize する
5. generation 前 gate / evaluator が unresolved request, missing trace, missing asset dependency, invalid dotted selector を止める

## Gate / Reason Keys

- `human_change_request_unresolved`
- `human_change_request_trace_missing`
- `location_asset_missing`
- `still_asset_missing`
- `still_asset_dependency_missing`
- `video_asset_reference_missing`
- `reference_usage_target_missing`
- `dotted_selector_invalid`
- `renumber_trace_missing`
