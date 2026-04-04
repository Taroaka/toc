# Tasklist

- [x] `script.md` に `human_change_requests[]` を追加する
- [x] `human_change_requests[]` に `request_id`, `source`, `created_at`, `raw_request`, `original_selectors[]`, `current_selectors[]`, `normalized_actions[]`, `status`, `resolution_notes`, `applied_manifest_targets[]` を追加する
- [x] `normalized_actions[]` の canonical action を追加する
- [x] `update_scene_contract` を canonical action に追加する
- [x] `script.md.scenes[].human_review` を追加する
- [x] `script.md.scenes[].cuts[].human_review` を拡張する

- [x] `video_manifest.md` に `assets.location_bible[]` を追加する
- [x] `image_generation` に `location_ids[]` / `location_variant_ids[]` を追加する
- [x] cut の still 管理を `still_assets[]` canonical にする
- [x] `still_assets[]` に `asset_id`, `role`, `output`, `image_generation`, `derived_from_asset_ids[]`, `reference_asset_ids[]`, `reference_usage[]`, `direction_notes[]`, `applied_request_ids[]` を追加する
- [x] `reference_usage[]` に `asset_id`, `mode`, `placement`, `keep[]`, `change[]`, `notes` を追加する
- [x] `video_generation` に `input_asset_id`, `first_frame_asset_id`, `last_frame_asset_id`, `reference_asset_ids[]`, `direction_notes[]`, `continuity_notes[]`, `applied_request_ids[]` を追加する
- [x] `audio.narration` に `applied_request_ids[]` を追加する
- [x] scene / cut / still / video / audio node に `implementation_trace` を追加する

- [x] `scene_id` / `cut_id` を dotted numeric string 許可に変更する
- [x] 並び順を numeric token sort に変更する
- [x] canonical selector を `scene<scene_id>_cut<cut_id>` に変更する
- [x] 出力ファイル名は `.` を `_` に slug 化する
- [x] stable UID は導入しない
- [x] renumber trace は `original_selectors[]`, `current_selectors[]`, `implementation_trace.source_request_ids[]` で担保する

- [x] 人レビュー後フローを `human_change_requests[]` 起点に変更する
- [x] `script.md` 更新対象を fixed field 化する
- [x] sync を `script.md -> video_manifest.md` の一方向で拡張する
- [x] sync 時に add/delete/renumber scene/cut を materialize する
- [x] sync 時に `location_bible`, `object_bible`, `character variant`, `still_assets[]`, `reference_usage[]`, `video_generation.*_asset_id`, `implementation_trace` を materialize する
- [x] generation 前 gate を追加する
- [x] 新しい canonical reason key を追加する

- [x] docs を更新する
- [x] template / schema を更新する
- [x] state に `review.human_changes.status` と `artifact.human_change_log` を追加する

- [x] テストを追加する
