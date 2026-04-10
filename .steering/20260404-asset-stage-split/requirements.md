# Requirements

## Summary

画像生成工程を 2 段へ分ける。

1. asset stage
   - character / object / location / reusable still anchor を設計し、review を通してから生成する
2. cut stage
   - 既存どおり `video_manifest.md` を使って各 cut の画像を設計・review・生成する

## Requirements

1. asset stage には cut stage と別の review document がある
2. asset stage document は `script.md` の該当箇所も参照して作る
3. 人間が asset stage document を review / approve してから asset を生成する
4. character asset は既存どおり front / side / back 等の複数 view 運用を維持する
5. object / location / setpiece 等は既存どおり単体 still 中心で運用できる
6. cut stage は既存の `video_manifest.md` / `image_generation.review` / `still_assets[]` 運用を維持する
7. asset stage で確定した asset は cut stage の参照元になる

## Non-goals

- cut stage の prompt 設計フローを今回変更しない
- 既存の `video_manifest.md` ベース review を廃止しない
- asset stage document を provider 実行 payload に直接すること
