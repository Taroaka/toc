# Design

## Contract

- `video_manifest.md`
  - `still_image_plan.mode`
  - `still_image_plan.generation_status`
  - `still_image_plan.source`
- request preview
  - `still_mode`
  - `generation_status`
  - `plan_source`

## Runtime

- `_should_generate_image_scene(...)`
  - `missing` と `recreate` は生成対象
  - `created` は非対象
  - 明示 status がなければ従来の `mode` 判定へフォールバック
- `recreate + --force`
  - 既存 canonical を `assets/test/` に timestamp 付き退避
  - その後に通常生成
- `--test-image-variants N`
  - `--force` 前提
  - canonical とは別に `assets/test/` へ追加出力

## Review

- `image_generation_requests.md` は新規生成対象だけでなく、review 対象の全 scene/cut を載せる
- 人は request を見て
  - 何が未作成か
  - 何が既存か
  - 何を再作成するか
  を判断する

