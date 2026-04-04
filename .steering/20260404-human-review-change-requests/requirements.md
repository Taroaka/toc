# Requirements

## Goal

人レビューが `script.md` 段階で narration だけでなく visual / asset / image / video まで指示する前提に、正本・実行 contract・trace・gate を広げる。

## Requirements

- 実装時も `script.md` を人レビュー正本にする
- 人の原文は削らず、`raw_request` と構造化 `normalized_actions[]` を両方残す
- `scene_id` / `cut_id` は stable UID を導入せず、dotted numeric string を許可する
- `video_manifest.md` は image/video generation がそのまま参照できる実行用 contract を持つ
- 場所再利用は `assets.location_bible[]` を canonical にする
- cut の静止画管理は `still_assets[]` を canonical にし、既存 `image_generation` は read-compatible に残す
- human request が unresolved のままなら generation 前 gate で止める
- request が manifest に反映されたかどうかを `applied_request_ids[]` と `implementation_trace` で追えるようにする
- add/delete/renumber scene/cut、location asset、multi-still、background-only reference などの高度な修正要求を表現できる
- 旧 manifest は暗黙 single-still cut として読み続けられる
