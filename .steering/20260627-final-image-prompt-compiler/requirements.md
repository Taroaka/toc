# Requirements

## Summary

p500 asset stage と p600 scene image stage の画像生成 request に、最終画像 prompt の 3 段階を明示して組み込む。

1. deterministic compiler
   - 構造化 artifact から image API に渡す最終 prompt を作る
   - asset stage は `asset_stage_manifest.md` / `asset_plan.md` の asset prompt を source にする
   - scene stage は既存の `image_api_prompt_v1` を維持する
2. prompt editor
   - provider に描かせる情報だけを残し、構造化設計・review・debug・制作管理語を削る
   - LLM agent を使う場合も、出力は deterministic compiler の同じ contract に格納する
3. leak gate
   - API prompt 本文に scene/cut/debug/first-frame/motion などの内部語が混ざったら fail する

## Requirements

1. `asset_generation_requests.md` は asset stage でも `prompt_policy_version: image_api_prompt_v1` と `api_prompt` fence を持つ。
2. asset request の `api_prompt` は `still_assets[].image_generation.prompt` を主 source にし、scene/cut first-frame prompt を使わない。
3. asset request には `first_frame_visual_plan` / `debug_prompt_source` を出さない。必要な review metadata は通常の request metadata に残す。
4. scene request の既存 `debug_prompt_source` と `api_prompt` 分離は維持する。
5. leak gate は `api_prompt` fence を検査し、`debug_prompt_source` は検査対象から除外する。
6. p550 verification は asset request の metadata に加え、最終 prompt が production/debug metadata を含まないことを検証する。

## Non-goals

- asset 設計そのものの自動改善ロジックを大きく作り替えない。
- p600 scene image prompt の内容設計を今回変更しない。
- LLM prompt editor agent の外部実行基盤を今回必須にしない。
